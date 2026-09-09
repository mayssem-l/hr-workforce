from django.contrib import messages
from django.db import DatabaseError, transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.models import Assignment, Employee, Project, Skill
from frontend.permissions import write_model_permission_required
from frontend.presenters.deletions import (
    build_assignment_deletion_impact,
    build_employee_deletion_impact,
    build_project_deletion_impact,
    build_skill_deletion_impact,
)
from frontend.selectors.deletions import (
    get_assignment_deletion_target,
    get_employee_deletion_target,
    get_project_deletion_target,
    get_skill_deletion_target,
)


@write_model_permission_required(Employee, "delete")
@require_http_methods(["GET", "POST"])
def employee_delete(request, employee_id):
    try:
        employee = get_employee_deletion_target(employee_id)
    except Employee.DoesNotExist as exc:
        if request.method == "POST":
            messages.info(
                request,
                "This employee no longer exists. No deletion was needed.",
            )
            return redirect("frontend:employee_list")
        raise Http404("Employee not found.") from exc

    employee_name = str(employee)
    employee_url = reverse(
        "frontend:employee_detail",
        args=[employee.employee_id],
    )
    delete_url = reverse(
        "frontend:employee_delete",
        args=[employee.employee_id],
    )
    impact = build_employee_deletion_impact(employee)

    if request.method == "POST":
        try:
            with transaction.atomic():
                employee.delete()
        except DatabaseError:
            messages.error(
                request,
                "We could not delete this employee. Nothing was deleted. "
                "Please try again.",
            )
        else:
            success_message = f"{employee_name} was deleted."
            if impact["has_related_information"]:
                success_message = (
                    f"{employee_name} and their related workforce information "
                    "were deleted."
                )
            messages.success(request, success_message)
            return redirect("frontend:employee_list")

    return render(
        request,
        "frontend/employees/confirm_delete.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {
                    "label": "Workforce",
                    "url": reverse("frontend:employee_list"),
                },
                {"label": employee_name, "url": employee_url},
                {"label": "Delete", "url": None},
            ],
            "cancel_url": employee_url,
            "confirmation_message": (
                f"Delete {employee_name}? This action cannot be undone."
            ),
            "delete_url": delete_url,
            "impact": impact,
            "target_name": employee_name,
        },
    )


@write_model_permission_required(Skill, "delete")
@require_http_methods(["GET", "POST"])
def skill_delete(request, skill_id):
    try:
        skill = get_skill_deletion_target(skill_id)
    except Skill.DoesNotExist as exc:
        if request.method == "POST":
            messages.info(
                request,
                "This skill no longer exists. No deletion was needed.",
            )
            return redirect("frontend:skill_list")
        raise Http404("Skill not found.") from exc

    skill_name = str(skill)
    skill_url = reverse(
        "frontend:skill_detail",
        args=[skill.skill_id],
    )
    delete_url = reverse(
        "frontend:skill_delete",
        args=[skill.skill_id],
    )
    impact = build_skill_deletion_impact(skill)

    if request.method == "POST":
        try:
            with transaction.atomic():
                skill.delete()
        except DatabaseError:
            messages.error(
                request,
                "We could not delete this skill. Nothing was deleted. "
                "Please try again.",
            )
        else:
            success_message = f"{skill_name} was deleted from the skill directory."
            if impact["has_related_information"]:
                success_message = (
                    f"{skill_name} was deleted from the skill directory and "
                    "removed from the employee profiles and project requirements "
                    "that used it."
                )
            messages.success(request, success_message)
            return redirect("frontend:skill_list")

    return render(
        request,
        "frontend/skills/confirm_delete.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {
                    "label": "Workforce",
                    "url": reverse("frontend:employee_list"),
                },
                {
                    "label": "Skills",
                    "url": reverse("frontend:skill_list"),
                },
                {"label": skill_name, "url": skill_url},
                {"label": "Delete", "url": None},
            ],
            "cancel_url": skill_url,
            "confirmation_message": (
                f"Delete {skill_name}? This action cannot be undone."
            ),
            "delete_url": delete_url,
            "impact": impact,
            "target_name": skill_name,
        },
    )


