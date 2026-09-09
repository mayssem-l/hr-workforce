from core.models import (
    Assignment,
    AssignmentSkill,
    Employee,
    Project,
    ProjectSkillRequirement,
)


def get_project_for_assignment(project_id):
    """Load the parent project used by an assignment workflow."""
    return Project.objects.only(
        "project_id",
        "name",
        "start_date",
        "end_date",
    ).get(project_id=project_id)


def get_project_assignment(project_id, assignment_id):
    """Load one assignment only when it belongs to the route's project."""
    return (
        Assignment.objects.select_related("project", "employee")
        .only(
            "assignment_id",
            "project_id",
            "project__project_id",
            "project__name",
            "project__start_date",
            "project__end_date",
            "employee_id",
            "employee__employee_id",
            "employee__first_name",
            "employee__last_name",
            "employee__department",
            "employee__position",
            "employee__status",
            "start_date",
            "end_date",
            "allocation_percentage",
            "role_on_project",
            "status",
        )
        .get(project_id=project_id, assignment_id=assignment_id)
    )


def get_assignment_employee_choices():
    """Return employees with the stored context needed by form labels."""
    return Employee.objects.only(
        "employee_id",
        "first_name",
        "last_name",
        "department",
        "position",
        "status",
    ).order_by("last_name", "first_name", "employee_id")


def get_assignment_coverage_profile(project_id, assignment_id):
    """Load one assignment and its project requirement coverage context."""
    assignment = get_project_assignment(project_id, assignment_id)
    assignment.coverage_requirements = list(
        ProjectSkillRequirement.objects.filter(project_id=project_id)
        .select_related("skill")
        .only(
            "project_skill_requirement_id",
            "project_id",
            "skill_id",
            "skill__skill_id",
            "skill__name",
            "skill__category",
            "required_level",
            "required_quantity",
            "priority",
            "is_mandatory",
            "estimated_effort_hours",
        )
        .order_by(
            "-is_mandatory",
            "skill__category",
            "skill__name",
            "project_skill_requirement_id",
        )
    )
    assignment.coverage_links = list(
        AssignmentSkill.objects.filter(assignment=assignment)
        .select_related("project_skill_requirement__skill")
        .only(
            "assignment_skill_id",
            "assignment_id",
            "project_skill_requirement_id",
            "project_skill_requirement__project_skill_requirement_id",
            "project_skill_requirement__project_id",
            "project_skill_requirement__required_level",
            "project_skill_requirement__required_quantity",
            "project_skill_requirement__skill_id",
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
    return assignment


def get_assignment_coverage_link(project_id, assignment_id, coverage_id):
    """Load one coverage link only within its routed project and assignment."""
    return (
        AssignmentSkill.objects.select_related(
            "assignment__project",
            "assignment__employee",
            "project_skill_requirement__skill",
        )
        .only(
            "assignment_skill_id",
            "assignment_id",
            "assignment__assignment_id",
            "assignment__project_id",
            "assignment__project__project_id",
            "assignment__project__name",
            "assignment__employee_id",
            "assignment__employee__employee_id",
            "assignment__employee__first_name",
            "assignment__employee__last_name",
            "assignment__employee__department",
            "assignment__employee__position",
            "project_skill_requirement_id",
            "project_skill_requirement__project_skill_requirement_id",
            "project_skill_requirement__project_id",
            "project_skill_requirement__required_level",
            "project_skill_requirement__required_quantity",
            "project_skill_requirement__skill_id",
            "project_skill_requirement__skill__skill_id",
            "project_skill_requirement__skill__name",
            "project_skill_requirement__skill__category",
        )
        .get(
            assignment_skill_id=coverage_id,
            assignment_id=assignment_id,
            assignment__project_id=project_id,
            project_skill_requirement__project_id=project_id,
        )
    )
