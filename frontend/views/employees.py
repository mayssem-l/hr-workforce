from django.contrib import messages
from django.core.paginator import Paginator
from django.db import DatabaseError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from core.models import Attendance, Employee
from frontend.forms.dashboard import (
    DashboardFilterForm,
    with_default_reporting_period,
)
from frontend.forms.employees import EmployeeDirectoryFilterForm, EmployeeForm
from frontend.navigation import (
    get_planning_return_url,
    planning_return_query,
    with_planning_return,
)
from frontend.permissions import (
    read_model_permission_required,
    write_model_permission_required,
)
from frontend.presenters.dashboard import (
    build_dashboard_filter_context,
    build_employee_navigation_context,
)
from frontend.presenters.employees import (
    build_employee_attendance_insight,
    build_employee_profile,
    build_employee_timeline,
)
from frontend.selectors.employees import (
    DEFAULT_EMPLOYEE_SORT,
    EMPLOYEE_PAGE_SIZE,
    get_employee_departments,
    get_employee_directory,
    get_employee_profile,
)


@read_model_permission_required(Employee)
def employee_list(request):
    departments = list(get_employee_departments())
    filter_form = EmployeeDirectoryFilterForm(
        request.GET,
        departments=departments,
    )

    filters = {
        "query": "",
        "status": "",
        "department": "",
        "sort": DEFAULT_EMPLOYEE_SORT,
    }
    if filter_form.is_valid():
        filters.update(filter_form.cleaned_data)

    navigation_context = None
    if "start_date" in request.GET or "end_date" in request.GET:
        navigation_data = request.GET.copy()
        navigation_data["employee_status"] = filters["status"]
        navigation_form = DashboardFilterForm(
            navigation_data,
            departments=departments,
        )
        if navigation_form.is_valid():
            navigation_context = build_dashboard_filter_context(
                navigation_form.cleaned_data
            )

    employees = get_employee_directory(**filters)
    page_obj = Paginator(employees, EMPLOYEE_PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    dashboard_url = reverse("frontend:landing")
    profile_query_string = ""
    if navigation_context is not None:
        dashboard_url = build_employee_navigation_context(
            navigation_context
        )["dashboard_url"]
        profile_query_string = navigation_context["query_string"]

    return render(
        request,
        "frontend/employees/list.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": dashboard_url},
                {"label": "Workforce", "url": None},
            ],
            "employee_headers": (
                "Employee",
                "Department",
                "Position",
                "Weekly capacity",
                "Experience",
                "Hire date",
                "Status",
            ),
            "filter_form": filter_form,
            "has_active_filters": any(
                filters[key] for key in ("query", "status", "department")
            ),
            "navigation_context": navigation_context,
            "page_obj": page_obj,
            "profile_query_string": profile_query_string,
            "dashboard_url": dashboard_url,
        },
    )


