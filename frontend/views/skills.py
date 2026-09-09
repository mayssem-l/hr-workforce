from django.contrib import messages
from django.core.paginator import Paginator
from django.db import DatabaseError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.models import Skill
from frontend.forms.skills import SkillDirectoryFilterForm, SkillForm
from frontend.permissions import (
    read_model_permission_required,
    write_model_permission_required,
)
from frontend.presenters.skills import group_skills_by_category
from frontend.selectors.skills import (
    SKILL_PAGE_SIZE,
    get_skill_categories,
    get_skill_detail,
    get_skill_directory,
)


@read_model_permission_required(Skill)
def skill_list(request):
    categories = list(get_skill_categories())
    filter_form = SkillDirectoryFilterForm(
        request.GET,
        categories=categories,
    )
    filters = {"category": ""}
    if filter_form.is_valid():
        filters.update(filter_form.cleaned_data)

    skills = get_skill_directory(**filters)
    page_obj = Paginator(skills, SKILL_PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    skill_groups = group_skills_by_category(page_obj.object_list)

    return render(
        request,
        "frontend/skills/list.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {
                    "label": "Workforce",
                    "url": reverse("frontend:employee_list"),
                },
                {"label": "Skills", "url": None},
            ],
            "filter_form": filter_form,
            "has_active_filters": bool(filters["category"]),
            "page_obj": page_obj,
            "skill_groups": skill_groups,
            "skill_headers": ("Skill", "Employee profiles"),
        },
    )


@read_model_permission_required(Skill)
def skill_detail(request, skill_id):
    try:
        skill = get_skill_detail(skill_id)
    except Skill.DoesNotExist as exc:
        raise Http404("Skill not found.") from exc

    return render(
        request,
        "frontend/skills/detail.html",
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
                {"label": skill.name, "url": None},
            ],
            "skill": skill,
        },
    )


def _save_skill_form(request, form, *, success_message):
    try:
        with transaction.atomic():
            skill = form.save()
    except DatabaseError:
        messages.error(
            request,
            "We could not save this skill. No changes were applied. "
            "Please try again.",
        )
        return None

    messages.success(request, success_message(skill))
    return skill


@write_model_permission_required(Skill, "add")
def skill_create(request):
    form = SkillForm(request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            skill = _save_skill_form(
                request,
                form,
                success_message=lambda saved: (
                    f"{saved} was added to the skill directory."
                ),
            )
            if skill is not None:
                return redirect("frontend:skill_detail", skill.skill_id)
        else:
            messages.error(
                request,
                "Please correct the highlighted fields before saving the skill.",
            )

    return render(
        request,
        "frontend/skills/create.html",
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
                {"label": "Add skill", "url": None},
            ],
            "cancel_url": reverse("frontend:skill_list"),
            "form": form,
        },
    )


@write_model_permission_required(Skill, "change")
def skill_update(request, skill_id):
    skill = get_object_or_404(Skill, skill_id=skill_id)
    skill_name = skill.name
    form = SkillForm(request.POST or None, instance=skill)

    if request.method == "POST":
        if form.is_valid():
            saved_skill = _save_skill_form(
                request,
                form,
                success_message=lambda saved: f"Skill {saved} was updated.",
            )
            if saved_skill is not None:
                return redirect("frontend:skill_detail", saved_skill.skill_id)
        else:
            messages.error(
                request,
                "Please correct the highlighted fields before saving changes.",
            )

    return render(
        request,
        "frontend/skills/edit.html",
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
                {
                    "label": skill_name,
                    "url": reverse(
                        "frontend:skill_detail",
                        args=[skill.skill_id],
                    ),
                },
                {"label": "Edit", "url": None},
            ],
            "cancel_url": reverse(
                "frontend:skill_detail",
                args=[skill.skill_id],
            ),
            "form": form,
            "skill": skill,
            "skill_name": skill_name,
        },
    )
