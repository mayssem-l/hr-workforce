from django import forms

from core.models import Employee, Project


class DashboardFilterForm(forms.Form):
    """Validate the shared, read-only dashboard reporting context."""

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

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and start_date > end_date:
            self.add_error(
                "end_date",
                "The end date must be on or after the start date.",
            )
        return cleaned_data
