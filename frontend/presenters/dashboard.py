from urllib.parse import urlencode

from django.utils import formats

from core.models import Employee, Project


def _choice_label(value, choices, default):
    return dict(choices).get(value, default)


def build_dashboard_filter_context(filters):
    """Shape one validated filter contract for display and dashboard links."""

    query_values = {
        "start_date": filters["start_date"].isoformat(),
        "end_date": filters["end_date"].isoformat(),
        "department": filters["department"],
        "employee_status": filters["employee_status"],
        "project_status": filters["project_status"],
    }
    return {
        **filters,
        "start_date_label": formats.date_format(filters["start_date"], "M j, Y"),
        "end_date_label": formats.date_format(filters["end_date"], "M j, Y"),
        "department_label": filters["department"] or "All departments",
        "employee_status_label": _choice_label(
            filters["employee_status"],
            Employee.Status.choices,
            "All employee statuses",
        ),
        "project_status_label": _choice_label(
            filters["project_status"],
            Project.Status.choices,
            "All project statuses",
        ),
        "active_optional_filter_count": sum(
            bool(filters[name])
            for name in ("department", "employee_status", "project_status")
        ),
        "query_string": urlencode(query_values),
    }
