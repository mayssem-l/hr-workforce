from django.contrib import messages
from django.core.paginator import Paginator
from django.db import DatabaseError, transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import formats
from django.views.decorators.http import require_http_methods

from core.models import Attendance
from frontend.forms.attendance import (
    AttendanceDirectoryFilterForm,
    AttendanceForm,
)
from frontend.permissions import (
    read_model_permission_required,
    write_model_permission_required,
)
from frontend.presenters.dashboard import build_operational_directory_navigation
from frontend.selectors.attendance import (
    ATTENDANCE_PAGE_SIZE,
    DEFAULT_ATTENDANCE_SORT,
    get_attendance,
    get_attendance_directory,
    get_attendance_employee_choices,
)


def _attendance_date_label(value):
    return formats.date_format(value, "M j, Y")


@read_model_permission_required(Attendance)
def attendance_list(request):
    employee_choices = get_attendance_employee_choices()
    filter_form = AttendanceDirectoryFilterForm(
        request.GET,
        employee_choices=employee_choices,
    )
    filters = {
        "employee": "",
        "status": "",
        "from_date": None,
        "to_date": None,
        "sort": DEFAULT_ATTENDANCE_SORT,
    }
    if filter_form.is_valid():
        filters.update(filter_form.cleaned_data)

    navigation_context = None
    if filters["from_date"] and filters["to_date"]:
        navigation_context = build_operational_directory_navigation(
            start_date=filters["from_date"],
            end_date=filters["to_date"],
            employee_id=filters["employee"],
        )

    records = get_attendance_directory(**filters)
    page_obj = Paginator(records, ATTENDANCE_PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    attendance_headers = ("Employee", "Date", "Status", "Recorded times")
    if request.user.has_perm("core.change_attendance") or request.user.has_perm(
        "core.delete_attendance"
    ):
        attendance_headers = (*attendance_headers, "Actions")

    dashboard_url = (
        navigation_context["dashboard_url"]
        if navigation_context
        else reverse("frontend:landing")
    )
    return render(
        request,
        "frontend/attendance/list.html",
        {
            "attendance_headers": attendance_headers,
            "breadcrumbs": [
                {"label": "Dashboard", "url": dashboard_url},
                {"label": "Workforce", "url": reverse("frontend:employee_list")},
                {"label": "Attendance", "url": None},
            ],
            "filter_form": filter_form,
            "has_active_filters": any(
                filters[key]
                for key in ("employee", "status", "from_date", "to_date")
            ),
            "navigation_context": navigation_context,
            "page_obj": page_obj,
            "dashboard_url": dashboard_url,
            "profile_query_string": (
                navigation_context["profile_query_string"]
                if navigation_context
                else ""
            ),
        },
    )


def _save_attendance_form(request, form, *, success_message):
    try:
        with transaction.atomic():
            attendance = form.save()
    except DatabaseError:
        messages.error(
            request,
            "We could not save this attendance record. No changes were applied. "
            "Please try again.",
        )
        return None

    messages.success(request, success_message(attendance))
    return attendance


@write_model_permission_required(Attendance, "add")
def attendance_create(request):
    form = AttendanceForm(request.POST if request.method == "POST" else None)

    if request.method == "POST":
        if form.is_valid():
            attendance = _save_attendance_form(
                request,
                form,
                success_message=lambda saved: (
                    f"Attendance for {saved.employee} on "
                    f"{_attendance_date_label(saved.date)} was added."
                ),
            )
            if attendance is not None:
                return redirect("frontend:attendance_list")
        else:
            messages.error(
                request,
                "Please correct the highlighted fields before saving the "
                "attendance record.",
            )

    return render(
        request,
        "frontend/attendance/create.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {"label": "Workforce", "url": reverse("frontend:employee_list")},
                {
                    "label": "Attendance",
                    "url": reverse("frontend:attendance_list"),
                },
                {"label": "Add attendance", "url": None},
            ],
            "cancel_url": reverse("frontend:attendance_list"),
            "form": form,
        },
    )


@write_model_permission_required(Attendance, "change")
def attendance_update(request, attendance_id):
    try:
        attendance = get_attendance(attendance_id)
    except Attendance.DoesNotExist as exc:
        raise Http404("Attendance record not found.") from exc

    employee_name = str(attendance.employee)
    form = AttendanceForm(
        request.POST if request.method == "POST" else None,
        instance=attendance,
    )

    if request.method == "POST":
        if form.is_valid():
            saved_attendance = _save_attendance_form(
                request,
                form,
                success_message=lambda saved: (
                    f"Attendance for {saved.employee} on "
                    f"{_attendance_date_label(saved.date)} was updated."
                ),
            )
            if saved_attendance is not None:
                return redirect("frontend:attendance_list")
        else:
            messages.error(
                request,
                "Please correct the highlighted fields before saving changes.",
            )

    return render(
        request,
        "frontend/attendance/edit.html",
        {
            "attendance": attendance,
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {"label": "Workforce", "url": reverse("frontend:employee_list")},
                {
                    "label": "Attendance",
                    "url": reverse("frontend:attendance_list"),
                },
                {"label": f"Edit {employee_name}", "url": None},
            ],
            "cancel_url": reverse("frontend:attendance_list"),
            "employee_name": employee_name,
            "form": form,
        },
    )


@write_model_permission_required(Attendance, "delete")
@require_http_methods(["GET", "POST"])
def attendance_delete(request, attendance_id):
    try:
        attendance = get_attendance(attendance_id)
    except Attendance.DoesNotExist as exc:
        if request.method == "POST":
            messages.info(
                request,
                "This attendance record no longer exists. No deletion was needed.",
            )
            return redirect("frontend:attendance_list")
        raise Http404("Attendance record not found.") from exc

    employee_name = str(attendance.employee)
    attendance_date = attendance.date
    delete_url = reverse(
        "frontend:attendance_delete",
        args=[attendance.attendance_id],
    )

    if request.method == "POST":
        try:
            with transaction.atomic():
                attendance.delete()
        except DatabaseError:
            messages.error(
                request,
                "We could not delete this attendance record. Nothing was "
                "deleted. Please try again.",
            )
        else:
            messages.success(
                request,
                f"Attendance for {employee_name} on "
                f"{_attendance_date_label(attendance_date)} was deleted.",
            )
            return redirect("frontend:attendance_list")

    return render(
        request,
        "frontend/attendance/confirm_delete.html",
        {
            "attendance": attendance,
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {"label": "Workforce", "url": reverse("frontend:employee_list")},
                {
                    "label": "Attendance",
                    "url": reverse("frontend:attendance_list"),
                },
                {"label": f"Delete {employee_name} attendance", "url": None},
            ],
            "cancel_url": reverse("frontend:attendance_list"),
            "confirmation_message": (
                f"Delete the attendance record for {employee_name} on "
                f"{_attendance_date_label(attendance_date)}? Employee details, "
                "planning, and "
                "staffing recommendations will not change. This action cannot "
                "be undone."
            ),
            "delete_url": delete_url,
            "employee_name": employee_name,
        },
    )
