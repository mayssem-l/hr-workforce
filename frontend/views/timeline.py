from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from core.models import Assignment, Employee, Project
from frontend.calendar_access import (
    get_calendar_link_access,
    get_calendar_source_access,
)
from frontend.permissions import read_models_permission_required
from frontend.presenters.calendar import build_calendar_legend_context
from frontend.presenters.timeline import (
    build_timeline_bands,
    build_timeline_table_rows,
)
from frontend.selectors.calendar import (
    APPROVED_LEAVE_SOURCE,
    ASSIGNMENT_SOURCE,
    CALENDAR_SOURCE_ORDER,
    PROJECT_SOURCE,
    get_calendar_events,
)


@read_models_permission_required(Project, Assignment, Employee)
@require_GET
def project_timeline(request, project_id):
    try:
        project = Project.objects.only(
            "project_id",
            "name",
            "description",
            "start_date",
            "end_date",
            "estimated_hours",
            "status",
            "priority",
            "criticality",
        ).get(project_id=project_id)
    except Project.DoesNotExist as exc:
        raise Http404("Project not found.") from exc

    source_access = get_calendar_source_access(request.user)
    link_access = get_calendar_link_access(request.user)
    period_start = project.start_date
    period_end = project.end_date

    scoped_events = get_calendar_events(
        start_date=period_start,
        end_date=period_end,
        source_access=source_access,
        filters={
            "sources": (PROJECT_SOURCE, ASSIGNMENT_SOURCE),
            "department": "",
            "employee": "",
            "project": str(project.project_id),
        },
    )
    assigned_employee_ids = frozenset(
        event.employee_id
        for event in scoped_events
        if event.source == ASSIGNMENT_SOURCE and event.employee_id
    )
    leave_events = ()
    if source_access.get("approved_leave", False) and assigned_employee_ids:
        leave_events = get_calendar_events(
            start_date=period_start,
            end_date=period_end,
            source_access=source_access,
            filters={
                "sources": (APPROVED_LEAVE_SOURCE,),
                "department": "",
                "employee": assigned_employee_ids,
                "project": "",
            },
        )
    events = tuple(
        sorted(
            (*scoped_events, *leave_events),
            key=lambda event: (
                event.start_date,
                event.end_date,
                CALENDAR_SOURCE_ORDER[event.source],
                event.title.casefold(),
                event.record_id,
            ),
        )
    )

    bands = build_timeline_bands(
        events,
        period_start=period_start,
        period_end=period_end,
    )
    table_rows = build_timeline_table_rows(
        events,
        project_id=project.project_id,
        user=request.user,
        link_access=link_access,
        filter_context={
            "start_date": period_start,
            "end_date": period_end,
        },
    )
    legend = build_calendar_legend_context(
        source_access,
        selected_sources=(PROJECT_SOURCE, ASSIGNMENT_SOURCE, APPROVED_LEAVE_SOURCE),
        events=events,
    )
    planning_url = reverse(
        "frontend:project_planning",
        args=[project.project_id],
    )
    project_detail_url = reverse(
        "frontend:project_detail",
        args=[project.project_id],
    )
    return render(
        request,
        "frontend/projects/timeline.html",
        {
            "breadcrumbs": [
                {"label": "Dashboard", "url": reverse("frontend:landing")},
                {"label": "Projects", "url": reverse("frontend:project_list")},
                {"label": project.name, "url": project_detail_url},
                {"label": "Project timeline", "url": None},
            ],
            "project": project,
            "project_detail_url": project_detail_url,
            "planning_url": planning_url,
            "project_list_url": reverse("frontend:project_list"),
            "period_start": period_start,
            "period_end": period_end,
            "bands": bands,
            "timeline_rows": table_rows,
            "timeline_event_headers": (
                "Entry",
                "Period",
                "Status",
                "Project",
                "Employee",
                "Leave type",
                "Evidence",
            ),
            "legend": legend,
            "leave_restricted": not source_access.get("approved_leave", False),
            "event_count": len(events),
        },
    )
