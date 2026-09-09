from django.contrib.auth.models import Group, Permission
from django.db import DEFAULT_DB_ALIAS, transaction


HR_ADMINISTRATOR_GROUP = "HR Administrators"
MANAGER_PLANNER_GROUP = "Managers / Planners"
VIEWER_GROUP = "Viewers"

CORE_MODEL_NAMES = (
    "assignment",
    "assignmentskill",
    "attendance",
    "employee",
    "employeeskill",
    "leave",
    "project",
    "projectskillrequirement",
    "skill",
)
PLANNING_MODEL_NAMES = (
    "assignment",
    "assignmentskill",
    "project",
    "projectskillrequirement",
)


def _permission_names(actions, model_names):
    return frozenset(
        f"core.{action}_{model_name}"
        for model_name in model_names
        for action in actions
    )


CORE_VIEW_PERMISSIONS = _permission_names(("view",), CORE_MODEL_NAMES)

ROLE_PERMISSION_MAP = {
    HR_ADMINISTRATOR_GROUP: _permission_names(
        ("add", "change", "delete", "view"),
        CORE_MODEL_NAMES,
    ),
    MANAGER_PLANNER_GROUP: CORE_VIEW_PERMISSIONS
    | _permission_names(("add", "change"), PLANNING_MODEL_NAMES),
    VIEWER_GROUP: CORE_VIEW_PERMISSIONS,
}


def sync_role_permissions(using=DEFAULT_DB_ALIAS):
    """Create the initial groups and make their core permissions match the map."""

    required_permission_names = set().union(*ROLE_PERMISSION_MAP.values())
    permissions = Permission.objects.using(using).filter(
        content_type__app_label="core",
        codename__in={
            permission_name.split(".", 1)[1]
            for permission_name in required_permission_names
        },
    ).select_related("content_type")
    permissions_by_name = {
        f"{permission.content_type.app_label}.{permission.codename}": permission
        for permission in permissions
    }

    missing_permissions = required_permission_names - permissions_by_name.keys()
    if missing_permissions:
        missing_list = ", ".join(sorted(missing_permissions))
        raise RuntimeError(
            "Core permissions must exist before frontend roles are synchronized: "
            f"{missing_list}"
        )

    synchronized_groups = {}
    with transaction.atomic(using=using):
        for group_name, permission_names in ROLE_PERMISSION_MAP.items():
            group, _ = Group.objects.using(using).get_or_create(name=group_name)
            group.permissions.set(
                [permissions_by_name[name] for name in sorted(permission_names)]
            )
            synchronized_groups[group_name] = group

    return synchronized_groups
