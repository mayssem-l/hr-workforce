from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import formats

from core.models import Employee, Project
from core.services.availability import get_working_days, has_approved_leave
from core.services.effective_availability import (
    calculate_daily_available_hours,
    calculate_daily_capacity_hours,
)
from core.services.workload import (
    calculate_current_workload,
    calculate_daily_allocated_hours,
)


AVAILABILITY_BANDS = (
    ("none", "No effective capacity", "0% available"),
    ("limited", "Limited capacity", "More than 0% and less than 25%"),
    ("partial", "Partial capacity", "25% to less than 75%"),
    ("strong", "Strong capacity", "75% or more"),
)

UTILIZATION_BANDS = (
    ("unallocated", "Unallocated", "0% scheduled"),
    ("light", "Light utilization", "More than 0% and less than 50%"),
    ("moderate", "Moderate utilization", "50% to less than 80%"),
    ("high", "High utilization", "80% to 100%"),
    ("over_capacity", "Over capacity", "More than 100%"),
)


def _choice_label(value, choices, default):
    return dict(choices).get(value, default)


def build_reporting_period_context(filters):
    """Shape the shared inclusive date contract for display and links."""

    query_values = {
        "start_date": filters["start_date"].isoformat(),
        "end_date": filters["end_date"].isoformat(),
    }
    return {
        "start_date": filters["start_date"],
        "end_date": filters["end_date"],
        "start_date_label": formats.date_format(filters["start_date"], "M j, Y"),
        "end_date_label": formats.date_format(filters["end_date"], "M j, Y"),
        "period_query_string": urlencode(query_values),
    }


