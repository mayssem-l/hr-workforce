from django.contrib import messages
from django.db import DatabaseError, transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from core.models import Employee, EmployeeSkill
from frontend.forms.proficiencies import (
    EmployeeSkillCreateForm,
    EmployeeSkillUpdateForm,
)
from frontend.permissions import write_model_permission_required
from frontend.selectors.employees import (
    get_employee_for_proficiency,
    get_employee_skill,
)


def _employee_or_404(employee_id):
    try:
        return get_employee_for_proficiency(employee_id)
    except Employee.DoesNotExist as exc:
        raise Http404("Employee not found.") from exc


def _employee_skill_or_404(employee_id, employee_skill_id):
    try:
        return get_employee_skill(employee_id, employee_skill_id)
    except EmployeeSkill.DoesNotExist as exc:
        raise Http404("Employee proficiency not found.") from exc


def _proficiency_breadcrumbs(employee, current_label):
    employee_url = reverse(
        "frontend:employee_detail",
        args=[employee.employee_id],
    )
    return [
        {"label": "Dashboard", "url": reverse("frontend:landing")},
        {
            "label": "Workforce",
            "url": reverse("frontend:employee_list"),
        },
        {"label": str(employee), "url": employee_url},
        {"label": current_label, "url": None},
    ]


def _save_proficiency_form(request, form, *, success_message):
    try:
        with transaction.atomic():
            employee_skill = form.save()
    except DatabaseError:
        messages.error(
            request,
            "We could not save this proficiency. No changes were applied. "
            "Please try again.",
        )
        return None

    messages.success(request, success_message(employee_skill))
    return employee_skill


@write_model_permission_required(EmployeeSkill, "add")
def employee_skill_create(request, employee_id):
    employee = _employee_or_404(employee_id)
    form = EmployeeSkillCreateForm(
        request.POST or None,
        employee=employee,
    )

    if request.method == "POST":
        if form.is_valid():
            employee_skill = _save_proficiency_form(
                request,
                form,
                success_message=lambda saved: (
                    f"{saved.skill} was added to {saved.employee}'s skill profile."
                ),
            )
            if employee_skill is not None:
                return redirect(
                    "frontend:employee_detail",
                    employee.employee_id,
                )
        else:
            messages.error(
                request,
                "Please correct the highlighted fields before adding the skill.",
            )

    return render(
        request,
        "frontend/employees/proficiencies/create.html",
        {
            "breadcrumbs": _proficiency_breadcrumbs(employee, "Add skill"),
            "cancel_url": reverse(
                "frontend:employee_detail",
                args=[employee.employee_id],
            ),
            "employee": employee,
            "employee_name": str(employee),
            "form": form,
        },
    )


@write_model_permission_required(EmployeeSkill, "change")
def employee_skill_update(request, employee_id, employee_skill_id):
    employee_skill = _employee_skill_or_404(employee_id, employee_skill_id)
    employee = employee_skill.employee
    form = EmployeeSkillUpdateForm(
        request.POST or None,
        instance=employee_skill,
    )

    if request.method == "POST":
        if form.is_valid():
            saved_employee_skill = _save_proficiency_form(
                request,
                form,
                success_message=lambda saved: (
                    f"{saved.skill} proficiency for {saved.employee} was updated."
                ),
            )
            if saved_employee_skill is not None:
                return redirect(
                    "frontend:employee_detail",
                    employee.employee_id,
                )
        else:
            messages.error(
                request,
                "Please correct the highlighted fields before saving changes.",
            )

    return render(
        request,
        "frontend/employees/proficiencies/edit.html",
        {
            "breadcrumbs": _proficiency_breadcrumbs(
                employee,
                f"Edit {employee_skill.skill}",
            ),
            "cancel_url": reverse(
                "frontend:employee_detail",
                args=[employee.employee_id],
            ),
            "employee": employee,
            "employee_name": str(employee),
            "employee_skill": employee_skill,
            "form": form,
        },
    )


@write_model_permission_required(EmployeeSkill, "delete")
def employee_skill_remove(request, employee_id, employee_skill_id):
    employee_skill = _employee_skill_or_404(employee_id, employee_skill_id)
    employee = employee_skill.employee
    employee_url = reverse(
        "frontend:employee_detail",
        args=[employee.employee_id],
    )
    remove_url = reverse(
        "frontend:employee_skill_remove",
        args=[employee.employee_id, employee_skill.employee_skill_id],
    )

    if request.method == "POST":
        skill_name = str(employee_skill.skill)
        employee_name = str(employee)
        try:
            with transaction.atomic():
                employee_skill.delete()
        except DatabaseError:
            messages.error(
                request,
                "We could not remove this proficiency. No changes were applied. "
                "Please try again.",
            )
        else:
            messages.success(
                request,
                f"{skill_name} was removed from {employee_name}'s skill profile.",
            )
            return redirect(employee_url)

    return render(
        request,
        "frontend/employees/proficiencies/confirm_remove.html",
        {
            "breadcrumbs": _proficiency_breadcrumbs(
                employee,
                f"Remove {employee_skill.skill}",
            ),
            "cancel_url": employee_url,
            "confirmation_message": (
                f"Remove {employee_skill.skill} from {employee}'s profile? "
                "The skill definition and employee record will remain unchanged."
            ),
            "employee": employee,
            "employee_name": str(employee),
            "employee_skill": employee_skill,
            "remove_url": remove_url,
        },
    )
