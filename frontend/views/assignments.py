from django.contrib import messages
from django.db import DatabaseError, transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from core.models import Assignment, Project
from frontend.forms.assignments import AssignmentForm
from frontend.navigation import get_planning_return_url
from frontend.permissions import write_model_permission_required
from frontend.selectors.assignments import (
    get_project_assignment,
    get_project_for_assignment,
)


def _project_or_404(project_id):
    try:
        return get_project_for_assignment(project_id)
    except Project.DoesNotExist as exc:
        raise Http404("Project not found.") from exc


def _assignment_or_404(project_id, assignment_id):
    try:
        return get_project_assignment(project_id, assignment_id)
    except Assignment.DoesNotExist as exc:
        raise Http404("Project assignment not found.") from exc


def _project_detail_url(project):
    return reverse("frontend:project_detail", args=[project.project_id])


def _assignment_breadcrumbs(project, current_label):
    return [
        {"label": "Dashboard", "url": reverse("frontend:landing")},
        {"label": "Projects", "url": reverse("frontend:project_list")},
        {"label": project.name, "url": _project_detail_url(project)},
        {"label": current_label, "url": None},
    ]


def _save_assignment_form(request, form, *, success_message):
    try:
        with transaction.atomic():
            assignment = form.save()
    except DatabaseError:
        messages.error(
            request,
            "We could not save this assignment. No changes were applied. "
            "Please try again.",
        )
        return None

    messages.success(request, success_message(assignment))
    return assignment


@write_model_permission_required(Assignment, "add")
def project_assignment_create(request, project_id):
    project = _project_or_404(project_id)
    planning_return_url = get_planning_return_url(
        request,
        project_id=project.project_id,
    )
    destination_url = planning_return_url or _project_detail_url(project)
    form = AssignmentForm(request.POST or None, project=project)

    if request.method == "POST":
        if form.is_valid():
            assignment = _save_assignment_form(
                request,
                form,
                success_message=lambda saved: (
                    f"{saved.employee} was assigned to {saved.project}."
                ),
            )
            if assignment is not None:
                return redirect(destination_url)
        else:
            messages.error(
                request,
                "Please correct the highlighted fields before adding the "
                "assignment.",
            )

    return render(
        request,
        "frontend/projects/assignments/create.html",
        {
            "breadcrumbs": _assignment_breadcrumbs(project, "Add assignment"),
            "cancel_label": (
                "Return to planning workspace" if planning_return_url else "Cancel"
            ),
            "cancel_url": destination_url,
            "form": form,
            "project": project,
        },
    )


@write_model_permission_required(Assignment, "change")
def project_assignment_update(request, project_id, assignment_id):
    assignment = _assignment_or_404(project_id, assignment_id)
    project = assignment.project
    planning_return_url = get_planning_return_url(
        request,
        project_id=project.project_id,
    )
    destination_url = planning_return_url or _project_detail_url(project)
    form = AssignmentForm(
        request.POST or None,
        instance=assignment,
        project=project,
    )

    if request.method == "POST":
        if form.is_valid():
            saved_assignment = _save_assignment_form(
                request,
                form,
                success_message=lambda saved: (
                    f"The assignment for {saved.employee} on {saved.project} "
                    "was updated."
                ),
            )
            if saved_assignment is not None:
                return redirect(destination_url)
        else:
            messages.error(
                request,
                "Please correct the highlighted fields before saving changes.",
            )

    return render(
        request,
        "frontend/projects/assignments/edit.html",
        {
            "assignment": assignment,
            "breadcrumbs": _assignment_breadcrumbs(
                project,
                f"Edit {assignment.employee}",
            ),
            "cancel_label": (
                "Return to planning workspace" if planning_return_url else "Cancel"
            ),
            "cancel_url": destination_url,
            "form": form,
            "project": project,
        },
    )
