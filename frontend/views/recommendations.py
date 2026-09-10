import logging

from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.models import (
    Assignment,
    AssignmentSkill,
    Employee,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from frontend.forms.recommendations import RecommendationGenerationForm
from frontend.orchestration.recommendations import run_recommendation_pipeline
from frontend.orchestration.recommendation_enrichment import (
    build_optional_manager_summaries,
)
from frontend.permissions import read_models_permission_required
from frontend.presenters.recommendations import (
    build_recommendation_error_foundation,
    build_recommendation_result_foundation,
)
from frontend.recommendation_execution import claim_recommendation_submission


logger = logging.getLogger(__name__)


def _result_context(project, run):
    planning_url = reverse(
        "frontend:project_planning",
        args=[project.project_id],
    )
    return {
        "breadcrumbs": [
            {"label": "Dashboard", "url": reverse("frontend:landing")},
            {"label": "Projects", "url": reverse("frontend:project_list")},
            {
                "label": project.name,
                "url": reverse(
                    "frontend:project_detail",
                    args=[project.project_id],
                ),
            },
            {"label": "Planning workspace", "url": planning_url},
            {"label": "Recommendation result", "url": None},
        ],
        "planning_url": planning_url,
        "project": project,
        "project_detail_url": reverse(
            "frontend:project_detail",
            args=[project.project_id],
        ),
        "run": run,
    }


def _render_result(request, project, run, *, status=200):
    return render(
        request,
        "frontend/recommendations/result.html",
        _result_context(project, run),
        status=status,
    )


@read_models_permission_required(
    Project,
    ProjectSkillRequirement,
    Assignment,
    AssignmentSkill,
    Employee,
    Skill,
)
@require_POST
def project_recommendation_generate(request, project_id):
    try:
        project = Project.objects.only(
            "project_id",
            "name",
            "start_date",
            "end_date",
            "estimated_hours",
            "status",
        ).get(project_id=project_id)
    except Project.DoesNotExist as exc:
        raise Http404("Project not found.") from exc

    form = RecommendationGenerationForm(
        request.POST,
        project=project,
        user=request.user,
    )
    if not form.is_valid():
        return _render_result(
            request,
            project,
            build_recommendation_error_foundation("invalid"),
            status=400,
        )

    submission_token = form.cleaned_data["submission_token"]
    if not claim_recommendation_submission(submission_token):
        return _render_result(
            request,
            project,
            build_recommendation_error_foundation("duplicate"),
            status=409,
        )

    try:
        pipeline_result = run_recommendation_pipeline(project)
    except Exception:
        logger.exception(
            "Recommendation generation failed for project %s.",
            project.project_id,
        )
        return _render_result(
            request,
            project,
            build_recommendation_error_foundation("error"),
            status=503,
        )

    manager_summaries = build_optional_manager_summaries(
        pipeline_result["explanations"]
    )

    return _render_result(
        request,
        project,
        build_recommendation_result_foundation(
            project,
            pipeline_result,
            request.user,
            manager_summaries,
        ),
    )
