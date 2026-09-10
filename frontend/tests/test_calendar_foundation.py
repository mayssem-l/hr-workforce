import statistics
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test import Client, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from core.models import Assignment, Employee, Leave, Project
from frontend.calendar_access import (
    CALENDAR_SOURCE_PERMISSION_NAMES,
    CALENDAR_WORKSPACE_REQUIRED_MODELS,
    get_calendar_source_access,
)
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)


class CalendarWorkspaceTests(TestCase):
    TODAY = date(2026, 9, 10)
    EXPECTED_QUERY_COUNT = 9
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.users_by_role = {}
        for index, group_name in enumerate(
            (HR_ADMINISTRATOR_GROUP, MANAGER_PLANNER_GROUP, VIEWER_GROUP),
            start=1,
        ):
            user = get_user_model().objects.create_user(
                username=f"calendar-role-{index}"
            )
            user.groups.add(Group.objects.get(name=group_name))
            cls.users_by_role[group_name] = user

        cls.restricted_leave_user = get_user_model().objects.create_user(
            username="calendar-no-leave"
        )
        cls._grant(
            cls.restricted_leave_user,
            "view_project",
            "view_assignment",
            "view_employee",
        )
        cls.unassigned_user = get_user_model().objects.create_user(
            username="calendar-unassigned"
        )

        cls.employee = Employee.objects.create(
            first_name="Private",
            last_name="Calendar Employee",
            department="Sensitive Department",
            position="Planner",
            hire_date=date(2020, 1, 1),
            experience_years=Decimal("6.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )
        cls.project = Project.objects.create(
            name="Private Calendar Project",
            description="Not available in the M7.1 foundation.",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
            estimated_hours=Decimal("80.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )
        Assignment.objects.create(
            employee=cls.employee,
            project=cls.project,
            start_date=date(2026, 9, 2),
            end_date=date(2026, 9, 12),
            allocation_percentage=50,
            role_on_project="Private Calendar Role",
            status=Assignment.Status.PLANNED,
        )
        Leave.objects.create(
            employee=cls.employee,
            start_date=date(2026, 9, 15),
            end_date=date(2026, 9, 16),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )

    @classmethod
    def _grant(cls, user, *codenames):
        user.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="core",
                codename__in=codenames,
            )
        )

    def setUp(self):
        self.url = reverse("frontend:calendar_workspace")
        self.client.force_login(self.users_by_role[VIEWER_GROUP])

    def _get(self, data=None, *, client=None):
        with patch(
            "frontend.views.calendar.timezone.localdate",
            return_value=self.TODAY,
        ):
            return (client or self.client).get(self.url, data or {})

    def test_namespaced_route_template_get_only_and_active_navigation(self):
        self.assertEqual(self.url, "/calendar/")
        match = resolve(self.url)
        self.assertEqual(match.view_name, "frontend:calendar_workspace")
        self.assertEqual(match.app_name, "frontend")
        self.assertEqual(match.namespace, "frontend")

        response = self._get()

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/calendar/workspace.html")
        self.assertContains(response, "<h1>Shared planning calendar</h1>", html=True)
        self.assertContains(
            response,
            '<form method="get" action="/calendar/">',
            html=False,
        )
        self.assertRegex(
            response.content.decode("utf-8"),
            r'href="/calendar/"\s+aria-current="page"',
        )
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_authentication_canonical_roles_and_required_permission_boundary(self):
        anonymous_response = Client().get(self.url)
        self.assertRedirects(
            anonymous_response,
            f"{reverse('frontend:login')}?next={self.url}",
            fetch_redirect_response=False,
        )

        for group_name, user in self.users_by_role.items():
            with self.subTest(group_name=group_name):
                client = Client()
                client.force_login(user)
                self.assertEqual(self._get(client=client).status_code, 200)

        required_codenames = tuple(
            f"view_{model._meta.model_name}"
            for model in CALENDAR_WORKSPACE_REQUIRED_MODELS
        )
        for omitted_codename in required_codenames:
            with self.subTest(omitted_codename=omitted_codename):
                user = get_user_model().objects.create_user(
                    username=f"missing-{omitted_codename}"
                )
                self._grant(
                    user,
                    *(
                        codename
                        for codename in required_codenames
                        if codename != omitted_codename
                    ),
                )
                client = Client()
                client.force_login(user)
                self.assertEqual(self._get(client=client).status_code, 403)

        client = Client()
        client.force_login(self.unassigned_user)
        self.assertEqual(self._get(client=client).status_code, 403)

    def test_leave_source_is_truthfully_restricted_without_record_disclosure(self):
        client = Client()
        client.force_login(self.restricted_leave_user)

        response = self._get(client=client)

        self.assertEqual(response.status_code, 200)
        source_by_key = {
            source["key"]: source for source in response.context["source_context"]
        }
        self.assertTrue(source_by_key["projects"]["is_available"])
        self.assertTrue(source_by_key["assignments"]["is_available"])
        self.assertFalse(source_by_key["approved_leave"]["is_available"])
        self.assertContains(response, "Restricted by your current access")
        self.assertNotContains(response, "Private Calendar Role")
        self.assertNotContains(response, "Sep 15, 2026")
        self.assertNotContains(response, "Sep 16, 2026")

    def test_default_state_is_current_inclusive_month_and_month_view(self):
        response = self._get()

        form = response.context["view_form"]
        context = response.context["view_context"]
        self.assertTrue(form.is_valid())
        self.assertEqual(form["start_date"].value(), "2026-09-01")
        self.assertEqual(form["end_date"].value(), "2026-09-30")
        self.assertEqual(form["view"].value(), "month")
        self.assertEqual(context["start_date"], date(2026, 9, 1))
        self.assertEqual(context["end_date"], date(2026, 9, 30))
        self.assertEqual(context["view"], "month")
        self.assertContains(response, "Both boundary dates are included.")
        self.assertContains(response, "UTC timezone")

    def test_partial_state_uses_defaults_only_for_omitted_values(self):
        response = self._get({"view": "week"})

        self.assertTrue(response.context["view_form"].is_valid())
        self.assertEqual(
            response.context["view_context"]["start_date"],
            date(2026, 9, 1),
        )
        self.assertEqual(
            response.context["view_context"]["end_date"],
            date(2026, 9, 30),
        )
        self.assertEqual(response.context["view_context"]["view"], "week")

    def test_valid_month_week_and_list_states_preserve_exact_inclusive_dates(self):
        for view in ("month", "week", "list"):
            with self.subTest(view=view):
                response = self._get(
                    {
                        "start_date": "2026-10-05",
                        "end_date": "2026-10-05",
                        "view": view,
                    }
                )
                context = response.context["view_context"]
                self.assertTrue(response.context["view_form"].is_valid())
                self.assertEqual(context["start_date"], date(2026, 10, 5))
                self.assertEqual(context["end_date"], date(2026, 10, 5))
                self.assertEqual(context["view"], view)
                self.assertEqual(
                    context["query_string"],
                    f"start_date=2026-10-05&end_date=2026-10-05&view={view}"
                    "&source=project&source=assignment&source=approved_leave"
                    "&department=&employee=&project=&filters=1",
                )

    def test_invalid_and_stale_state_is_rejected_with_reset_path(self):
        cases = (
            (
                {
                    "start_date": "not-a-date",
                    "end_date": "2026-09-30",
                    "view": "month",
                },
                "Enter a valid reporting start date.",
            ),
            (
                {
                    "start_date": "2026-10-01",
                    "end_date": "2026-09-30",
                    "view": "week",
                },
                "The end date must be on or after the start date.",
            ),
            (
                {
                    "start_date": "2025-01-01",
                    "end_date": "2026-01-02",
                    "view": "list",
                },
                "Choose a reporting period of 366 days or fewer.",
            ),
            (
                {
                    "start_date": "2026-09-01",
                    "end_date": "2026-09-30",
                    "view": "agenda",
                },
                "Choose month, week, or list view.",
            ),
            (
                {
                    "start_date": "",
                    "end_date": "2026-09-30",
                    "view": "",
                },
                "Choose a reporting start date.",
            ),
        )
        for query, error in cases:
            with self.subTest(query=query):
                response = self._get(query)
                self.assertFalse(response.context["view_form"].is_valid())
                self.assertIsNone(response.context["view_context"])
                self.assertContains(response, error)
                self.assertContains(response, "Calendar settings need attention")
                self.assertContains(
                    response,
                    '<a class="btn btn-outline-secondary" href="/calendar/">Reset</a>',
                    html=False,
                )

    def test_accessible_list_guidance_renders_without_chart_output(self):
        response = self._get({"view": "list"})
        html = response.content.decode("utf-8")

        self.assertContains(response, "Calendar entries")
        self.assertContains(response, "complete read-only calendar evidence")
        self.assertContains(response, "Calendar entries for the selected inclusive period")
        self.assertContains(response, "Monday through Friday")
        self.assertContains(response, "does not include public holidays")
        self.assertContains(response, "This page does not calculate capacity.")
        self.assertEqual(html.count("<h1"), 1)
        self.assertNotIn("<canvas", html)
        self.assertNotIn("FullCalendar", html)
        self.assertNotIn("Chart.js", html)
        self.assertNotIn('"event_count"', html)
        self.assertNotIn('"events"', html)

    def test_filtered_foundation_uses_shared_event_reads_without_planning_calculations(self):
        with patch(
            "core.services.workload.calculate_daily_allocated_hours",
            side_effect=AssertionError("Workload calculation must not run in M7.1."),
        ), patch(
            "core.services.effective_availability.calculate_daily_available_hours",
            side_effect=AssertionError("Capacity calculation must not run in M7.1."),
        ), CaptureQueriesContext(connection) as queries:
            response = self._get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(queries), self.EXPECTED_QUERY_COUNT)
        sql = "\n".join(query["sql"] for query in queries.captured_queries)
        self.assertIn('"core_project"', sql)
        self.assertIn('"core_assignment"', sql)
        self.assertIn('"core_employee"', sql)
        self.assertIn('"core_leave"', sql)
        self.assertNotIn('"core_attendance"', sql)

    def test_warm_foundation_response_time_is_recorded(self):
        warmup_response = self._get()
        self.assertEqual(warmup_response.status_code, 200)

        durations_ms = []
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as queries:
                started_at = time.perf_counter()
                response = self._get()
                durations_ms.append((time.perf_counter() - started_at) * 1000)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(queries), self.EXPECTED_QUERY_COUNT)

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
            "\nM7.1 calendar foundation baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs):\n"
            f"  queries={self.EXPECTED_QUERY_COUNT}, "
            f"median={result['median_ms']:.3f} ms, "
            f"p95={result['p95_ms']:.3f} ms, "
            f"min={result['min_ms']:.3f} ms, "
            f"max={result['max_ms']:.3f} ms"
        )


