from dataclasses import dataclass

from django.db.models import Prefetch

from core.models import Assignment, Employee, Leave, Project


@dataclass(frozen=True)
class DashboardSnapshot:
    """Stored records needed to compose the filtered KPI summary."""

    employees: tuple
    active_project_count: int
    projects: tuple = ()


def get_dashboard_snapshot(*, filters):
    """Load filtered workforce records and period projects in fixed queries."""

    start_date = filters["start_date"]
    end_date = filters["end_date"]

    assignments = (
        Assignment.objects.filter(
            start_date__lte=end_date,
            end_date__gte=start_date,
        )
        .only(
            "assignment_id",
            "employee_id",
            "project_id",
            "start_date",
            "end_date",
            "allocation_percentage",
            "status",
        )
        .order_by("start_date", "end_date", "assignment_id")
    )
    approved_leaves = (
        Leave.objects.filter(
            status=Leave.Status.APPROVED,
            start_date__lte=end_date,
            end_date__gte=start_date,
        )
        .only(
            "leave_id",
            "employee_id",
            "start_date",
            "end_date",
            "type",
            "status",
        )
        .order_by("start_date", "end_date", "leave_id")
    )

    employees = Employee.objects.only(
        "employee_id",
        "first_name",
        "last_name",
        "department",
        "capacity_hours_week",
        "status",
    )
    if filters["department"]:
        employees = employees.filter(department=filters["department"])
    if filters["employee_status"]:
        employees = employees.filter(status=filters["employee_status"])

    employees = tuple(
        employees.prefetch_related(
            Prefetch(
                "assignments",
                queryset=assignments,
                to_attr="dashboard_assignments",
            ),
            Prefetch(
                "leaves",
                queryset=approved_leaves,
                to_attr="dashboard_approved_leaves",
            ),
        ).order_by("employee_id")
    )

    projects = Project.objects.only(
        "project_id",
        "name",
        "start_date",
        "end_date",
        "status",
    ).filter(
        start_date__lte=end_date,
        end_date__gte=start_date,
    )
    if filters["project_status"]:
        projects = projects.filter(status=filters["project_status"])
    projects = tuple(projects.order_by("start_date", "end_date", "name", "project_id"))

    return DashboardSnapshot(
        employees=employees,
        active_project_count=len(projects),
        projects=projects,
    )
