from core.models import Attendance, Employee


DEFAULT_ATTENDANCE_SORT = "date_desc"
ATTENDANCE_PAGE_SIZE = 20

ATTENDANCE_SORT_OPTIONS = {
    "date_desc": (
        "-date",
        "employee__last_name",
        "employee__first_name",
        "attendance_id",
    ),
    "date_asc": (
        "date",
        "employee__last_name",
        "employee__first_name",
        "attendance_id",
    ),
    "employee": (
        "employee__last_name",
        "employee__first_name",
        "-date",
        "attendance_id",
    ),
    "employee_desc": (
        "-employee__last_name",
        "-employee__first_name",
        "-date",
        "attendance_id",
    ),
    "status": (
        "status",
        "-date",
        "employee__last_name",
        "employee__first_name",
        "attendance_id",
    ),
}

ATTENDANCE_SORT_CHOICES = (
    ("date_desc", "Date: newest first"),
    ("date_asc", "Date: oldest first"),
    ("employee", "Employee: A to Z"),
    ("employee_desc", "Employee: Z to A"),
    ("status", "Status: A to Z"),
)

ATTENDANCE_DIRECTORY_FIELDS = (
    "attendance_id",
    "employee_id",
    "employee__employee_id",
    "employee__first_name",
    "employee__last_name",
    "employee__department",
    "date",
    "status",
    "arrival_time",
    "departure_time",
)


def get_attendance_employee_choices():
    """Return deterministic employee choices for the attendance filter."""
    employees = Employee.objects.only(
        "employee_id",
        "first_name",
        "last_name",
        "department",
    ).order_by("last_name", "first_name", "employee_id")
    return tuple(
        (str(employee.employee_id), f"{employee} — {employee.department}")
        for employee in employees
    )


def get_attendance_directory(
    *,
    employee="",
    status="",
    from_date=None,
    to_date=None,
    sort="",
):
    """Return filtered attendance history with employee context in one query."""
    records = Attendance.objects.select_related("employee").only(
        *ATTENDANCE_DIRECTORY_FIELDS
    )

    if str(employee or "").isdigit():
        records = records.filter(employee_id=employee)

    valid_statuses = {value for value, _label in Attendance.Status.choices}
    if status in valid_statuses:
        records = records.filter(status=status)

    if from_date:
        records = records.filter(date__gte=from_date)

    if to_date:
        records = records.filter(date__lte=to_date)

    ordering = ATTENDANCE_SORT_OPTIONS.get(
        sort,
        ATTENDANCE_SORT_OPTIONS[DEFAULT_ATTENDANCE_SORT],
    )
    return records.order_by(*ordering)


def get_attendance(attendance_id):
    """Load one attendance record with its employee context."""
    return (
        Attendance.objects.select_related("employee")
        .only(*ATTENDANCE_DIRECTORY_FIELDS)
        .get(attendance_id=attendance_id)
    )
