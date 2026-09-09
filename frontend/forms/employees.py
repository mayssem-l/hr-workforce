from django import forms

from core.models import Employee
from frontend.selectors.employees import (
    DEFAULT_EMPLOYEE_SORT,
    EMPLOYEE_SORT_CHOICES,
    EMPLOYEE_SORT_OPTIONS,
)


class EmployeeDirectoryFilterForm(forms.Form):
    query = forms.CharField(
        required=False,
        max_length=100,
        label="Search employees",
        widget=forms.TextInput(
            attrs={
                "type": "search",
                "placeholder": "First or last name",
                "autocomplete": "off",
            }
        ),
    )
    status = forms.CharField(
        required=False,
        label="Status",
        widget=forms.Select(
            choices=(("", "All statuses"), *Employee.Status.choices),
        ),
    )
    department = forms.CharField(
        required=False,
        label="Department",
        widget=forms.Select(choices=(("", "All departments"),)),
    )
    sort = forms.CharField(
        required=False,
        label="Sort by",
        initial=DEFAULT_EMPLOYEE_SORT,
        widget=forms.Select(choices=EMPLOYEE_SORT_CHOICES),
    )

    def __init__(self, *args, departments=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].widget.choices = (
            ("", "All departments"),
            *((department, department) for department in departments),
        )

    def clean_status(self):
        status = self.cleaned_data["status"]
        valid_statuses = {value for value, _label in Employee.Status.choices}
        return status if status in valid_statuses else ""

    def clean_sort(self):
        sort = self.cleaned_data["sort"]
        return sort if sort in EMPLOYEE_SORT_OPTIONS else DEFAULT_EMPLOYEE_SORT


class EmployeeForm(forms.ModelForm):
    """Create or update an employee through the model validation pipeline."""

    class Meta:
        model = Employee
        fields = (
            "first_name",
            "last_name",
            "department",
            "position",
            "hire_date",
            "experience_years",
            "capacity_hours_week",
            "status",
        )
        labels = {
            "capacity_hours_week": "Weekly capacity (hours)",
            "experience_years": "Professional experience (years)",
        }
        help_texts = {
            "department": "The employee's primary organizational department.",
            "position": "The employee's current role or job title.",
            "hire_date": "The employee's official employment start date.",
            "experience_years": "Enter completed professional experience in years.",
            "capacity_hours_week": (
                "Enter contracted hours for the standard Monday-to-Friday week."
            ),
            "status": (
                "Employment status is managed separately from dated leave records."
            ),
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "department": forms.TextInput(attrs={"autocomplete": "organization"}),
            "position": forms.TextInput(
                attrs={"autocomplete": "organization-title"}
            ),
            "hire_date": forms.DateInput(attrs={"type": "date"}),
            "experience_years": forms.NumberInput(
                attrs={"min": "0", "step": "0.1"}
            ),
            "capacity_hours_week": forms.NumberInput(
                attrs={"min": "0", "step": "0.01"}
            ),
        }
