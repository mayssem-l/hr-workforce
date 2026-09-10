import logging

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from core.models import (
    Assignment,
    AssignmentSkill,
    Employee,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from frontend.forms.recommendations import RecommendationGenerationForm
from frontend.orchestration.recommendations import (
    RecommendationPipelineStageError,
    run_recommendation_pipeline,
)
from frontend.orchestration.recommendation_enrichment import (
    build_optional_manager_summaries,
    build_unavailable_manager_summaries,
)
from frontend.permissions import read_models_permission_required
from frontend.presenters.recommendations import (
    build_recommendation_error_foundation,
    build_recommendation_readiness_foundation,
    build_recommendation_result_foundation,
)
from frontend.recommendation_execution import claim_recommendation_submission
from frontend.recommendation_runs import (
    fetch_recommendation_run,
    issue_recommendation_run_id,
    store_recommendation_run,
)
from frontend.presenters.planning import build_project_planning_readiness
from frontend.selectors.projects import get_project_profile
from frontend.selectors.recommendations import (
    get_recommendation_input_snapshot,
    recommendation_pipeline_result_is_complete,
    recommendation_references_are_current,
)


logger = logging.getLogger(__name__)


def _result_context(project, run, run_id=None):
    project_is_available = run["state"] != "project_changed"
    planning_url = (
        reverse(
            "frontend:project_planning",
            args=[project.project_id],
        )
        if project_is_available
        else None
    )
    project_detail_url = (
        reverse(
            "frontend:project_detail",
            args=[project.project_id],
        )
        if project_is_available
        else None
    )
    return {
        "breadcrumbs": [
            {"label": "Dashboard", "url": reverse("frontend:landing")},
            {"label": "Projects", "url": reverse("frontend:project_list")},
            {
                "label": project.name,
                "url": project_detail_url,
            },
            {
                "label": "Planning workspace",
                "url": planning_url,
            },
            {"label": "Recommendation result", "url": None},
        ],
        "planning_url": planning_url,
        "project": project,
        "project_detail_url": project_detail_url,
        "project_list_url": reverse("frontend:project_list"),
        "run": run,
        "recommendation_run_id": run_id,
    }


def _render_result(request, project, run, *, status=200, run_id=None):
    return render(
        request,
        "frontend/recommendations/result.html",
        _result_context(project, run, run_id),
        status=status,
    )


def _render_current_data_result(request, project, state, *, status):
    """Render recovery against a freshly loaded project or a deleted state."""

    try:
        current_project = get_project_profile(project.project_id)
    except Project.DoesNotExist:
        return _render_result(
            request,
            project,
            build_recommendation_error_foundation(
                "project_changed", user=request.user
            ),
            status=409,
        )
    return _render_result(
        request,
        current_project,
        build_recommendation_error_foundation(
            state, project=current_project, user=request.user
        ),
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
        project = get_project_profile(project_id)
        starting_snapshot = get_recommendation_input_snapshot(project_id)
    except Project.DoesNotExist as exc:
        raise Http404("Project not found.") from exc

    form = RecommendationGenerationForm(
        request.POST,
        project=project,
        user=request.user,
        input_signature=starting_snapshot["signature"],
    )
    if not form.is_valid():
        state = "stale" if form.is_stale else "invalid"
        if state == "stale":
            return _render_current_data_result(
                request,
                project,
                state,
                status=409,
            )
        return _render_result(
            request,
            project,
            build_recommendation_error_foundation(
                state, project=project, user=request.user
            ),
            status=409 if state == "stale" else 400,
        )

    submission_token = form.cleaned_data["submission_token"]
    if not claim_recommendation_submission(submission_token):
        return _render_result(
            request,
            project,
            build_recommendation_error_foundation(
                "duplicate", project=project, user=request.user
            ),
            status=409,
        )

    try:
        readiness_assessment = build_project_planning_readiness(project)
    except Exception:
        logger.exception(
            "Recommendation readiness assessment failed for project %s.",
            project.project_id,
        )
        return _render_result(
            request,
            project,
            build_recommendation_error_foundation(
                "error", project=project, user=request.user
            ),
            status=503,
        )

    readiness = readiness_assessment["readiness"]
    try:
        pre_run_snapshot = get_recommendation_input_snapshot(project_id)
    except Project.DoesNotExist:
        return _render_current_data_result(
            request, project, "project_changed", status=409
        )
    if pre_run_snapshot["signature"] != starting_snapshot["signature"]:
        return _render_current_data_result(
            request,
            project,
            "stale",
            status=409,
        )
    if not readiness["candidate_assessment_allowed"]:
        return _render_result(
            request,
            project,
            build_recommendation_readiness_foundation(
                project, readiness, request.user
            ),
            status=422,
        )

    try:
        pipeline_result = run_recommendation_pipeline(project)
    except RecommendationPipelineStageError as exc:
        logger.exception(
            "Recommendation generation failed in stage %s for project %s.",
            exc.stage,
            project.project_id,
        )
        return _render_result(
            request,
            project,
            build_recommendation_error_foundation(
                "error", project=project, user=request.user
            ),
            status=503,
        )
    except Exception:
        logger.exception(
            "Recommendation generation failed for project %s.",
            project.project_id,
        )
        return _render_result(
            request,
            project,
            build_recommendation_error_foundation(
                "error", project=project, user=request.user
            ),
            status=503,
        )

    if not recommendation_pipeline_result_is_complete(pipeline_result):
        return _render_result(
            request,
            project,
            build_recommendation_error_foundation(
                "incomplete", project=project, user=request.user
            ),
            status=503,
        )

    try:
        completed_snapshot = get_recommendation_input_snapshot(project_id)
    except Project.DoesNotExist:
        return _render_current_data_result(
            request, project, "project_changed", status=409
        )
    if (
        completed_snapshot["signature"] != pre_run_snapshot["signature"]
        or not recommendation_references_are_current(
            pipeline_result,
            completed_snapshot,
        )
    ):
        return _render_current_data_result(
            request,
            project,
            "stale",
            status=409,
        )

    try:
        manager_summaries = build_optional_manager_summaries(
            pipeline_result["explanations"]
        )
    except Exception:
        logger.warning(
            "Optional recommendation wording was unavailable for project %s.",
            project.project_id,
        )
        manager_summaries = build_unavailable_manager_summaries(
            pipeline_result["explanations"]
        )

    try:
        presentation_snapshot = get_recommendation_input_snapshot(project_id)
    except Project.DoesNotExist:
        return _render_current_data_result(
            request, project, "project_changed", status=409
        )
    if presentation_snapshot["signature"] != completed_snapshot["signature"]:
        return _render_current_data_result(
            request,
            project,
            "stale",
            status=409,
        )

    try:
        run_id = issue_recommendation_run_id()
        run = build_recommendation_result_foundation(
            project,
            pipeline_result,
            request.user,
            manager_summaries,
            run_id=run_id,
        )
    except Exception:
        logger.exception(
            "Recommendation presentation failed for project %s.",
            project.project_id,
        )
        return _render_result(
            request,
            project,
            build_recommendation_error_foundation(
                "incomplete", project=project, user=request.user
            ),
            status=503,
        )
    store_recommendation_run(
        run_id,
        project_id=project.project_id,
        user_id=request.user.pk,
        input_signature=presentation_snapshot["signature"],
        pipeline_result=pipeline_result,
        manager_summaries=manager_summaries,
    )
    return _render_result(request, project, run, run_id=run_id)


@read_models_permission_required(
    Project,
    ProjectSkillRequirement,
    Assignment,
    AssignmentSkill,
    Employee,
    Skill,
)
@require_GET
def project_recommendation_result(request, project_id, run_id):
    """Re-render one cached generation result without rerunning the pipeline."""

    try:
        project = get_project_profile(project_id)
    except Project.DoesNotExist as exc:
        raise Http404("Project not found.") from exc

    planning_url = reverse(
        "frontend:project_planning", args=[project.project_id]
    )

    def _fresh_required():
        messages.warning(
            request,
            "This recommendation result is no longer current. "
            "Generate a fresh recommendation from the planning workspace.",
        )
        return redirect(planning_url)

    record = fetch_recommendation_run(run_id)
    if (
        record is None
        or record.get("project_id") != project.project_id
        or record.get("user_id") != request.user.pk
    ):
        return _fresh_required()

    pipeline_result = record.get("pipeline_result")
    manager_summaries = record.get("manager_summaries")
    if not isinstance(pipeline_result, dict):
        return _fresh_required()

    try:
        current_snapshot = get_recommendation_input_snapshot(project_id)
    except Project.DoesNotExist:
        return _fresh_required()
    if (
        record.get("input_signature") != current_snapshot["signature"]
        or not recommendation_pipeline_result_is_complete(pipeline_result)
        or not recommendation_references_are_current(
            pipeline_result, current_snapshot
        )
    ):
        return _fresh_required()

    try:
        run = build_recommendation_result_foundation(
            project,
            pipeline_result,
            request.user,
            manager_summaries,
            run_id=run_id,
        )
    except Exception:
        logger.exception(
            "Cached recommendation result failed for project %s.",
            project.project_id,
        )
        return _fresh_required()
    return _render_result(request, project, run, run_id=run_id)
