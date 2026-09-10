"""Shape a reviewed staffing proposal for templates without new logic."""

from urllib.parse import urlencode

from django.urls import reverse

from frontend.navigation import with_planning_return


def handoff_navigation(project, user):
    planning_url = reverse(
        "frontend:project_planning",
        args=[project.project_id],
    )
    can_view_employee = user.has_perm("core.view_employee")
    return {
        "planning_url": planning_url,
        "project_url": reverse(
            "frontend:project_detail",
            args=[project.project_id],
        ),
    }


def _employee_profile_url(employee, project, user, planning_url):
    employee_id = getattr(employee, "employee_id", None)
    if (
        not employee_id
        or not user.has_perm("core.view_employee")
    ):
        return None
    period_query = urlencode(
        {
            "start_date": project.start_date.isoformat(),
            "end_date": project.end_date.isoformat(),
        }
    )
    profile_url = (
        reverse("frontend:employee_detail", args=[employee_id])
        + f"?{period_query}"
    )
    return with_planning_return(profile_url, planning_url)


def present_handoff_review(
    project,
    recommendation,
    proposals,
    validation,
    user,
    form,
    confirm_url,
    planning_url,
):
    rows = []
    for proposal, row_errors in zip(proposals, validation["rows"]):
        employee = proposal["employee"]
        label = str(employee).strip() or "Employee record unavailable"
        coverage_labels = []
        for requirement in proposal["coverage_requirements"]:
            skill = getattr(requirement, "skill", None)
            skill_label = str(skill).strip() if skill is not None else ""
            if skill_label:
                coverage_labels.append(skill_label)
            else:
                coverage_labels.append("Requirement record unavailable")
        rows.append(
            {
                "employee": employee,
                "label": label,
                "profile_url": _employee_profile_url(
                    employee, project, user, planning_url
                ),
                "start_date": proposal["start_date"],
                "end_date": proposal["end_date"],
                "allocation_percentage": proposal[
                    "allocation_percentage"
                ],
                "role_on_project": proposal["role_on_project"],
                "status": proposal["status"],
                "allocated_hours": proposal["allocated_hours"],
                "available_hours": proposal["available_hours"],
                "coverage_labels": tuple(coverage_labels),
                "errors": row_errors,
                "has_error": bool(row_errors),
            }
        )
    return {
        "category": recommendation["category"],
        "label": recommendation["label"],
        "reason": recommendation.get("reason", ""),
        "team_size": recommendation["result"]["team_size"],
        "team_score": recommendation["result"]["team_score"],
        "rows": tuple(rows),
        "has_error": validation["has_error"],
        "form": form,
        "confirm_url": confirm_url,
        "planning_url": planning_url,
    }
