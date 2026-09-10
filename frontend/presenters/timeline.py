"""Shape project-timeline evidence without deriving schedule rules."""

from django.urls import reverse

from frontend.presenters.calendar import build_calendar_event_payload
from frontend.selectors.calendar import ASSIGNMENT_SOURCE


def _clamped_span(start_date, end_date, period_start, period_end):
    total_days = (period_end - period_start).days + 1
    if total_days <= 0:
        return {
            "start_percent": 0.0,
            "width_percent": 100.0,
            "starts_before": False,
            "ends_after": False,
        }
    visible_start = max(start_date, period_start)
    visible_end = min(end_date, period_end)
    if visible_end < visible_start:
        return {
            "start_percent": 0.0,
            "width_percent": 0.0,
            "starts_before": start_date < period_start,
            "ends_after": end_date > period_end,
        }
    start_percent = (visible_start - period_start).days / total_days * 100.0
    width_percent = (
        (visible_end - visible_start).days + 1
    ) / total_days * 100.0
    return {
        "start_percent": round(start_percent, 2),
        "width_percent": max(round(width_percent, 2), 2.0),
        "starts_before": start_date < period_start,
        "ends_after": end_date > period_end,
    }


def build_timeline_bands(events, *, period_start, period_end):
    """Position one display band per event inside the stored project period."""

    bands = []
    for event in events:
        span = _clamped_span(
            event.start_date, event.end_date, period_start, period_end
        )
        bands.append(
            {
                "event": event,
                "source": event.source,
                "label": event.title,
                "start_percent": span["start_percent"],
                "width_percent": span["width_percent"],
                "starts_before": span["starts_before"],
                "ends_after": span["ends_after"],
            }
        )
    return tuple(bands)


def _coverage_url(assignment_id, project_id, user):
    if not (
        user.has_perm("core.view_project")
        and user.has_perm("core.view_projectskillrequirement")
        and user.has_perm("core.view_assignment")
        and user.has_perm("core.view_assignmentskill")
    ):
        return None
    return reverse(
        "frontend:project_assignment_coverage",
        args=[project_id, assignment_id],
    )


def build_timeline_table_rows(
    events, *, project_id, user, link_access, filter_context
):
    """Reuse the endpoint payload so rows match the shared contract exactly."""

    rows = []
    for event in events:
        payload = build_calendar_event_payload(
            event,
            link_access=link_access,
            filter_context=filter_context,
        )
        if event.source == ASSIGNMENT_SOURCE:
            coverage_url = _coverage_url(event.record_id, project_id, user)
            if coverage_url is not None:
                payload["links"] = [
                    *payload["links"],
                    {
                        "kind": "coverage",
                        "label": "View coverage",
                        "url": coverage_url,
                    },
                ]
        rows.append(
            {
                "event": payload,
                "start_date_value": event.start_date,
                "end_date_value": event.end_date,
            }
        )
    return tuple(rows)
