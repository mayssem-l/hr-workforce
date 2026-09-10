import re
import statistics
import time
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import Assignment, Employee, Project
from core.services.effective_availability import calculate_daily_capacity_hours
from frontend.presenters.dashboard import (
    build_dashboard_distributions,
    get_availability_band_key,
    get_utilization_band_key,
)
from frontend.roles import VIEWER_GROUP, sync_role_permissions


class DashboardDistributionTests(TestCase):
    REPORT_DATE = date(2026, 9, 7)
    EXPECTED_QUERY_COUNT = 9
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="distribution-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.project = Project.objects.create(
            name="Distribution project",
            description="Project used to verify dashboard distributions.",
            start_date=cls.REPORT_DATE,
            end_date=cls.REPORT_DATE,
            estimated_hours=Decimal("40.00"),
            status=Project.Status.IN_PROGRESS,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )

        cls.free = cls.create_employee("Free", "Capacity", "Engineering")
        cls.light = cls.create_employee("Light", "Load", "Engineering")
        cls.partial = cls.create_employee("Partial", "Capacity", "Finance")
        cls.limited = cls.create_employee("Limited", "Capacity", "Finance")
        cls.over = cls.create_employee("Over", "Capacity", "Finance")
        cls.zero_capacity = cls.create_employee(
            "Missing",
            "Capacity",
            "Finance",
            capacity="0.00",
        )
        cls.create_employee(
            "Inactive",
            "Employee",
            "Operations",
            status=Employee.Status.INACTIVE,
        )

        Assignment.objects.bulk_create(
            [
                cls.assignment(cls.light, 20),
                cls.assignment(cls.partial, 50),
                cls.assignment(cls.limited, 80),
                cls.assignment(cls.over, 60),
                cls.assignment(cls.over, 50),
            ]
        )

    @classmethod
    def create_employee(
        cls,
        first_name,
        last_name,
        department,
        *,
        status=Employee.Status.ACTIVE,
        capacity="40.00",
    ):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department=department,
            position="Specialist",
            hire_date=date(2021, 1, 4),
            experience_years=Decimal("5.0"),
            capacity_hours_week=Decimal(capacity),
            status=status,
        )

    @classmethod
    def assignment(cls, employee, allocation):
        return Assignment(
            employee=employee,
            project=cls.project,
            start_date=cls.REPORT_DATE,
            end_date=cls.REPORT_DATE,
            allocation_percentage=allocation,
            role_on_project="Contributor",
            status=Assignment.Status.ACTIVE,
        )

    def setUp(self):
        self.url = reverse("frontend:landing")
        self.client.force_login(self.viewer)

    def filter_data(self, **overrides):
        data = {
            "start_date": self.REPORT_DATE.isoformat(),
            "end_date": self.REPORT_DATE.isoformat(),
            "department": "",
            "employee_status": Employee.Status.ACTIVE,
            "project_status": "",
        }
        data.update(overrides)
        return data

    def test_capacity_and_utilization_band_boundaries_are_stable(self):
        availability_cases = {
            "0": "none",
            "0.1": "limited",
            "24.9": "limited",
            "25": "partial",
            "74.9": "partial",
            "75": "strong",
            "100": "strong",
        }
        utilization_cases = {
            "0": "unallocated",
            "0.1": "light",
            "49.9": "light",
            "50": "moderate",
            "79.9": "moderate",
            "80": "high",
            "100": "high",
            "100.1": "over_capacity",
        }

        for percentage, expected in availability_cases.items():
            with self.subTest(distribution="availability", percentage=percentage):
                self.assertEqual(
                    get_availability_band_key(Decimal(percentage)),
                    expected,
                )
        for percentage, expected in utilization_cases.items():
            with self.subTest(distribution="utilization", percentage=percentage):
                self.assertEqual(
                    get_utilization_band_key(Decimal(percentage)),
                    expected,
                )

    def test_distribution_shaping_uses_exact_period_measures_and_serializes_stably(self):
        measures = (
            self.measure("100", "0", "0"),
            self.measure("100", "24.9", "49.9"),
            self.measure("100", "25", "50"),
            self.measure("100", "75", "80"),
            self.measure("100", "100", "100.1"),
            self.measure("0", "0", "0"),
        )

        distributions = build_dashboard_distributions(
            kpi_summary=self.summary(measures)
        )

        self.assertEqual(distributions["state"], "ready")
        self.assertEqual(distributions["total_employee_count"], 6)
        self.assertEqual(distributions["classified_employee_count"], 5)
        self.assertEqual(distributions["unclassified_employee_count"], 1)
        self.assertEqual(
            self.band_counts(distributions["availability"]),
            {
                "none": 1,
                "limited": 1,
                "partial": 1,
                "strong": 2,
                "unclassified": 1,
            },
        )
        self.assertEqual(
            self.band_counts(distributions["utilization"]),
            {
                "unallocated": 1,
                "light": 1,
                "moderate": 1,
                "high": 1,
                "over_capacity": 1,
                "unclassified": 1,
            },
        )
        self.assertEqual(
            [band["share_serialized"] for band in distributions["availability"]["bands"]],
            ["16.7", "16.7", "16.7", "33.3", "16.7"],
        )

    def test_dashboard_renders_tables_before_matching_supplemental_bars(self):
        response = self.client.get(self.url, self.filter_data())

        self.assertEqual(response.status_code, 200)
        distributions = response.context["distribution_context"]
        self.assertEqual(distributions["state"], "ready")
        self.assertEqual(
            self.band_counts(distributions["availability"]),
            {
                "none": 1,
                "limited": 1,
                "partial": 1,
                "strong": 2,
                "unclassified": 1,
            },
        )
        self.assertEqual(
            self.band_counts(distributions["utilization"]),
            {
                "unallocated": 1,
                "light": 1,
                "moderate": 1,
                "high": 1,
                "over_capacity": 1,
                "unclassified": 1,
            },
        )

        self.assertContains(response, "Capacity and utilization distributions")
        self.assertContains(response, "Available capacity distribution")
        self.assertContains(response, "Utilization distribution")
        self.assertContains(
            response,
            '<table class="table distribution-table">',
            count=2,
        )
        self.assertContains(
            response,
            "Effective available capacity bands for the filtered workforce",
            count=1,
        )
        self.assertContains(
            response,
            "Scheduled utilization bands for the filtered workforce",
            count=1,
        )
        self.assertContains(
            response,
            'class="distribution-visual" aria-hidden="true"',
            count=2,
        )
        self.assertContains(response, "No positive stored weekly capacity", count=2)
        self.assertNotContains(response, "<canvas")

        html = response.content.decode("utf-8")
        first_table = html.index('<table class="table distribution-table">')
        first_visual = html.index('<div class="distribution-visual"')
        self.assertLess(first_table, first_visual)
        for distribution_name in ("availability", "utilization"):
            for band in distributions[distribution_name]["bands"]:
                with self.subTest(
                    distribution=distribution_name,
                    band=band["key"],
                ):
                    self.assertRegex(
                        html,
                        rf'(?s)<tr data-distribution-band="{re.escape(band["key"])}">'
                        rf'.*?<td class="text-end">{band["count"]}</td>'
                        rf'.*?<td class="text-end">{band["share_serialized"]}%</td>'
                        r'.*?</tr>',
                    )
                    self.assertContains(
                        response,
                        f'data-distribution-band="{band["key"]}" '
                        f'data-count="{band["count"]}" '
                        f'data-share="{band["share_serialized"]}"',
                    )
                    self.assertContains(
                        response,
                        f'--distribution-share: {band["share_serialized"]}%;',
                    )

    def test_department_filter_changes_distribution_without_changing_band_rules(self):
        response = self.client.get(
            self.url,
            self.filter_data(department="Engineering"),
        )

        distributions = response.context["distribution_context"]
        self.assertEqual(distributions["total_employee_count"], 2)
        self.assertEqual(
            self.band_counts(distributions["availability"]),
            {
                "none": 0,
                "limited": 0,
                "partial": 0,
                "strong": 2,
            },
        )
        self.assertEqual(
            self.band_counts(distributions["utilization"]),
            {
                "unallocated": 1,
                "light": 1,
                "moderate": 0,
                "high": 0,
                "over_capacity": 0,
            },
        )

    def test_no_employee_no_working_day_and_invalid_filter_states_are_distinct(self):
        no_employees = self.client.get(
            self.url,
            self.filter_data(employee_status=Employee.Status.ON_LEAVE),
        )
        self.assertEqual(
            no_employees.context["distribution_context"]["state"],
            "no_employees",
        )
        self.assertContains(no_employees, "No distribution is available.")

        weekend = self.client.get(
            self.url,
            self.filter_data(start_date="2026-09-12", end_date="2026-09-13"),
        )
        self.assertEqual(
            weekend.context["distribution_context"]["state"],
            "no_working_days",
        )
        self.assertContains(weekend, "No working-day distribution is available.")
        self.assertContains(weekend, "are not presented as zero")

        invalid = self.client.get(
            self.url,
            self.filter_data(start_date="2026-09-08", end_date="2026-09-07"),
        )
        self.assertIsNone(invalid.context["distribution_context"])
        self.assertNotContains(invalid, "Capacity and utilization distributions")

    def test_all_zero_signals_and_zero_capacity_have_clear_nonmisleading_states(self):
        response = self.client.get(
            self.url,
            self.filter_data(
                department="Operations",
                employee_status=Employee.Status.INACTIVE,
            ),
        )

        distributions = response.context["distribution_context"]
        self.assertTrue(distributions["availability"]["all_zero"])
        self.assertTrue(distributions["utilization"]["all_zero"])
        self.assertContains(
            response,
            "All classified employees have no effective available hours.",
        )
        self.assertContains(response, "No scheduled assignment hours in this period.")

        zero_capacity_response = self.client.get(
            self.url,
            self.filter_data(department="Finance"),
        )
        self.assertEqual(
            zero_capacity_response.context["distribution_context"][
                "unclassified_employee_count"
            ],
            1,
        )
        self.assertContains(zero_capacity_response, "not classified")
        self.assertContains(
            zero_capacity_response,
            "does not present missing capacity context as 0%",
        )

    def test_daily_capacity_service_preserves_weekday_and_weekend_assumptions(self):
        self.assertEqual(
            calculate_daily_capacity_hours(self.free, self.REPORT_DATE),
            Decimal("8.00"),
        )
        self.assertEqual(
            calculate_daily_capacity_hours(self.free, date(2026, 9, 12)),
            Decimal("0.00"),
        )

    def test_distribution_rendering_keeps_populated_query_count_fixed(self):
        with self.assertNumQueries(self.EXPECTED_QUERY_COUNT):
            response = self.client.get(self.url, self.filter_data())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["distribution_context"]["state"], "ready")

    def test_warm_distribution_response_time_is_recorded(self):
        warmup_response = self.client.get(self.url, self.filter_data())
        self.assertEqual(warmup_response.status_code, 200)

        durations_ms = []
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as captured_queries:
                started_at = time.perf_counter()
                response = self.client.get(self.url, self.filter_data())
                durations_ms.append((time.perf_counter() - started_at) * 1000)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(captured_queries), self.EXPECTED_QUERY_COUNT)

        p95_ms = statistics.quantiles(
            durations_ms,
            n=20,
            method="inclusive",
        )[18]
        print(
            "\nM4.3 distribution dashboard baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            "7 employees, 1 working day):\n"
            f"  queries={self.EXPECTED_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )

    @staticmethod
    def measure(capacity, available, allocated):
        return {
            "employee_id": 1,
            "capacity_hours": Decimal(capacity),
            "available_hours": Decimal(available),
            "allocated_hours": Decimal(allocated),
        }

    @staticmethod
    def summary(measures, *, has_employees=True, working_day_count=1):
        return {
            "has_employees": has_employees,
            "working_day_count": working_day_count,
            "employee_measures": measures,
        }

    @staticmethod
    def band_counts(distribution):
        return {band["key"]: band["count"] for band in distribution["bands"]}
