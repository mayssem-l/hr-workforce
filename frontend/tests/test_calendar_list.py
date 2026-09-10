import html
import re
import statistics
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test import Client, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import Assignment, Employee, Leave, Project
from frontend.roles import VIEWER_GROUP, sync_role_permissions
from frontend.views.calendar import CALENDAR_LIST_PAGE_SIZE


class CalendarListTests(TestCase):
    START_DATE = date(2026, 9, 1)
    END_DATE = date(2026, 9, 30)
    EXPECTED_QUERY_COUNT = 9
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="calendar-list-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.no_leave_user = get_user_model().objects.create_user(
            username="calendar-list-no-leave"
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
            first_name="Ada",
            last_name="Calendar",
            department="Research & Delivery",
            position="Planner",
            hire_date=date(2020, 1, 1),
            experience_years=Decimal("6.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )
        cls.boundary_project = cls._project(
            "Boundary programme",
            date(2026, 8, 20),
            cls.START_DATE,
            Project.Status.ON_HOLD,
        )
        cls.same_day_project = cls._project(
            "One-day launch",
            date(2026, 9, 10),
            date(2026, 9, 10),
            Project.Status.PLANNED,
        )
        cls.delivery_project = cls._project(
            "September delivery",
            cls.START_DATE,
            cls.END_DATE,
            Project.Status.IN_PROGRESS,
        )
        cls.outside_project = cls._project(
            "October follow-up",
            date(2026, 10, 1),
            date(2026, 10, 2),
            Project.Status.PLANNED,
        )
        cls.assignment = Assignment.objects.create(
            employee=cls.employee,
            project=cls.delivery_project,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 18),
            allocation_percentage=50,
            role_on_project="Delivery lead",
            status=Assignment.Status.ACTIVE,
        )
        cls.approved_leave = Leave.objects.create(
            employee=cls.employee,
            start_date=date(2026, 9, 20),
            end_date=date(2026, 9, 20),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )
        cls.pending_leave = Leave.objects.create(
            employee=cls.employee,
            start_date=date(2026, 9, 21),
            end_date=date(2026, 9, 22),
            type=Leave.Type.SICK,
            status=Leave.Status.PENDING,
        )

    @classmethod
    def _project(cls, name, start_date, end_date, status):
        return Project.objects.create(
            name=name,
            description=f"Description for {name}",
            start_date=start_date,
            end_date=end_date,
            estimated_hours=Decimal("80.00"),
            status=status,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )

    def setUp(self):
        self.workspace_url = reverse("frontend:calendar_workspace")
        self.events_url = reverse("frontend:calendar_events")
        self.client.force_login(self.viewer)

    def _filters(self, **overrides):
        values = {
            "start_date": self.START_DATE.isoformat(),
            "end_date": self.END_DATE.isoformat(),
            "view": "list",
            "source": ["project", "assignment", "approved_leave"],
            "department": "",
            "employee": "",
            "project": "",
            "filters": "1",
        }
        values.update(overrides)
        return values

    @staticmethod
    def _page_events(response):
        return [row["event"] for row in response.context["event_page"]]

    def test_list_rows_are_the_exact_endpoint_contract_in_selector_order(self):
        query = self._filters()
        page = self.client.get(self.workspace_url, query)
        endpoint = self.client.get(self.events_url, query)

        self.assertEqual(page.status_code, 200)
        self.assertEqual(endpoint.status_code, 200)
        self.assertEqual(self._page_events(page), endpoint.json()["events"])
        self.assertEqual(
            [event["id"] for event in self._page_events(page)],
            [
                f"project:{self.boundary_project.pk}",
                f"project:{self.delivery_project.pk}",
                f"assignment:{self.assignment.pk}",
                f"project:{self.same_day_project.pk}",
                f"approved_leave:{self.approved_leave.pk}",
            ],
        )
        self.assertNotContains(page, "Sick leave")

    def test_table_exposes_exact_source_period_status_and_record_context(self):
        response = self.client.get(self.workspace_url, self._filters())

        self.assertContains(
            response,
            "<caption>Calendar entries for the selected inclusive period</caption>",
            html=True,
        )
        self.assertEqual(response.content.decode("utf-8").count('scope="col"'), 7)
        self.assertContains(response, "Boundary programme")
        self.assertContains(response, "Project")
        self.assertContains(response, "On hold")
        self.assertContains(response, 'datetime="2026-08-20"', html=False)
        self.assertContains(response, 'datetime="2026-09-01"', html=False)
        self.assertContains(response, "One-day launch")
        self.assertEqual(
            response.content.decode("utf-8").count('datetime="2026-09-10"'),
            2,
        )
        self.assertContains(response, "Assignment")
        self.assertContains(response, "Ada Calendar — September delivery")
        self.assertContains(response, "Active")
        self.assertContains(response, "Approved leave")
        self.assertContains(response, "Annual")
        self.assertContains(response, "View project")
        self.assertContains(response, "View employee")
        self.assertContains(response, "View approved leave")

    def test_list_evidence_links_preserve_endpoint_permissions_and_period(self):
        response = self.client.get(self.workspace_url, self._filters())
        by_id = {event["id"]: event for event in self._page_events(response)}

        assignment = by_id[f"assignment:{self.assignment.pk}"]
        self.assertEqual(
            assignment["links"],
            [
                {
                    "kind": "project",
                    "label": "View project",
                    "url": reverse(
                        "frontend:project_detail",
                        args=[self.delivery_project.pk],
                    )
                    + "#project-assignments-title",
                },
                {
                    "kind": "employee",
                    "label": "View employee",
                    "url": reverse(
                        "frontend:employee_detail",
                        args=[self.employee.pk],
                    )
                    + "?start_date=2026-09-01&end_date=2026-09-30",
                },
            ],
        )
        leave = by_id[f"approved_leave:{self.approved_leave.pk}"]
        self.assertIn("from_date=2026-09-01", leave["links"][1]["url"])
        self.assertIn("to_date=2026-09-30", leave["links"][1]["url"])

    def test_month_week_and_list_modes_render_identical_event_evidence(self):
        results = []
        for view in ("month", "week", "list"):
            response = self.client.get(
                self.workspace_url,
                self._filters(view=view),
            )
            self.assertEqual(response.status_code, 200)
            results.append(self._page_events(response))

        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])

    def test_filtered_and_period_empty_states_are_distinct(self):
        period_empty = self.client.get(
            self.workspace_url,
            self._filters(
                start_date="2027-01-01",
                end_date="2027-01-31",
            ),
        )
        self.assertContains(period_empty, "No calendar entries in this period")
        self.assertNotContains(period_empty, "No calendar entries match these filters")

        filtered_empty = self.client.get(
            self.workspace_url,
            self._filters(
                source=["assignment"],
                project=str(self.same_day_project.pk),
            ),
        )
        self.assertContains(filtered_empty, "No calendar entries match these filters")
        self.assertContains(filtered_empty, "Reset calendar filters")
        self.assertNotContains(filtered_empty, "No calendar entries in this period")

    def test_invalid_filter_state_renders_no_event_table(self):
        response = self.client.get(
            self.workspace_url,
            self._filters(employee="999999"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["event_page"])
        self.assertContains(response, "Calendar entries are unavailable")
        self.assertNotContains(
            response,
            "Calendar entries for the selected inclusive period",
        )

    def test_leave_restriction_omits_leave_rows_and_keeps_truthful_state(self):
        client = Client()
        client.force_login(self.no_leave_user)
        response = client.get(
            self.workspace_url,
            self._filters(source=["project", "assignment"]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {event["source"] for event in self._page_events(response)},
            {"project", "assignment"},
        )
        self.assertContains(response, "Restricted by your current access")
        self.assertNotContains(response, "Annual leave")
        self.assertNotContains(response, "View approved leave")

    def test_deleted_records_disappear_on_the_next_server_render(self):
        first = self.client.get(self.workspace_url, self._filters())
        deleted_id = f"project:{self.same_day_project.pk}"
        self.assertIn(deleted_id, {event["id"] for event in self._page_events(first)})

        self.same_day_project.delete()
        second = self.client.get(self.workspace_url, self._filters())

        self.assertNotIn(
            deleted_id,
            {event["id"] for event in self._page_events(second)},
        )

    def test_large_result_pagination_is_deterministic_and_preserves_filters(self):
        for index in range(28):
            self._project(
                f"Paged project {index:02d}",
                date(2026, 9, 15),
                date(2026, 9, 16),
                Project.Status.PLANNED,
            )
        query = self._filters(source=["project"])
        first = self.client.get(self.workspace_url, query)
        second = self.client.get(self.workspace_url, {**query, "page": "2"})
        repeated = self.client.get(self.workspace_url, {**query, "page": "2"})
        endpoint = self.client.get(self.events_url, query)

        self.assertEqual(first.context["event_page"].paginator.per_page, 25)
        self.assertEqual(first.context["event_page"].paginator.count, 31)
        self.assertEqual(len(first.context["event_page"].object_list), 25)
        self.assertEqual(second.context["event_page"].number, 2)
        self.assertEqual(len(second.context["event_page"].object_list), 6)
        self.assertEqual(self._page_events(second), self._page_events(repeated))
        self.assertEqual(
            self._page_events(first) + self._page_events(second),
            endpoint.json()["events"],
        )

        match = re.search(r'href="([^"]*page=2[^"]*)"', first.content.decode())
        self.assertIsNotNone(match)
        pagination_url = html.unescape(match.group(1))
        values = parse_qs(urlsplit(pagination_url).query, keep_blank_values=True)
        self.assertEqual(values["start_date"], ["2026-09-01"])
        self.assertEqual(values["end_date"], ["2026-09-30"])
        self.assertEqual(values["view"], ["list"])
        self.assertEqual(values["source"], ["project"])
        self.assertEqual(values["department"], [""])
        self.assertEqual(values["employee"], [""])
        self.assertEqual(values["project"], [""])
        self.assertEqual(values["filters"], ["1"])
        self.assertEqual(values["page"], ["2"])

    def test_invalid_and_out_of_range_pages_are_resolved_deterministically(self):
        for index in range(CALENDAR_LIST_PAGE_SIZE):
            self._project(
                f"Extra project {index:02d}",
                date(2026, 9, 15),
                date(2026, 9, 16),
                Project.Status.PLANNED,
            )
        query = self._filters(source=["project"])
        invalid = self.client.get(
            self.workspace_url,
            {**query, "page": "not-a-page"},
        )
        out_of_range = self.client.get(
            self.workspace_url,
            {**query, "page": "999999"},
        )

        self.assertEqual(invalid.context["event_page"].number, 1)
        self.assertEqual(
            out_of_range.context["event_page"].number,
            out_of_range.context["event_page"].paginator.num_pages,
        )

    def test_large_list_keeps_fixed_queries_and_records_warm_response_time(self):
        for index in range(75):
            self._project(
                f"Performance project {index:02d}",
                date(2026, 9, 14),
                date(2026, 9, 17),
                Project.Status.PLANNED,
            )
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
            self.assertEqual(len(response.context["event_page"].object_list), 25)
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
            "\nM7.4 accessible-list baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm GETs, 80 matching events, "
            "25 rendered rows):\n"
            f"  queries={self.EXPECTED_QUERY_COUNT}, "
            f"median={result['median_ms']:.3f} ms, "
            f"p95={result['p95_ms']:.3f} ms, "
            f"response={response_size} bytes"
        )


class CalendarListSourceBoundaryTests(SimpleTestCase):
    def test_list_is_server_rendered_without_browser_event_or_domain_logic(self):
        project_root = Path(__file__).resolve().parents[2]
        template_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                project_root
                / "frontend"
                / "templates"
                / "frontend"
                / "calendar"
                / "workspace.html",
                project_root
                / "frontend"
                / "templates"
                / "frontend"
                / "calendar"
                / "_event_row.html",
            )
        )
        javascript_source = (
            project_root / "frontend" / "static" / "frontend" / "js" / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("event_page.object_list", template_source)
        self.assertIn("row.event", template_source)
        self.assertNotIn("data-calendar-events-url", javascript_source)
        for forbidden in (
            "start_date__lte",
            "end_date__gte",
            "employee__department",
            "allocation_percentage",
            "fetch(",
            "calculate_current_workload",
            "calculate_available_hours_for_project",
            "find_all_feasible_teams",
            "ortools",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, f"{template_source}\n{javascript_source}")
