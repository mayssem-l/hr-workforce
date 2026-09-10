import html
import statistics
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.staticfiles import finders
from django.db import connection
from django.test import Client, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import Assignment, Employee, Leave, Project
from frontend.roles import VIEWER_GROUP, sync_role_permissions


class InteractiveCalendarTests(TestCase):
    START_DATE = date(2026, 9, 1)
    END_DATE = date(2026, 9, 30)
    EXPECTED_QUERY_COUNT = 9
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="interactive-calendar-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.no_leave_user = get_user_model().objects.create_user(
            username="interactive-calendar-no-leave"
        )
        cls.no_leave_user.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="core",
                codename__in=(
                    "view_project",
                    "view_assignment",
                    "view_employee",
                ),
            )
        )
        cls.employee = Employee.objects.create(
            first_name="Maya",
            last_name="Rivera",
            department="Delivery & Operations",
            position="Programme Manager",
            hire_date=date(2020, 1, 1),
            experience_years=Decimal("7.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )
        cls.project = Project.objects.create(
            name="Interactive rollout",
            description="Calendar visualization fixture",
            start_date=cls.START_DATE,
            end_date=cls.END_DATE,
            estimated_hours=Decimal("120.00"),
            status=Project.Status.IN_PROGRESS,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        cls.assignment = Assignment.objects.create(
            employee=cls.employee,
            project=cls.project,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 18),
            allocation_percentage=50,
            role_on_project="Programme lead",
            status=Assignment.Status.ACTIVE,
        )
        cls.leave = Leave.objects.create(
            employee=cls.employee,
            start_date=date(2026, 9, 21),
            end_date=date(2026, 9, 22),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )

    def setUp(self):
        self.workspace_url = reverse("frontend:calendar_workspace")
        self.events_url = reverse("frontend:calendar_events")
        self.client.force_login(self.viewer)

    def _filters(self, **overrides):
        values = {
            "start_date": self.START_DATE.isoformat(),
            "end_date": self.END_DATE.isoformat(),
            "view": "month",
            "source": ["project", "assignment", "approved_leave"],
            "department": "",
            "employee": "",
            "project": "",
            "filters": "1",
        }
        values.update(overrides)
        return values

    def test_month_and_week_load_local_calendar_while_list_remains_server_rendered(self):
        for view, initial_label in (("month", "Month"), ("week", "Week")):
            with self.subTest(view=view):
                response = self.client.get(
                    self.workspace_url,
                    self._filters(view=view),
                )
                self.assertContains(response, 'data-calendar-enabled="true"')
                self.assertContains(response, f'data-calendar-view="{view}"')
                self.assertContains(response, f"{initial_label} calendar view")
                self.assertContains(
                    response,
                    "/static/frontend/vendor/"
                    "fullcalendar-6.1.21.index.global.min.js",
                )
                self.assertContains(
                    response,
                    "/static/frontend/js/calendar.js",
                )
                self.assertContains(
                    response,
                    "Calendar entries for the selected inclusive period",
                )

        list_response = self.client.get(
            self.workspace_url,
            self._filters(view="list"),
        )
        self.assertContains(list_response, 'data-calendar-enabled="false"')
        self.assertContains(list_response, "List view selected")
        self.assertNotContains(
            list_response,
            "fullcalendar-6.1.21.index.global.min.js",
        )
        self.assertNotContains(list_response, "/static/frontend/js/calendar.js")
        self.assertContains(
            list_response,
            "Calendar entries for the selected inclusive period",
        )

    def test_visualization_uses_exact_endpoint_url_and_normalized_state(self):
        response = self.client.get(
            self.workspace_url,
            self._filters(
                view="week",
                source=["assignment", "approved_leave"],
                department="Delivery & Operations",
                employee=str(self.employee.pk),
            ),
        )

        self.assertEqual(response.status_code, 200)
        expected_url = response.context["calendar_event_url"]
        self.assertContains(
            response,
            f'data-calendar-events-url="{html.escape(expected_url)}"',
            html=False,
        )
        self.assertContains(response, 'data-calendar-start-date="2026-09-01"')
        self.assertContains(response, 'data-calendar-timezone="UTC"')

    def test_view_links_preserve_every_filter_and_reset_pagination(self):
        response = self.client.get(
            self.workspace_url,
            {
                **self._filters(
                    source=["assignment"],
                    department="Delivery & Operations",
                    employee=str(self.employee.pk),
                    project=str(self.project.pk),
                ),
                "page": "2",
            },
        )

        links = response.context["filter_context"]["view_links"]
        self.assertEqual([link["value"] for link in links], ["month", "week", "list"])
        for link in links:
            values = parse_qs(
                urlsplit(link["url"]).query,
                keep_blank_values=True,
            )
            self.assertEqual(values["start_date"], ["2026-09-01"])
            self.assertEqual(values["end_date"], ["2026-09-30"])
            self.assertEqual(values["view"], [link["value"]])
            self.assertEqual(values["source"], ["assignment"])
            self.assertEqual(
                values["department"],
                ["Delivery & Operations"],
            )
            self.assertEqual(values["employee"], [str(self.employee.pk)])
            self.assertEqual(values["project"], [str(self.project.pk)])
            self.assertEqual(values["filters"], ["1"])
            self.assertNotIn("page", values)

        current = next(link for link in links if link["value"] == "month")
        self.assertTrue(current["is_current"])
        self.assertContains(response, 'aria-label="Calendar views"')
        self.assertContains(response, 'aria-current="page">Month</a>', html=False)

    def test_endpoint_supplies_fullcalendar_ready_events_from_existing_contract(self):
        payload = self.client.get(self.events_url, self._filters()).json()
        by_source = {event["source"]: event for event in payload["events"]}

        expected = (
            ("project", "2026-09-01", "2026-10-01", "Project"),
            ("assignment", "2026-09-07", "2026-09-19", "Assignment"),
            (
                "approved_leave",
                "2026-09-21",
                "2026-09-23",
                "Approved leave",
            ),
        )
        for source, start, exclusive_end, source_label in expected:
            with self.subTest(source=source):
                event = by_source[source]
                visual = event["calendar"]
                self.assertEqual(visual["id"], event["id"])
                self.assertEqual(visual["title"], event["title"])
                self.assertEqual(visual["start"], start)
                self.assertEqual(visual["end"], exclusive_end)
                self.assertTrue(visual["allDay"])
                self.assertEqual(
                    visual["classNames"],
                    [f"calendar-event--{source}"],
                )
                self.assertEqual(
                    visual["extendedProps"]["sourceLabel"],
                    source_label,
                )
                self.assertEqual(
                    visual["extendedProps"]["statusLabel"],
                    event["status"]["label"],
                )
                self.assertEqual(visual["url"], event["links"][0]["url"])
                self.assertEqual(event["start_date"], start)

    def test_restricted_sources_are_absent_from_visual_and_list_contracts(self):
        client = Client()
        client.force_login(self.no_leave_user)
        query = self._filters(source=["project", "assignment"])
        page = client.get(self.workspace_url, query)
        endpoint = client.get(self.events_url, query).json()

        self.assertEqual(
            {event["source"] for event in endpoint["events"]},
            {"project", "assignment"},
        )
        self.assertContains(page, "Restricted by your current access")
        self.assertNotContains(page, "View approved leave")
        self.assertNotContains(page, "calendar-event--approved_leave")

    def test_visualization_markup_has_loading_failure_empty_and_no_script_fallbacks(self):
        response = self.client.get(self.workspace_url, self._filters())

        self.assertContains(response, 'data-calendar-status role="status"')
        self.assertContains(response, 'aria-live="polite"')
        self.assertContains(response, "data-calendar-large-result")
        self.assertContains(response, "data-calendar-viewport hidden")
        self.assertContains(response, "<noscript>", html=False)
        self.assertContains(response, "JavaScript is turned off.")
        self.assertContains(response, "complete chronological calendar entries")

    def test_invalid_state_does_not_load_or_initialize_fullcalendar(self):
        response = self.client.get(
            self.workspace_url,
            self._filters(employee="999999"),
        )

        self.assertContains(response, "Calendar settings need attention")
        self.assertNotContains(response, "data-calendar-workspace")
        self.assertNotContains(
            response,
            "fullcalendar-6.1.21.index.global.min.js",
        )
        self.assertNotContains(response, "/static/frontend/js/calendar.js")

    def test_calendar_page_and_endpoint_query_counts_remain_fixed(self):
        query = self._filters()
        with CaptureQueriesContext(connection) as page_queries:
            page = self.client.get(self.workspace_url, query)
        with CaptureQueriesContext(connection) as endpoint_queries:
            endpoint = self.client.get(self.events_url, query)

        self.assertEqual(page.status_code, 200)
        self.assertEqual(endpoint.status_code, 200)
        self.assertEqual(len(page_queries), self.EXPECTED_QUERY_COUNT)
        self.assertEqual(len(endpoint_queries), self.EXPECTED_QUERY_COUNT)

    def test_interactive_page_warm_response_time_is_recorded(self):
        query = self._filters()
        self.assertEqual(self.client.get(self.workspace_url, query).status_code, 200)
        durations = []
        response_size = 0
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as queries:
                started_at = time.perf_counter()
                response = self.client.get(self.workspace_url, query)
                durations.append((time.perf_counter() - started_at) * 1000)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(queries), self.EXPECTED_QUERY_COUNT)
            response_size = len(response.content)

        result = {
            "median_ms": statistics.median(durations),
            "p95_ms": statistics.quantiles(
                durations,
                n=20,
                method="inclusive",
            )[18],
        }
        print(
            "\nM7.5 interactive-calendar page baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm GETs, 3 matching events):\n"
            f"  queries={self.EXPECTED_QUERY_COUNT}, "
            f"median={result['median_ms']:.3f} ms, "
            f"p95={result['p95_ms']:.3f} ms, "
            f"response={response_size} bytes"
        )


class InteractiveCalendarSourceTests(SimpleTestCase):
    FULLCALENDAR_ASSET = "frontend/vendor/fullcalendar-6.1.21.index.global.min.js"
    FULLCALENDAR_LICENSE = "frontend/vendor/FULLCALENDAR-6.1.21-LICENSE.md"

    def test_pinned_assets_are_local_discoverable_and_identify_version_and_license(self):
        bundle_path = finders.find(self.FULLCALENDAR_ASSET)
        license_path = finders.find(self.FULLCALENDAR_LICENSE)

        self.assertIsNotNone(bundle_path)
        self.assertIsNotNone(license_path)
        bundle = Path(bundle_path).read_text(encoding="utf-8")
        license_text = Path(license_path).read_text(encoding="utf-8")
        self.assertGreater(len(bundle), 250_000)
        self.assertIn("FullCalendar Standard Bundle v6.1.21", bundle[:300])
        self.assertIn("MIT License", license_text)
        self.assertIn("Adam Shaw", license_text)

    def test_javascript_uses_endpoint_payload_without_domain_recalculation(self):
        project_root = Path(__file__).resolve().parents[2]
        javascript = (
            project_root / "frontend" / "static" / "frontend" / "js" / "calendar.js"
        ).read_text(encoding="utf-8")
        template = (
            project_root
            / "frontend"
            / "templates"
            / "frontend"
            / "calendar"
            / "workspace.html"
        ).read_text(encoding="utf-8")

        self.assertIn("workspace.dataset.calendarEventsUrl", javascript)
        self.assertIn("viewport.hidden = false", javascript)
        self.assertLess(
            javascript.index("viewport.hidden = false"),
            javascript.index("calendar.render()"),
            "The viewport must be measurable before FullCalendar lays out, "
            "otherwise every day cell collapses.",
        )
        self.assertIn("event.calendar", javascript)
        self.assertIn('editable: false', javascript)
        self.assertIn('selectable: false', javascript)
        self.assertIn("Interactive calendar unavailable", javascript)
        self.assertIn("LARGE_RESULT_THRESHOLD", javascript)
        self.assertIn("complete chronological list", javascript)
        self.assertNotIn("https://cdn", template)
        for forbidden in (
            "Date(",
            "setDate(",
            "start_date__lte",
            "end_date__gte",
            "employee__department",
            "allocation_percentage",
            "calculate_current_workload",
            "calculate_available_hours_for_project",
            "find_all_feasible_teams",
            "ortools",
            "eventDrop",
            "eventResize",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, f"{javascript}\n{template}")

    def test_theme_has_focus_responsive_source_and_reduced_motion_hooks(self):
        theme = (
            Path(__file__).resolve().parents[1]
            / "static"
            / "frontend"
            / "css"
            / "theme.css"
        ).read_text(encoding="utf-8")

        for expected in (
            ".calendar-view-switcher__link:focus-visible",
            ".calendar-visualization .fc a:focus-visible",
            ".calendar-visualization__viewport",
            "overflow-x: auto",
            ".calendar-event--project",
            ".calendar-event--assignment",
            ".calendar-event--approved_leave",
            "@media (max-width: 767.98px)",
            "@media (prefers-reduced-motion: reduce)",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, theme)
