from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from core.models import (
    Assignment,
    AssignmentSkill,
    Employee,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from frontend.forms.recommendations import RecommendationGenerationForm
from frontend.permissions import read_models_permission_required
from frontend.presenters.planning import (
    build_candidate_exclusion_context,
    build_project_planning_workspace,
)
from frontend.presenters.planning_navigation import (
    add_planning_repair_navigation,
)
from frontend.presenters.recommendations import (
    build_recommendation_generation_context,
)
from frontend.selectors.planning import get_candidate_exclusion_workforce
from frontend.selectors.projects import get_project_profile
from frontend.selectors.recommendations import get_recommendation_input_snapshot


@read_models_permission_required(
    Project,
    ProjectSkillRequirement,
    Assignment,
    AssignmentSkill,
    Employee,
    Skill,
)
@require_GET
def project_planning(request, project_id):
    try:
        project = get_project_profile(project_id)
    except Project.DoesNotExist as exc:
        raise Http404("Project not found.") from exc

    workspace = build_project_planning_workspace(project)
    workforce = ()
    if workspace["readiness"]["candidate_assessment_allowed"]:
        workforce = get_candidate_exclusion_workforce()
    workspace["candidate_exclusions"] = build_candidate_exclusion_context(
        project,
        workspace["readiness"],
        workspace["candidates"],
        workforce,
    )
    add_planning_repair_navigation(workspace, request.user)
    recommendation_form = None
    if workspace["readiness"]["candidate_assessment_allowed"]:
        input_snapshot = get_recommendation_input_snapshot(project.project_id)
        recommendation_form = RecommendationGenerationForm(
            project=project,
            user=request.user,
            input_signature=input_snapshot["signature"],
        )
    recommendation_generation = build_recommendation_generation_context(
        project,
        workspace["readiness"],
        recommendation_form,
    )
    return render(
        request,
        "frontend/planning/workspace.html",
        {
            "assignment_headers": (
                "Employee",
                "Role",
                "Schedule",
                "Allocation",
                "Status",
                "Requirements covered",
                "Next step",
            ),
            "candidate_headers": (
                "Rank",
                "Employee",
                "Skill match",
                "Workload",
                "Leave",
                "Experience",
                "Project fit",
                "Requirement evidence",
            ),
            "candidate_exclusion_headers": (
                "Employee",
                "Why not ranked",
                "Evidence",
            ),
            "qualified_employee_headers": (
                "Qualified employee",
                "Current level",
                "Available project capacity",
            ),
            "requirement_coverage_headers": (
                "Currently covering",
                "Role",
                "Assignment status",
                "Next step",
            ),
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {
                    "label": "Projects",
                    "url": reverse("frontend:project_list"),
                },
                {
                    "label": project.name,
                    "url": reverse(
                        "frontend:project_detail",
                        args=[project.project_id],
                    ),
                },
                {"label": "Planning workspace", "url": None},
            ],
            "project_detail_url": reverse(
                "frontend:project_detail",
                args=[project.project_id],
            ),
            "project_list_url": reverse("frontend:project_list"),
            "recommendation_generation": recommendation_generation,
            "requirement_headers": (
                "Skill",
                "Required level",
                "People needed",
                "Estimated effort",
                "Priority",
                "Requirement type",
                "Next step",
            ),
            "workspace": workspace,
        },
    )
