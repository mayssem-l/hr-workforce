"""M7.6 project-focused timelines from the shared event contract.

Read-only schedule visualization for one project's stored period, its
assignments, and approved leave for assigned employees, reusing selector
overlap rules, endpoint payload parity, permission boundaries, and the
accessible M7.4 evidence structures.
"""

import statistics
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from core.models import (
    Assignment,
    AssignmentSkill,
    Employee,
    EmployeeSkill,
    Leave,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from frontend.presenters.timeline import build_timeline_bands
from frontend.roles import VIEWER_GROUP, sync_role_permissions
from frontend.selectors.calendar import get_calendar_events


class ProjectTimelineTests(TestCase):
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="timeline-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.no_leave_user = get_user_model().objects.create_user(
            username="timeline-no-leave"
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
        cls.python = Skill.objects.create(
            name="Python", category="Engineering"
        )
        cls.project = Project.objects.create(
            name="Timeline project",
            description="Project timeline fixture.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 18),
            estimated_hours=Decimal("80.00"),
            status=Project.Status.IN_PROGRESS,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        cls.other_project = Project.objects.create(
            name="Unrelated project",
            description="Out-of-scope timeline fixture.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 18),
            estimated_hours=Decimal("40.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )
        cls.alex = Employee.objects.create(
            first_name="Alex",
            last_name="Able",
            department="Engineering",
            position="Engineer",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("6.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )
        cls.blake = Employee.objects.create(
            first_name="Blake",
            last_name="Baker",
            department="Engineering",
            position="Engineer",
            hire_date=date(2020, 2, 3),
            experience_years=Decimal("4.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )
        for employee in (cls.alex, cls.blake):
            EmployeeSkill.objects.create(
                employee=employee,
                skill=cls.python,
                level=4,
                years_experience=Decimal("3.0"),
            )
        cls.first_assignment = Assignment.objects.create(
            employee=cls.alex,
            project=cls.project,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 12),
            allocation_percentage=50,
            role_on_project="Backend work",
            status=Assignment.Status.ACTIVE,
        )
        cls.second_assignment = Assignment.objects.create(
            employee=cls.blake,
            project=cls.project,
            start_date=date(2026, 9, 10),
            end_date=date(2026, 9, 18),
            allocation_percentage=50,
            role_on_project="Frontend work",
            status=Assignment.Status.PLANNED,
        )
        cls.outside_assignment = Assignment.objects.create(
            employee=cls.alex,
            project=cls.other_project,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 18),
            allocation_percentage=25,
            role_on_project="Other work",
            status=Assignment.Status.ACTIVE,
        )
        cls.leave = Leave.objects.create(
            employee=cls.alex,
            start_date=date(2026, 9, 14),
            end_date=date(2026, 9, 15),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )
        cls.unrelated_leave = Leave.objects.create(
            employee=cls.blake,
            start_date=date(2026, 10, 5),
            end_date=date(2026, 10, 6),
            type=Leave.Type.SICK,
            status=Leave.Status.APPROVED,
        )

    def setUp(self):
        self.client.force_login(self.viewer)
        self.timeline_url = reverse(
            "frontend:project_timeline",
            args=[self.project.project_id],
        )
        self.planning_url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )
        self.detail_url = reverse(
            "frontend:project_detail",
            args=[self.project.project_id],
        )

    def test_route_methods_navigation_and_templates(self):
        self.assertEqual(
            self.timeline_url,
            f"/projects/{self.project.project_id}/timeline/",
        )
        match = resolve(self.timeline_url)
        self.assertEqual(match.view_name, "frontend:project_timeline")
        response = self.client.get(self.timeline_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "frontend/projects/timeline.html"
        )
        self.assertRegex(
            response.content.decode("utf-8"),
            r'href="/projects/"\s+aria-current="page"',
        )
        self.assertContains(response, f'href="{self.planning_url}"')
        self.assertContains(response, f'href="{self.detail_url}"')
        self.assertEqual(
            self.client.post(self.timeline_url, {}).status_code, 405
        )
        self.assertEqual(
            self.client.put(self.timeline_url, {}).status_code, 405
        )

    def test_authentication_and_permission_contract(self):
        anonymous = Client()
        self.assertRedirects(
            anonymous.get(self.timeline_url),
            f"{reverse('frontend:login')}?next={self.timeline_url}",
            fetch_redirect_response=False,
        )
        unassigned = get_user_model().objects.create_user(
            username="timeline-unassigned"
        )
        unassigned_client = Client()
        unassigned_client.force_login(unassigned)
        self.assertEqual(
            unassigned_client.get(self.timeline_url).status_code, 403
        )
        for codename in (
            "view_project",
            "view_assignment",
            "view_employee",
        ):
            restricted = get_user_model().objects.create_user(
                username=f"timeline-without-{codename}"
            )
            wanted = {
                "view_project",
                "view_assignment",
                "view_employee",
            } - {codename}
            restricted.user_permissions.add(
                *Permission.objects.filter(
                    content_type__app_label="core",
                    codename__in=wanted,
                )
            )
            restricted_client = Client()
            restricted_client.force_login(restricted)
            with self.subTest(missing=codename):
                self.assertEqual(
                    restricted_client.get(self.timeline_url).status_code,
                    403,
                )

    def test_scoping_keeps_only_routed_project_evidence(self):
        response = self.client.get(self.timeline_url)
        titles = [
            row["event"]["title"] for row in response.context["timeline_rows"]
        ]
        self.assertIn("Timeline project", titles)
        self.assertIn("Alex Able — Timeline project", titles)
        self.assertIn("Blake Baker — Timeline project", titles)
        self.assertNotIn("Unrelated project", titles)
        self.assertNotIn("Alex Able — Unrelated project", titles)
        sources = {
            row["event"]["source"] for row in response.context["timeline_rows"]
        }
        self.assertEqual(
            sources, {"project", "assignment", "approved_leave"}
        )
        html = response.content.decode("utf-8")
        self.assertNotIn("Unrelated project", html)

    def test_overlapping_assignments_share_the_visual_period(self):
        response = self.client.get(self.timeline_url)
        bands = {
            band["label"]: band for band in response.context["bands"]
        }
        first = bands["Alex Able — Timeline project"]
        second = bands["Blake Baker — Timeline project"]
        self.assertLess(first["start_percent"], second["start_percent"])
        self.assertGreater(
            first["start_percent"] + first["width_percent"],
            second["start_percent"],
        )
        self.assertContains(response, "infers no conflict")

    def test_boundary_dates_and_overhang_are_truthful(self):
        edge = Assignment.objects.create(
            employee=self.blake,
            project=self.project,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
            allocation_percentage=10,
            role_on_project="Overhang work",
            status=Assignment.Status.PLANNED,
        )
        try:
            response = self.client.get(self.timeline_url)
            bands = list(response.context["bands"])
            overhang = next(
                band
                for band in bands
                if band["event"].record_id == edge.assignment_id
            )
            self.assertEqual(overhang["start_percent"], 0.0)
            self.assertEqual(overhang["width_percent"], 100.0)
            self.assertTrue(overhang["starts_before"])
            self.assertTrue(overhang["ends_after"])
            first_day = next(
                band
                for band in bands
                if band["event"].record_id
                == self.first_assignment.assignment_id
            )
            self.assertEqual(first_day["start_percent"], 0.0)
            self.assertGreater(first_day["width_percent"], 0.0)
        finally:
            edge.delete()

    def test_empty_and_restricted_states(self):
        empty_project = Project.objects.create(
            name="Empty timeline project",
            description="No staffing fixture.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            estimated_hours=Decimal("8.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )
        try:
            response = self.client.get(
                reverse(
                    "frontend:project_timeline",
                    args=[empty_project.project_id],
                )
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["event_count"], 1)
            self.assertContains(response, "Empty timeline project")
            self.assertContains(response, "no matching entries")
        finally:
            empty_project.delete()

        restricted_client = Client()
        restricted_client.force_login(self.no_leave_user)
        restricted = restricted_client.get(self.timeline_url)
        self.assertEqual(restricted.status_code, 200)
        sources = {
            row["event"]["source"]
            for row in restricted.context["timeline_rows"]
        }
        self.assertNotIn("approved_leave", sources)
        self.assertContains(restricted, "Approved leave is restricted")

    def test_stale_and_deleted_records(self):
        missing_url = reverse(
            "frontend:project_timeline", args=[999999]
        )
        self.assertEqual(self.client.get(missing_url).status_code, 404)
        doomed = Assignment.objects.create(
            employee=self.blake,
            project=self.project,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 8),
            allocation_percentage=10,
            role_on_project="Doomed work",
            status=Assignment.Status.PLANNED,
        )
        doomed_id = doomed.assignment_id
        doomed.delete()
        response = self.client.get(self.timeline_url)
        record_ids = [
            row["event"]["id"] for row in response.context["timeline_rows"]
        ]
        self.assertNotIn(f"assignment:{doomed_id}", record_ids)

    def test_entry_links_use_existing_workflows(self):
        response = self.client.get(self.timeline_url)
        coverage_url = reverse(
            "frontend:project_assignment_coverage",
            args=[self.project.project_id, self.first_assignment.assignment_id],
        )
        self.assertContains(response, coverage_url)
        self.assertContains(
            response,
            reverse(
                "frontend:employee_detail",
                args=[self.alex.employee_id],
            ),
        )
        self.assertContains(response, reverse("frontend:leave_list"))
        self.assertContains(response, self.planning_url)
        detail = self.client.get(self.detail_url)
        self.assertContains(
            detail,
            reverse(
                "frontend:project_timeline",
                args=[self.project.project_id],
            ),
        )
        planning = self.client.get(self.planning_url)
        self.assertContains(
            planning,
            reverse(
                "frontend:project_timeline",
                args=[self.project.project_id],
            ),
        )

    def test_rows_match_shared_selector_contract_in_order(self):
        response = self.client.get(self.timeline_url)
        selector_events = get_calendar_events(
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            source_access={
                "projects": True,
                "assignments": True,
                "approved_leave": True,
            },
            filters={
                "sources": ("project", "assignment"),
                "department": "",
                "employee": "",
                "project": str(self.project.project_id),
            },
        )
        assigned_ids = frozenset(
            event.employee_id
            for event in selector_events
            if event.source == "assignment" and event.employee_id
        )
        selector_leave = get_calendar_events(
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            source_access={
                "projects": True,
                "assignments": True,
                "approved_leave": True,
            },
            filters={
                "sources": ("approved_leave",),
                "department": "",
                "employee": assigned_ids,
                "project": "",
            },
        )
        expected_ids = [
            event.event_id
            for event in (*selector_events, *selector_leave)
        ]
        rendered_ids = [
            row["event"]["id"] for row in response.context["timeline_rows"]
        ]
        self.assertEqual(rendered_ids, expected_ids)
        for row in response.context["timeline_rows"]:
            self.assertIn("calendar", row["event"])
            self.assertIn(row["event"]["source"], ("project", "assignment", "approved_leave"))

    def test_accessible_markup_and_deterministic_repeat(self):
        first = self.client.get(self.timeline_url)
        second = self.client.get(self.timeline_url)
        self.assertEqual(
            [row["event"]["id"] for row in first.context["timeline_rows"]],
            [row["event"]["id"] for row in second.context["timeline_rows"]],
        )
        html = first.content.decode("utf-8")
        self.assertEqual(html.count("<h1"), 1)
        self.assertIn("<caption>", html)
        self.assertIn('scope="col"', html)
        self.assertIn("<time datetime=", html)
        self.assertIn('aria-hidden="true"', html)
        self.assertNotIn("onclick", html)
        self.assertNotIn("conflict score", html.lower())
        self.assertContains(
            first, "infers no conflict", status_code=200
        )

    def test_band_positions_follow_one_deterministic_contract(self):
        from datetime import date as date_class

        bands = build_timeline_bands(
            get_calendar_events(
                start_date=self.project.start_date,
                end_date=self.project.end_date,
                source_access={
                    "projects": True,
                    "assignments": True,
                    "approved_leave": True,
                },
                filters={
                    "sources": ("project", "assignment"),
                    "department": "",
                    "employee": "",
                    "project": str(self.project.project_id),
                },
            ),
            period_start=date_class(2026, 9, 7),
            period_end=date_class(2026, 9, 18),
        )
        by_label = {band["label"]: band for band in bands}
        project_band = by_label["Timeline project"]
        self.assertEqual(project_band["start_percent"], 0.0)
        self.assertEqual(project_band["width_percent"], 100.0)
        alex_band = by_label["Alex Able — Timeline project"]
        self.assertEqual(alex_band["start_percent"], 0.0)
        self.assertEqual(alex_band["width_percent"], 50.0)
        for band in bands:
            self.assertGreaterEqual(band["start_percent"], 0.0)
            self.assertGreaterEqual(band["width_percent"], 2.0)
            self.assertLessEqual(
                band["start_percent"] + band["width_percent"], 102.0
            )

    def test_fixed_queries_and_warm_response(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.timeline_url)
        self.assertEqual(response.status_code, 200)
        count = len(queries)
        for _ in range(5):
            Assignment.objects.create(
                employee=self.blake,
                project=self.project,
                start_date=date(2026, 9, 7),
                end_date=date(2026, 9, 8),
                allocation_percentage=5,
                role_on_project="Extra work",
                status=Assignment.Status.PLANNED,
            )
        try:
            with CaptureQueriesContext(connection) as grown_queries:
                grown = self.client.get(self.timeline_url)
            self.assertEqual(grown.status_code, 200)
            self.assertEqual(len(grown_queries), count)
        finally:
            Assignment.objects.filter(role_on_project="Extra work").delete()
        durations = []
        response_size = 0
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as timed_queries:
                started_at = time.perf_counter()
                timed = self.client.get(self.timeline_url)
                durations.append((time.perf_counter() - started_at) * 1000)
            self.assertEqual(timed.status_code, 200)
            self.assertEqual(len(timed_queries), count)
            response_size = len(timed.content)
        print(
            "\nM7.6 project-timeline baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm GETs, "
            f"{response.context['event_count']} entries):\n"
            f"  queries={count}, "
            f"median={statistics.median(durations):.3f} ms, "
            f"p95={statistics.quantiles(durations, n=20, method='inclusive')[18]:.3f} ms, "
            f"response={response_size} bytes"
        )

    def test_source_boundaries_exclude_duplicated_logic(self):
        frontend_root = Path(__file__).resolve().parents[1]
        combined = "\n".join(
            (frontend_root / path).read_text(encoding="utf-8").lower()
            for path in (
                "presenters/timeline.py",
                "views/timeline.py",
                "templates/frontend/projects/timeline.html",
            )
        )
        for forbidden in (
            "calculate_current_workload",
            "calculate_available_hours_for_project",
            "find_all_feasible_teams",
            "select_recommended_teams",
            "conflict score",
            "attendance.objects",
            "ortools",
            ".save(",
            ".delete(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)
