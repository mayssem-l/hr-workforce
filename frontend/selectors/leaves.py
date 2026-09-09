from core.models import Employee, Leave


DEFAULT_LEAVE_SORT = "start_date_desc"
LEAVE_PAGE_SIZE = 20

LEAVE_SORT_OPTIONS = {
    "start_date_desc": (
        "-start_date",
        "-end_date",
        "employee__last_name",
        "employee__first_name",
        "leave_id",
    ),
    "start_date_asc": (
        "start_date",
        "end_date",
        "employee__last_name",
        "employee__first_name",
        "leave_id",
    ),
    "end_date_desc": (
        "-end_date",
        "-start_date",
        "employee__last_name",
        "employee__first_name",
        "leave_id",
    ),
    "end_date_asc": (
        "end_date",
        "start_date",
        "employee__last_name",
        "employee__first_name",
        "leave_id",
    ),
    "employee": (
        "employee__last_name",
        "employee__first_name",
        "-start_date",
        "leave_id",
    ),
    "employee_desc": (
        "-employee__last_name",
        "-employee__first_name",
        "-start_date",
        "leave_id",
    ),
}

LEAVE_SORT_CHOICES = (
    ("start_date_desc", "Start date: newest first"),
    ("start_date_asc", "Start date: oldest first"),
    ("end_date_desc", "End date: latest first"),
    ("end_date_asc", "End date: soonest first"),
    ("employee", "Employee: A to Z"),
    ("employee_desc", "Employee: Z to A"),
)

LEAVE_DIRECTORY_FIELDS = (
    "leave_id",
    "employee_id",
    "employee__employee_id",
    "employee__first_name",
    "employee__last_name",
    "employee__department",
    "start_date",
    "end_date",
    "type",
    "status",
)


def get_leave_employee_choices():
    """Return deterministic employee choices for leave filters and forms."""
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


def get_leave_directory(
    *,
    employee="",
    leave_type="",
    status="",
    from_date=None,
    to_date=None,
    sort="",
):
    """Return filtered dated leave records with employee context in one query."""
    leaves = Leave.objects.select_related("employee").only(
        *LEAVE_DIRECTORY_FIELDS
    )

    if str(employee or "").isdigit():
        leaves = leaves.filter(employee_id=employee)

    valid_types = {value for value, _label in Leave.Type.choices}
    if leave_type in valid_types:
        leaves = leaves.filter(type=leave_type)

    valid_statuses = {value for value, _label in Leave.Status.choices}
    if status in valid_statuses:
        leaves = leaves.filter(status=status)

    if from_date:
        leaves = leaves.filter(end_date__gte=from_date)

    if to_date:
        leaves = leaves.filter(start_date__lte=to_date)

    ordering = LEAVE_SORT_OPTIONS.get(
        sort,
        LEAVE_SORT_OPTIONS[DEFAULT_LEAVE_SORT],
    )
    return leaves.order_by(*ordering)


def get_leave(leave_id):
    """Load one dated leave record with its employee context."""
    return (
        Leave.objects.select_related("employee")
        .only(*LEAVE_DIRECTORY_FIELDS)
        .get(leave_id=leave_id)
    )
