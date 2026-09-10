from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode

from core.models import Attendance, Employee
from core.services.attendance import (
    calculate_absenteeism_rate,
    calculate_late_rate,
    get_attendance_records,
    get_attendance_summary,
)
from core.services.availability import get_approved_leaves, get_working_days
from core.services.effective_availability import calculate_daily_available_hours
from core.services.effective_availability import calculate_daily_capacity_hours
from core.services.workload import (
    calculate_available_hours,
    calculate_current_workload,
    calculate_daily_allocated_hours,
    get_current_assignments,
)


ATTENDANCE_STATUS_ROWS = (
    (Attendance.Status.PRESENT, "present_days", "Recorded as present"),
    (Attendance.Status.ABSENT, "absent_days", "Recorded as absent"),
    (Attendance.Status.LATE, "late_days", "Recorded as late"),
    (Attendance.Status.REMOTE, "remote_days", "Recorded as remote"),
    (Attendance.Status.HALF_DAY, "half_days", "Recorded as a half day"),
)


def build_employee_profile(employee, *, on_date):
    """Compose service-owned workforce values for the employee detail page."""

    assignment_records = getattr(
        employee,
        "profile_calculation_assignments",
        None,
    )
    leave_records = getattr(
        employee,
        "profile_calculation_leaves",
        None,
    )
    return {
        "employee": employee,
        "full_name": str(employee),
        "position_summary": f"{employee.position} in {employee.department}",
        "as_of": on_date,
        "weekly_capacity_hours": employee.capacity_hours_week,
        "current_workload_percentage": calculate_current_workload(
            employee,
            on_date,
            assignment_records=assignment_records,
        ),
        "available_weekly_hours": calculate_available_hours(
            employee,
            on_date,
            assignment_records=assignment_records,
        ),
        "available_today_hours": calculate_daily_available_hours(
            employee,
            on_date,
            assignment_records=assignment_records,
            leave_records=leave_records,
        ),
        "upcoming_leaves": employee.profile_upcoming_leaves,
        "assignments": employee.profile_assignments,
        "skills": employee.profile_skills,
    }


def build_employee_timeline(employee, *, start_date, end_date):
    """Build daily evidence exclusively from shared workforce services."""

    assignment_records = employee.profile_timeline_assignments
    leave_records = employee.profile_timeline_leaves
    working_days = frozenset(get_working_days(start_date, end_date))
    rows = []
    current_date = start_date

    while current_date <= end_date:
        assignments = get_current_assignments(
            employee,
            current_date,
            assignment_records=assignment_records,
        )
        approved_leaves = get_approved_leaves(
            employee,
            current_date,
            current_date,
            leave_records=leave_records,
        )
        capacity_hours = calculate_daily_capacity_hours(employee, current_date)
        workload_percentage = calculate_current_workload(
            employee,
            current_date,
            assignment_records=assignment_records,
        )
        allocated_hours = calculate_daily_allocated_hours(
            employee,
            current_date,
            assignment_records=assignment_records,
        )
        available_hours = calculate_daily_available_hours(
            employee,
            current_date,
            assignment_records=assignment_records,
            leave_records=leave_records,
        )

        is_working_day = current_date in working_days
        if not is_working_day:
            state_key = "weekend"
            state_label = "Weekend"
        elif employee.status == Employee.Status.INACTIVE:
            state_key = "inactive"
            state_label = "Inactive employee"
        elif approved_leaves:
            state_key = "leave"
            state_label = "Approved leave"
        elif capacity_hours <= 0:
            state_key = "unconfigured"
            state_label = "No stored capacity"
        elif workload_percentage > 100:
            state_key = "over_capacity"
            state_label = "Over capacity"
        elif workload_percentage == 100:
            state_key = "fully_scheduled"
            state_label = "Fully scheduled"
        else:
            state_key = "available"
            state_label = "Availability remaining"

        rows.append(
            {
                "date": current_date,
                "is_working_day": is_working_day,
                "state_key": state_key,
                "state_label": state_label,
                "capacity_hours": capacity_hours,
                "workload_percentage": workload_percentage,
                "allocated_hours": allocated_hours,
                "available_hours": available_hours,
                "assignments": tuple(assignments),
                "approved_leaves": tuple(approved_leaves),
            }
        )
        current_date += timedelta(days=1)

    contributing_assignments = {
        assignment.assignment_id
        for row in rows
        for assignment in row["assignments"]
    }
    approved_leave_records = {
        leave.leave_id
        for row in rows
        for leave in row["approved_leaves"]
    }
    return {
        "rows": tuple(rows),
        "working_day_count": len(working_days),
        "has_assignments": bool(contributing_assignments),
        "has_approved_leave": bool(approved_leave_records),
        "has_unconfigured_capacity": employee.capacity_hours_week <= 0,
    }


def _attendance_share(count, total):
    if not total:
        return Decimal("0.0")
    return (
        Decimal(count) / Decimal(total) * Decimal("100")
    ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _attendance_query(employee, start_date, end_date, *, status=""):
    values = {
        "employee": str(employee.employee_id),
        "status": status,
        "from_date": start_date.isoformat(),
        "to_date": end_date.isoformat(),
        "sort": "date_asc",
    }
    return urlencode(values)


def build_employee_attendance_insight(employee, *, start_date, end_date):
    """Shape descriptive attendance service outputs and their evidence links."""

    loaded_records = employee.profile_attendance_records
    records = tuple(
        get_attendance_records(
            employee,
            start_date,
            end_date,
            attendance_records=loaded_records,
        )
    )
    summary = get_attendance_summary(
        employee,
        start_date,
        end_date,
        attendance_records=loaded_records,
    )
    absenteeism_rate = calculate_absenteeism_rate(
        employee,
        start_date,
        end_date,
        attendance_records=loaded_records,
    )
    late_rate = calculate_late_rate(
        employee,
        start_date,
        end_date,
        attendance_records=loaded_records,
    )
    total_records = summary["total_days"]

    status_rows = []
    for status, summary_key, definition in ATTENDANCE_STATUS_ROWS:
        count = summary[summary_key]
        share = _attendance_share(count, total_records)
        status_rows.append(
            {
                "status": status,
                "label": Attendance.Status(status).label,
                "definition": definition,
                "count": count,
                "share": share,
                "share_serialized": f"{share:.1f}",
                "evidence_query_string": (
                    _attendance_query(
                        employee,
                        start_date,
                        end_date,
                        status=status,
                    )
                    if count
                    else ""
                ),
            }
        )

    return {
        "records": records,
        "summary": summary,
        "status_rows": tuple(status_rows),
        "total_query_string": _attendance_query(
            employee,
            start_date,
            end_date,
        ),
        "absenteeism_rate": absenteeism_rate,
        "absenteeism_has_denominator": total_records > 0,
        "absenteeism_query_string": (
            _attendance_query(
                employee,
                start_date,
                end_date,
                status=Attendance.Status.ABSENT,
            )
            if summary["absent_days"]
            else ""
        ),
        "late_rate": late_rate,
        "late_has_denominator": summary["non_absent_days"] > 0,
        "late_query_string": (
            _attendance_query(
                employee,
                start_date,
                end_date,
                status=Attendance.Status.LATE,
            )
            if summary["late_days"]
            else ""
        ),
        "has_records": bool(total_records),
    }
