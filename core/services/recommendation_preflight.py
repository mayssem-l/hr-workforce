from django.db.models import Q

from core.models import ProjectSkillRequirement


MANDATORY_EFFORT_BLOCKER_CODE = "mandatory_effort_must_be_positive"


def get_recommendation_preflight(project):
    """Return actionable blockers that must be resolved before team search."""

    invalid_requirements = list(
        ProjectSkillRequirement.objects.filter(
            project=project,
            is_mandatory=True,
        )
        .filter(
            Q(estimated_effort_hours__isnull=True)
            | Q(estimated_effort_hours__lte=0)
        )
        .select_related("skill")
        .order_by("project_skill_requirement_id")
    )

    blockers = [
        {
            "code": MANDATORY_EFFORT_BLOCKER_CODE,
            "field": "estimated_effort_hours",
            "requirement": requirement,
            "message": (
                "Enter estimated effort greater than 0 hours for the mandatory "
                f"{requirement.skill} requirement before generating recommendations."
            ),
        }
        for requirement in invalid_requirements
    ]

    return {
        "can_generate_recommendations": not blockers,
        "blockers": blockers,
    }
