from django.core.exceptions import ValidationError

from core.models import AssignmentSkill


def _requirement_validation_message(error):
    messages = error.message_dict.get("project_skill_requirement", [])
    if messages:
        return str(messages[0])
    return "This requirement is not available for this assignment."


def build_assignment_coverage_profile(assignment):
    """Describe requirement coverage using AssignmentSkill's existing rules."""
    coverage_by_requirement = {
        coverage.project_skill_requirement_id: coverage
        for coverage in assignment.coverage_links
    }
    rows = []
    available_count = 0

    for requirement in assignment.coverage_requirements:
        coverage = coverage_by_requirement.get(
            requirement.project_skill_requirement_id
        )
        if coverage is not None:
            status = "covered"
            status_label = "Covered"
            status_tone = "active"
            message = (
                f"{assignment.employee} is already linked to this requirement."
            )
        else:
            candidate = AssignmentSkill(
                assignment=assignment,
                project_skill_requirement=requirement,
            )
            try:
                candidate.clean()
            except ValidationError as error:
                status = "unavailable"
                status_label = "Unavailable"
                status_tone = "inactive"
                message = _requirement_validation_message(error)
            else:
                status = "available"
                status_label = "Available"
                status_tone = "planned"
                message = (
                    f"{assignment.employee} meets this requirement's current "
                    "coverage rules."
                )
                available_count += 1

        rows.append(
            {
                "assignment_id": assignment.assignment_id,
                "coverage": coverage,
                "message": message,
                "project_id": assignment.project_id,
                "requirement": requirement,
                "status": status,
                "status_label": status_label,
                "status_tone": status_tone,
            }
        )

    return {
        "assignment": assignment,
        "available_count": available_count,
        "covered_count": len(assignment.coverage_links),
        "rows": rows,
    }
