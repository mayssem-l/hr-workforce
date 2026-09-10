from django import forms

from frontend.forms.dashboard import (
    ReportingPeriodForm,
    with_default_reporting_period,
)
from frontend.selectors.calendar import (
    APPROVED_LEAVE_SOURCE,
    ASSIGNMENT_SOURCE,
    CALENDAR_SOURCE_ACCESS_KEYS,
    PROJECT_SOURCE,
)


CALENDAR_VIEW_CHOICES = (
    ("month", "Month"),
    ("week", "Week"),
    ("list", "List"),
)
DEFAULT_CALENDAR_VIEW = "month"
CALENDAR_FILTER_MARKER = "filters"
CALENDAR_FILTER_FIELDS = frozenset(
    {
        "start_date",
        "end_date",
        "view",
        "source",
        "department",
        "employee",
        "project",
        CALENDAR_FILTER_MARKER,
    }
)
CALENDAR_SOURCE_CHOICES = (
    (PROJECT_SOURCE, "Project schedules"),
    (ASSIGNMENT_SOURCE, "Assignment schedules"),
    (APPROVED_LEAVE_SOURCE, "Approved leave"),
)


def with_default_calendar_state(query_data, *, today):
    """Return calendar GET data with deterministic period and view defaults."""

    data = with_default_reporting_period(query_data, today=today)
    if "view" not in data:
        data["view"] = DEFAULT_CALENDAR_VIEW
    return data


def with_default_calendar_filter_state(
    query_data,
    *,
    source_access,
    today=None,
):
    """Apply shared view/source defaults without defaulting endpoint dates."""

    if today is None:
        data = query_data.copy()
        if "view" not in data:
            data["view"] = DEFAULT_CALENDAR_VIEW
    else:
        data = with_default_calendar_state(query_data, today=today)

    if "source" not in data and data.get(CALENDAR_FILTER_MARKER) != "1":
        default_sources = [
            source
            for source, _label in CALENDAR_SOURCE_CHOICES
            if source_access.get(CALENDAR_SOURCE_ACCESS_KEYS[source], False)
        ]
        setlist = getattr(data, "setlist", None)
        if setlist:
            setlist("source", default_sources)
        else:
            data["source"] = default_sources
    return data


class CalendarViewStateForm(ReportingPeriodForm):
    """Validate the inclusive date range and planned calendar display mode."""

    view = forms.ChoiceField(
        label="View",
        choices=CALENDAR_VIEW_CHOICES,
        error_messages={
            "required": "Choose a calendar view.",
            "invalid_choice": "Choose month, week, or list view.",
        },
    )


class CalendarFilterForm(CalendarViewStateForm):
    """Validate the shared source and record context for calendar reads."""

    source = forms.MultipleChoiceField(
        label="Sources",
        choices=CALENDAR_SOURCE_CHOICES,
        error_messages={
            "required": "Choose at least one available calendar source.",
            "invalid_choice": "Choose only calendar sources available to you.",
        },
        help_text="Choose one or more schedule sources to include.",
        widget=forms.CheckboxSelectMultiple,
    )
    department = forms.ChoiceField(
        required=False,
        label="Department",
        choices=(("", "All departments"),),
        error_messages={"invalid_choice": "Choose a current department."},
    )
    employee = forms.ChoiceField(
        required=False,
        label="Employee",
        choices=(("", "All employees"),),
        error_messages={"invalid_choice": "Choose a current employee."},
    )
    project = forms.ChoiceField(
        required=False,
        label="Project",
        choices=(("", "All projects"),),
        error_messages={"invalid_choice": "Choose a current project."},
    )
    filters = forms.ChoiceField(
        required=False,
        choices=(("", "Not submitted"), ("1", "Submitted")),
        widget=forms.HiddenInput,
    )

    def __init__(self, *args, filter_options, source_access, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source"].choices = tuple(
            (source, label)
            for source, label in CALENDAR_SOURCE_CHOICES
            if source_access.get(CALENDAR_SOURCE_ACCESS_KEYS[source], False)
        )
        self.fields["department"].choices = (
            ("", "All departments"),
            *((department, department) for department in filter_options.departments),
        )
        self.fields["employee"].choices = (
            ("", "All employees"),
            *filter_options.employees,
        )
        self.fields["project"].choices = (
            ("", "All projects"),
            *filter_options.projects,
        )


class CalendarEventRequestForm(CalendarFilterForm):
    """Validate the exact inclusive date-window contract for event reads."""

    def clean(self):
        cleaned_data = super().clean()
        unexpected_fields = set(self.data) - CALENDAR_FILTER_FIELDS
        if unexpected_fields:
            self.add_error(
                None,
                "Use only supported calendar filter parameters.",
            )

        getlist = getattr(self.data, "getlist", None)
        if getlist and any(
            len(getlist(field_name)) != 1
            for field_name in (
                "start_date",
                "end_date",
                "view",
                "department",
                "employee",
                "project",
                CALENDAR_FILTER_MARKER,
            )
            if field_name in self.data
        ):
            self.add_error(
                None,
                "Provide each calendar request parameter once.",
            )
        return cleaned_data
