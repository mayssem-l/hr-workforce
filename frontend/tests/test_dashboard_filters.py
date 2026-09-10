import statistics
import time
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from core.models import Employee, Project
from frontend.roles import VIEWER_GROUP, sync_role_permissions


class DashboardFilterTests(TestCase):
    EXPECTED_QUERY_COUNT = 9
    TIMING_SAMPLE_COUNT = 25
    TODAY = date(2026, 9, 9)

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(username="dashboard-viewer")
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.unassigned = get_user_model().objects.create_user(
            username="dashboard-unassigned"
        )
        cls.employee_only = get_user_model().objects.create_user(
            username="dashboard-employee-only"
        )
        cls.employee_only.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename="view_employee",
            )
        )
        cls.project_only = get_user_model().objects.create_user(
            username="dashboard-project-only"
        )
        cls.project_only.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename="view_project",
            )
        )
        cls._create_employee("Maurice", "Joly", "Engineering")
        cls._create_employee("Jeanne", "Briand", "Finance")

    @classmethod
    def _create_employee(cls, first_name, last_name, department):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department=department,
            position="Workforce Specialist",
            hire_date=date(2022, 1, 3),
            experience_years=Decimal("4.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )

    def setUp(self):
        self.url = reverse("frontend:landing")
        self.client.force_login(self.viewer)

    def _get(self, data=None):
        with patch(
            "frontend.views.landing.timezone.localdate",
            return_value=self.TODAY,
        ):
            return self.client.get(self.url, data or {})

    def test_route_template_navigation_and_read_only_dashboard_frame(self):
        self.assertEqual(self.url, "/")
        match = resolve(self.url)
        self.assertEqual(match.view_name, "frontend:landing")

        response = self._get()

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/dashboard/landing.html")
        self.assertContains(response, "<h1>Workforce overview</h1>", html=True)
        self.assertContains(response, "Reporting filters")
        self.assertContains(response, "Current reporting context")
        self.assertContains(response, "Inclusive period")
        self.assertContains(response, "Monday&ndash;Friday")
        self.assertNotContains(response, "Your workforce planning workspace")
        self.assertNotContains(response, "Coming soon")
        self.assertNotContains(response, "<canvas")
        self.assertRegex(
            response.content.decode("utf-8"),
            r'href="/"\s+aria-current="page"',
        )
        self.assertContains(response, '<form method="get" action="/">', html=False)

    def test_default_period_is_the_inclusive_current_calendar_month(self):
        response = self._get()

        form = response.context["filter_form"]
        context = response.context["filter_context"]
        self.assertEqual(form["start_date"].value(), "2026-09-01")
        self.assertEqual(form["end_date"].value(), "2026-09-30")
        self.assertEqual(context["start_date"], date(2026, 9, 1))
        self.assertEqual(context["end_date"], date(2026, 9, 30))
        self.assertContains(response, "Start and end dates are both included.")

    def test_partial_query_uses_defaults_for_omitted_period_dates(self):
        response = self._get({"department": "Engineering"})

        self.assertTrue(response.context["filter_form"].is_valid())
        self.assertEqual(
            response.context["filter_context"]["start_date"],
            date(2026, 9, 1),
        )
        self.assertEqual(
            response.context["filter_context"]["department"],
            "Engineering",
        )

    def test_valid_filters_are_summarized_and_preserved_in_dashboard_link(self):
        response = self._get(
            {
                "start_date": "2026-08-15",
                "end_date": "2026-09-09",
                "department": "Engineering",
                "employee_status": Employee.Status.ACTIVE,
                "project_status": Project.Status.IN_PROGRESS,
            }
        )

        self.assertTrue(response.context["filter_form"].is_valid())
        context = response.context["filter_context"]
        self.assertEqual(context["department_label"], "Engineering")
        self.assertEqual(context["employee_status_label"], "Active")
        self.assertEqual(context["project_status_label"], "In progress")
        self.assertEqual(context["active_optional_filter_count"], 3)
        self.assertEqual(
            response.context["dashboard_filter_url"],
            "/?start_date=2026-08-15&end_date=2026-09-09&department=Engineering"
            "&employee_status=active&project_status=in_progress",
        )
        self.assertContains(response, "3 additional filters applied")
        self.assertContains(response, "Aug 15, 2026")
        self.assertContains(response, "Sep 9, 2026")
        self.assertContains(response, "Current reporting view")

    def test_same_day_period_is_valid_and_both_boundaries_are_preserved(self):
        response = self._get(
            {"start_date": "2026-09-09", "end_date": "2026-09-09"}
        )

        self.assertTrue(response.context["filter_form"].is_valid())
        self.assertEqual(
            response.context["filter_context"]["start_date"],
            response.context["filter_context"]["end_date"],
        )
        self.assertContains(response, "Both boundary dates are included")

    def test_reversed_and_malformed_dates_show_clear_server_errors(self):
        reversed_response = self._get(
            {"start_date": "2026-09-10", "end_date": "2026-09-09"}
        )
        self.assertFalse(reversed_response.context["filter_form"].is_valid())
        self.assertContains(
            reversed_response,
            "The end date must be on or after the start date.",
        )
        self.assertContains(reversed_response, "Reporting filters need attention")
        self.assertIsNone(reversed_response.context["filter_context"])

        malformed_response = self._get(
            {"start_date": "not-a-date", "end_date": "2026-09-09"}
        )
        self.assertContains(
            malformed_response,
            "Enter a valid reporting start date.",
        )
        self.assertIsNone(malformed_response.context["filter_context"])

        missing_response = self._get(
            {"start_date": "", "end_date": "2026-09-09"}
        )
        self.assertContains(missing_response, "Choose a reporting start date.")

    def test_stale_optional_values_are_ignored_and_canonicalized_safely(self):
        response = self._get(
            {
                "start_date": "2026-09-01",
                "end_date": "2026-09-30",
                "department": "Former department",
                "employee_status": "archived",
                "project_status": "unknown",
            }
        )

        self.assertTrue(response.context["filter_form"].is_valid())
        context = response.context["filter_context"]
        self.assertEqual(context["department"], "")
        self.assertEqual(context["employee_status"], "")
        self.assertEqual(context["project_status"], "")
        self.assertEqual(context["active_optional_filter_count"], 0)
        self.assertEqual(context["department_label"], "All departments")
        self.assertEqual(
            response.context["dashboard_filter_url"],
            "/?start_date=2026-09-01&end_date=2026-09-30&department="
            "&employee_status=&project_status=",
        )

    def test_department_choices_are_stable_and_handle_an_empty_dataset(self):
        response = self._get()
        choices = list(
            response.context["filter_form"].fields["department"].widget.choices
        )
        self.assertEqual(
            choices,
            [
                ("", "All departments"),
                ("Engineering", "Engineering"),
                ("Finance", "Finance"),
            ],
        )

        Employee.objects.all().delete()
        empty_response = self._get({"department": "Engineering"})
        empty_choices = list(
            empty_response.context["filter_form"].fields["department"].widget.choices
        )
        self.assertEqual(empty_choices, [("", "All departments")])
        self.assertEqual(empty_response.context["filter_context"]["department"], "")
        self.assertContains(empty_response, "All departments")

    def test_both_employee_and_project_view_permissions_are_required(self):
        anonymous_response = Client().get(self.url)
        self.assertRedirects(
            anonymous_response,
            f"{reverse('frontend:login')}?next={self.url}",
            fetch_redirect_response=False,
        )

        for user in (self.unassigned, self.employee_only, self.project_only):
            with self.subTest(username=user.username):
                client = Client()
                client.force_login(user)
                self.assertEqual(client.get(self.url).status_code, 403)

        self.assertEqual(self._get().status_code, 200)

    def test_dashboard_accepts_get_only(self):
        response = self.client.post(
            self.url,
            {"start_date": "2026-09-01", "end_date": "2026-09-30"},
        )

        self.assertEqual(response.status_code, 405)

    def test_dashboard_query_count_includes_fixed_kpi_snapshot_queries(self):
        with patch(
            "frontend.views.landing.timezone.localdate",
            return_value=self.TODAY,
        ):
            with self.assertNumQueries(self.EXPECTED_QUERY_COUNT):
                response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

    def test_warm_dashboard_response_time_is_recorded(self):
        with patch(
            "frontend.views.landing.timezone.localdate",
            return_value=self.TODAY,
        ):
            warmup_response = self.client.get(self.url)
            self.assertEqual(warmup_response.status_code, 200)

            durations_ms = []
            for _ in range(self.TIMING_SAMPLE_COUNT):
                with CaptureQueriesContext(connection) as captured_queries:
                    started_at = time.perf_counter()
                    response = self.client.get(self.url)
                    durations_ms.append((time.perf_counter() - started_at) * 1000)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(captured_queries), self.EXPECTED_QUERY_COUNT)

        result = {
            "median_ms": statistics.median(durations_ms),
            "p95_ms": statistics.quantiles(
                durations_ms,
                n=20,
                method="inclusive",
            )[18],
            "min_ms": min(durations_ms),
            "max_ms": max(durations_ms),
        }
        print(
            "\nM4.2 dashboard baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs):\n"
            f"  queries={self.EXPECTED_QUERY_COUNT}, "
            f"median={result['median_ms']:.3f} ms, "
            f"p95={result['p95_ms']:.3f} ms, "
            f"min={result['min_ms']:.3f} ms, "
            f"max={result['max_ms']:.3f} ms"
        )
