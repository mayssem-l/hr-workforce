from django import forms
from django.core.exceptions import NON_FIELD_ERRORS

from core.models import AssignmentSkill, ProjectSkillRequirement


class CoverageRequirementChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, requirement):
        requirement_type = "Mandatory" if requirement.is_mandatory else "Optional"
        return (
            f"{requirement.skill.name} — Level {requirement.required_level} · "
            f"{requirement.required_quantity} needed · {requirement_type}"
        )


class AssignmentSkillCoverageForm(forms.ModelForm):
    """Link an assignment to project demand through AssignmentSkill validation."""

    project_skill_requirement = CoverageRequirementChoiceField(
        queryset=ProjectSkillRequirement.objects.none(),
        empty_label="Select a project requirement",
    )

    class Meta:
        model = AssignmentSkill
        fields = ("assignment", "project_skill_requirement")
        labels = {
            "project_skill_requirement": "Project requirement",
        }
        help_texts = {
            "project_skill_requirement": (
                "Choose a requirement this employee will cover. Skill, "
                "proficiency, project, and staffing limits are checked when "
                "you save."
            ),
        }
        widgets = {"assignment": forms.HiddenInput()}
        error_messages = {
            NON_FIELD_ERRORS: {
                "unique_together": (
                    "This assignment already covers this project requirement."
                ),
            }
        }

    def __init__(self, *args, assignment, **kwargs):
        instance = kwargs.get("instance") or AssignmentSkill()
        instance.assignment = assignment
        kwargs["instance"] = instance
        super().__init__(*args, **kwargs)

        self.fields["assignment"].disabled = True
        self.fields["assignment"].initial = assignment
        requirements = (
            ProjectSkillRequirement.objects.filter(project=assignment.project)
            .select_related("skill")
            .order_by(
                "-is_mandatory",
                "skill__category",
                "skill__name",
                "project_skill_requirement_id",
            )
        )
        if not self.is_bound:
            requirements = requirements.exclude(
                assignment_skills__assignment=assignment
            )
        self.fields["project_skill_requirement"].queryset = requirements

    def _post_clean(self):
        # AssignmentSkill.clean() expects both relationships to be present.
        # A rejected scoped choice is deliberately absent from cleaned_data,
        # so retain that field error without invoking model validation on an
        # incomplete request-local instance.
        if "project_skill_requirement" in self.errors:
            return
        super()._post_clean()
