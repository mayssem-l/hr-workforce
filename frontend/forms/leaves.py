from django import forms

from core.models import Employee, Leave
from frontend.selectors.leaves import (
    DEFAULT_LEAVE_SORT,
    LEAVE_SORT_CHOICES,
    LEAVE_SORT_OPTIONS,
)


class LeaveDirectoryFilterForm(forms.Form):
    employee = forms.CharField(
        required=False,
        label="Employee",
        widget=forms.Select(choices=(("", "All employees"),)),
    )
    leave_type = forms.CharField(
        required=False,
        label="Leave type",
        widget=forms.Select(choices=(("", "All leave types"), *Leave.Type.choices)),
    )
    status = forms.CharField(
        required=False,
        label="Status",
        widget=forms.Select(choices=(("", "All statuses"), *Leave.Status.choices)),
    )
    from_date = forms.DateField(
        required=False,
        label="Overlaps on or after",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    to_date = forms.DateField(
        required=False,
        label="Overlaps on or before",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    sort = forms.CharField(
        required=False,
        label="Sort by",
        initial=DEFAULT_LEAVE_SORT,
        widget=forms.Select(choices=LEAVE_SORT_CHOICES),
    )

    def __init__(self, *args, employee_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.employee_values = {value for value, _label in employee_choices}
        self.fields["employee"].widget.choices = (
            ("", "All employees"),
            *employee_choices,
        )

    @staticmethod
    def _valid_choice(value, choices):
        valid_values = {choice_value for choice_value, _label in choices}
        return value if value in valid_values else ""

    def clean_employee(self):
        employee = self.cleaned_data["employee"]
        return employee if employee in self.employee_values else ""

    def clean_leave_type(self):
        return self._valid_choice(
            self.cleaned_data["leave_type"],
            Leave.Type.choices,
        )

    def clean_status(self):
        return self._valid_choice(
            self.cleaned_data["status"],
            Leave.Status.choices,
        )

    def clean_sort(self):
        sort = self.cleaned_data["sort"]
        return sort if sort in LEAVE_SORT_OPTIONS else DEFAULT_LEAVE_SORT

    def clean(self):
        cleaned_data = super().clean()
        from_date = cleaned_data.get("from_date")
        to_date = cleaned_data.get("to_date")
        if from_date and to_date and from_date > to_date:
            self.add_error(
                "to_date",
                "The end of the filter period must be on or after its start.",
            )
        return cleaned_data


class LeaveForm(forms.ModelForm):
    """Create or update dated leave through the model validation pipeline."""

    class Meta:
        model = Leave
        fields = ("employee", "type", "start_date", "end_date", "status")
        labels = {"type": "Leave type"}
        help_texts = {
            "employee": "Choose the employee this dated leave belongs to.",
            "type": "Choose the leave category used in workforce records.",
            "start_date": "The first calendar day of this leave period.",
            "end_date": "The final calendar day of this leave period.",
            "status": (
                "Only approved leave affects dated availability checks. "
                "Employment status is managed separately."
            ),
        }
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.only(
            "employee_id",
            "first_name",
            "last_name",
        ).order_by("last_name", "first_name", "employee_id")