@write_model_permission_required(Project, "delete")
@require_http_methods(["GET", "POST"])
def project_delete(request, project_id):
    try:
        project = get_project_deletion_target(project_id)
    except Project.DoesNotExist as exc:
        if request.method == "POST":
            messages.info(
                request,
                "This project no longer exists. No deletion was needed.",
            )
            return redirect("frontend:project_list")
        raise Http404("Project not found.") from exc

    project_name = str(project)
    project_url = reverse(
        "frontend:project_detail",
        args=[project.project_id],
    )
    delete_url = reverse(
        "frontend:project_delete",
        args=[project.project_id],
    )
    impact = build_project_deletion_impact(project)

    if request.method == "POST":
        try:
            with transaction.atomic():
                project.delete()
        except DatabaseError:
            messages.error(
                request,
                "We could not delete this project. Nothing was deleted. "
                "Please try again.",
            )
        else:
            success_message = f"{project_name} was deleted."
            if impact["has_related_information"]:
                success_message = (
                    f"{project_name} and its project planning information "
                    "were deleted."
                )
            messages.success(request, success_message)
            return redirect("frontend:project_list")

    return render(
        request,
        "frontend/projects/confirm_delete.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {
                    "label": "Projects",
                    "url": reverse("frontend:project_list"),
                },
                {"label": project_name, "url": project_url},
                {"label": "Delete", "url": None},
            ],
            "cancel_url": project_url,
            "confirmation_message": (
                f"Delete {project_name}? This action cannot be undone."
            ),
            "delete_url": delete_url,
            "impact": impact,
            "project": project,
            "target_name": project_name,
        },
    )


@write_model_permission_required(Assignment, "delete")
@require_http_methods(["GET", "POST"])
def assignment_delete(request, project_id, assignment_id):
    try:
        assignment = get_assignment_deletion_target(project_id, assignment_id)
    except Assignment.DoesNotExist as exc:
        if request.method == "POST":
            if Project.objects.filter(project_id=project_id).exists():
                messages.info(
                    request,
                    "This assignment no longer exists on this project. No "
                    "deletion was needed.",
                )
                return redirect("frontend:project_detail", project_id)
            messages.info(
                request,
                "This project and assignment no longer exist. No deletion was "
                "needed.",
            )
            return redirect("frontend:project_list")
        raise Http404("Project assignment not found.") from exc

    project = assignment.project
    employee_name = str(assignment.employee)
    project_url = reverse(
        "frontend:project_detail",
        args=[project.project_id],
    )
    delete_url = reverse(
        "frontend:project_assignment_delete",
        args=[project.project_id, assignment.assignment_id],
    )
    impact = build_assignment_deletion_impact(assignment)

    if request.method == "POST":
        try:
            with transaction.atomic():
                assignment.delete()
        except DatabaseError:
            messages.error(
                request,
                "We could not delete this assignment. Nothing was deleted. "
                "Please try again.",
            )
        else:
            success_message = (
                f"The assignment for {employee_name} on {project.name} was deleted."
            )
            if impact["has_related_information"]:
                success_message = (
                    f"The assignment for {employee_name} on {project.name} and "
                    "its requirement coverage were deleted."
                )
            messages.success(request, success_message)
            return redirect(project_url)

    return render(
        request,
        "frontend/projects/assignments/confirm_delete.html",
        {
            "assignment": assignment,
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {
                    "label": "Projects",
                    "url": reverse("frontend:project_list"),
                },
                {"label": project.name, "url": project_url},
                {"label": f"Delete {employee_name} assignment", "url": None},
            ],
            "cancel_url": project_url,
            "confirmation_message": (
                f"Delete {employee_name}'s assignment on {project.name}? This "
                "action cannot be undone."
            ),
            "delete_url": delete_url,
            "impact": impact,
            "project": project,
            "target_name": employee_name,
        },
    )
