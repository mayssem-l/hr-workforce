from django.contrib import messages
from django.core.paginator import Paginator
from django.db import DatabaseError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from core.models import Employee
from frontend.forms.employees import EmployeeDirectoryFilterForm, EmployeeForm
from frontend.permissions import (
    read_model_permission_required,
    write_model_permission_required,
)
from frontend.presenters.employees import build_employee_profile
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

    employees = get_employee_directory(**filters)
    page_obj = Paginator(employees, EMPLOYEE_PAGE_SIZE).get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "frontend/employees/list.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
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
            "page_obj": page_obj,
        },
    )


@read_model_permission_required(Employee)
def employee_detail(request, employee_id):
    as_of = timezone.localdate()
    try:
        employee = get_employee_profile(employee_id, on_date=as_of)
    except Employee.DoesNotExist as exc:
        raise Http404("Employee not found.") from exc

    profile = build_employee_profile(employee, on_date=as_of)
    return render(
        request,
        "frontend/employees/detail.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {
                    "label": "Workforce",
                    "url": reverse("frontend:employee_list"),
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
            "profile": profile,
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
                return redirect(
                    "frontend:employee_detail",
                    saved_employee.employee_id,
                )
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
            "cancel_url": reverse(
                "frontend:employee_detail",
                args=[employee.employee_id],
            ),
            "employee": employee,
            "employee_name": employee_name,
            "form": form,
        },
    )
