from django.db.models import Prefetch

from core.models import Employee, EmployeeSkill


def get_candidate_exclusion_workforce():
    """Load the current workforce and skill evidence in two fixed queries."""

    employee_skills = EmployeeSkill.objects.only(
        "employee_skill_id",
        "employee_id",
        "skill_id",
        "level",
    )
    return Employee.objects.prefetch_related(
        Prefetch(
            "employee_skills",
            queryset=employee_skills,
            to_attr="planning_skills",
        )
    ).order_by("last_name", "first_name", "employee_id")
