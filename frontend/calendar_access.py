from core.models import (
    Assignment,
    AssignmentSkill,
    Employee,
    Project,
    ProjectSkillRequirement,
)


CALENDAR_WORKSPACE_REQUIRED_MODELS = (Project, Assignment, Employee)
CALENDAR_SOURCE_PERMISSION_NAMES = {
    "projects": ("core.view_project",),
    "assignments": (
        "core.view_project",
        "core.view_assignment",
        "core.view_employee",
    ),
    "approved_leave": ("core.view_employee", "core.view_leave"),
}
CALENDAR_LINK_PERMISSION_NAMES = {
    "project_detail": tuple(
        f"{model._meta.app_label}.view_{model._meta.model_name}"
        for model in (
            Project,
            ProjectSkillRequirement,
            Assignment,
            AssignmentSkill,
        )
    ),
    "employee_detail": ("core.view_employee",),
    "leave_list": ("core.view_leave",),
}


def get_calendar_source_access(user):
    """Return source-level read access without selecting any calendar records."""

    return {
        source: user.has_perms(permission_names)
        for source, permission_names in CALENDAR_SOURCE_PERMISSION_NAMES.items()
    }


def get_calendar_link_access(user):
    """Return access to established read workflows used by event links."""

    return {
        target: user.has_perms(permission_names)
        for target, permission_names in CALENDAR_LINK_PERMISSION_NAMES.items()
    }
