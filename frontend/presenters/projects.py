from decimal import Decimal

from core.services.recommendation_preflight import get_recommendation_preflight


def build_project_profile(project):
    """Shape stored project context and existing preflight feedback for display."""
    requirements = project.profile_requirements
    assignments = project.profile_assignments
    mandatory_requirements = [
        requirement for requirement in requirements if requirement.is_mandatory
    ]
    mandatory_effort_hours = sum(
        (
            requirement.estimated_effort_hours or Decimal("0")
            for requirement in mandatory_requirements
        ),
        Decimal("0"),
    )
    preflight = get_recommendation_preflight(project)

    if preflight["blockers"]:
        readiness = {
            "label": "Planning input needed",
            "message": (
                "At least one mandatory skill requirement needs positive "
                "estimated effort before recommendations can run."
            ),
            "tone": "warning",
        }
    elif not mandatory_requirements:
        readiness = {
            "label": "No mandatory requirements",
            "message": (
                "There are no mandatory skill requirements to compare with "
                "the project estimate."
            ),
            "tone": "neutral",
        }
    elif project.estimated_hours != mandatory_effort_hours:
        readiness = {
            "label": "Review project estimates",
            "message": (
                "The project estimate and mandatory skill effort total do not "
                "match. Review both values before planning the team."
            ),
            "tone": "warning",
        }
    else:
        readiness = {
            "label": "Planning inputs aligned",
            "message": (
                "The project estimate matches the total effort assigned to "
                "mandatory skill requirements."
            ),
            "tone": "success",
        }

    return {
        "project": project,
        "requirements": requirements,
        "assignments": assignments,
        "mandatory_requirement_count": len(mandatory_requirements),
        "mandatory_effort_hours": mandatory_effort_hours,
        "coverage_count": sum(
            len(assignment.profile_coverage) for assignment in assignments
        ),
        "preflight": preflight,
        "readiness": readiness,
    }
