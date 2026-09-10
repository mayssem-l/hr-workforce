import statistics
import time
from datetime import date, timedelta
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.staticfiles import finders
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import Assignment, Attendance, Employee, Leave, Project
from core.services.effective_availability import calculate_daily_available_hours
from core.services.workload import (
    calculate_available_hours,
    calculate_current_workload,
)
from frontend.roles import VIEWER_GROUP, sync_role_permissions
from frontend.selectors.employees import get_employee_profile


class _MarkupAudit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.references = []
        self.headings = []
        self.tables = []
        self._table_stack = []
        self.positive_tabindex = []
        self.inline_handlers = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.ids.append(element_id)
        for attribute in ("aria-labelledby", "aria-describedby"):
            if attributes.get(attribute):
                self.references.extend(attributes[attribute].split())
        if len(tag) == 2 and tag.startswith("h") and tag[1].isdigit():
            self.headings.append(int(tag[1]))
        if tag == "table":
            table = {"has_caption": False, "header_scopes": []}
            self.tables.append(table)
            self._table_stack.append(table)
        elif tag == "caption" and self._table_stack:
            self._table_stack[-1]["has_caption"] = True
        elif tag == "th" and self._table_stack:
            self._table_stack[-1]["header_scopes"].append(
                attributes.get("scope")
            )
        tabindex = attributes.get("tabindex")
        if tabindex and tabindex.lstrip("-").isdigit() and int(tabindex) > 0:
            self.positive_tabindex.append((tag, tabindex))
        self.inline_handlers.extend(
            attribute
            for attribute in attributes
            if attribute.startswith("on")
        )

    def handle_endtag(self, tag):
        if tag == "table" and self._table_stack:
            self._table_stack.pop()


