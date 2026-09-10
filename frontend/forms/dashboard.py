from calendar import monthrange

from django import forms

from core.models import Employee, Project


MAX_REPORTING_PERIOD_DAYS = 366


def with_default_reporting_period(query_data, *, today):
    """Return a mutable query mapping with the shared calendar-month defaults."""
    data = query_data.copy()
    if "start_date" not in data:
        data["start_date"] = today.replace(day=1).isoformat()
    if "end_date" not in data:
        data["end_date"] = today.replace(
            day=monthrange(today.year, today.month)[1]
        ).isoformat()
    return data


class ReportingPeriodForm(forms.Form):
    """Validate the inclusive reporting-period contract shared by read views."""

    start_date = forms.DateField(
        label="Start date",
        help_text="The first day included in this reporting period.",
        error_messages={
            "required": "Choose a reporting start date.",
            "invalid": "Enter a valid reporting start date.",
        },
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    end_date = forms.DateField(
        label="End date",
        help_text="The last day included in this reporting period.",
        error_messages={
            "required": "Choose a reporting end date.",
            "invalid": "Enter a valid reporting end date.",
        },
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and start_date > end_date:
            self.add_error(
                "end_date",
                "The end date must be on or after the start date.",
            )
        elif (
            start_date
            and end_date
            and (end_date - start_date).days + 1 > MAX_REPORTING_PERIOD_DAYS
        ):
            self.add_error(
                "end_date",
                "Choose a reporting period of 366 days or fewer.",
            )
        return cleaned_data


class DashboardFilterForm(ReportingPeriodForm):
    """Validate the shared, read-only dashboard reporting context."""

    department = forms.CharField(
        required=False,
        label="Department",
        widget=forms.Select(choices=(("", "All departments"),)),
    )
    employee_status = forms.CharField(
        required=False,
        label="Employee status",
        widget=forms.Select(
            choices=(("", "All employee statuses"), *Employee.Status.choices)
        ),
    )
    project_status = forms.CharField(
        required=False,
        label="Project status",
        widget=forms.Select(
            choices=(("", "All project statuses"), *Project.Status.choices)
        ),
    )

    def __init__(self, *args, departments=(), **kwargs):
        super().__init__(*args, **kwargs)
        normalized_departments = tuple(
            str(department).strip()
            for department in departments
            if str(department).strip()
        )
        self._departments = frozenset(normalized_departments)
        self.fields["department"].widget.choices = (
            ("", "All departments"),
            *((department, department) for department in normalized_departments),
        )

    def clean_department(self):
        department = str(self.cleaned_data["department"] or "").strip()
        return department if department in self._departments else ""

    def clean_employee_status(self):
        status = self.cleaned_data["employee_status"]
        valid_statuses = {value for value, _label in Employee.Status.choices}
        return status if status in valid_statuses else ""

    def clean_project_status(self):
        status = self.cleaned_data["project_status"]
        valid_statuses = {value for value, _label in Project.Status.choices}
        return status if status in valid_statuses else ""
