from datetime import timedelta
from urllib.parse import urlencode

from django.urls import reverse

from frontend.forms.calendar import CALENDAR_SOURCE_CHOICES, CALENDAR_VIEW_CHOICES
from frontend.presenters.dashboard import build_reporting_period_context
from frontend.selectors.calendar import (
    APPROVED_LEAVE_SOURCE,
    ASSIGNMENT_SOURCE,
    CALENDAR_SOURCE_ACCESS_KEYS,
    PROJECT_SOURCE,
)


CALENDAR_SOURCE_PRESENTATION = (
    (
        "projects",
        "Project schedules",
        "Uses stored project start and end dates.",
    ),
    (
        "assignments",
        "Assignment schedules",
        "Uses stored assignment periods to connect employees with projects.",
    ),
    (
        "approved_leave",
        "Approved leave",
        "Only approved dated leave will be included in this source.",
    ),
)
CALENDAR_SOURCE_LABELS = {
    PROJECT_SOURCE: "Project",
    ASSIGNMENT_SOURCE: "Assignment",
    APPROVED_LEAVE_SOURCE: "Approved leave",
}


def _calendar_filter_query_values(filter_data, *, sources, view):
    return [
        ("start_date", filter_data["start_date"].isoformat()),
        ("end_date", filter_data["end_date"].isoformat()),
        ("view", view),
        *(("source", source) for source in sources),
        ("department", filter_data["department"]),
        ("employee", filter_data["employee"]),
        ("project", filter_data["project"]),
        ("filters", "1"),
    ]


def build_calendar_view_context(view_state):
    """Shape validated date and mode values for display without deriving events."""

    period_context = build_reporting_period_context(view_state)
    view_labels = dict(CALENDAR_VIEW_CHOICES)
    query_values = {
        "start_date": view_state["start_date"].isoformat(),
        "end_date": view_state["end_date"].isoformat(),
        "view": view_state["view"],
    }
    return {
        **period_context,
        "view": view_state["view"],
        "view_label": view_labels[view_state["view"]],
        "query_string": urlencode(query_values),
    }


def build_calendar_source_context(source_access):
    """Describe calendar source access without exposing records or counts."""

    return tuple(
        {
            "key": key,
            "source": next(
                source_name
                for source_name, access_key in CALENDAR_SOURCE_ACCESS_KEYS.items()
                if access_key == key
            ),
            "title": title,
            "description": description,
            "is_available": source_access[key],
            "state": "available" if source_access[key] else "restricted",
            "state_label": (
                "Available for this workspace"
                if source_access[key]
                else "Restricted by your current access"
            ),
        }
        for key, title, description in CALENDAR_SOURCE_PRESENTATION
    )


def build_calendar_filter_context(filter_data, *, filter_options):
    """Normalize one validated filter contract for pages, endpoints, and links."""

    view_context = build_calendar_view_context(filter_data)
    selected_source_set = frozenset(filter_data["source"])
    sources = tuple(
        source
        for source, _label in CALENDAR_SOURCE_CHOICES
        if source in selected_source_set
    )
    source_labels = tuple(
        label
        for source, label in CALENDAR_SOURCE_CHOICES
        if source in selected_source_set
    )
    employee_labels = dict(filter_options.employees)
    project_labels = dict(filter_options.projects)
    query_values = _calendar_filter_query_values(
        filter_data,
        sources=sources,
        view=filter_data["view"],
    )
    workspace_url = reverse("frontend:calendar_workspace")
    return {
        **view_context,
        "sources": sources,
        "source_labels": source_labels,
        "department": filter_data["department"],
        "department_label": filter_data["department"] or "All departments",
        "employee": filter_data["employee"],
        "employee_label": employee_labels.get(
            filter_data["employee"],
            "All employees",
        ),
        "project": filter_data["project"],
        "project_label": project_labels.get(
            filter_data["project"],
            "All projects",
        ),
        "query_string": urlencode(query_values, doseq=True),
        "view_links": tuple(
            {
                "value": view,
                "label": label,
                "is_current": view == filter_data["view"],
                "url": (
                    f"{workspace_url}?"
                    f"{urlencode(_calendar_filter_query_values(filter_data, sources=sources, view=view), doseq=True)}"
                ),
            }
            for view, label in CALENDAR_VIEW_CHOICES
        ),
    }


def build_calendar_legend_context(source_access, *, selected_sources, events):
    """Explain permission, selection, and matching state for each source."""

    selected_source_set = frozenset(selected_sources)
    matching_sources = {event.source for event in events}
    rows = []
    for key, title, description in CALENDAR_SOURCE_PRESENTATION:
        source = next(
            source_name
            for source_name, access_key in CALENDAR_SOURCE_ACCESS_KEYS.items()
            if access_key == key
        )
        if not source_access[key]:
            state = "restricted"
            state_label = "Restricted by your current access"
        elif source not in selected_source_set:
            state = "not_selected"
            state_label = "Not included in this view"
        elif source not in matching_sources:
            state = "empty"
            state_label = "Included — no matching entries"
        else:
            state = "included"
            state_label = "Included — matching entries available"
        rows.append(
            {
                "key": key,
                "source": source,
                "title": title,
                "description": description,
                "is_available": source_access[key],
                "state": state,
                "state_label": state_label,
            }
        )
    return tuple(rows)


