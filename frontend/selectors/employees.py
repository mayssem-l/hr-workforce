from datetime import date

from django.db.models import Q

from core.models import Assignment, Employee, EmployeeSkill
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


def get_employee_profile(employee_id, *, on_date):
    """Load one employee and profile collections in four fixed queries."""
    employee = Employee.objects.only(*EMPLOYEE_DIRECTORY_FIELDS).get(
        employee_id=employee_id
    )

    employee.profile_upcoming_leaves = list(
        get_approved_leaves(employee, on_date, date.max)
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
    employee.profile_assignments = list(
        Assignment.objects.filter(
            employee=employee,
            status__in=(Assignment.Status.ACTIVE, Assignment.Status.PLANNED),
            end_date__gte=on_date,
        )
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
