from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from core.models import Employee, Project
from frontend.forms.dashboard import (
    DashboardFilterForm,
    with_default_reporting_period,
)
from frontend.permissions import read_models_permission_required
from frontend.presenters.dashboard import (
    build_dashboard_distributions,
    build_dashboard_evidence_context,
    build_dashboard_filter_context,
    build_dashboard_kpi_summary,
)
from frontend.selectors.dashboard import get_dashboard_snapshot
from frontend.selectors.employees import get_employee_departments


@read_models_permission_required(Employee, Project)
@require_GET
def landing(request):
    today = timezone.localdate()
    filter_data = with_default_reporting_period(
        request.GET,
        today=today,
    )

    filter_form = DashboardFilterForm(
        filter_data,
        departments=tuple(get_employee_departments()),
    )
    filter_context = None
    kpi_summary = None
    distribution_context = None
    evidence_context = None
    dashboard_filter_url = None
    if filter_form.is_valid():
        filter_context = build_dashboard_filter_context(filter_form.cleaned_data)
        snapshot = get_dashboard_snapshot(filters=filter_form.cleaned_data)
        kpi_summary = build_dashboard_kpi_summary(
            snapshot=snapshot,
            filters=filter_form.cleaned_data,
        )
        distribution_context = build_dashboard_distributions(
            kpi_summary=kpi_summary,
        )
        evidence_context = build_dashboard_evidence_context(
            kpi_summary=kpi_summary,
            distribution_context=distribution_context,
            filter_context=filter_context,
        )
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
            "kpi_summary": kpi_summary,
            "distribution_context": distribution_context,
            "evidence_context": evidence_context,
            "employee_evidence_headers": (
                "Employee",
                "Period capacity",
                "Effective available",
                "Scheduled allocation",
                "Over-capacity dates",
                "Evidence",
            ),
            "leave_evidence_headers": (
                "Employee",
                "Approved records",
                "Leave periods",
                "Evidence",
            ),
            "project_evidence_headers": (
                "Project",
                "Schedule",
                "Status",
            ),
            "dashboard_filter_url": dashboard_filter_url,
        },
    )
