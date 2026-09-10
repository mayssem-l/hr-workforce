import statistics
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test import Client, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from core.models import Assignment, Employee, Leave, Project
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)
from frontend.selectors.calendar import (
    APPROVED_LEAVE_SOURCE,
    CALENDAR_SOURCE_ORDER,
    CalendarEventRecord,
    get_calendar_events,
)


class CalendarEventEndpointTests(TestCase):
    START_DATE = date(2026, 9, 10)
    END_DATE = date(2026, 9, 20)
    EXPECTED_QUERY_COUNT = 9
    RESTRICTED_LEAVE_QUERY_COUNT = 8
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
                username=f"calendar-events-role-{index}"
            )
            user.groups.add(Group.objects.get(name=group_name))
            cls.users_by_role[group_name] = user

        cls.base_only_user = get_user_model().objects.create_user(
            username="calendar-events-base-only"
        )
        cls._grant(
            cls.base_only_user,
            "view_project",
            "view_assignment",
            "view_employee",
        )
        cls.unassigned_user = get_user_model().objects.create_user(
            username="calendar-events-unassigned"
        )

        cls.employee = cls._create_employee("Ada", "Boundary")
        cls.leave_only_employee = cls._create_employee("Leave", "Secret Person")
        cls.left_project = cls._create_project(
            "Left boundary project",
            date(2026, 9, 1),
            cls.START_DATE,
            Project.Status.ON_HOLD,
        )
        cls.right_project = cls._create_project(
            "Right boundary project",
            cls.END_DATE,
            date(2026, 9, 30),
            Project.Status.IN_PROGRESS,
        )
        cls.before_project = cls._create_project(
            "Before window project",
            date(2026, 8, 1),
            date(2026, 9, 9),
            Project.Status.COMPLETED,
        )
        cls.after_project = cls._create_project(
            "After window project",
            date(2026, 9, 21),
            date(2026, 10, 1),
            Project.Status.PLANNED,
        )
        cls.assignment = Assignment.objects.create(
            employee=cls.employee,
            project=cls.right_project,
            start_date=date(2026, 9, 12),
            end_date=date(2026, 9, 18),
            allocation_percentage=60,
            role_on_project="Backend Engineer",
            status=Assignment.Status.ACTIVE,
        )
        cls.outside_assignment = Assignment.objects.create(
            employee=cls.employee,
            project=cls.after_project,
            start_date=date(2026, 9, 21),
            end_date=date(2026, 9, 25),
            allocation_percentage=20,
            role_on_project="Reviewer",
            status=Assignment.Status.PLANNED,
        )
        cls.approved_leave = Leave.objects.create(
            employee=cls.leave_only_employee,
            start_date=cls.START_DATE,
            end_date=date(2026, 9, 11),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )
        cls.pending_leave = Leave.objects.create(
            employee=cls.leave_only_employee,
            start_date=date(2026, 9, 13),
            end_date=date(2026, 9, 14),
            type=Leave.Type.SICK,
            status=Leave.Status.PENDING,
        )
        cls.outside_leave = Leave.objects.create(
            employee=cls.leave_only_employee,
            start_date=date(2026, 9, 21),
            end_date=date(2026, 9, 22),
            type=Leave.Type.OTHER,
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

    @classmethod
    def _create_employee(cls, first_name, last_name):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Engineering",
            position="Engineer",
            hire_date=date(2020, 1, 1),
            experience_years=Decimal("6.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )

    @classmethod
    def _create_project(cls, name, start_date, end_date, status):
        return Project.objects.create(
            name=name,
            description=f"Private description for {name}",
            start_date=start_date,
            end_date=end_date,
            estimated_hours=Decimal("80.00"),
            status=status,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )

    def setUp(self):
        self.url = reverse("frontend:calendar_events")
        self.client.force_login(self.users_by_role[VIEWER_GROUP])

    def _query(self):
        return {
            "start_date": self.START_DATE.isoformat(),
            "end_date": self.END_DATE.isoformat(),
        }

    def test_namespaced_endpoint_is_get_only_and_requires_authentication(self):
        self.assertEqual(self.url, "/calendar/events/")
        match = resolve(self.url)
        self.assertEqual(match.view_name, "frontend:calendar_events")
        self.assertEqual(match.namespace, "frontend")

        anonymous = Client().get(self.url, self._query())
        self.assertRedirects(
            anonymous,
            f"{reverse('frontend:login')}?next="
            f"{self.url}%3Fstart_date%3D2026-09-10%26end_date%3D2026-09-20",
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client.post(self.url, self._query()).status_code, 405)

    def test_selector_returns_exact_permitted_overlap_contract_in_three_queries(self):
        with self.assertNumQueries(3):
            events = get_calendar_events(
                start_date=self.START_DATE,
                end_date=self.END_DATE,
                source_access={
                    "projects": True,
                    "assignments": True,
                    "approved_leave": True,
                },
            )

        self.assertEqual(
            {event.event_id for event in events},
            {
                f"project:{self.left_project.project_id}",
                f"project:{self.right_project.project_id}",
                f"assignment:{self.assignment.assignment_id}",
                f"approved_leave:{self.approved_leave.leave_id}",
            },
        )
        self.assertNotIn(
            f"project:{self.before_project.project_id}",
            {event.event_id for event in events},
        )
        self.assertNotIn(
            f"project:{self.after_project.project_id}",
            {event.event_id for event in events},
        )
        self.assertNotIn(
            f"assignment:{self.outside_assignment.assignment_id}",
            {event.event_id for event in events},
        )
        self.assertNotIn(
            f"approved_leave:{self.pending_leave.leave_id}",
            {event.event_id for event in events},
        )
        self.assertNotIn(
            f"approved_leave:{self.outside_leave.leave_id}",
            {event.event_id for event in events},
        )

        by_id = {event.event_id: event for event in events}
        project_event = by_id[f"project:{self.left_project.project_id}"]
        self.assertEqual(project_event.start_date, self.left_project.start_date)
        self.assertEqual(project_event.end_date, self.left_project.end_date)
        self.assertEqual(project_event.status, Project.Status.ON_HOLD)
        self.assertEqual(project_event.status_label, "On hold")
        self.assertEqual(project_event.project_id, self.left_project.project_id)
        self.assertEqual(project_event.project_label, self.left_project.name)
        self.assertIsNone(project_event.employee_id)

        assignment_event = by_id[f"assignment:{self.assignment.assignment_id}"]
        self.assertEqual(assignment_event.start_date, self.assignment.start_date)
        self.assertEqual(assignment_event.end_date, self.assignment.end_date)
        self.assertEqual(assignment_event.status, Assignment.Status.ACTIVE)
        self.assertEqual(assignment_event.status_label, "Active")
        self.assertEqual(assignment_event.project_id, self.right_project.project_id)
        self.assertEqual(assignment_event.employee_id, self.employee.employee_id)

        leave_event = by_id[f"approved_leave:{self.approved_leave.leave_id}"]
        self.assertEqual(leave_event.start_date, self.approved_leave.start_date)
        self.assertEqual(leave_event.end_date, self.approved_leave.end_date)
        self.assertEqual(leave_event.status, Leave.Status.APPROVED)
        self.assertEqual(leave_event.leave_type, Leave.Type.ANNUAL)
        self.assertEqual(leave_event.leave_type_label, "Annual")
        self.assertEqual(
            leave_event.employee_id,
            self.leave_only_employee.employee_id,
        )

    def test_endpoint_returns_stable_safe_payload_and_permission_aware_links(self):
        response = self.client.get(self.url, self._query())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/json")
        payload = response.json()
        self.assertEqual(
            set(payload),
            {
                "state",
                "period",
                "source_access",
                "filters",
                "event_count",
                "events",
            },
        )
        self.assertEqual(payload["state"], "ready")
        self.assertEqual(
            payload["period"],
            {
                "start_date": "2026-09-10",
                "end_date": "2026-09-20",
                "inclusive": True,
                "timezone": "UTC",
            },
        )
        self.assertEqual(payload["event_count"], 4)
        self.assertEqual(
            payload["filters"],
            {
                "view": "month",
                "sources": ["project", "assignment", "approved_leave"],
                "department": "",
                "employee": "",
                "project": "",
                "query_string": (
                    "start_date=2026-09-10&end_date=2026-09-20&view=month"
                    "&source=project&source=assignment&source=approved_leave"
                    "&department=&employee=&project=&filters=1"
                ),
            },
        )
        self.assertEqual(
            payload["source_access"],
            {
                "projects": "available",
                "assignments": "available",
                "approved_leave": "available",
            },
        )

        expected_event_fields = {
            "id",
            "source",
            "source_label",
            "title",
            "start_date",
            "end_date",
            "status",
            "project",
            "employee",
            "leave_type",
            "links",
            "calendar",
        }
        for event in payload["events"]:
            self.assertEqual(set(event), expected_event_fields)

        by_id = {event["id"]: event for event in payload["events"]}
        project_event = by_id[f"project:{self.left_project.project_id}"]
        self.assertEqual(project_event["source_label"], "Project")
        self.assertEqual(
            project_event["status"], {"value": "on_hold", "label": "On hold"}
        )
        self.assertEqual(
            project_event["links"],
            [
                {
                    "kind": "project",
                    "label": "View project",
                    "url": reverse(
                        "frontend:project_detail",
                        args=[self.left_project.project_id],
                    ),
                }
            ],
        )
        self.assertEqual(
            project_event["calendar"],
            {
                "id": f"project:{self.left_project.project_id}",
                "title": self.left_project.name,
                "start": "2026-09-01",
                "end": "2026-09-11",
                "allDay": True,
                "url": reverse(
                    "frontend:project_detail",
                    args=[self.left_project.project_id],
                ),
                "classNames": ["calendar-event--project"],
                "extendedProps": {
                    "sourceLabel": "Project",
                    "statusLabel": "On hold",
                },
            },
        )

        assignment_event = by_id[f"assignment:{self.assignment.assignment_id}"]
        self.assertEqual(assignment_event["source_label"], "Assignment")
        self.assertEqual(
            assignment_event["project"],
            {
                "id": self.right_project.project_id,
                "label": self.right_project.name,
            },
        )
        self.assertEqual(
            assignment_event["employee"],
            {"id": self.employee.employee_id, "label": str(self.employee)},
        )
        self.assertEqual(
            assignment_event["links"],
            [
                {
                    "kind": "project",
                    "label": "View project",
                    "url": reverse(
                        "frontend:project_detail",
                        args=[self.right_project.project_id],
                    )
                    + "#project-assignments-title",
                },
                {
                    "kind": "employee",
                    "label": "View employee",
                    "url": reverse(
                        "frontend:employee_detail",
                        args=[self.employee.employee_id],
                    )
                    + "?start_date=2026-09-10&end_date=2026-09-20",
                },
            ],
        )

        leave_event = by_id[f"approved_leave:{self.approved_leave.leave_id}"]
        leave_query = urlencode(
            {
                "employee": self.leave_only_employee.employee_id,
                "status": "approved",
                "from_date": "2026-09-10",
                "to_date": "2026-09-20",
            }
        )
        self.assertEqual(leave_event["source_label"], "Approved leave")
        self.assertEqual(
            leave_event["leave_type"],
            {"value": "annual", "label": "Annual"},
        )
        self.assertEqual(
            leave_event["links"],
            [
                {
                    "kind": "employee",
                    "label": "View employee",
                    "url": reverse(
                        "frontend:employee_detail",
                        args=[self.leave_only_employee.employee_id],
                    )
                    + "?start_date=2026-09-10&end_date=2026-09-20",
                },
                {
                    "kind": "leave",
                    "label": "View approved leave",
                    "url": f"{reverse('frontend:leave_list')}?{leave_query}",
                },
            ],
        )

        response_text = response.content.decode("utf-8")
        for forbidden in (
            "Private description",
            "estimated_hours",
            "capacity_hours_week",
            "allocation_percentage",
            "role_on_project",
        ):
            self.assertNotIn(forbidden, response_text)

    def test_order_is_deterministic_by_date_source_title_and_record_id(self):
        first = self.client.get(self.url, self._query()).json()["events"]
        second = self.client.get(self.url, self._query()).json()["events"]

        self.assertEqual(first, second)
        sort_keys = [
            (
                event["start_date"],
                event["end_date"],
                CALENDAR_SOURCE_ORDER[event["source"]],
                event["title"].casefold(),
                int(event["id"].split(":", 1)[1]),
            )
            for event in first
        ]
        self.assertEqual(sort_keys, sorted(sort_keys))

    def test_missing_dates_invalid_ranges_unknown_and_repeated_params_return_400(self):
        cases = (
            ({}, "Choose a reporting start date."),
            (
                {"start_date": "bad", "end_date": "2026-09-20"},
                "Enter a valid reporting start date.",
            ),
            (
                {"start_date": "2026-09-21", "end_date": "2026-09-20"},
                "The end date must be on or after the start date.",
            ),
            (
                {"start_date": "2025-01-01", "end_date": "2026-01-02"},
                "Choose a reporting period of 366 days or fewer.",
            ),
            (
                {
                    "start_date": "2026-09-10",
                    "end_date": "2026-09-20",
                    "capacity": "available",
                },
                "Use only supported calendar filter parameters.",
            ),
        )
        for query, expected_error in cases:
            with self.subTest(query=query), patch(
                "frontend.views.calendar.get_calendar_events"
            ) as selector:
                response = self.client.get(self.url, query)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["state"], "invalid")
                self.assertIn(expected_error, str(response.json()["errors"]))
                selector.assert_not_called()

        repeated_url = (
            f"{self.url}?start_date=2026-09-10&start_date=2026-09-11"
            "&end_date=2026-09-20"
        )
        with patch("frontend.views.calendar.get_calendar_events") as selector:
            repeated = self.client.get(repeated_url)
            self.assertEqual(repeated.status_code, 400)
            self.assertIn(
                "Provide each calendar request parameter once.",
                str(repeated.json()["errors"]),
            )
            selector.assert_not_called()

    def test_required_permissions_are_enforced_before_selection(self):
        required_codenames = (
            "view_project",
            "view_assignment",
            "view_employee",
        )
        users = [self.unassigned_user]
        for omitted_codename in required_codenames:
            user = get_user_model().objects.create_user(
                username=f"events-missing-{omitted_codename}"
            )
            self._grant(
                user,
                *(codename for codename in required_codenames if codename != omitted_codename),
            )
            users.append(user)

        for user in users:
            with self.subTest(username=user.username), patch(
                "frontend.views.calendar.get_calendar_events"
            ) as selector:
                client = Client()
                client.force_login(user)
                response = client.get(self.url, self._query())
                self.assertEqual(response.status_code, 403)
                selector.assert_not_called()

    def test_all_canonical_roles_receive_the_same_permitted_records(self):
        expected_ids = None
        for group_name, user in self.users_by_role.items():
            with self.subTest(group_name=group_name):
                client = Client()
                client.force_login(user)
                response = client.get(self.url, self._query())
                self.assertEqual(response.status_code, 200)
                event_ids = [event["id"] for event in response.json()["events"]]
                if expected_ids is None:
                    expected_ids = event_ids
                self.assertEqual(event_ids, expected_ids)

    def test_leave_is_omitted_before_query_and_links_follow_actual_permissions(self):
        client = Client()
        client.force_login(self.base_only_user)

        with CaptureQueriesContext(connection) as queries:
            response = client.get(self.url, self._query())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(queries), self.RESTRICTED_LEAVE_QUERY_COUNT)
        payload = response.json()
        self.assertEqual(payload["source_access"]["approved_leave"], "restricted")
        self.assertEqual(payload["event_count"], 3)
        self.assertFalse(
            any(event["source"] == "approved_leave" for event in payload["events"])
        )
        self.assertNotContains(response, "Leave Secret Person")
        self.assertFalse(
            any('"core_leave"' in query["sql"] for query in queries.captured_queries)
        )

        assignment_event = next(
            event for event in payload["events"] if event["source"] == "assignment"
        )
        self.assertEqual(
            assignment_event["links"],
            [
                {
                    "kind": "employee",
                    "label": "View employee",
                    "url": reverse(
                        "frontend:employee_detail",
                        args=[self.employee.employee_id],
                    )
                    + "?start_date=2026-09-10&end_date=2026-09-20",
                }
            ],
        )
        project_event = next(
            event for event in payload["events"] if event["source"] == "project"
        )
        self.assertEqual(project_event["links"], [])

    def test_restricted_source_is_checked_again_before_serialization(self):
        client = Client()
        client.force_login(self.base_only_user)
        unexpected_leave_event = CalendarEventRecord(
            record_id=self.approved_leave.leave_id,
            source=APPROVED_LEAVE_SOURCE,
            title="Leave Secret Person — Annual leave",
            start_date=self.approved_leave.start_date,
            end_date=self.approved_leave.end_date,
            status=Leave.Status.APPROVED,
            status_label="Approved",
            employee_id=self.leave_only_employee.employee_id,
            employee_label=str(self.leave_only_employee),
            leave_type=Leave.Type.ANNUAL,
            leave_type_label="Annual",
        )

        with patch(
            "frontend.views.calendar.get_calendar_events",
            return_value=(unexpected_leave_event,),
        ):
            response = client.get(self.url, self._query())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["event_count"], 0)
        self.assertEqual(response.json()["events"], [])
        self.assertNotContains(response, "Leave Secret Person")

    def test_empty_and_deleted_records_are_reflected_on_the_next_read(self):
        empty = self.client.get(
            self.url,
            {"start_date": "2027-01-01", "end_date": "2027-01-31"},
        ).json()
        self.assertEqual(empty["state"], "ready")
        self.assertEqual(empty["event_count"], 0)
        self.assertEqual(empty["events"], [])

        first = self.client.get(self.url, self._query()).json()
        deleted_id = f"project:{self.left_project.project_id}"
        self.assertIn(deleted_id, {event["id"] for event in first["events"]})
        Project.objects.filter(pk=self.left_project.pk).delete()

        second = self.client.get(self.url, self._query()).json()
        self.assertNotIn(deleted_id, {event["id"] for event in second["events"]})

    def test_endpoint_has_fixed_query_count_and_recorded_warm_response_time(self):
        warmup = self.client.get(self.url, self._query())
        self.assertEqual(warmup.status_code, 200)

        durations_ms = []
        response_size = None
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as queries:
                started_at = time.perf_counter()
                response = self.client.get(self.url, self._query())
                durations_ms.append((time.perf_counter() - started_at) * 1000)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(queries), self.EXPECTED_QUERY_COUNT)
            response_size = len(response.content)

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
            "\nM7.2 calendar-event endpoint baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            "4 returned events):\n"
            f"  queries={self.EXPECTED_QUERY_COUNT}, "
            f"median={result['median_ms']:.3f} ms, "
            f"p95={result['p95_ms']:.3f} ms, "
            f"min={result['min_ms']:.3f} ms, "
            f"max={result['max_ms']:.3f} ms, "
            f"response={response_size} bytes"
        )