def _event_links(event, link_access, filter_context):
    links = []
    if event.project_id and link_access["project_detail"]:
        project_url = reverse(
            "frontend:project_detail",
            args=[event.project_id],
        )
        if event.source == ASSIGNMENT_SOURCE:
            project_url = f"{project_url}#project-assignments-title"
        links.append(
            {
                "kind": "project",
                "label": "View project",
                "url": project_url,
            }
        )
    if event.employee_id and link_access["employee_detail"]:
        employee_query = urlencode(
            {
                "start_date": filter_context["start_date"].isoformat(),
                "end_date": filter_context["end_date"].isoformat(),
            }
        )
        links.append(
            {
                "kind": "employee",
                "label": "View employee",
                "url": (
                    f"{reverse('frontend:employee_detail', args=[event.employee_id])}"
                    f"?{employee_query}"
                ),
            }
        )
    if event.source == APPROVED_LEAVE_SOURCE and link_access["leave_list"]:
        leave_query = urlencode(
            {
                "employee": event.employee_id,
                "status": event.status,
                "from_date": filter_context["start_date"].isoformat(),
                "to_date": filter_context["end_date"].isoformat(),
            }
        )
        links.append(
            {
                "kind": "leave",
                "label": "View approved leave",
                "url": f"{reverse('frontend:leave_list')}?{leave_query}",
            }
        )
    return links


def _calendar_exclusive_end(end_date):
    try:
        return (end_date + timedelta(days=1)).isoformat()
    except OverflowError:
        return None


def build_calendar_event_payload(event, *, link_access, filter_context):
    """Serialize one selector record without deriving schedule evidence."""

    links = _event_links(event, link_access, filter_context)
    return {
        "id": event.event_id,
        "source": event.source,
        "source_label": CALENDAR_SOURCE_LABELS[event.source],
        "title": event.title,
        "start_date": event.start_date.isoformat(),
        "end_date": event.end_date.isoformat(),
        "status": {
            "value": event.status,
            "label": event.status_label,
        },
        "project": (
            {"id": event.project_id, "label": event.project_label}
            if event.project_id
            else None
        ),
        "employee": (
            {"id": event.employee_id, "label": event.employee_label}
            if event.employee_id
            else None
        ),
        "leave_type": (
            {"value": event.leave_type, "label": event.leave_type_label}
            if event.leave_type
            else None
        ),
        "links": links,
        "calendar": {
            "id": event.event_id,
            "title": event.title,
            "start": event.start_date.isoformat(),
            "end": _calendar_exclusive_end(event.end_date),
            "allDay": True,
            "url": links[0]["url"] if links else "",
            "classNames": [f"calendar-event--{event.source}"],
            "extendedProps": {
                "sourceLabel": CALENDAR_SOURCE_LABELS[event.source],
                "statusLabel": event.status_label,
            },
        },
    }


def build_calendar_list_rows(events, *, link_access, filter_context):
    """Wrap endpoint-contract events with date values used only for display."""

    return tuple(
        {
            "event": build_calendar_event_payload(
                event,
                link_access=link_access,
                filter_context=filter_context,
            ),
            "start_date_value": event.start_date,
            "end_date_value": event.end_date,
        }
        for event in events
    )


def calendar_has_narrowing_filters(filter_context, *, source_access):
    """Report whether the valid view narrows records beyond available sources."""

    available_sources = tuple(
        source
        for source, access_key in CALENDAR_SOURCE_ACCESS_KEYS.items()
        if source_access.get(access_key, False)
    )
    return bool(
        filter_context["department"]
        or filter_context["employee"]
        or filter_context["project"]
        or filter_context["sources"] != available_sources
    )


def build_calendar_events_response(
    events,
    *,
    start_date,
    end_date,
    configured_timezone,
    source_access,
    link_access,
    filter_context,
):
    """Build the stable endpoint envelope from selector-owned event records."""

    permitted_events = tuple(
        event
        for event in events
        if source_access.get(CALENDAR_SOURCE_ACCESS_KEYS[event.source], False)
        and event.source in filter_context["sources"]
    )
    return {
        "state": "ready",
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "inclusive": True,
            "timezone": configured_timezone,
        },
        "source_access": {
            source: "available" if is_available else "restricted"
            for source, is_available in source_access.items()
        },
        "filters": {
            "view": filter_context["view"],
            "sources": list(filter_context["sources"]),
            "department": filter_context["department"],
            "employee": filter_context["employee"],
            "project": filter_context["project"],
            "query_string": filter_context["query_string"],
        },
        "event_count": len(permitted_events),
        "events": [
            build_calendar_event_payload(
                event,
                link_access=link_access,
                filter_context=filter_context,
            )
            for event in permitted_events
        ],
    }
