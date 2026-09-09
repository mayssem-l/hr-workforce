from django import forms
from django.core.exceptions import NON_FIELD_ERRORS

from core.models import ProjectSkillRequirement, Skill


class RequirementSkillChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, skill):
        return f"{skill.name} — {skill.category}"


class ProjectSkillRequirementForm(forms.ModelForm):
    """Maintain project demand through existing requirement validation."""

    skill = RequirementSkillChoiceField(
        queryset=Skill.objects.none(),
        empty_label="Select a skill",
    )

    class Meta:
        model = ProjectSkillRequirement
        fields = (
            "project",
            "skill",
            "required_level",
            "priority",
            "is_mandatory",
            "required_quantity",
            "estimated_effort_hours",
        )
        labels = {
            "required_level": "Required proficiency level",
            "required_quantity": "People needed",
            "estimated_effort_hours": "Estimated effort (hours)",
            "is_mandatory": "Mandatory requirement",
        }
        help_texts = {
            "skill": "Choose the capability this project needs.",
            "required_level": "Choose the minimum proficiency level from 1 to 5.",
            "priority": "Indicate this requirement's importance for planning.",
            "is_mandatory": (
                "Mark this when the skill is essential for a feasible team."
            ),
            "required_quantity": (
                "Enter how many assigned employees need to cover this skill."
            ),
            "estimated_effort_hours": (
                "Enter the total project effort associated with this skill."
            ),
        }
        widgets = {
            "project": forms.HiddenInput(),
            "required_level": forms.NumberInput(
                attrs={"min": "1", "max": "5", "step": "1"}
            ),
            "required_quantity": forms.NumberInput(
                attrs={"min": "1", "step": "1"}
            ),
            "estimated_effort_hours": forms.NumberInput(
                attrs={"min": "0", "step": "0.01"}
            ),
        }
        error_messages = {
            NON_FIELD_ERRORS: {
                "unique_together": "This project already requires this skill.",
            }
        }

    def __init__(self, *args, project, **kwargs):
        instance = kwargs.get("instance") or ProjectSkillRequirement()
        instance.project = project
        kwargs["instance"] = instance
        super().__init__(*args, **kwargs)

        self.fields["project"].disabled = True
        self.fields["project"].initial = project
        skills = Skill.objects.order_by("category", "name", "skill_id")
        if not self.is_bound:
            used_skills = ProjectSkillRequirement.objects.filter(
                project=project
            )
            if instance.pk:
                used_skills = used_skills.exclude(pk=instance.pk)
            skills = skills.exclude(
                project_requirements__in=used_skills
            )
        self.fields["skill"].queryset = skills