class CalendarEventSourceBoundaryTests(SimpleTestCase):
    def test_event_selection_and_serialization_stay_out_of_templates_and_javascript(self):
        project_root = Path(__file__).resolve().parents[2]
        template_source = (
            project_root
            / "frontend"
            / "templates"
            / "frontend"
            / "calendar"
            / "workspace.html"
        ).read_text(encoding="utf-8")
        javascript_source = (
            project_root / "frontend" / "static" / "frontend" / "js" / "app.js"
        ).read_text(encoding="utf-8")
        combined_source = f"{template_source}\n{javascript_source}"

        for forbidden in (
            "start_date__lte",
            "end_date__gte",
            "allocation_percentage",
            "calculate_current_workload",
            "calculate_available_hours_for_project",
            "find_all_feasible_teams",
            "ortools",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined_source)

    def test_endpoint_calls_only_the_calendar_selector_for_event_records(self):
        project_root = Path(__file__).resolve().parents[2]
        view_source = (
            project_root / "frontend" / "views" / "calendar.py"
        ).read_text(encoding="utf-8")

        self.assertEqual(view_source.count("get_calendar_events("), 2)
        self.assertNotIn(".objects", view_source)
        self.assertNotIn("core.services", view_source)
        self.assertNotIn("Assignment.objects", view_source)
        self.assertNotIn("Leave.objects", view_source)
        self.assertNotIn("Project.objects", view_source)
