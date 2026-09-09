from django.db.models import Count, Prefetch, Q

from core.models import (
    Assignment,
    AssignmentSkill,
    Employee,
    EmployeeSkill,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from frontend.selectors.employees import EMPLOYEE_DIRECTORY_FIELDS
from frontend.selectors.projects import PROJECT_PROFILE_FIELDS
from frontend.selectors.skills import SKILL_DIRECTORY_FIELDS


def get_employee_deletion_target(employee_id):
    """Load an employee and manager-facing deletion context."""
    return (
        Employee.objects.only(*EMPLOYEE_DIRECTORY_FIELDS)
        .annotate(
            assignment_count=Count("assignments", distinct=True),
            leave_count=Count("leaves", distinct=True),
            attendance_count=Count("attendances", distinct=True),
        )
        .prefetch_related(
            Prefetch(
                "employee_skills",
                queryset=(
                    EmployeeSkill.objects.select_related("skill")
                    .only(
                        "employee_skill_id",
                        "employee_id",
                        "skill_id",
                        "skill__skill_id",
                        "skill__name",
                        "skill__category",
                        "level",
                    )
                    .order_by("skill__category", "skill__name", "skill_id")
                ),
                to_attr="deletion_employee_skills",
            )
        )
        .get(employee_id=employee_id)
    )


def get_skill_deletion_target(skill_id):
    """Load a skill and manager-facing deletion context."""
    return (
        Skill.objects.only(*SKILL_DIRECTORY_FIELDS)
        .annotate(
            project_requirement_count=Count(
                "project_requirements",
                distinct=True,
            ),
        )
        .prefetch_related(
            Prefetch(
                "employee_skills",
                queryset=(
                    EmployeeSkill.objects.select_related("employee")
                    .only(
                        "employee_skill_id",
                        "employee_id",
                        "employee__employee_id",
                        "employee__first_name",
                        "employee__last_name",
                        "skill_id",
                        "level",
                    )
                    .order_by(
                        "employee__last_name",
                        "employee__first_name",
                        "employee_id",
                    )
                ),
                to_attr="deletion_employee_skills",
            )
        )
        .get(skill_id=skill_id)
    )


def get_project_deletion_target(project_id):
    """Load a project and every manager-facing deletion consequence."""
    project = Project.objects.only(*PROJECT_PROFILE_FIELDS).get(
        project_id=project_id
    )
    project.deletion_requirements = list(
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
            "required_quantity",
            "is_mandatory",
        )
        .order_by(
            "-is_mandatory",
            "skill__category",
            "skill__name",
            "project_skill_requirement_id",
        )
    )
    project.deletion_assignments = list(
        Assignment.objects.filter(project=project)
        .select_related("employee")
        .only(
            "assignment_id",
            "project_id",
            "employee_id",
            "employee__employee_id",
            "employee__first_name",
            "employee__last_name",
            "role_on_project",
            "status",
        )
        .order_by(
            "employee__last_name",
            "employee__first_name",
            "assignment_id",
        )
    )
    project.deletion_coverage_count = (
        AssignmentSkill.objects.filter(
            Q(assignment__project=project)
            | Q(project_skill_requirement__project=project)
        )
        .distinct()
        .count()
    )
    return project


def get_assignment_deletion_target(project_id, assignment_id):
    """Load one project-scoped assignment and its coverage consequences."""
    assignment = (
        Assignment.objects.filter(project_id=project_id)
        .select_related("project", "employee")
        .only(
            "assignment_id",
            "project_id",
            "project__project_id",
            "project__name",
            "employee_id",
            "employee__employee_id",
            "employee__first_name",
            "employee__last_name",
            "employee__department",
            "employee__position",
            "start_date",
            "end_date",
            "allocation_percentage",
            "role_on_project",
            "status",
        )
        .get(assignment_id=assignment_id)
    )
    assignment.deletion_coverage = list(
        AssignmentSkill.objects.filter(assignment=assignment)
        .select_related("project_skill_requirement__skill")
        .only(
            "assignment_skill_id",
            "assignment_id",
            "project_skill_requirement_id",
            "project_skill_requirement__project_skill_requirement_id",
            "project_skill_requirement__required_level",
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
