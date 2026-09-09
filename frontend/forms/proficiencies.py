from django import forms
from django.core.exceptions import NON_FIELD_ERRORS

from core.models import EmployeeSkill, Skill


class SkillChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, skill):
        return f"{skill.name} — {skill.category}"


class EmployeeSkillProficiencyForm(forms.ModelForm):
    """Edit proficiency values through EmployeeSkill's model validators."""

    class Meta:
        model = EmployeeSkill
        fields = ("level", "years_experience")
        labels = {
            "level": "Proficiency level",
            "years_experience": "Years of experience",
        }
        help_texts = {
            "level": "Choose a proficiency level from 1 to 5.",
            "years_experience": (
                "Enter the employee's experience with this skill in years."
            ),
        }
        widgets = {
            "level": forms.NumberInput(attrs={"min": "1", "max": "5", "step": "1"}),
            "years_experience": forms.NumberInput(
                attrs={"min": "0", "step": "0.1"}
            ),
        }


class EmployeeSkillCreateForm(EmployeeSkillProficiencyForm):
    skill = SkillChoiceField(
        queryset=Skill.objects.none(),
        empty_label="Select a skill",
        help_text="Only skills not already on this employee's profile are shown.",
    )

    class Meta(EmployeeSkillProficiencyForm.Meta):
        fields = ("employee", "skill", "level", "years_experience")
        widgets = {
            **EmployeeSkillProficiencyForm.Meta.widgets,
            "employee": forms.HiddenInput(),
        }
        error_messages = {
            NON_FIELD_ERRORS: {
                "unique_together": "This employee already has this skill.",
            }
        }

    def __init__(self, *args, employee, **kwargs):
        instance = kwargs.get("instance") or EmployeeSkill()
        instance.employee = employee
        kwargs["instance"] = instance
        super().__init__(*args, **kwargs)

        self.fields["employee"].disabled = True
        self.fields["employee"].initial = employee
        available_skills = Skill.objects.order_by("category", "name", "skill_id")
        if not self.is_bound:
            available_skills = available_skills.exclude(
                employee_skills__employee=employee
            )
        self.fields["skill"].queryset = available_skills


class EmployeeSkillUpdateForm(EmployeeSkillProficiencyForm):
    """Edit proficiency without changing the employee/skill relationship."""
