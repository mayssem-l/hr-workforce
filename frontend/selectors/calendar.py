from dataclasses import dataclass
from datetime import date

from core.models import Assignment, Employee, Leave, Project


PROJECT_SOURCE = "project"
ASSIGNMENT_SOURCE = "assignment"
APPROVED_LEAVE_SOURCE = "approved_leave"
CALENDAR_SOURCE_ORDER = {
    PROJECT_SOURCE: 0,
    ASSIGNMENT_SOURCE: 1,
    APPROVED_LEAVE_SOURCE: 2,
}
CALENDAR_SOURCE_ACCESS_KEYS = {
    PROJECT_SOURCE: "projects",
    ASSIGNMENT_SOURCE: "assignments",
    APPROVED_LEAVE_SOURCE: "approved_leave",
}


@dataclass(frozen=True)
class CalendarEventRecord:
    """Stable, read-only record contract shared by calendar consumers."""

    record_id: int
    source: str
    title: str
    start_date: date
    end_date: date
    status: str
    status_label: str
    project_id: int | None = None
    project_label: str | None = None
    employee_id: int | None = None
    employee_label: str | None = None
    leave_type: str | None = None
    leave_type_label: str | None = None

    @property
    def event_id(self):
        return f"{self.source}:{self.record_id}"


@dataclass(frozen=True)
class CalendarFilterOptions:
    """Current permitted choices used to validate calendar filters."""

    departments: tuple
    employees: tuple
    projects: tuple


def get_calendar_filter_options():
    """Load employee and project filter choices in two fixed queries."""

    employees = tuple(
        Employee.objects.only(
            "employee_id",
            "first_name",
            "last_name",
            "department",
        ).order_by("last_name", "first_name", "employee_id")
    )
    projects = tuple(
        Project.objects.only("project_id", "name").order_by("name", "project_id")
    )
    return CalendarFilterOptions(
        departments=tuple(
            sorted(
                {
                    employee.department.strip()
                    for employee in employees
                    if employee.department.strip()
                },
                key=str.casefold,
            )
        ),
        employees=tuple(
            (
                str(employee.employee_id),
                f"{employee} — {employee.department}",
            )
            for employee in employees
        ),
        projects=tuple(
            (str(project.project_id), project.name) for project in projects
        ),
    )


def _employee_filter_ids(value):
    """Accept one employee choice or an internal set of employee IDs."""

    if not value:
        return None
    if isinstance(value, str):
        return frozenset({value})
    return frozenset(value)


def _project_events(*, start_date, end_date, filters):
    if filters["department"] or filters["employee"]:
        return ()

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
    if filters["project"]:
        projects = projects.filter(project_id=filters["project"])
    return tuple(
        CalendarEventRecord(
            record_id=project.project_id,
            source=PROJECT_SOURCE,
            title=project.name,
            start_date=project.start_date,
            end_date=project.end_date,
            status=project.status,
            status_label=project.get_status_display(),
            project_id=project.project_id,
            project_label=project.name,
        )
        for project in projects.order_by("start_date", "end_date", "name", "project_id")
    )


def _assignment_events(*, start_date, end_date, filters):
    assignments = (
        Assignment.objects.select_related("project", "employee")
        .only(
            "assignment_id",
            "start_date",
            "end_date",
            "status",
            "project__project_id",
            "project__name",
            "employee__employee_id",
            "employee__first_name",
            "employee__last_name",
        )
        .filter(
            start_date__lte=end_date,
            end_date__gte=start_date,
        )
    )
    if filters["department"]:
        assignments = assignments.filter(
            employee__department=filters["department"]
        )
    employee_ids = _employee_filter_ids(filters["employee"])
    if employee_ids is not None:
        assignments = assignments.filter(employee_id__in=employee_ids)
    if filters["project"]:
        assignments = assignments.filter(project_id=filters["project"])
    assignments = assignments.order_by(
        "start_date",
        "end_date",
        "project__name",
        "employee__last_name",
        "employee__first_name",
        "assignment_id",
    )
    return tuple(
        CalendarEventRecord(
            record_id=assignment.assignment_id,
            source=ASSIGNMENT_SOURCE,
            title=f"{assignment.employee} — {assignment.project.name}",
            start_date=assignment.start_date,
            end_date=assignment.end_date,
            status=assignment.status,
            status_label=assignment.get_status_display(),
            project_id=assignment.project_id,
            project_label=assignment.project.name,
            employee_id=assignment.employee_id,
            employee_label=str(assignment.employee),
        )
        for assignment in assignments
    )


def _approved_leave_events(*, start_date, end_date, filters):
    if filters["project"]:
        return ()

    leaves = (
        Leave.objects.select_related("employee")
        .only(
            "leave_id",
            "start_date",
            "end_date",
            "type",
            "status",
            "employee__employee_id",
            "employee__first_name",
            "employee__last_name",
        )
        .filter(
            status=Leave.Status.APPROVED,
            start_date__lte=end_date,
            end_date__gte=start_date,
        )
    )
    if filters["department"]:
        leaves = leaves.filter(employee__department=filters["department"])
    employee_ids = _employee_filter_ids(filters["employee"])
    if employee_ids is not None:
        leaves = leaves.filter(employee_id__in=employee_ids)
    leaves = leaves.order_by(
        "start_date",
        "end_date",
        "employee__last_name",
        "employee__first_name",
        "leave_id",
    )
    return tuple(
        CalendarEventRecord(
            record_id=leave.leave_id,
            source=APPROVED_LEAVE_SOURCE,
            title=f"{leave.employee} — {leave.get_type_display()} leave",
            start_date=leave.start_date,
            end_date=leave.end_date,
            status=leave.status,
            status_label=leave.get_status_display(),
            employee_id=leave.employee_id,
            employee_label=str(leave.employee),
            leave_type=leave.type,
            leave_type_label=leave.get_type_display(),
        )
        for leave in leaves
    )


def get_calendar_events(*, start_date, end_date, source_access, filters=None):
    """Load permitted records overlapping one inclusive period in fixed queries."""

    filters = {
        "sources": tuple(CALENDAR_SOURCE_ACCESS_KEYS),
        "department": "",
        "employee": "",
        "project": "",
        **(filters or {}),
    }
    selected_sources = frozenset(filters["sources"])
    events = []
    if (
        PROJECT_SOURCE in selected_sources
        and source_access.get(CALENDAR_SOURCE_ACCESS_KEYS[PROJECT_SOURCE], False)
    ):
        events.extend(
            _project_events(
                start_date=start_date,
                end_date=end_date,
                filters=filters,
            )
        )
    if (
        ASSIGNMENT_SOURCE in selected_sources
        and source_access.get(CALENDAR_SOURCE_ACCESS_KEYS[ASSIGNMENT_SOURCE], False)
    ):
        events.extend(
            _assignment_events(
                start_date=start_date,
                end_date=end_date,
                filters=filters,
            )
        )
    if source_access.get(
        CALENDAR_SOURCE_ACCESS_KEYS[APPROVED_LEAVE_SOURCE],
        False,
    ) and APPROVED_LEAVE_SOURCE in selected_sources:
        events.extend(
            _approved_leave_events(
                start_date=start_date,
                end_date=end_date,
                filters=filters,
            )
        )

    return tuple(
        sorted(
            events,
            key=lambda event: (
                event.start_date,
                event.end_date,
                CALENDAR_SOURCE_ORDER[event.source],
                event.title.casefold(),
                event.record_id,
            ),
        )
    )