class Milestone4HardeningTests(TestCase):
    AS_OF = date(2026, 1, 15)
    START_DATE = date(2026, 1, 1)
    END_DATE = date(2026, 1, 31)
    DASHBOARD_QUERY_COUNT = 9
    PROFILE_QUERY_COUNT = 10
    TIMING_SAMPLE_COUNT = 7

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="m4-hardening-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))

        cls.employees = [
            Employee.objects.create(
                first_name=f"Employee {index:02d}",
                last_name="Evidence",
                department="Engineering",
                position="Engineer",
                hire_date=date(2020, 1, 6),
                experience_years=Decimal("6.0"),
                capacity_hours_week=Decimal("40.00"),
                status=Employee.Status.ACTIVE,
            )
            for index in range(24)
        ]
        cls.filtered_empty_employee = Employee.objects.create(
            first_name="Inactive",
            last_name="Operations",
            department="Operations",
            position="Coordinator",
            hire_date=date(2021, 2, 1),
            experience_years=Decimal("4.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.INACTIVE,
        )
        cls.projects = [
            Project.objects.create(
                name=f"Hardening Project {index}",
                description="Milestone 4 query and boundary verification.",
                start_date=cls.START_DATE,
                end_date=date(2026, 12, 31),
                estimated_hours=Decimal("240.00"),
                status=Project.Status.IN_PROGRESS,
                priority=Project.Priority.MEDIUM,
                criticality=Project.Criticality.MEDIUM,
            )
            for index in range(3)
        ]
        Assignment.objects.bulk_create(
            [
                Assignment(
                    employee=employee,
                    project=cls.projects[project_index],
                    start_date=cls.START_DATE,
                    end_date=date(2026, 12, 31),
                    allocation_percentage=allocation,
                    role_on_project="Contributor",
                    status=Assignment.Status.ACTIVE,
                )
                for employee in cls.employees
                for project_index, allocation in ((0, 40), (1, 20))
            ]
        )
        cls.completed_current_assignment = Assignment.objects.create(
            employee=cls.employees[0],
            project=cls.projects[2],
            start_date=cls.AS_OF,
            end_date=cls.AS_OF,
            allocation_percentage=25,
            role_on_project="Closeout reviewer",
            status=Assignment.Status.COMPLETED,
        )
        Leave.objects.bulk_create(
            [
                Leave(
                    employee=employee,
                    start_date=cls.AS_OF,
                    end_date=cls.AS_OF,
                    type=Leave.Type.ANNUAL,
                    status=Leave.Status.APPROVED,
                )
                for employee in cls.employees[::4]
            ]
        )
        attendance_statuses = tuple(Attendance.Status.values)
        Attendance.objects.bulk_create(
            [
                Attendance(
                    employee=cls.employees[0],
                    date=cls.START_DATE + timedelta(days=index),
                    status=attendance_statuses[index % len(attendance_statuses)],
                )
                for index in range(20)
            ]
        )

    def setUp(self):
        self.client.force_login(self.viewer)

    def dashboard_data(self, **overrides):
        data = {
            "start_date": self.START_DATE.isoformat(),
            "end_date": self.END_DATE.isoformat(),
            "department": "Engineering",
            "employee_status": Employee.Status.ACTIVE,
            "project_status": Project.Status.IN_PROGRESS,
        }
        data.update(overrides)
        return data

    def profile_url(self, **overrides):
        query = self.dashboard_data(**overrides)
        return (
            reverse(
                "frontend:employee_detail",
                args=[self.employees[0].employee_id],
            )
            + "?"
            + "&".join(f"{key}={value}" for key, value in query.items())
        )

    def assert_accessible_markup(self, response):
        html = response.content.decode("utf-8")
        audit = _MarkupAudit()
        audit.feed(html)

        self.assertIn('<html lang="en">', html)
        self.assertLess(html.index('class="skip-link"'), html.index("<main"))
        self.assertIn('class="skip-link" href="#main-content"', html)
        self.assertIn('<main class="app-main" id="main-content" tabindex="-1">', html)
        self.assertEqual(len(audit.ids), len(set(audit.ids)))
        self.assertFalse(set(audit.references) - set(audit.ids))
        self.assertTrue(audit.headings)
        self.assertEqual(audit.headings[0], 1)
        self.assertTrue(
            all(
                current <= previous + 1
                for previous, current in zip(
                    audit.headings,
                    audit.headings[1:],
                )
            )
        )
        self.assertTrue(audit.tables)
        self.assertTrue(all(table["has_caption"] for table in audit.tables))
        self.assertTrue(
            all(
                scope in {"col", "row"}
                for table in audit.tables
                for scope in table["header_scopes"]
            )
        )
        self.assertFalse(audit.positive_tabindex)
        self.assertFalse(audit.inline_handlers)

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_dashboard_and_profile_keep_accessible_evidence_structure(
        self,
        _localdate,
    ):
        dashboard = self.client.get(
            reverse("frontend:landing"),
            self.dashboard_data(),
        )
        profile = self.client.get(self.profile_url())

        self.assert_accessible_markup(dashboard)
        self.assert_accessible_markup(profile)
        self.assertContains(
            dashboard,
            'class="distribution-visual" aria-hidden="true"',
            count=2,
        )
        self.assertContains(
            profile,
            'class="employee-timeline-strip" aria-hidden="true"',
        )
        self.assertContains(
            profile,
            'class="attendance-timeline-strip" aria-hidden="true"',
        )
        self.assertContains(dashboard, "Effective available capacity bands")
        self.assertContains(profile, "Daily workload and effective availability")
        self.assertContains(profile, "Attendance status counts and record shares")
        self.assertContains(profile, "Chronological recorded attendance evidence")
        self.assertContains(dashboard, "Active")
        self.assertContains(profile, "Availability remaining")
        self.assertContains(profile, "Recorded as present")
        self.assertNotContains(dashboard, "<canvas")
        self.assertNotContains(profile, "<canvas")

        theme_path = finders.find("frontend/css/theme.css")
        self.assertIsNotNone(theme_path)
        theme = Path(theme_path).read_text(encoding="utf-8")
        self.assertIn(":focus-visible", theme)
        self.assertIn(".skip-link:focus", theme)
        self.assertIn("@media (prefers-reduced-motion: reduce)", theme)

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_shared_range_limit_accepts_366_days_and_rejects_367(
        self,
        _localdate,
    ):
        accepted = {
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "department": "Engineering",
            "employee_status": "active",
            "project_status": "",
        }
        dashboard = self.client.get(reverse("frontend:landing"), accepted)
        profile = self.client.get(
            self.profile_url(
                start_date=accepted["start_date"],
                end_date=accepted["end_date"],
                project_status="",
            )
        )
        self.assertIsNotNone(dashboard.context["filter_context"])
        self.assertEqual(profile.context["timeline"]["working_day_count"], 262)
        self.assertEqual(len(profile.context["timeline"]["rows"]), 366)

        rejected = {**accepted, "end_date": "2025-01-01"}
        dashboard = self.client.get(reverse("frontend:landing"), rejected)
        profile = self.client.get(
            self.profile_url(
                start_date=rejected["start_date"],
                end_date=rejected["end_date"],
                project_status="",
            )
        )
        self.assertIsNone(dashboard.context["filter_context"])
        self.assertIsNone(dashboard.context["kpi_summary"])
        self.assertIsNone(profile.context["period_context"])
        self.assertIsNone(profile.context["timeline"])
        self.assertContains(
            dashboard,
            "Choose a reporting period of 366 days or fewer.",
        )
        self.assertContains(
            profile,
            "Choose a reporting period of 366 days or fewer.",
        )

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_boundary_weekend_empty_and_filtered_empty_states_remain_distinct(
        self,
        _localdate,
    ):
        weekend_data = self.dashboard_data(
            start_date="2026-01-03",
            end_date="2026-01-04",
        )
        dashboard = self.client.get(reverse("frontend:landing"), weekend_data)
        profile = self.client.get(
            self.profile_url(
                start_date="2026-01-03",
                end_date="2026-01-04",
            )
        )
        self.assertEqual(
            dashboard.context["distribution_context"]["state"],
            "no_working_days",
        )
        self.assertEqual(profile.context["timeline"]["working_day_count"], 0)
        self.assertTrue(
            all(
                row["state_key"] == "weekend"
                for row in profile.context["timeline"]["rows"]
            )
        )

        filtered_empty = self.client.get(
            reverse("frontend:landing"),
            self.dashboard_data(
                department="Operations",
                employee_status=Employee.Status.ACTIVE,
            ),
        )
        self.assertEqual(
            filtered_empty.context["distribution_context"]["state"],
            "no_employees",
        )
        self.assertContains(
            filtered_empty,
            "No employees match the workforce filters.",
        )

        Employee.objects.all().delete()
        Project.objects.all().delete()
        empty = self.client.get(
            reverse("frontend:landing"),
            {
                "start_date": self.START_DATE.isoformat(),
                "end_date": self.END_DATE.isoformat(),
            },
        )
        self.assertEqual(empty.context["kpi_summary"]["headcount"]["total"], 0)
        self.assertEqual(empty.context["kpi_summary"]["active_project_count"], 0)
        self.assertContains(empty, "No employee evidence matches these filters")
        self.assertContains(empty, "No project evidence matches this period")

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_repeated_results_and_employee_pagination_are_deterministic(
        self,
        _localdate,
    ):
        snapshots = []
        for _ in range(3):
            response = self.client.get(
                reverse("frontend:landing"),
                self.dashboard_data(),
            )
            summary = response.context["kpi_summary"]
            distributions = response.context["distribution_context"]
            snapshots.append(
                (
                    summary["headcount"]["total"],
                    summary["available_hours"],
                    summary["allocated_hours"],
                    summary["approved_leave_employee_count"],
                    summary["active_project_count"],
                    summary["over_capacity_employee_count"],
                    tuple(
                        (band["key"], band["count"], band["share_serialized"])
                        for name in ("availability", "utilization")
                        for band in distributions[name]["bands"]
                    ),
                    tuple(
                        row["employee"].employee_id
                        for row in response.context["evidence_context"][
                            "employee_rows"
                        ]
                    ),
                )
            )
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(snapshots[1], snapshots[2])

        directory_url = reverse("frontend:employee_list")
        directory_data = {
            "department": "Engineering",
            "status": "active",
            "sort": "name",
        }
        first_page = self.client.get(directory_url, directory_data)
        second_page = self.client.get(
            directory_url,
            {**directory_data, "page": 2},
        )
        repeated_second_page = self.client.get(
            directory_url,
            {**directory_data, "page": 2},
        )
        first_ids = [row.employee_id for row in first_page.context["page_obj"]]
        second_ids = [row.employee_id for row in second_page.context["page_obj"]]
        repeated_ids = [
            row.employee_id for row in repeated_second_page.context["page_obj"]
        ]
        self.assertEqual(len(first_ids), 20)
        self.assertEqual(len(second_ids), 4)
        self.assertFalse(set(first_ids) & set(second_ids))
        self.assertEqual(second_ids, repeated_ids)

    def test_prefetched_profile_values_match_default_service_paths(self):
        employee = self.employees[0]
        legacy_workload = calculate_current_workload(employee, self.AS_OF)
        legacy_weekly = calculate_available_hours(employee, self.AS_OF)
        legacy_daily = calculate_daily_available_hours(employee, self.AS_OF)

        selected = get_employee_profile(
            employee.employee_id,
            on_date=self.AS_OF,
            timeline_start_date=self.START_DATE,
            timeline_end_date=self.END_DATE,
            include_attendance=True,
        )
        self.assertIn(
            self.completed_current_assignment.assignment_id,
            {
                assignment.assignment_id
                for assignment in selected.profile_calculation_assignments
            },
        )
        with self.assertNumQueries(0):
            prefetched_workload = calculate_current_workload(
                selected,
                self.AS_OF,
                assignment_records=selected.profile_calculation_assignments,
            )
            prefetched_weekly = calculate_available_hours(
                selected,
                self.AS_OF,
                assignment_records=selected.profile_calculation_assignments,
            )
            prefetched_daily = calculate_daily_available_hours(
                selected,
                self.AS_OF,
                assignment_records=selected.profile_calculation_assignments,
                leave_records=selected.profile_calculation_leaves,
            )
        self.assertEqual(prefetched_workload, legacy_workload)
        self.assertEqual(prefetched_weekly, legacy_weekly)
        self.assertEqual(prefetched_daily, legacy_daily)

    def _measure(self, url, data, expected_queries):
        warmup = self.client.get(url, data)
        self.assertEqual(warmup.status_code, 200)
        durations = []
        response_sizes = []
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as captured_queries:
                started_at = time.perf_counter()
                response = self.client.get(url, data)
                durations.append((time.perf_counter() - started_at) * 1000)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(captured_queries), expected_queries)
            response_sizes.append(len(response.content))
        return {
            "median": statistics.median(durations),
            "p95": statistics.quantiles(
                durations,
                n=20,
                method="inclusive",
            )[18],
            "minimum": min(durations),
            "maximum": max(durations),
            "response_bytes": max(response_sizes),
        }

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_final_query_and_warm_performance_baselines(self, _localdate):
        dashboard_url = reverse("frontend:landing")
        profile_base = reverse(
            "frontend:employee_detail",
            args=[self.employees[0].employee_id],
        )
        month_data = self.dashboard_data()
        year_data = self.dashboard_data(
            start_date="2024-01-01",
            end_date="2024-12-31",
            project_status="",
        )

        measurements = (
            (
                "dashboard, 24 employees, 31 days",
                self.DASHBOARD_QUERY_COUNT,
                self._measure(
                    dashboard_url,
                    month_data,
                    self.DASHBOARD_QUERY_COUNT,
                ),
            ),
            (
                "employee timeline and attendance, 31 days",
                self.PROFILE_QUERY_COUNT,
                self._measure(
                    profile_base,
                    month_data,
                    self.PROFILE_QUERY_COUNT,
                ),
            ),
            (
                "dashboard, 24 employees, 366 days",
                self.DASHBOARD_QUERY_COUNT,
                self._measure(
                    dashboard_url,
                    year_data,
                    self.DASHBOARD_QUERY_COUNT,
                ),
            ),
            (
                "employee timeline and attendance, 366 days",
                self.PROFILE_QUERY_COUNT,
                self._measure(
                    profile_base,
                    year_data,
                    self.PROFILE_QUERY_COUNT,
                ),
            ),
        )
        print("\nM4.7 final warm Django test-client baselines:")
        for label, queries, measurement in measurements:
            print(
                f"  {label}: queries={queries}, "
                f"median={measurement['median']:.3f} ms, "
                f"p95={measurement['p95']:.3f} ms, "
                f"min={measurement['minimum']:.3f} ms, "
                f"max={measurement['maximum']:.3f} ms, "
                f"response={measurement['response_bytes']} bytes"
            )

