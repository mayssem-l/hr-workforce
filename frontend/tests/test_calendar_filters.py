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
from django.urls import reverse

from core.models import Assignment, Employee, Leave, Project
from frontend.roles import VIEWER_GROUP, sync_role_permissions


class CalendarFilterTests(TestCase):
    START_DATE = date(2026, 9, 1)
    END_DATE = date(2026, 9, 30)
    ALL_SOURCE_QUERY_COUNT = 9
    TWO_SOURCE_QUERY_COUNT = 8
    ONE_MATCHING_SOURCE_QUERY_COUNT = 7
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="calendar-filter-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.no_leave_user = get_user_model().objects.create_user(
            username="calendar-filter-no-leave"
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

        cls.ada = cls._employee("Ada", "Alpha", "Engineering")
        cls.bea = cls._employee("Bea", "Beta", "Finance")
        cls.rene = cls._employee("René", "Cœur", "R&D / North")
        cls.alpha = cls._project("Alpha launch")
        cls.beta = cls._project("Beta renewal")
        cls.ada_assignment = cls._assignment(cls.ada, cls.alpha)
        cls.bea_assignment = cls._assignment(cls.bea, cls.beta)
        cls.rene_assignment = cls._assignment(cls.rene, cls.alpha)
        cls.ada_leave = cls._leave(cls.ada, Leave.Status.APPROVED)
        cls.bea_leave = cls._leave(cls.bea, Leave.Status.APPROVED)
        cls.rene_leave = cls._leave(cls.rene, Leave.Status.APPROVED)
        cls.pending_leave = cls._leave(cls.ada, Leave.Status.PENDING)

    @classmethod
    def _employee(cls, first_name, last_name, department):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department=department,
            position="Planner",
            hire_date=date(2020, 1, 1),
            experience_years=Decimal("5.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )

    @classmethod
    def _project(cls, name):
        return Project.objects.create(
            name=name,
            description=f"Description for {name}",
            start_date=cls.START_DATE,
            end_date=cls.END_DATE,
            estimated_hours=Decimal("80.00"),
            status=Project.Status.IN_PROGRESS,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )

    @classmethod
    def _assignment(cls, employee, project):
        return Assignment.objects.create(
            employee=employee,
            project=project,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 18),
            allocation_percentage=50,
            role_on_project="Contributor",
            status=Assignment.Status.ACTIVE,
        )

    @classmethod
    def _leave(cls, employee, status):
        return Leave.objects.create(
            employee=employee,
            start_date=date(2026, 9, 21),
            end_date=date(2026, 9, 22),
            type=Leave.Type.ANNUAL,
            status=status,
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

    def _event_sources(self, **overrides):
        response = self.client.get(self.events_url, self._filters(**overrides))
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_default_page_has_deterministic_current_choices_and_all_sources(self):
        with patch(
            "frontend.views.calendar.timezone.localdate",
            return_value=date(2026, 9, 10),
        ):
            response = self.client.get(self.workspace_url)

        self.assertEqual(response.status_code, 200)
        form = response.context["view_form"]
        context = response.context["filter_context"]
        self.assertTrue(form.is_valid())
        self.assertEqual(context["sources"], ("project", "assignment", "approved_leave"))
        self.assertEqual(
            list(form.fields["department"].choices),
            [
                ("", "All departments"),
                ("Engineering", "Engineering"),
                ("Finance", "Finance"),
                ("R&D / North", "R&D / North"),
            ],
        )
        self.assertEqual(
            list(form.fields["employee"].choices),
            [
                ("", "All employees"),
                (str(self.ada.pk), "Ada Alpha — Engineering"),
                (str(self.bea.pk), "Bea Beta — Finance"),
                (str(self.rene.pk), "René Cœur — R&D / North"),
            ],
        )
        self.assertEqual(
            list(form.fields["project"].choices),
            [
                ("", "All projects"),
                (str(self.alpha.pk), "Alpha launch"),
                (str(self.beta.pk), "Beta renewal"),
            ],
        )
        self.assertContains(response, "Calendar filters")
        self.assertContains(response, "all available sources are used by default")
        self.assertContains(response, "Project schedules")
        self.assertContains(response, "Assignment schedules")
        self.assertContains(response, "Approved leave")

    def test_each_source_toggle_filters_the_existing_event_contract(self):
        expected_ids = {
            "project": {
                f"project:{self.alpha.pk}",
                f"project:{self.beta.pk}",
            },
            "assignment": {
                f"assignment:{self.ada_assignment.pk}",
                f"assignment:{self.bea_assignment.pk}",
                f"assignment:{self.rene_assignment.pk}",
            },
            "approved_leave": {
                f"approved_leave:{self.ada_leave.pk}",
                f"approved_leave:{self.bea_leave.pk}",
                f"approved_leave:{self.rene_leave.pk}",
            },
        }
        for source, event_ids in expected_ids.items():
            with self.subTest(source=source):
                payload = self._event_sources(source=[source])
                self.assertEqual(payload["filters"]["sources"], [source])
                self.assertEqual(
                    {event["id"] for event in payload["events"]},
                    event_ids,
                )
                self.assertNotIn(
                    f"approved_leave:{self.pending_leave.pk}",
                    {event["id"] for event in payload["events"]},
                )

    def test_department_employee_and_project_filters_apply_to_event_context(self):
        department = self._event_sources(department="Engineering")
        self.assertEqual(
            {event["id"] for event in department["events"]},
            {
                f"assignment:{self.ada_assignment.pk}",
                f"approved_leave:{self.ada_leave.pk}",
            },
        )

        employee = self._event_sources(employee=str(self.bea.pk))
        self.assertEqual(
            {event["id"] for event in employee["events"]},
            {
                f"assignment:{self.bea_assignment.pk}",
                f"approved_leave:{self.bea_leave.pk}",
            },
        )

        project = self._event_sources(project=str(self.alpha.pk))
        self.assertEqual(
            {event["id"] for event in project["events"]},
            {
                f"project:{self.alpha.pk}",
                f"assignment:{self.ada_assignment.pk}",
                f"assignment:{self.rene_assignment.pk}",
            },
        )

    def test_combined_filters_require_every_applicable_event_context(self):
        matching = self._event_sources(
            department="Engineering",
            employee=str(self.ada.pk),
            project=str(self.alpha.pk),
        )
        self.assertEqual(
            [event["id"] for event in matching["events"]],
            [f"assignment:{self.ada_assignment.pk}"],
        )

        mismatched = self._event_sources(
            department="Finance",
            employee=str(self.ada.pk),
            project=str(self.alpha.pk),
        )
        self.assertEqual(mismatched["events"], [])
        self.assertEqual(mismatched["event_count"], 0)

    def test_special_characters_are_validated_and_canonically_encoded(self):
        response = self.client.get(
            self.workspace_url,
            self._filters(
                view="week",
                source=["assignment", "approved_leave"],
                department="R&D / North",
                employee=str(self.rene.pk),
            ),
        )

        self.assertEqual(response.status_code, 200)
        context = response.context["filter_context"]
        self.assertEqual(context["department"], "R&D / North")
        self.assertEqual(context["employee"], str(self.rene.pk))
        self.assertEqual(
            context["query_string"],
            "start_date=2026-09-01&end_date=2026-09-30&view=week"
            "&source=assignment&source=approved_leave"
            f"&department=R%26D+%2F+North&employee={self.rene.pk}"
            "&project=&filters=1",
        )
        self.assertEqual(
            response.context["calendar_filter_url"],
            f"{self.workspace_url}?{context['query_string']}",
        )
        self.assertEqual(
            response.context["calendar_event_url"],
            f"{self.events_url}?{context['query_string']}",
        )
        self.assertContains(response, "Current calendar view")
        self.assertContains(response, "René Cœur — R&amp;D / North", html=False)

    def test_page_and_endpoint_share_the_same_normalized_filter_context(self):
        query = self._filters(
            view="list",
            source=["assignment"],
            department="Engineering",
            employee=str(self.ada.pk),
            project=str(self.alpha.pk),
        )
        page = self.client.get(self.workspace_url, query)
        endpoint = self.client.get(self.events_url, query)

        self.assertEqual(page.status_code, 200)
        self.assertEqual(endpoint.status_code, 200)
        context = page.context["filter_context"]
        self.assertEqual(
            endpoint.json()["filters"],
            {
                "view": context["view"],
                "sources": list(context["sources"]),
                "department": context["department"],
                "employee": context["employee"],
                "project": context["project"],
                "query_string": context["query_string"],
            },
        )
        self.assertIn(context["query_string"], page.context["calendar_filter_url"])
        self.assertIn(context["query_string"], page.context["calendar_event_url"])

        event = endpoint.json()["events"][0]
        employee_link = next(
            link for link in event["links"] if link["kind"] == "employee"
        )
        self.assertEqual(
            employee_link["url"],
            reverse("frontend:employee_detail", args=[self.ada.pk])
            + "?start_date=2026-09-01&end_date=2026-09-30",
        )

    def test_legend_has_color_independent_included_unselected_empty_and_restricted_states(self):
        selected_page = self.client.get(
            self.workspace_url,
            self._filters(source=["project"]),
        )
        selected_by_source = {
            row["source"]: row for row in selected_page.context["source_context"]
        }
        self.assertEqual(selected_by_source["project"]["state"], "included")
        self.assertEqual(
            selected_by_source["assignment"]["state"], "not_selected"
        )
        self.assertContains(selected_page, "Included — matching entries available")
        self.assertContains(selected_page, "Not included in this view")
        self.assertContains(selected_page, "calendar-source-card--project")

        empty_page = self.client.get(
            self.workspace_url,
            self._filters(
                start_date="2027-01-01",
                end_date="2027-01-31",
                source=["assignment"],
            ),
        )
        empty_assignment = next(
            row
            for row in empty_page.context["source_context"]
            if row["source"] == "assignment"
        )
        self.assertEqual(empty_assignment["state"], "empty")
        self.assertContains(empty_page, "Included — no matching entries")

        client = Client()
        client.force_login(self.no_leave_user)
        restricted_page = client.get(self.workspace_url)
        restricted_leave = next(
            row
            for row in restricted_page.context["source_context"]
            if row["source"] == "approved_leave"
        )
        self.assertEqual(restricted_leave["state"], "restricted")
        self.assertContains(restricted_page, "Restricted by your current access")
        self.assertContains(restricted_page, "calendar-source-card--restricted")

    def test_no_source_selected_is_a_safe_validation_error(self):
        query = self._filters(source=[])
        page = self.client.get(self.workspace_url, query)
        endpoint = self.client.get(self.events_url, query)

        self.assertEqual(page.status_code, 200)
        self.assertFalse(page.context["view_form"].is_valid())
        self.assertIsNone(page.context["filter_context"])
        self.assertContains(page, "Choose at least one available calendar source.")
        self.assertEqual(endpoint.status_code, 400)
        self.assertEqual(endpoint.json()["state"], "invalid")

    def test_stale_deleted_and_forged_record_choices_fail_closed(self):
        stale_employee = self._employee("Stale", "Employee", "Operations")
        stale_project = self._project("Stale project")
        stale_employee_id = str(stale_employee.pk)
        stale_project_id = str(stale_project.pk)
        stale_employee.delete()
        stale_project.delete()

        cases = (
            ({"employee": stale_employee_id}, "Choose a current employee."),
            ({"project": stale_project_id}, "Choose a current project."),
            ({"employee": "999999"}, "Choose a current employee."),
            ({"project": "999999"}, "Choose a current project."),
            ({"department": "Former / Department"}, "Choose a current department."),
        )
        for override, expected_error in cases:
            with self.subTest(override=override), patch(
                "frontend.views.calendar.get_calendar_events"
            ) as selector:
                page = self.client.get(
                    self.workspace_url,
                    self._filters(**override),
                )
                self.assertEqual(page.status_code, 200)
                self.assertFalse(page.context["view_form"].is_valid())
                self.assertContains(page, expected_error)
                selector.assert_not_called()

                endpoint = self.client.get(
                    self.events_url,
                    self._filters(**override),
                )
                self.assertEqual(endpoint.status_code, 400)
                self.assertIn(expected_error, str(endpoint.json()["errors"]))
                selector.assert_not_called()

    def test_restricted_or_unknown_source_cannot_be_selected(self):
        client = Client()
        client.force_login(self.no_leave_user)
        for source in ("approved_leave", "attendance", "recommendation"):
            with self.subTest(source=source), patch(
                "frontend.views.calendar.get_calendar_events"
            ) as selector:
                query = self._filters(source=[source])
                page = client.get(self.workspace_url, query)
                endpoint = client.get(self.events_url, query)
                self.assertFalse(page.context["view_form"].is_valid())
                self.assertContains(
                    page,
                    "Choose only calendar sources available to you.",
                )
                self.assertEqual(endpoint.status_code, 400)
                selector.assert_not_called()

    def test_query_counts_and_warm_response_times_are_recorded(self):
        page_warmup = self.client.get(self.workspace_url, self._filters())
        endpoint_warmup = self.client.get(self.events_url, self._filters())
        self.assertEqual(page_warmup.status_code, 200)
        self.assertEqual(endpoint_warmup.status_code, 200)

        page_durations = []
        endpoint_durations = []
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as page_queries:
                started_at = time.perf_counter()
                page = self.client.get(self.workspace_url, self._filters())
                page_durations.append((time.perf_counter() - started_at) * 1000)
            self.assertEqual(page.status_code, 200)
            self.assertEqual(len(page_queries), self.ALL_SOURCE_QUERY_COUNT)

            with CaptureQueriesContext(connection) as endpoint_queries:
                started_at = time.perf_counter()
                endpoint = self.client.get(self.events_url, self._filters())
                endpoint_durations.append((time.perf_counter() - started_at) * 1000)
            self.assertEqual(endpoint.status_code, 200)
            self.assertEqual(len(endpoint_queries), self.ALL_SOURCE_QUERY_COUNT)

        page_result = self._timing_result(page_durations)
        endpoint_result = self._timing_result(endpoint_durations)
        print(
            "\nM7.3 calendar-filter baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm GETs per route, 8 matching events):\n"
            f"  page:     queries={self.ALL_SOURCE_QUERY_COUNT}, "
            f"median={page_result['median_ms']:.3f} ms, "
            f"p95={page_result['p95_ms']:.3f} ms\n"
            f"  endpoint: queries={self.ALL_SOURCE_QUERY_COUNT}, "
            f"median={endpoint_result['median_ms']:.3f} ms, "
            f"p95={endpoint_result['p95_ms']:.3f} ms, "
            f"response={len(endpoint.content)} bytes"
        )

    def test_source_toggles_skip_unselected_source_queries(self):
        cases = (
            (
                ["assignment", "approved_leave"],
                self.TWO_SOURCE_QUERY_COUNT,
                ('"core_assignment"', '"core_leave"'),
                ('"core_project"."start_date"',),
            ),
            (
                ["assignment"],
                self.ONE_MATCHING_SOURCE_QUERY_COUNT,
                ('"core_assignment"',),
                ('"core_project"."start_date"', 'FROM "core_leave"'),
            ),
        )
        for sources, expected_count, included_tables, omitted_tables in cases:
            with self.subTest(sources=sources), CaptureQueriesContext(
                connection
            ) as queries:
                response = self.client.get(
                    self.events_url,
                    self._filters(source=sources),
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(queries), expected_count)
            sql = "\n".join(query["sql"] for query in queries.captured_queries)
            for table in included_tables:
                self.assertIn(table, sql)
            for query_fragment in omitted_tables:
                self.assertNotIn(query_fragment, sql)

    @staticmethod
    def _timing_result(durations_ms):
        return {
            "median_ms": statistics.median(durations_ms),
            "p95_ms": statistics.quantiles(
                durations_ms,
                n=20,
                method="inclusive",
            )[18],
        }


class CalendarFilterSourceBoundaryTests(SimpleTestCase):
    def test_templates_and_javascript_do_not_filter_or_calculate_events(self):
        project_root = Path(__file__).resolve().parents[2]
        template = (
            project_root
            / "frontend"
            / "templates"
            / "frontend"
            / "calendar"
            / "workspace.html"
        ).read_text(encoding="utf-8")
        javascript = (
            project_root / "frontend" / "static" / "frontend" / "js" / "app.js"
        ).read_text(encoding="utf-8")

        for forbidden in (
            "start_date__lte",
            "end_date__gte",
            "employee__department",
            "project_id=",
            "calculate_current_workload",
            "calculate_available_hours_for_project",
            "find_all_feasible_teams",
            "ortools",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, f"{template}\n{javascript}")
