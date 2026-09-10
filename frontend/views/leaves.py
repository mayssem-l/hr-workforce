from django.contrib import messages
from django.core.paginator import Paginator
from django.db import DatabaseError, transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.models import Leave
from frontend.forms.leaves import LeaveDirectoryFilterForm, LeaveForm
from frontend.navigation import (
    get_planning_return_url,
    planning_return_query,
    with_planning_return,
)
from frontend.permissions import (
    read_model_permission_required,
    write_model_permission_required,
)
from frontend.presenters.dashboard import build_operational_directory_navigation
from frontend.selectors.leaves import (
    DEFAULT_LEAVE_SORT,
    LEAVE_PAGE_SIZE,
    get_leave,
    get_leave_directory,
    get_leave_employee_choices,
)


@read_model_permission_required(Leave)
def leave_list(request):
    planning_return_url = get_planning_return_url(request)
    employee_choices = get_leave_employee_choices()
    filter_form = LeaveDirectoryFilterForm(
        request.GET,
        employee_choices=employee_choices,
    )
    filters = {
        "employee": "",
        "leave_type": "",
        "status": "",
        "from_date": None,
        "to_date": None,
        "sort": DEFAULT_LEAVE_SORT,
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

    leaves = get_leave_directory(**filters)
    page_obj = Paginator(leaves, LEAVE_PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    leave_headers = ("Employee", "Leave type", "Dates", "Status")
    if request.user.has_perm("core.change_leave") or request.user.has_perm(
        "core.delete_leave"
    ):
        leave_headers = (*leave_headers, "Actions")

    dashboard_url = (
        navigation_context["dashboard_url"]
        if navigation_context
        else reverse("frontend:landing")
    )
    return render(
        request,
        "frontend/leaves/list.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": dashboard_url},
                {"label": "Workforce", "url": reverse("frontend:employee_list")},
                {"label": "Leave", "url": None},
            ],
            "filter_form": filter_form,
            "has_active_filters": any(
                filters[key]
                for key in (
                    "employee",
                    "leave_type",
                    "status",
                    "from_date",
                    "to_date",
                )
            ),
            "leave_headers": leave_headers,
            "leave_create_url": (
                with_planning_return(
                    reverse("frontend:leave_create"),
                    planning_return_url,
                )
                if request.user.has_perm("core.add_leave")
                else None
            ),
            "leave_list_clear_url": with_planning_return(
                reverse("frontend:leave_list"),
                planning_return_url,
            ),
            "navigation_context": navigation_context,
            "page_obj": page_obj,
            "dashboard_url": dashboard_url,
            "profile_query_string": (
                navigation_context["profile_query_string"]
                if navigation_context
                else ""
            ),
            "planning_return_query": planning_return_query(planning_return_url),
            "planning_return_url": planning_return_url,
        },
    )


def _save_leave_form(request, form, *, success_message):
    try:
        with transaction.atomic():
            leave = form.save()
    except DatabaseError:
        messages.error(
            request,
            "We could not save this leave record. No changes were applied. "
            "Please try again.",
        )
        return None

    messages.success(request, success_message(leave))
    return leave


@write_model_permission_required(Leave, "add")
def leave_create(request):
    planning_return_url = get_planning_return_url(request)
    destination_url = planning_return_url or reverse("frontend:leave_list")
    form = LeaveForm(request.POST if request.method == "POST" else None)

    if request.method == "POST":
        if form.is_valid():
            leave = _save_leave_form(
                request,
                form,
                success_message=lambda saved: (
                    f"{saved.get_type_display()} leave for {saved.employee} "
                    "was added."
                ),
            )
            if leave is not None:
                return redirect(destination_url)
        else:
            messages.error(
                request,
                "Please correct the highlighted fields before saving the leave "
                "record.",
            )

    return render(
        request,
        "frontend/leaves/create.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {"label": "Workforce", "url": reverse("frontend:employee_list")},
                {"label": "Leave", "url": reverse("frontend:leave_list")},
                {"label": "Add leave", "url": None},
            ],
            "cancel_label": (
                "Return to planning workspace" if planning_return_url else "Cancel"
            ),
            "cancel_url": destination_url,
            "form": form,
        },
    )


@write_model_permission_required(Leave, "change")
def leave_update(request, leave_id):
    try:
        leave = get_leave(leave_id)
    except Leave.DoesNotExist as exc:
        raise Http404("Leave record not found.") from exc

    employee_name = str(leave.employee)
    planning_return_url = get_planning_return_url(request)
    destination_url = planning_return_url or reverse("frontend:leave_list")
    form = LeaveForm(
        request.POST if request.method == "POST" else None,
        instance=leave,
    )

    if request.method == "POST":
        if form.is_valid():
            saved_leave = _save_leave_form(
                request,
                form,
                success_message=lambda saved: (
                    f"{saved.get_type_display()} leave for {saved.employee} "
                    "was updated."
                ),
            )
            if saved_leave is not None:
                return redirect(destination_url)
        else:
            messages.error(
                request,
                "Please correct the highlighted fields before saving changes.",
            )

    return render(
        request,
        "frontend/leaves/edit.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {"label": "Workforce", "url": reverse("frontend:employee_list")},
                {"label": "Leave", "url": reverse("frontend:leave_list")},
                {"label": f"Edit {employee_name}", "url": None},
            ],
            "cancel_label": (
                "Return to planning workspace" if planning_return_url else "Cancel"
            ),
            "cancel_url": destination_url,
            "employee_name": employee_name,
            "form": form,
            "leave": leave,
        },
    )


@write_model_permission_required(Leave, "delete")
@require_http_methods(["GET", "POST"])
def leave_delete(request, leave_id):
    planning_return_url = get_planning_return_url(request)
    destination_url = planning_return_url or reverse("frontend:leave_list")
    try:
        leave = get_leave(leave_id)
    except Leave.DoesNotExist as exc:
        if request.method == "POST":
            messages.info(
                request,
                "This leave record no longer exists. No deletion was needed.",
            )
            return redirect(destination_url)
        raise Http404("Leave record not found.") from exc

    employee_name = str(leave.employee)
    leave_type = leave.get_type_display()
    delete_url = reverse("frontend:leave_delete", args=[leave.leave_id])
    delete_url = with_planning_return(delete_url, planning_return_url)

    if request.method == "POST":
        try:
            with transaction.atomic():
                leave.delete()
        except DatabaseError:
            messages.error(
                request,
                "We could not delete this leave record. Nothing was deleted. "
                "Please try again.",
            )
        else:
            messages.success(
                request,
                f"{leave_type} leave for {employee_name} was deleted.",
            )
            return redirect(destination_url)

    return render(
        request,
        "frontend/leaves/confirm_delete.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {"label": "Workforce", "url": reverse("frontend:employee_list")},
                {"label": "Leave", "url": reverse("frontend:leave_list")},
                {"label": f"Delete {employee_name} leave", "url": None},
            ],
            "cancel_url": destination_url,
            "confirmation_message": (
                f"Delete this {leave_type.lower()} leave record for "
                f"{employee_name}? The employee profile and employment status "
                "will not change. This action cannot be undone."
            ),
            "delete_url": delete_url,
            "employee_name": employee_name,
            "leave": leave,
            "leave_type": leave_type,
        },
    )
