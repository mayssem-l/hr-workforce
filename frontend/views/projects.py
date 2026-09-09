from django.contrib import messages
from django.core.paginator import Paginator
from django.db import DatabaseError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.models import (
    Assignment,
    AssignmentSkill,
    Project,
    ProjectSkillRequirement,
)
from frontend.forms.projects import ProjectDirectoryFilterForm, ProjectForm
from frontend.permissions import (
    read_model_permission_required,
    read_models_permission_required,
    write_model_permission_required,
)
from frontend.presenters.projects import build_project_profile
from frontend.selectors.projects import (
    DEFAULT_PROJECT_SORT,
    PROJECT_PAGE_SIZE,
    get_project_directory,
    get_project_profile,
)


@read_model_permission_required(Project)
def project_list(request):
    filter_form = ProjectDirectoryFilterForm(request.GET)
    filters = {
        "query": "",
        "status": "",
        "priority": "",
        "criticality": "",
        "starts_on_or_after": None,
        "ends_on_or_before": None,
        "sort": DEFAULT_PROJECT_SORT,
    }
    if filter_form.is_valid():
        filters.update(filter_form.cleaned_data)

    projects = get_project_directory(**filters)
    page_obj = Paginator(projects, PROJECT_PAGE_SIZE).get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "frontend/projects/list.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {"label": "Projects", "url": None},
            ],
            "filter_form": filter_form,
            "has_active_filters": any(
                filters[key]
                for key in (
                    "query",
                    "status",
                    "priority",
                    "criticality",
                    "starts_on_or_after",
                    "ends_on_or_before",
                )
            ),
            "page_obj": page_obj,
            "project_headers": (
                "Project",
                "Schedule",
                "Estimated hours",
                "Priority",
                "Criticality",
                "Status",
            ),
        },
    )


@read_models_permission_required(
    Project,
    ProjectSkillRequirement,
    Assignment,
    AssignmentSkill,
)
def project_detail(request, project_id):
    try:
        project = get_project_profile(project_id)
    except Project.DoesNotExist as exc:
        raise Http404("Project not found.") from exc

    profile = build_project_profile(project)
    assignment_headers = (
        "Employee",
        "Role",
        "Schedule",
        "Allocation",
        "Status",
        "Requirements covered",
    )
    if request.user.has_perm(
        "core.change_assignment"
    ) or request.user.has_perm("core.delete_assignment"):
        assignment_headers = (*assignment_headers, "Actions")

    requirement_headers = (
        "Skill",
        "Required level",
        "People needed",
        "Estimated effort",
        "Priority",
        "Requirement type",
    )
    if request.user.has_perm(
        "core.change_projectskillrequirement"
    ) or request.user.has_perm("core.delete_projectskillrequirement"):
        requirement_headers = (*requirement_headers, "Actions")
    return render(
        request,
        "frontend/projects/detail.html",
        {
            "assignment_headers": assignment_headers,
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {
                    "label": "Projects",
                    "url": reverse("frontend:project_list"),
                },
                {"label": project.name, "url": None},
            ],
            "profile": profile,
            "requirement_headers": requirement_headers,
        },
    )


def _save_project_form(request, form, *, success_message):
    try:
        with transaction.atomic():
            project = form.save()
    except DatabaseError:
        messages.error(
            request,
            "We could not save this project. No changes were applied. "
            "Please try again.",
        )
        return None

    messages.success(request, success_message(project))
    return project


@write_model_permission_required(Project, "add")
def project_create(request):
    form = ProjectForm(request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            project = _save_project_form(
                request,
                form,
                success_message=lambda saved: (
                    f"{saved} was added to the project directory."
                ),
            )
            if project is not None:
                return redirect("frontend:project_detail", project.project_id)
        else:
            messages.error(
                request,
                "Please correct the highlighted fields before saving the project.",
            )

    return render(
        request,
        "frontend/projects/create.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {
                    "label": "Projects",
                    "url": reverse("frontend:project_list"),
                },
                {"label": "Add project", "url": None},
            ],
            "cancel_url": reverse("frontend:project_list"),
            "form": form,
        },
    )


@write_model_permission_required(Project, "change")
def project_update(request, project_id):
    project = get_object_or_404(Project, project_id=project_id)
    project_name = project.name
    form = ProjectForm(request.POST or None, instance=project)

    if request.method == "POST":
        if form.is_valid():
            saved_project = _save_project_form(
                request,
                form,
                success_message=lambda saved: f"Project {saved} was updated.",
            )
            if saved_project is not None:
                return redirect(
                    "frontend:project_detail",
                    saved_project.project_id,
                )
        else:
            messages.error(
                request,
                "Please correct the highlighted fields before saving changes.",
            )

    return render(
        request,
        "frontend/projects/edit.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {
                    "label": "Projects",
                    "url": reverse("frontend:project_list"),
                },
                {
                    "label": project_name,
                    "url": reverse(
                        "frontend:project_detail",
                        args=[project.project_id],
                    ),
                },
                {"label": "Edit", "url": None},
            ],
            "cancel_url": reverse(
                "frontend:project_detail",
                args=[project.project_id],
            ),
            "form": form,
            "project": project,
            "project_name": project_name,
        },
    )
