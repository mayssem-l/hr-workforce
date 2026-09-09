from calendar import monthrange

from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from core.models import Employee, Project
from frontend.forms.dashboard import DashboardFilterForm
from frontend.permissions import read_models_permission_required
from frontend.presenters.dashboard import build_dashboard_filter_context
from frontend.selectors.employees import get_employee_departments


@read_models_permission_required(Employee, Project)
@require_GET
def landing(request):
    today = timezone.localdate()
    default_start_date = today.replace(day=1)
    default_end_date = today.replace(
        day=monthrange(today.year, today.month)[1]
    )
    filter_data = request.GET.copy()
    if "start_date" not in filter_data:
        filter_data["start_date"] = default_start_date.isoformat()
    if "end_date" not in filter_data:
        filter_data["end_date"] = default_end_date.isoformat()

    filter_form = DashboardFilterForm(
        filter_data,
        departments=tuple(get_employee_departments()),
    )
    filter_context = None
    dashboard_filter_url = None
    if filter_form.is_valid():
        filter_context = build_dashboard_filter_context(filter_form.cleaned_data)
        dashboard_filter_url = (
            f"{reverse('frontend:landing')}?{filter_context['query_string']}"
        )

    return render(
        request,
        "frontend/dashboard/landing.html",
        {
            "breadcrumbs": [{"label": "Dashboard", "url": None}],
            "filter_form": filter_form,
            "filter_context": filter_context,
            "dashboard_filter_url": dashboard_filter_url,
        },
    )
