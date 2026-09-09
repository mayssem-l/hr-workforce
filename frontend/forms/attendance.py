from django import forms

from core.models import Attendance, Employee
from frontend.selectors.attendance import (
    ATTENDANCE_SORT_CHOICES,
    ATTENDANCE_SORT_OPTIONS,
    DEFAULT_ATTENDANCE_SORT,
)


class AttendanceDirectoryFilterForm(forms.Form):
    employee = forms.CharField(
        required=False,
        label="Employee",
        widget=forms.Select(choices=(("", "All employees"),)),
    )
    status = forms.CharField(
        required=False,
        label="Status",
        widget=forms.Select(
            choices=(("", "All attendance statuses"), *Attendance.Status.choices)
        ),
    )
    from_date = forms.DateField(
        required=False,
        label="From date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    to_date = forms.DateField(
        required=False,
        label="To date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    sort = forms.CharField(
        required=False,
        label="Sort by",
        initial=DEFAULT_ATTENDANCE_SORT,
        widget=forms.Select(choices=ATTENDANCE_SORT_CHOICES),
    )

    def __init__(self, *args, employee_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.employee_values = {value for value, _label in employee_choices}
        self.fields["employee"].widget.choices = (
            ("", "All employees"),
            *employee_choices,
        )

    def clean_employee(self):
        employee = self.cleaned_data["employee"]
        return employee if employee in self.employee_values else ""

    def clean_status(self):
        status = self.cleaned_data["status"]
        valid_statuses = {value for value, _label in Attendance.Status.choices}
        return status if status in valid_statuses else ""

    def clean_sort(self):
        sort = self.cleaned_data["sort"]
        return (
            sort
            if sort in ATTENDANCE_SORT_OPTIONS
            else DEFAULT_ATTENDANCE_SORT
        )

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


class AttendanceForm(forms.ModelForm):
    """Create or update attendance through the model validation pipeline."""

    class Meta:
        model = Attendance
        fields = (
            "employee",
            "date",
            "status",
            "arrival_time",
            "departure_time",
        )
        help_texts = {
            "employee": "Choose the employee this attendance record belongs to.",
            "date": "Each employee can have one attendance record per date.",
            "status": (
                "Attendance is descriptive operational history and does not "
                "affect staffing recommendations."
            ),
            "arrival_time": "Optional. Record the observed arrival time.",
            "departure_time": "Optional. Record the observed departure time.",
        }
        error_messages = {
            "departure_time": {
                None: "Departure time must be at or after arrival time.",
            },
        }
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "arrival_time": forms.TimeInput(
                format="%H:%M",
                attrs={"type": "time"},
            ),
            "departure_time": forms.TimeInput(
                format="%H:%M",
                attrs={"type": "time"},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.only(
            "employee_id",
            "first_name",
            "last_name",
        ).order_by("last_name", "first_name", "employee_id")

    def clean(self):
        cleaned_data = super().clean()
        employee = cleaned_data.get("employee")
        attendance_date = cleaned_data.get("date")
        if not employee or not attendance_date:
            return cleaned_data

        duplicates = Attendance.objects.filter(
            employee=employee,
            date=attendance_date,
        )
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            self.add_error(
                "date",
                f"An attendance record already exists for {employee} on this date.",
            )
        return cleaned_data