class CalendarFoundationSourceBoundaryTests(SimpleTestCase):
    def test_access_contract_names_every_source_and_base_model(self):
        self.assertEqual(
            tuple(model._meta.model_name for model in CALENDAR_WORKSPACE_REQUIRED_MODELS),
            ("project", "assignment", "employee"),
        )
        self.assertEqual(
            CALENDAR_SOURCE_PERMISSION_NAMES,
            {
                "projects": ("core.view_project",),
                "assignments": (
                    "core.view_project",
                    "core.view_assignment",
                    "core.view_employee",
                ),
                "approved_leave": (
                    "core.view_employee",
                    "core.view_leave",
                ),
            },
        )

    def test_source_access_is_permission_derived_without_queries(self):
        class PermissionProbe:
            def __init__(self):
                self.requested = []

            def has_perms(self, permission_names):
                self.requested.append(permission_names)
                return "core.view_leave" not in permission_names

        probe = PermissionProbe()

        result = get_calendar_source_access(probe)

        self.assertEqual(
            result,
            {"projects": True, "assignments": True, "approved_leave": False},
        )
        self.assertEqual(
            probe.requested,
            list(CALENDAR_SOURCE_PERMISSION_NAMES.values()),
        )

    def test_foundation_source_files_have_no_event_query_or_planning_calculation(self):
        project_root = Path(__file__).resolve().parents[2]
        paths = (
            project_root / "frontend" / "calendar_access.py",
            project_root / "frontend" / "forms" / "calendar.py",
            project_root / "frontend" / "presenters" / "calendar.py",
            project_root / "frontend" / "views" / "calendar.py",
            project_root
            / "frontend"
            / "templates"
            / "frontend"
            / "calendar"
            / "workspace.html",
        )
        combined_source = "\n".join(
            path.read_text(encoding="utf-8") for path in paths
        )

        for forbidden in (
            ".objects",
            "core.services",
            "find_all_feasible_teams",
            "find_pareto_teams",
            "select_recommended_teams",
            "run_recommendation_pipeline",
            "calculate_current_workload",
            "calculate_available_hours_for_project",
            "ortools",
            "Attendance",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined_source)
