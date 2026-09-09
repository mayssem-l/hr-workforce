from django.db.models import Count

from core.models import Skill


SKILL_PAGE_SIZE = 24
SKILL_DIRECTORY_FIELDS = ("skill_id", "name", "category")


def _with_employee_count(skills):
    return skills.annotate(
        employee_count=Count("employee_skills__employee", distinct=True)
    )


def get_skill_categories():
    """Return stable, nonempty categories for the directory filter."""
    return (
        Skill.objects.exclude(category="")
        .order_by("category")
        .values_list("category", flat=True)
        .distinct()
    )


def get_skill_directory(*, category=""):
    """Return directory rows with one bulk employee-profile count."""
    skills = _with_employee_count(
        Skill.objects.only(*SKILL_DIRECTORY_FIELDS)
    )
    normalized_category = str(category or "").strip()
    if normalized_category:
        skills = skills.filter(category=normalized_category)
    return skills.order_by("category", "name", "skill_id")


def get_skill_detail(skill_id):
    """Load one skill and its read-only usage count in one query."""
    return _with_employee_count(
        Skill.objects.only(*SKILL_DIRECTORY_FIELDS)
    ).get(skill_id=skill_id)
