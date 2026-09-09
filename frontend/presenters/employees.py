from core.services.effective_availability import calculate_daily_available_hours
from core.services.workload import (
    calculate_available_hours,
    calculate_current_workload,
)


def build_employee_profile(employee, *, on_date):
    """Compose service-owned workforce values for the employee detail page."""
    return {
        "employee": employee,
        "full_name": str(employee),
        "position_summary": f"{employee.position} in {employee.department}",
        "as_of": on_date,
        "weekly_capacity_hours": employee.capacity_hours_week,
        "current_workload_percentage": calculate_current_workload(
            employee,
            on_date,
        ),
        "available_weekly_hours": calculate_available_hours(
            employee,
            on_date,
        ),
        "available_today_hours": calculate_daily_available_hours(
            employee,
            on_date,
        ),
        "upcoming_leaves": employee.profile_upcoming_leaves,
        "assignments": employee.profile_assignments,
        "skills": employee.profile_skills,
    }
