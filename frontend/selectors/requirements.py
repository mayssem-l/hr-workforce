from core.models import Project, ProjectSkillRequirement


def get_project_for_requirement(project_id):
    """Load the parent project used by a requirement workflow."""
    return Project.objects.only("project_id", "name").get(project_id=project_id)


def get_project_requirement(project_id, requirement_id):
    """Load one requirement only when it belongs to the route's project."""
    return (
        ProjectSkillRequirement.objects.select_related("project", "skill")
        .only(
            "project_skill_requirement_id",
            "project_id",
            "project__project_id",
            "project__name",
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
        .get(
            project_id=project_id,
            project_skill_requirement_id=requirement_id,
        )
    )
