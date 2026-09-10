from datetime import date

from django.db.models import Q

from core.models import Assignment, Employee, EmployeeSkill, Leave
from core.services.attendance import get_attendance_records
from core.services.availability import get_approved_leaves


DEFAULT_EMPLOYEE_SORT = "name"
EMPLOYEE_PAGE_SIZE = 20

EMPLOYEE_SORT_OPTIONS = {
    "name": ("last_name", "first_name", "employee_id"),
    "name_desc": ("-last_name", "-first_name", "employee_id"),
    "department": ("department", "last_name", "first_name", "employee_id"),
    "capacity_desc": (
        "-capacity_hours_week",
        "last_name",
        "first_name",
        "employee_id",
    ),
    "capacity_asc": (
        "capacity_hours_week",
        "last_name",
        "first_name",
        "employee_id",
    ),
    "hire_date_desc": ("-hire_date", "last_name", "first_name", "employee_id"),
    "hire_date_asc": ("hire_date", "last_name", "first_name", "employee_id"),
}

EMPLOYEE_SORT_CHOICES = (
    ("name", "Name: A to Z"),
    ("name_desc", "Name: Z to A"),
    ("department", "Department: A to Z"),
    ("capacity_desc", "Weekly capacity: highest first"),
    ("capacity_asc", "Weekly capacity: lowest first"),
    ("hire_date_desc", "Hire date: newest first"),
    ("hire_date_asc", "Hire date: oldest first"),
)

EMPLOYEE_DIRECTORY_FIELDS = (
    "employee_id",
    "first_name",
    "last_name",
    "department",
    "position",
    "hire_date",
    "experience_years",
    "capacity_hours_week",
    "status",
)


def get_employee_directory(*, query="", status="", department="", sort=""):
    """Return the filtered employee directory without related-record queries."""
    employees = Employee.objects.only(*EMPLOYEE_DIRECTORY_FIELDS)

    for term in str(query or "").strip().split():
        employees = employees.filter(
            Q(first_name__icontains=term) | Q(last_name__icontains=term)
        )

    valid_statuses = {value for value, _label in Employee.Status.choices}
    if status in valid_statuses:
        employees = employees.filter(status=status)

    normalized_department = str(department or "").strip()
    if normalized_department:
        employees = employees.filter(department=normalized_department)

    ordering = EMPLOYEE_SORT_OPTIONS.get(sort, EMPLOYEE_SORT_OPTIONS[DEFAULT_EMPLOYEE_SORT])
    return employees.order_by(*ordering)


def get_employee_departments():
    """Return stable, nonempty department options for the directory filter."""
    return (
        Employee.objects.exclude(department="")
        .order_by("department")
        .values_list("department", flat=True)
        .distinct()
    )


def get_employee_profile(
    employee_id,
    *,
    on_date,
    timeline_start_date=None,
    timeline_end_date=None,
    include_attendance=False,
):
    """Load one employee and its permitted profile insight collections."""
    employee = Employee.objects.only(*EMPLOYEE_DIRECTORY_FIELDS).get(
        employee_id=employee_id
    )

    has_timeline_period = (
        timeline_start_date is not None
        and timeline_end_date is not None
        and timeline_start_date <= timeline_end_date
    )

    leave_scope = Q(
        status=Leave.Status.APPROVED,
        end_date__gte=on_date,
    )
    if has_timeline_period:
        leave_scope |= Q(
            start_date__lte=timeline_end_date,
            end_date__gte=timeline_start_date,
        )
    loaded_leaves = list(
        Leave.objects.filter(employee=employee)
        .filter(leave_scope)
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
    employee.profile_calculation_leaves = loaded_leaves
    employee.profile_upcoming_leaves = get_approved_leaves(
        employee,
        on_date,
        date.max,
        leave_records=loaded_leaves,
    )
    employee.profile_timeline_leaves = [
        leave
        for leave in loaded_leaves
        if has_timeline_period
        and leave.start_date <= timeline_end_date
        and leave.end_date >= timeline_start_date
    ]

    assignment_scope = Q(
        status__in=(Assignment.Status.ACTIVE, Assignment.Status.PLANNED),
        end_date__gte=on_date,
    ) | Q(
        start_date__lte=on_date,
        end_date__gte=on_date,
    )
    if has_timeline_period:
        assignment_scope |= Q(
            start_date__lte=timeline_end_date,
            end_date__gte=timeline_start_date,
        )
    loaded_assignments = list(
        Assignment.objects.filter(employee=employee)
        .filter(assignment_scope)
        .select_related("project")
        .only(
            "assignment_id",
            "employee_id",
            "project_id",
            "project__project_id",
            "project__name",
            "start_date",
            "end_date",
            "allocation_percentage",
            "role_on_project",
            "status",
        )
        .order_by("start_date", "end_date", "project__name", "assignment_id")
    )
    employee.profile_calculation_assignments = loaded_assignments
    employee.profile_assignments = [
        assignment
        for assignment in loaded_assignments
        if assignment.status in (Assignment.Status.ACTIVE, Assignment.Status.PLANNED)
        and assignment.end_date >= on_date
    ]
    employee.profile_timeline_assignments = [
        assignment
        for assignment in loaded_assignments
        if has_timeline_period
        and assignment.start_date <= timeline_end_date
        and assignment.end_date >= timeline_start_date
    ]
    employee.profile_skills = list(
        EmployeeSkill.objects.filter(employee=employee)
        .select_related("skill")
        .only(
            "employee_skill_id",
            "employee_id",
            "skill_id",
            "skill__skill_id",
            "skill__name",
            "skill__category",
            "level",
            "years_experience",
        )
        .order_by("skill__category", "skill__name", "employee_skill_id")
    )
    employee.profile_attendance_records = []
    if has_timeline_period and include_attendance:
        employee.profile_attendance_records = list(
            get_attendance_records(
                employee,
                timeline_start_date,
                timeline_end_date,
            )
            .only(
                "attendance_id",
                "employee_id",
                "date",
                "status",
                "arrival_time",
                "departure_time",
            )
            .order_by("date", "attendance_id")
        )
    return employee


def get_employee_for_proficiency(employee_id):
    """Load the stored employee context needed by a proficiency form."""
    return Employee.objects.only(*EMPLOYEE_DIRECTORY_FIELDS).get(
        employee_id=employee_id
    )


def get_employee_skill(employee_id, employee_skill_id):
    """Load one proficiency link scoped to its employee in one query."""
    return (
        EmployeeSkill.objects.select_related("employee", "skill")
        .only(
            "employee_skill_id",
            "employee_id",
            "employee__employee_id",
            "employee__first_name",
            "employee__last_name",
            "employee__department",
            "employee__position",
            "skill_id",
            "skill__skill_id",
            "skill__name",
            "skill__category",
            "level",
            "years_experience",
        )
        .get(
            employee_id=employee_id,
            employee_skill_id=employee_skill_id,
        )
    )
