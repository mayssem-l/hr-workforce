import logging

from django.contrib import messages
from django.db import DatabaseError, transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.models import (
    Assignment,
    AssignmentSkill,
    Employee,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from frontend.assignment_handoff import claim_handoff_submission
from frontend.forms.assignment_handoff import AssignmentHandoffForm
from frontend.orchestration.assignment_handoff import (
    build_handoff_proposal,
    validate_handoff_proposal,
)
from frontend.orchestration.recommendations import (
    RecommendationPipelineStageError,
    run_recommendation_pipeline,
)
from frontend.permissions import (
    read_models_permission_required,
    write_model_permission_required,
)
from frontend.presenters.assignment_handoff import present_handoff_review
from frontend.presenters.recommendations import (
    build_recommendation_error_foundation,
    build_recommendation_readiness_foundation,
)
from frontend.presenters.planning import build_project_planning_readiness
from frontend.selectors.projects import get_project_profile
from frontend.selectors.recommendations import (
    get_recommendation_input_snapshot,
    recommendation_pipeline_result_is_complete,
    recommendation_references_are_current,
)


logger = logging.getLogger(__name__)

ALLOWED_HANDOFF_CATEGORIES = ("compact_match", "balanced", "capacity")


def _planning_url(project_id):
    return reverse("frontend:project_planning", args=[project_id])


def _confirm_url(project_id, category):
    return reverse(
        "frontend:project_recommendation_confirm",
        args=[project_id, category],
    )


def _handoff_error(title, message, *, recovery_section=None):
    return {
        "title": title,
        "message": message,
        "recovery_section": recovery_section,
    }


def _render_confirm(
    request,
    project,
    category,
    *,
    run=None,
    review=None,
    status=200,
):
    planning_url = _planning_url(project.project_id)
    return render(
        request,
        "frontend/recommendations/confirm.html",
        {
            "breadcrumbs": [
                {
                    "label": "Dashboard",
                    "url": reverse("frontend:landing"),
                },
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
                {"label": "Planning workspace", "url": planning_url},
                {"label": "Staffing confirmation", "url": None},
            ],
            "project": project,
            "category": category,
            "planning_url": planning_url,
            "project_detail_url": reverse(
                "frontend:project_detail",
                args=[project.project_id],
            ),
            "project_list_url": reverse("frontend:project_list"),
            "run": run,
            "review": review,
        },
        status=status,
    )


def _load_pipeline_state(project, project_id):
    """Run readiness plus the deterministic pipeline with currency checks."""

    try:
        readiness_assessment = build_project_planning_readiness(project)
    except Exception:
        logger.exception(
            "Staffing review readiness failed for project %s.",
            project.project_id,
        )
        return {"outcome": "error"}

    readiness = readiness_assessment["readiness"]
    try:
        pre_run_snapshot = get_recommendation_input_snapshot(project_id)
    except Project.DoesNotExist:
        return {"outcome": "project_changed"}
    if not readiness["candidate_assessment_allowed"]:
        return {
            "outcome": "blocked",
            "readiness": readiness,
        }

    try:
        pipeline_result = run_recommendation_pipeline(project)
    except RecommendationPipelineStageError as exc:
        logger.exception(
            "Staffing review generation failed in stage %s for project %s.",
            exc.stage,
            project.project_id,
        )
        return {"outcome": "error"}
    except Exception:
        logger.exception(
            "Staffing review generation failed for project %s.",
            project.project_id,
        )
        return {"outcome": "error"}

    if not recommendation_pipeline_result_is_complete(pipeline_result):
        return {"outcome": "incomplete"}

    try:
        completed_snapshot = get_recommendation_input_snapshot(project_id)
    except Project.DoesNotExist:
        return {"outcome": "project_changed"}
    if (
        completed_snapshot["signature"] != pre_run_snapshot["signature"]
        or not recommendation_references_are_current(
            pipeline_result, completed_snapshot
        )
    ):
        return {"outcome": "stale"}
    return {
        "outcome": "ready",
        "readiness": readiness,
        "pipeline_result": pipeline_result,
        "snapshot": completed_snapshot,
    }


def _select_recommendation(pipeline_result, category):
    for recommendation in pipeline_result["recommendations"]:
        if recommendation.get("category") == category:
            return recommendation
    return None


@read_models_permission_required(
    Project,
    ProjectSkillRequirement,
    Assignment,
    AssignmentSkill,
    Employee,
    Skill,
)
@write_model_permission_required(Assignment, "add")
@write_model_permission_required(AssignmentSkill, "add")
@require_http_methods(["GET", "POST"])
def project_recommendation_confirm(request, project_id, category):
    if category not in ALLOWED_HANDOFF_CATEGORIES:
        raise Http404("Recommendation strategy not found.")
    try:
        project = get_project_profile(project_id)
        starting_snapshot = get_recommendation_input_snapshot(project_id)
    except Project.DoesNotExist as exc:
        raise Http404("Project not found.") from exc

    planning_url = _planning_url(project.project_id)
    confirm_url = _confirm_url(project.project_id, category)

    if request.method == "GET":
        state = _load_pipeline_state(project, project_id)
        outcome = state["outcome"]
        if outcome == "blocked":
            return _render_confirm(
                request,
                project,
                category,
                run=build_recommendation_readiness_foundation(
                    project, state["readiness"], request.user
                ),
                status=422,
            )
        if outcome == "project_changed":
            return _render_confirm(
                request,
                project,
                category,
                run=build_recommendation_error_foundation(
                    "project_changed", user=request.user
                ),
                status=409,
            )
        if outcome == "stale":
            return _render_confirm(
                request,
                project,
                category,
                run=build_recommendation_error_foundation(
                    "stale", project=project, user=request.user
                ),
                status=409,
            )
        if outcome == "error":
            return _render_confirm(
                request,
                project,
                category,
                run=build_recommendation_error_foundation(
                    "error", project=project, user=request.user
                ),
                status=503,
            )
        if outcome == "incomplete":
            return _render_confirm(
                request,
                project,
                category,
                run=build_recommendation_error_foundation(
                    "incomplete", project=project, user=request.user
                ),
                status=503,
            )

        recommendation = _select_recommendation(
            state["pipeline_result"], category
        )
        if recommendation is None:
            return _render_confirm(
                request,
                project,
                category,
                run=build_recommendation_error_foundation(
                    "stale", project=project, user=request.user
                ),
                status=409,
            )
        proposals = build_handoff_proposal(project, recommendation)
        validation = validate_handoff_proposal(project, proposals)
        form = AssignmentHandoffForm(
            project=project,
            user=request.user,
            category=category,
            input_signature=state["snapshot"]["signature"],
        )
        review = present_handoff_review(
            project,
            recommendation,
            proposals,
            validation,
            request.user,
            form if not validation["has_error"] else None,
            confirm_url,
            planning_url,
        )
        return _render_confirm(
            request,
            project,
            category,
            review=review,
            status=422 if validation["has_error"] else 200,
        )

    form = AssignmentHandoffForm(
        request.POST,
        project=project,
        user=request.user,
        category=category,
        input_signature=starting_snapshot["signature"],
    )
    if not form.is_valid():
        state = "stale" if form.is_stale else "invalid"
        return _render_confirm(
            request,
            project,
            category,
            run=build_recommendation_error_foundation(
                state, project=project, user=request.user
            ),
            status=409 if state == "stale" else 400,
        )

    if not claim_handoff_submission(form.cleaned_data["submission_token"]):
        return _render_confirm(
            request,
            project,
            category,
            run=build_recommendation_error_foundation(
                "duplicate", project=project, user=request.user
            ),
            status=409,
        )

    state = _load_pipeline_state(project, project_id)
    outcome = state["outcome"]
    if outcome == "blocked":
        return _render_confirm(
            request,
            project,
            category,
            run=build_recommendation_readiness_foundation(
                project, state["readiness"], request.user
            ),
            status=422,
        )
    if outcome in ("project_changed", "stale", "error", "incomplete"):
        return _render_confirm(
            request,
            project,
            category,
            run=build_recommendation_error_foundation(
                outcome, project=project, user=request.user
            )
            if outcome != "project_changed"
            else build_recommendation_error_foundation(
                "project_changed", user=request.user
            ),
            status=409 if outcome in ("project_changed", "stale") else 503,
        )

    if state["snapshot"]["signature"] != starting_snapshot["signature"]:
        return _render_confirm(
            request,
            project,
            category,
            run=build_recommendation_error_foundation(
                "stale", project=project, user=request.user
            ),
            status=409,
        )

    recommendation = _select_recommendation(
        state["pipeline_result"], category
    )
    if recommendation is None:
        return _render_confirm(
            request,
            project,
            category,
            run=build_recommendation_error_foundation(
                "stale", project=project, user=request.user
            ),
            status=409,
        )

    proposals = build_handoff_proposal(project, recommendation)
    validation = validate_handoff_proposal(project, proposals)
    if validation["has_error"]:
        review = present_handoff_review(
            project,
            recommendation,
            proposals,
            validation,
            request.user,
            None,
            confirm_url,
            planning_url,
        )
        return _render_confirm(
            request, project, category, review=review, status=422
        )

    try:
        with transaction.atomic():
            saved_assignments = []
            for proposal in proposals:
                assignment = Assignment(
                    project=project,
                    employee=proposal["employee"],
                    start_date=proposal["start_date"],
                    end_date=proposal["end_date"],
                    allocation_percentage=proposal[
                        "allocation_percentage"
                    ],
                    role_on_project=proposal["role_on_project"],
                    status=proposal["status"],
                )
                assignment.full_clean()
                assignment.save()
                saved_assignments.append((assignment, proposal))
            for assignment, proposal in saved_assignments:
                for requirement in proposal["coverage_requirements"]:
                    link = AssignmentSkill(
                        assignment=assignment,
                        project_skill_requirement=requirement,
                    )
                    link.full_clean()
                    link.save()
    except Exception:
        logger.exception(
            "Staffing confirmation save failed for project %s.",
            project.project_id,
        )
        review = present_handoff_review(
            project,
            recommendation,
            proposals,
            {
                "rows": tuple(
                    {"__all__": ["This staffing confirmation could not be saved. No changes were applied."]}
                    for _ in proposals
                ),
                "has_error": True,
            },
            request.user,
            None,
            confirm_url,
            planning_url,
        )
        return _render_confirm(
            request, project, category, review=review, status=422
        )

    member_count = len(saved_assignments)
    messages.success(
        request,
        f"{member_count} staffing "
        f"{'assignment' if member_count == 1 else 'assignments'} "
        f"created from the {recommendation['label']} review.",
    )
    return redirect(planning_url)