@read_model_permission_required(Employee)
def employee_detail(request, employee_id):
    as_of = timezone.localdate()
    planning_return_url = get_planning_return_url(request)
    can_view_attendance = request.user.has_perm(
        f"{Attendance._meta.app_label}.view_{Attendance._meta.model_name}"
    )
    period_form = DashboardFilterForm(
        with_default_reporting_period(request.GET, today=as_of),
        departments=tuple(get_employee_departments()),
    )
    period_context = None
    timeline = None
    navigation_context = None
    profile_selector_kwargs = {"on_date": as_of}
    if period_form.is_valid():
        period_context = build_dashboard_filter_context(period_form.cleaned_data)
        navigation_context = build_employee_navigation_context(period_context)
        profile_selector_kwargs.update(
            {
                "include_attendance": can_view_attendance,
                "timeline_start_date": period_context["start_date"],
                "timeline_end_date": period_context["end_date"],
            }
        )

    try:
        employee = get_employee_profile(employee_id, **profile_selector_kwargs)
    except Employee.DoesNotExist as exc:
        raise Http404("Employee not found.") from exc

    profile = build_employee_profile(employee, on_date=as_of)
    attendance_insight = None
    dashboard_url = reverse("frontend:landing")
    workforce_url = reverse("frontend:employee_list")
    if period_context is not None:
        timeline = build_employee_timeline(
            employee,
            start_date=period_context["start_date"],
            end_date=period_context["end_date"],
        )
        dashboard_url = navigation_context["dashboard_url"]
        workforce_url = navigation_context["workforce_url"]
        if can_view_attendance:
            attendance_insight = build_employee_attendance_insight(
                employee,
                start_date=period_context["start_date"],
                end_date=period_context["end_date"],
            )

    return render(
        request,
        "frontend/employees/detail.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": dashboard_url},
                {
                    "label": "Workforce",
                    "url": workforce_url,
                },
                {"label": profile["full_name"], "url": None},
            ],
            "assignment_headers": (
                "Project",
                "Role",
                "Schedule",
                "Allocation",
                "Status",
            ),
            "attendance_headers": (
                "Date",
                "Status",
                "Recorded times",
            ),
            "attendance_status_headers": (
                "Status",
                "Meaning",
                "Records",
                "Share",
                "Evidence",
            ),
            "attendance_insight": attendance_insight,
            "attendance_list_url": reverse("frontend:attendance_list"),
            "dashboard_url": dashboard_url,
            "navigation_context": navigation_context,
            "period_context": period_context,
            "period_form": period_form,
            "planning_return_query": planning_return_query(planning_return_url),
            "planning_return_url": planning_return_url,
            "employee_update_url": with_planning_return(
                reverse(
                    "frontend:employee_update",
                    args=[employee.employee_id],
                ),
                planning_return_url,
            ),
            "profile": profile,
            "timeline": timeline,
            "workforce_url": workforce_url,
            "timeline_headers": (
                "Date",
                "Day",
                "Daily capacity",
                "Scheduled workload",
                "Scheduled hours",
                "Effective availability",
                "Assignment context",
                "Approved leave context",
            ),
        },
    )


def _save_employee_form(request, form, *, success_message):
    try:
        with transaction.atomic():
            employee = form.save()
    except DatabaseError:
        messages.error(
            request,
            "We could not save this employee. No changes were applied. "
            "Please try again.",
        )
        return None

    messages.success(request, success_message(employee))
    return employee


@write_model_permission_required(Employee, "add")
def employee_create(request):
    form = EmployeeForm(request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            employee = _save_employee_form(
                request,
                form,
                success_message=lambda saved: (
                    f"{saved} was added to the workforce."
                ),
            )
            if employee is not None:
                return redirect("frontend:employee_detail", employee.employee_id)
        else:
            messages.error(
                request,
                "Please correct the highlighted fields before saving the employee.",
            )

    return render(
        request,
        "frontend/employees/create.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {
                    "label": "Workforce",
                    "url": reverse("frontend:employee_list"),
                },
                {"label": "Add employee", "url": None},
            ],
            "cancel_url": reverse("frontend:employee_list"),
            "form": form,
        },
    )


@write_model_permission_required(Employee, "change")
def employee_update(request, employee_id):
    employee = get_object_or_404(Employee, employee_id=employee_id)
    planning_return_url = get_planning_return_url(request)
    destination_url = planning_return_url or reverse(
        "frontend:employee_detail",
        args=[employee.employee_id],
    )
    employee_name = str(employee)
    form = EmployeeForm(request.POST or None, instance=employee)

    if request.method == "POST":
        if form.is_valid():
            saved_employee = _save_employee_form(
                request,
                form,
                success_message=lambda saved: (
                    f"Employee profile for {saved} was updated."
                ),
            )
            if saved_employee is not None:
                return redirect(destination_url)
        else:
            messages.error(
                request,
                "Please correct the highlighted fields before saving changes.",
            )

    return render(
        request,
        "frontend/employees/edit.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {
                    "label": "Workforce",
                    "url": reverse("frontend:employee_list"),
                },
                {
                    "label": employee_name,
                    "url": reverse(
                        "frontend:employee_detail",
                        args=[employee.employee_id],
                    ),
                },
                {"label": "Edit", "url": None},
            ],
            "cancel_label": (
                "Return to planning workspace" if planning_return_url else "Cancel"
            ),
            "cancel_url": destination_url,
            "employee": employee,
            "employee_name": employee_name,
            "form": form,
        },
    )
