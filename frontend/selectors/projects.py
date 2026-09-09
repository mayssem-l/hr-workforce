from django.db.models import Prefetch, Q

from core.models import (
    Assignment,
    AssignmentSkill,
    Project,
    ProjectSkillRequirement,
)


DEFAULT_PROJECT_SORT = "name"
PROJECT_PAGE_SIZE = 20

PROJECT_SORT_OPTIONS = {
    "name": ("name", "project_id"),
    "name_desc": ("-name", "project_id"),
    "start_date_desc": ("-start_date", "name", "project_id"),
    "start_date_asc": ("start_date", "name", "project_id"),
    "end_date_asc": ("end_date", "name", "project_id"),
    "estimated_hours_desc": ("-estimated_hours", "name", "project_id"),
    "estimated_hours_asc": ("estimated_hours", "name", "project_id"),
}

PROJECT_SORT_CHOICES = (
    ("name", "Project name: A to Z"),
    ("name_desc", "Project name: Z to A"),
    ("start_date_desc", "Start date: newest first"),
    ("start_date_asc", "Start date: oldest first"),
    ("end_date_asc", "End date: soonest first"),
    ("estimated_hours_desc", "Estimated hours: highest first"),
    ("estimated_hours_asc", "Estimated hours: lowest first"),
)

PROJECT_DIRECTORY_FIELDS = (
    "project_id",
    "name",
    "start_date",
    "end_date",
    "estimated_hours",
    "status",
    "priority",
    "criticality",
)

PROJECT_PROFILE_FIELDS = (*PROJECT_DIRECTORY_FIELDS, "description")


def get_project_directory(
    *,
    query="",
    status="",
    priority="",
    criticality="",
    starts_on_or_after=None,
    ends_on_or_before=None,
    sort="",
):
    """Return a filtered project directory without related-record queries."""
    projects = Project.objects.only(*PROJECT_DIRECTORY_FIELDS)

    for term in str(query or "").strip().split():
        projects = projects.filter(Q(name__icontains=term))

    valid_statuses = {value for value, _label in Project.Status.choices}
    if status in valid_statuses:
        projects = projects.filter(status=status)

    valid_priorities = {value for value, _label in Project.Priority.choices}
    if priority in valid_priorities:
        projects = projects.filter(priority=priority)

    valid_criticalities = {
        value for value, _label in Project.Criticality.choices
    }
    if criticality in valid_criticalities:
        projects = projects.filter(criticality=criticality)

    if starts_on_or_after:
        projects = projects.filter(start_date__gte=starts_on_or_after)

    if ends_on_or_before:
        projects = projects.filter(end_date__lte=ends_on_or_before)

    ordering = PROJECT_SORT_OPTIONS.get(
        sort,
        PROJECT_SORT_OPTIONS[DEFAULT_PROJECT_SORT],
    )
    return projects.order_by(*ordering)


def get_project_profile(project_id):
    """Load one project and its planning context in four fixed queries."""
    project = Project.objects.only(*PROJECT_PROFILE_FIELDS).get(
        project_id=project_id
    )

    project.profile_requirements = list(
        ProjectSkillRequirement.objects.filter(project=project)
        .select_related("skill")
        .only(
            "project_skill_requirement_id",
            "project_id",
            "skill_id",
            "skill__skill_id",
            "skill__name",
            "skill__category",
            "required_level",
            "priority",
            "is_mandatory",
            "required_quantity",
            "estimated_effort_hours",
        )
        .order_by(
            "-is_mandatory",
            "skill__category",
            "skill__name",
            "project_skill_requirement_id",
        )
    )

    coverage_queryset = (
        AssignmentSkill.objects.select_related(
            "project_skill_requirement__skill"
        )
        .only(
            "assignment_skill_id",
            "assignment_id",
            "project_skill_requirement_id",
            "project_skill_requirement__project_skill_requirement_id",
            "project_skill_requirement__skill_id",
            "project_skill_requirement__required_level",
            "project_skill_requirement__skill__skill_id",
            "project_skill_requirement__skill__name",
            "project_skill_requirement__skill__category",
        )
        .order_by(
            "project_skill_requirement__skill__category",
            "project_skill_requirement__skill__name",
            "assignment_skill_id",
        )
    )
    project.profile_assignments = list(
        Assignment.objects.filter(project=project)
        .select_related("employee")
        .only(
            "assignment_id",
            "employee_id",
            "employee__employee_id",
            "employee__first_name",
            "employee__last_name",
            "employee__department",
            "employee__position",
            "project_id",
            "start_date",
            "end_date",
            "allocation_percentage",
            "role_on_project",
            "status",
        )
        .prefetch_related(
            Prefetch(
                "covered_skill_requirements",
                queryset=coverage_queryset,
                to_attr="profile_coverage",
            )
        )
        .order_by(
            "start_date",
            "end_date",
            "employee__last_name",
            "employee__first_name",
            "assignment_id",
        )
    )
    return project
