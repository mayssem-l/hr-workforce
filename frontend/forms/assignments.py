from django import forms

from core.models import Assignment, Employee
from frontend.presenters.assignments import build_assignment_employee_hints
from frontend.selectors.assignments import get_assignment_employee_choices


class AssignmentEmployeeChoiceField(forms.ModelChoiceField):
    def __init__(self, *args, employee_hints=None, **kwargs):
        self.employee_hints = employee_hints or {}
        super().__init__(*args, **kwargs)

    def label_from_instance(self, employee):
        hint = self.employee_hints.get(employee.employee_id, {})
        skill_message = hint.get("skill_message", "Skill match not assessed")
        status = hint.get("status", employee.get_status_display())
        return (
            f"{employee} — {employee.position}, {employee.department} — "
            f"{status} · {skill_message}"
        )


class AssignmentForm(forms.ModelForm):
    """Create or update an assignment through existing model validation."""

    employee = AssignmentEmployeeChoiceField(
        queryset=Employee.objects.none(),
        empty_label="Select an employee",
        help_text=(
            "Skill-match notes are advisory; all assignment rules are "
            "checked when you save."
        ),
    )

    class Meta:
        model = Assignment
        fields = (
            "project",
            "employee",
            "start_date",
            "end_date",
            "allocation_percentage",
            "role_on_project",
            "status",
        )
        labels = {
            "allocation_percentage": "Allocation",
            "role_on_project": "Project role",
        }
        help_texts = {
            "employee": (
                "Skill-match notes are advisory; all assignment rules are "
                "checked when you save."
            ),
            "start_date": "The employee's first planned day on this project.",
            "end_date": "The employee's final planned day on this project.",
            "allocation_percentage": (
                "Enter the percentage of working capacity assigned to this project."
            ),
            "role_on_project": "Describe the employee's delivery role.",
            "status": "Choose the assignment's current planning stage.",
        }
        widgets = {
            "project": forms.HiddenInput(),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "allocation_percentage": forms.NumberInput(
                attrs={"min": "0", "max": "100", "step": "1"}
            ),
            "role_on_project": forms.TextInput(attrs={"autocomplete": "off"}),
        }

    def __init__(self, *args, project, **kwargs):
        instance = kwargs.get("instance") or Assignment()
        instance.project = project
        kwargs["instance"] = instance
        super().__init__(*args, **kwargs)

        self.fields["project"].disabled = True
        self.fields["project"].initial = project
        employees, hints = build_assignment_employee_hints(
            project,
            get_assignment_employee_choices(),
        )
        employee_ids = [employee.employee_id for employee in employees]
        self.fields["employee"].queryset = get_assignment_employee_choices().filter(
            employee_id__in=employee_ids
        )
        self.fields["employee"].employee_hints = hints

        if not self.is_bound and not instance.pk:
            self.initial["start_date"] = project.start_date
            self.initial["end_date"] = project.end_date