def build_dashboard_filter_context(filters):
    """Shape one validated filter contract for display and dashboard links."""

    period_context = build_reporting_period_context(filters)
    query_values = {
        "start_date": filters["start_date"].isoformat(),
        "end_date": filters["end_date"].isoformat(),
        "department": filters["department"],
        "employee_status": filters["employee_status"],
        "project_status": filters["project_status"],
    }
    return {
        **filters,
        **period_context,
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


def build_dashboard_kpi_summary(*, snapshot, filters):
    """Aggregate service-owned values for the validated dashboard period."""

    working_days = get_working_days(filters["start_date"], filters["end_date"])
    status_counts = Counter(employee.status for employee in snapshot.employees)
    available_hours = Decimal("0.00")
    allocated_hours = Decimal("0.00")
    approved_leave_employee_count = 0
    over_capacity_employee_count = 0
    employee_measures = []
    approved_leave_evidence = []

    for employee in snapshot.employees:
        assignment_records = employee.dashboard_assignments
        leave_records = employee.dashboard_approved_leaves
        employee_has_approved_leave = has_approved_leave(
            employee,
            filters["start_date"],
            filters["end_date"],
            leave_records=leave_records,
        )
        approved_leave_employee_count += int(employee_has_approved_leave)
        if employee_has_approved_leave:
            approved_leave_evidence.append(
                {
                    "employee": employee,
                    "leaves": tuple(leave_records),
                }
            )

        over_capacity_dates = []
        employee_capacity_hours = Decimal("0.00")
        employee_available_hours = Decimal("0.00")
        employee_allocated_hours = Decimal("0.00")
        for working_day in working_days:
            employee_capacity_hours += calculate_daily_capacity_hours(
                employee,
                working_day,
            )
            daily_available_hours = calculate_daily_available_hours(
                employee,
                working_day,
                assignment_records=assignment_records,
                leave_records=leave_records,
            )
            daily_allocated_hours = calculate_daily_allocated_hours(
                employee,
                working_day,
                assignment_records=assignment_records,
            )
            employee_available_hours += daily_available_hours
            employee_allocated_hours += daily_allocated_hours
            daily_workload = calculate_current_workload(
                employee,
                working_day,
                assignment_records=assignment_records,
            )
            if daily_workload > 100:
                over_capacity_dates.append(
                    {
                        "date": working_day,
                        "workload_percentage": daily_workload,
                    }
                )

        available_hours += employee_available_hours
        allocated_hours += employee_allocated_hours
        over_capacity_employee_count += int(bool(over_capacity_dates))
        employee_measures.append(
            {
                "employee": employee,
                "employee_id": employee.employee_id,
                "capacity_hours": employee_capacity_hours.quantize(
                    Decimal("0.01")
                ),
                "available_hours": employee_available_hours.quantize(
                    Decimal("0.01")
                ),
                "allocated_hours": employee_allocated_hours.quantize(
                    Decimal("0.01")
                ),
                "over_capacity_dates": tuple(over_capacity_dates),
            }
        )

    return {
        "headcount": {
            "total": len(snapshot.employees),
            "by_status": tuple(
                {
                    "value": status,
                    "label": label,
                    "count": status_counts[status],
                }
                for status, label in Employee.Status.choices
            ),
        },
        "available_hours": available_hours.quantize(Decimal("0.01")),
        "allocated_hours": allocated_hours.quantize(Decimal("0.01")),
        "approved_leave_employee_count": approved_leave_employee_count,
        "approved_leave_evidence": tuple(approved_leave_evidence),
        "active_project_count": snapshot.active_project_count,
        "projects": snapshot.projects,
        "over_capacity_employee_count": over_capacity_employee_count,
        "working_day_count": len(working_days),
        "has_employees": bool(snapshot.employees),
        "employee_measures": tuple(employee_measures),
    }


def get_availability_band_key(percentage):
    """Return the stable display band for an effective-capacity percentage."""

    percentage = Decimal(str(percentage))
    if percentage == 0:
        return "none"
    if percentage < 25:
        return "limited"
    if percentage < 75:
        return "partial"
    return "strong"


def get_utilization_band_key(percentage):
    """Return the stable display band for a scheduled-utilization percentage."""

    percentage = Decimal(str(percentage))
    if percentage == 0:
        return "unallocated"
    if percentage < 50:
        return "light"
    if percentage < 80:
        return "moderate"
    if percentage <= 100:
        return "high"
    return "over_capacity"


def _percentage(numerator, denominator):
    return (
        numerator / denominator * Decimal("100")
    ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _build_distribution(*, definitions, counts, total_count):
    bands = []
    for key, label, range_label in definitions:
        count = counts[key]
        share = (
            _percentage(Decimal(count), Decimal(total_count))
            if total_count
            else Decimal("0.0")
        )
        bands.append(
            {
                "key": key,
                "label": label,
                "range_label": range_label,
                "count": count,
                "share": share,
                "share_serialized": f"{share:.1f}",
            }
        )
    return bands


def build_dashboard_distributions(*, kpi_summary):
    """Shape service-backed employee measures into accessible distributions."""

    if not kpi_summary["has_employees"]:
        return {"state": "no_employees"}
    if not kpi_summary["working_day_count"]:
        return {"state": "no_working_days"}

    availability_counts = Counter()
    utilization_counts = Counter()
    unclassified_count = 0
    classifiable_measures = []
    employee_evidence = []

    for measure in kpi_summary["employee_measures"]:
        if measure["capacity_hours"] <= 0:
            unclassified_count += 1
            employee_evidence.append(
                {
                    **measure,
                    "availability_percentage": None,
                    "availability_band_key": "unclassified",
                    "availability_band_label": "Not classified",
                    "utilization_percentage": None,
                    "utilization_band_key": "unclassified",
                    "utilization_band_label": "Not classified",
                }
            )
            continue

        availability_percentage = _percentage(
            measure["available_hours"],
            measure["capacity_hours"],
        )
        utilization_percentage = _percentage(
            measure["allocated_hours"],
            measure["capacity_hours"],
        )
        availability_band_key = get_availability_band_key(availability_percentage)
        utilization_band_key = get_utilization_band_key(utilization_percentage)
        availability_counts[availability_band_key] += 1
        utilization_counts[utilization_band_key] += 1
        classifiable_measures.append(measure)
        employee_evidence.append(
            {
                **measure,
                "availability_percentage": availability_percentage,
                "availability_band_key": availability_band_key,
                "availability_band_label": next(
                    label
                    for key, label, _range_label in AVAILABILITY_BANDS
                    if key == availability_band_key
                ),
                "utilization_percentage": utilization_percentage,
                "utilization_band_key": utilization_band_key,
                "utilization_band_label": next(
                    label
                    for key, label, _range_label in UTILIZATION_BANDS
                    if key == utilization_band_key
                ),
            }
        )

    total_count = len(kpi_summary["employee_measures"])
    availability_bands = _build_distribution(
        definitions=AVAILABILITY_BANDS,
        counts=availability_counts,
        total_count=total_count,
    )
    utilization_bands = _build_distribution(
        definitions=UTILIZATION_BANDS,
        counts=utilization_counts,
        total_count=total_count,
    )

    if unclassified_count:
        unclassified_share = _percentage(
            Decimal(unclassified_count),
            Decimal(total_count),
        )
        unclassified_band = {
            "key": "unclassified",
            "label": "Not classified",
            "range_label": "No positive stored weekly capacity",
            "count": unclassified_count,
            "share": unclassified_share,
            "share_serialized": f"{unclassified_share:.1f}",
        }
        availability_bands.append(unclassified_band)
        utilization_bands.append(unclassified_band.copy())

    return {
        "state": "ready",
        "total_employee_count": total_count,
        "classified_employee_count": len(classifiable_measures),
        "unclassified_employee_count": unclassified_count,
        "employee_evidence": tuple(employee_evidence),
        "availability": {
            "bands": tuple(availability_bands),
            "all_zero": bool(classifiable_measures)
            and all(
                measure["available_hours"] == 0
                for measure in classifiable_measures
            ),
        },
        "utilization": {
            "bands": tuple(utilization_bands),
            "all_zero": bool(classifiable_measures)
            and all(
                measure["allocated_hours"] == 0
                for measure in classifiable_measures
            ),
        },
    }


def _url_with_query(view_name, values, *, args=None):
    base_url = reverse(view_name, args=args)
    query_string = urlencode(values)
    return f"{base_url}?{query_string}" if query_string else base_url


def build_dashboard_evidence_context(
    *,
    kpi_summary,
    distribution_context,
    filter_context,
):
    """Map each dashboard aggregate to exact directory or on-page evidence."""

    directory_values = {
        "start_date": filter_context["start_date"].isoformat(),
        "end_date": filter_context["end_date"].isoformat(),
        "department": filter_context["department"],
        "status": filter_context["employee_status"],
        "project_status": filter_context["project_status"],
        "sort": "name",
    }
    headcount_statuses = []
    for status in kpi_summary["headcount"]["by_status"]:
        status_values = {**directory_values, "status": status["value"]}
        headcount_statuses.append(
            {
                **status,
                "evidence_url": (
                    _url_with_query(
                        "frontend:employee_list",
                        status_values,
                    )
                    if status["count"]
                    else ""
                ),
            }
        )

    employee_measures = (
        distribution_context.get("employee_evidence", ())
        if distribution_context
        else ()
    )
    if not employee_measures:
        employee_measures = kpi_summary["employee_measures"]

    employee_rows = []
    for measure in employee_measures:
        employee = measure.get("employee")
        if employee is None:
            continue
        employee_rows.append(
            {
                **measure,
                "profile_url": _url_with_query(
                    "frontend:employee_detail",
                    {
                        "start_date": filter_context["start_date"].isoformat(),
                        "end_date": filter_context["end_date"].isoformat(),
                        "department": filter_context["department"],
                        "employee_status": filter_context["employee_status"],
                        "project_status": filter_context["project_status"],
                    },
                    args=[employee.employee_id],
                ),
            }
        )

    leave_rows = []
    for evidence in kpi_summary["approved_leave_evidence"]:
        employee = evidence["employee"]
        leave_rows.append(
            {
                **evidence,
                "profile_url": _url_with_query(
                    "frontend:employee_detail",
                    {
                        "start_date": filter_context["start_date"].isoformat(),
                        "end_date": filter_context["end_date"].isoformat(),
                        "department": filter_context["department"],
                        "employee_status": filter_context["employee_status"],
                        "project_status": filter_context["project_status"],
                    },
                    args=[employee.employee_id],
                ),
                "records_url": _url_with_query(
                    "frontend:leave_list",
                    {
                        "employee": employee.employee_id,
                        "status": "approved",
                        "from_date": filter_context["start_date"].isoformat(),
                        "to_date": filter_context["end_date"].isoformat(),
                        "sort": "start_date_asc",
                    },
                ),
            }
        )

    for distribution_name in ("availability", "utilization"):
        distribution = distribution_context.get(distribution_name, {})
        for band in distribution.get("bands", ()):
            band["evidence_url"] = (
                "#employee-capacity-evidence" if band["count"] else ""
            )

    return {
        "headcount": {
            "evidence_url": _url_with_query(
                "frontend:employee_list",
                directory_values,
            ),
            "statuses": tuple(headcount_statuses),
        },
        "employee_rows": tuple(employee_rows),
        "leave_rows": tuple(leave_rows),
        "project_rows": tuple(
            {"project": project} for project in kpi_summary["projects"]
        ),
        "available_capacity_url": "#employee-capacity-evidence",
        "allocated_capacity_url": "#employee-capacity-evidence",
        "approved_leave_url": "#approved-leave-evidence",
        "project_url": "#project-period-evidence",
        "over_capacity_url": "#employee-capacity-evidence",
    }


def build_employee_navigation_context(filter_context):
    """Translate dashboard context into links each destination understands."""

    return {
        "dashboard_url": _url_with_query(
            "frontend:landing",
            {
                "start_date": filter_context["start_date"].isoformat(),
                "end_date": filter_context["end_date"].isoformat(),
                "department": filter_context["department"],
                "employee_status": filter_context["employee_status"],
                "project_status": filter_context["project_status"],
            },
        ),
        "workforce_url": _url_with_query(
            "frontend:employee_list",
            {
                "start_date": filter_context["start_date"].isoformat(),
                "end_date": filter_context["end_date"].isoformat(),
                "department": filter_context["department"],
                "status": filter_context["employee_status"],
                "project_status": filter_context["project_status"],
                "sort": "name",
            },
        ),
    }


def build_operational_directory_navigation(
    *,
    start_date,
    end_date,
    employee_id="",
):
    """Preserve supported period context from operational evidence links."""

    period_values = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    context = {
        "dashboard_url": _url_with_query(
            "frontend:landing",
            period_values,
        ),
        "profile_query_string": urlencode(period_values),
        "employee_profile_url": "",
    }
    if str(employee_id or "").isdigit():
        context["employee_profile_url"] = _url_with_query(
            "frontend:employee_detail",
            period_values,
            args=[employee_id],
        )
    return context
