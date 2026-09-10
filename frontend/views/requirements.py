from django.contrib import messages
from django.db import DatabaseError, transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.models import Project, ProjectSkillRequirement
from core.services.recommendation_preflight import get_recommendation_preflight
from frontend.forms.requirements import ProjectSkillRequirementForm
from frontend.navigation import get_planning_return_url
from frontend.permissions import write_model_permission_required
from frontend.selectors.requirements import (
    get_project_for_requirement,
    get_project_requirement,
)


def _project_or_404(project_id):
    try:
        return get_project_for_requirement(project_id)
    except Project.DoesNotExist as exc:
        raise Http404("Project not found.") from exc


def _requirement_or_404(project_id, requirement_id):
    try:
        return get_project_requirement(project_id, requirement_id)
    except ProjectSkillRequirement.DoesNotExist as exc:
        raise Http404("Project skill requirement not found.") from exc


def _project_detail_url(project):
    return reverse("frontend:project_detail", args=[project.project_id])


def _requirement_breadcrumbs(project, current_label):
    return [
        {"label": "Dashboard", "url": reverse("frontend:landing")},
        {"label": "Projects", "url": reverse("frontend:project_list")},
        {"label": project.name, "url": _project_detail_url(project)},
        {"label": current_label, "url": None},
    ]


def _save_requirement_form(request, form, *, success_message):
    try:
        with transaction.atomic():
            requirement = form.save()
    except DatabaseError:
        messages.error(
            request,
            "We could not save this skill requirement. No changes were "
            "applied. Please try again.",
        )
        return None

    messages.success(request, success_message(requirement))
    return requirement


@write_model_permission_required(ProjectSkillRequirement, "add")
def project_requirement_create(request, project_id):
    project = _project_or_404(project_id)
    planning_return_url = get_planning_return_url(
        request,
        project_id=project.project_id,
    )
    destination_url = planning_return_url or _project_detail_url(project)
    form = ProjectSkillRequirementForm(
        request.POST or None,
        project=project,
    )

    if request.method == "POST":
        if form.is_valid():
            requirement = _save_requirement_form(
                request,
                form,
                success_message=lambda saved: (
                    f"{saved.skill} was added to {saved.project}'s skill demand."
                ),
            )
            if requirement is not None:
                return redirect(destination_url)
        else:
            messages.error(
                request,
                "Please correct the highlighted fields before adding the "
                "skill requirement.",
            )

    return render(
        request,
        "frontend/projects/requirements/create.html",
        {
            "breadcrumbs": _requirement_breadcrumbs(
                project,
                "Add skill requirement",
            ),
            "cancel_label": (
                "Return to planning workspace" if planning_return_url else "Cancel"
            ),
            "cancel_url": destination_url,
            "form": form,
            "preflight": get_recommendation_preflight(project),
            "project": project,
        },
    )


@write_model_permission_required(ProjectSkillRequirement, "change")
def project_requirement_update(request, project_id, requirement_id):
    requirement = _requirement_or_404(project_id, requirement_id)
    project = requirement.project
    planning_return_url = get_planning_return_url(
        request,
        project_id=project.project_id,
    )
    destination_url = planning_return_url or _project_detail_url(project)
    form = ProjectSkillRequirementForm(
        request.POST or None,
        instance=requirement,
        project=project,
    )

    if request.method == "POST":
        if form.is_valid():
            saved_requirement = _save_requirement_form(
                request,
                form,
                success_message=lambda saved: (
                    f"The {saved.skill} requirement for {saved.project} was "
                    "updated."
                ),
            )
            if saved_requirement is not None:
                return redirect(destination_url)
        else:
            messages.error(
                request,
                "Please correct the highlighted fields before saving changes.",
            )

    return render(
        request,
        "frontend/projects/requirements/edit.html",
        {
            "breadcrumbs": _requirement_breadcrumbs(
                project,
                f"Edit {requirement.skill}",
            ),
            "cancel_label": (
                "Return to planning workspace" if planning_return_url else "Cancel"
            ),
            "cancel_url": destination_url,
            "form": form,
            "preflight": get_recommendation_preflight(project),
            "project": project,
            "requirement": requirement,
        },
    )


@write_model_permission_required(ProjectSkillRequirement, "delete")
@require_http_methods(["GET", "POST"])
def project_requirement_remove(request, project_id, requirement_id):
    requirement = _requirement_or_404(project_id, requirement_id)
    project = requirement.project
    detail_url = _project_detail_url(project)
    remove_url = reverse(
        "frontend:project_requirement_remove",
        args=[project.project_id, requirement.project_skill_requirement_id],
    )
    coverage_count = requirement.assignment_skills.count()

    if request.method == "POST":
        skill_name = requirement.skill.name
        project_name = project.name
        try:
            with transaction.atomic():
                requirement.delete()
        except DatabaseError:
            messages.error(
                request,
                "We could not remove this skill requirement. No changes were "
                "applied. Please try again.",
            )
        else:
            messages.success(
                request,
                f"The {skill_name} requirement was removed from {project_name}.",
            )
            return redirect(detail_url)

    return render(
        request,
        "frontend/projects/requirements/confirm_remove.html",
        {
            "breadcrumbs": _requirement_breadcrumbs(
                project,
                f"Remove {requirement.skill}",
            ),
            "cancel_url": detail_url,
            "confirmation_message": (
                f"Remove {requirement.skill} from {project}? Any assignment "
                "coverage linked to this requirement will also be removed. "
                "The project and skill will remain unchanged."
            ),
            "coverage_count": coverage_count,
            "project": project,
            "remove_url": remove_url,
            "requirement": requirement,
        },
    )
