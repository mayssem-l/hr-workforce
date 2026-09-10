from django.contrib import messages
from django.db import DatabaseError, transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.models import Assignment, AssignmentSkill, Project, ProjectSkillRequirement
from frontend.forms.coverage import AssignmentSkillCoverageForm
from frontend.navigation import (
    get_planning_return_url,
    planning_return_query,
    with_planning_return,
)
from frontend.permissions import (
    read_models_permission_required,
    write_model_permission_required,
)
from frontend.presenters.coverage import build_assignment_coverage_profile
from frontend.selectors.assignments import (
    get_assignment_coverage_link,
    get_assignment_coverage_profile,
    get_project_assignment,
)


def _assignment_or_404(project_id, assignment_id, *, coverage_profile=False):
    try:
        selector = (
            get_assignment_coverage_profile
            if coverage_profile
            else get_project_assignment
        )
        return selector(project_id, assignment_id)
    except Assignment.DoesNotExist as exc:
        raise Http404("Project assignment not found.") from exc


def _coverage_or_404(project_id, assignment_id, coverage_id):
    try:
        return get_assignment_coverage_link(
            project_id,
            assignment_id,
            coverage_id,
        )
    except AssignmentSkill.DoesNotExist as exc:
        raise Http404("Assignment coverage not found.") from exc


def _coverage_detail_url(assignment):
    return reverse(
        "frontend:project_assignment_coverage",
        args=[assignment.project_id, assignment.assignment_id],
    )


def _coverage_breadcrumbs(assignment, current_label):
    project = assignment.project
    return [
        {"label": "Dashboard", "url": reverse("frontend:landing")},
        {"label": "Projects", "url": reverse("frontend:project_list")},
        {
            "label": project.name,
            "url": reverse(
                "frontend:project_detail",
                args=[project.project_id],
            ),
        },
        {
            "label": f"{assignment.employee} coverage",
            "url": _coverage_detail_url(assignment),
        },
        {"label": current_label, "url": None},
    ]


@read_models_permission_required(
    Project,
    Assignment,
    ProjectSkillRequirement,
    AssignmentSkill,
)
@require_http_methods(["GET"])
def project_assignment_coverage(request, project_id, assignment_id):
    assignment = _assignment_or_404(
        project_id,
        assignment_id,
        coverage_profile=True,
    )
    profile = build_assignment_coverage_profile(assignment)
    planning_return_url = get_planning_return_url(
        request,
        project_id=assignment.project_id,
    )
    return render(
        request,
        "frontend/projects/assignments/coverage/detail.html",
        {
            "breadcrumbs": _coverage_breadcrumbs(
                assignment,
                "Requirement coverage",
            )[:-1]
            + [{"label": "Requirement coverage", "url": None}],
            "coverage_headers": (
                "Project requirement",
                "People needed",
                "Requirement type",
                "Coverage status",
                "Planning note",
                "Actions",
            ),
            "add_coverage_url": with_planning_return(
                reverse(
                    "frontend:project_assignment_coverage_create",
                    args=[assignment.project_id, assignment.assignment_id],
                ),
                planning_return_url,
            ),
            "profile": profile,
            "planning_return_query": planning_return_query(planning_return_url),
            "planning_return_url": planning_return_url,
        },
    )


@write_model_permission_required(AssignmentSkill, "add")
@require_http_methods(["GET", "POST"])
def project_assignment_coverage_create(request, project_id, assignment_id):
    assignment = _assignment_or_404(project_id, assignment_id)
    planning_return_url = get_planning_return_url(
        request,
        project_id=assignment.project_id,
    )
    destination_url = planning_return_url or _coverage_detail_url(assignment)
    form = AssignmentSkillCoverageForm(
        request.POST or None,
        assignment=assignment,
    )

    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    coverage = form.save()
            except DatabaseError:
                messages.error(
                    request,
                    "We could not add this requirement coverage. No changes "
                    "were applied. Please try again.",
                )
            else:
                messages.success(
                    request,
                    f"{coverage.project_skill_requirement.skill} coverage was "
                    f"added for {coverage.assignment.employee}.",
                )
                return redirect(destination_url)
        else:
            messages.error(
                request,
                "Please correct the highlighted field before adding coverage.",
            )

    return render(
        request,
        "frontend/projects/assignments/coverage/create.html",
        {
            "assignment": assignment,
            "available_requirement_count": form.fields[
                "project_skill_requirement"
            ].queryset.count(),
            "breadcrumbs": _coverage_breadcrumbs(assignment, "Add coverage"),
            "cancel_label": (
                "Return to planning workspace" if planning_return_url else "Cancel"
            ),
            "cancel_url": destination_url,
            "form": form,
            "project": assignment.project,
        },
    )


@write_model_permission_required(AssignmentSkill, "delete")
@require_http_methods(["GET", "POST"])
def project_assignment_coverage_remove(
    request,
    project_id,
    assignment_id,
    coverage_id,
):
    coverage = _coverage_or_404(project_id, assignment_id, coverage_id)
    assignment = coverage.assignment
    requirement = coverage.project_skill_requirement
    detail_url = _coverage_detail_url(assignment)
    planning_return_url = get_planning_return_url(
        request,
        project_id=assignment.project_id,
    )
    destination_url = planning_return_url or detail_url
    remove_url = reverse(
        "frontend:project_assignment_coverage_remove",
        args=[project_id, assignment_id, coverage_id],
    )
    remove_url = with_planning_return(remove_url, planning_return_url)

    if request.method == "POST":
        skill_name = requirement.skill.name
        employee_name = str(assignment.employee)
        try:
            with transaction.atomic():
                coverage.delete()
        except DatabaseError:
            messages.error(
                request,
                "We could not remove this requirement coverage. No changes "
                "were applied. Please try again.",
            )
        else:
            messages.success(
                request,
                f"{skill_name} coverage was removed for {employee_name}.",
            )
            return redirect(destination_url)

    return render(
        request,
        "frontend/projects/assignments/coverage/confirm_remove.html",
        {
            "assignment": assignment,
            "breadcrumbs": _coverage_breadcrumbs(
                assignment,
                f"Remove {requirement.skill}",
            ),
            "cancel_url": destination_url,
            "confirmation_message": (
                f"Remove {requirement.skill} coverage from "
                f"{assignment.employee}'s assignment? The assignment, project "
                "requirement, employee skill, and project will remain unchanged."
            ),
            "coverage": coverage,
            "project": assignment.project,
            "remove_url": remove_url,
            "requirement": requirement,
        },
    )
