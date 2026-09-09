import statistics
import time
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from core.models import Assignment, Employee, EmployeeSkill, Leave, Project, Skill
from frontend.roles import VIEWER_GROUP, sync_role_permissions
from frontend.selectors.employees import get_employee_profile


class EmployeeDetailTests(TestCase):
    AS_OF = date(2026, 9, 8)
    EXPECTED_QUERY_COUNT = 12
    SELECTOR_QUERY_COUNT = 4
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(username="profile-viewer")
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.unassigned = get_user_model().objects.create_user(
            username="profile-unassigned"
        )

        cls.employee = cls._create_employee(first_name="Jamie", last_name="Rivera")
        cls.empty_employee = cls._create_employee(
            first_name="Morgan",
            last_name="Lee",
        )

        active_project = cls._create_project(
            name="Project Atlas",
            start_date=cls.AS_OF - timedelta(days=30),
            end_date=cls.AS_OF + timedelta(days=45),
            status=Project.Status.IN_PROGRESS,
        )
        planned_project = cls._create_project(
            name="Project Horizon",
            start_date=cls.AS_OF + timedelta(days=20),
            end_date=cls.AS_OF + timedelta(days=75),
            status=Project.Status.PLANNED,
        )
        cancelled_project = cls._create_project(
            name="Cancelled Initiative",
            start_date=cls.AS_OF - timedelta(days=5),
            end_date=cls.AS_OF + timedelta(days=10),
            status=Project.Status.CANCELLED,
        )
        completed_project = cls._create_project(
            name="Completed Rollout",
            start_date=cls.AS_OF - timedelta(days=80),
            end_date=cls.AS_OF - timedelta(days=10),
            status=Project.Status.COMPLETED,
        )

        Assignment.objects.create(
            employee=cls.employee,
            project=active_project,
            start_date=cls.AS_OF - timedelta(days=10),
            end_date=cls.AS_OF + timedelta(days=20),
            allocation_percentage=50,
            role_on_project="Technical lead",
            status=Assignment.Status.ACTIVE,
        )
        Assignment.objects.create(
            employee=cls.employee,
            project=planned_project,
            start_date=cls.AS_OF + timedelta(days=20),
            end_date=cls.AS_OF + timedelta(days=60),
            allocation_percentage=25,
            role_on_project="Architecture advisor",
            status=Assignment.Status.PLANNED,
        )
        Assignment.objects.create(
            employee=cls.employee,
            project=cancelled_project,
            start_date=cls.AS_OF - timedelta(days=5),
            end_date=cls.AS_OF + timedelta(days=10),
            allocation_percentage=30,
            role_on_project="Cancelled role",
            status=Assignment.Status.CANCELLED,
        )
        Assignment.objects.create(
            employee=cls.employee,
            project=completed_project,
            start_date=cls.AS_OF - timedelta(days=60),
            end_date=cls.AS_OF - timedelta(days=10),
            allocation_percentage=40,
            role_on_project="Completed role",
            status=Assignment.Status.COMPLETED,
        )

        Leave.objects.create(
            employee=cls.employee,
            start_date=cls.AS_OF + timedelta(days=7),
            end_date=cls.AS_OF + timedelta(days=11),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )
        Leave.objects.create(
            employee=cls.employee,
            start_date=cls.AS_OF + timedelta(days=3),
            end_date=cls.AS_OF + timedelta(days=4),
            type=Leave.Type.SICK,
            status=Leave.Status.PENDING,
        )
        Leave.objects.create(
            employee=cls.employee,
            start_date=cls.AS_OF - timedelta(days=20),
            end_date=cls.AS_OF - timedelta(days=18),
            type=Leave.Type.OTHER,
            status=Leave.Status.APPROVED,
        )

        python_skill = Skill.objects.create(name="Python", category="Engineering")
        leadership_skill = Skill.objects.create(
            name="Leadership",
            category="Management",
        )
        EmployeeSkill.objects.create(
            employee=cls.employee,
            skill=python_skill,
            level=4,
            years_experience=Decimal("6.5"),
        )
        EmployeeSkill.objects.create(
            employee=cls.employee,
            skill=leadership_skill,
            level=3,
            years_experience=Decimal("2.0"),
        )

    @classmethod
    def _create_employee(cls, *, first_name, last_name):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Engineering",
            position="Platform Engineer",
            hire_date=date(2019, 4, 15),
            experience_years=Decimal("7.5"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )

    @classmethod
    def _create_project(cls, *, name, start_date, end_date, status):
        return Project.objects.create(
            name=name,
            description=f"Planning context for {name}.",
            start_date=start_date,
            end_date=end_date,
            estimated_hours=Decimal("200.00"),
            status=status,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )

    def setUp(self):
        self.url = reverse(
            "frontend:employee_detail",
            args=[self.employee.employee_id],
        )
        self.client.force_login(self.viewer)

    def test_route_is_namespaced_and_resolves_to_employee_detail(self):
        self.assertEqual(self.url, f"/employees/{self.employee.employee_id}/")
        match = resolve(self.url)
        self.assertEqual(match.view_name, "frontend:employee_detail")
        self.assertEqual(match.namespace, "frontend")
        self.assertEqual(match.kwargs["employee_id"], self.employee.employee_id)

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_read_permission_handles_anonymous_unassigned_and_viewer_users(
        self,
        _localdate,
    ):
        anonymous_response = Client().get(self.url)
        self.assertRedirects(
            anonymous_response,
            f"{reverse('frontend:login')}?next={self.url}",
            fetch_redirect_response=False,
        )

        unassigned_client = Client()
        unassigned_client.force_login(self.unassigned)
        self.assertEqual(unassigned_client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_missing_employee_returns_not_found(self, _localdate):
        missing_url = reverse("frontend:employee_detail", args=[999999])
        self.assertEqual(self.client.get(missing_url).status_code, 404)

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_profile_renders_core_details_and_service_calculated_capacity(
        self,
        _localdate,
    ):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/employees/detail.html")
        self.assertTemplateUsed(response, "frontend/employees/_assignment_row.html")
        self.assertContains(response, "<h1>Jamie Rivera</h1>", html=True)
        self.assertContains(
            response,
            f"Employee #{self.employee.employee_id:04d}",
        )
        self.assertContains(response, "Platform Engineer")
        self.assertContains(response, "Engineering")
        self.assertContains(response, "Apr 15, 2019")
        self.assertContains(response, "7.5 years")
        self.assertContains(response, "40.00 h")
        self.assertContains(response, "50.0%")
        self.assertContains(response, "20.00 h")
        self.assertContains(response, "4.00 h")
        self.assertContains(response, "Monday-to-Friday")
        self.assertContains(response, "Employment status")
        self.assertContains(response, "Dated availability")
        self.assertRegex(
            response.content.decode("utf-8"),
            r'href="/employees/"\s+aria-current="page"',
        )
        self.assertNotContains(response, "Edit employee")
        self.assertNotContains(response, "Delete employee")

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_profile_shows_only_relevant_assignments_leave_and_skills(
        self,
        _localdate,
    ):
        response = self.client.get(self.url)

        self.assertContains(response, "Project Atlas")
        self.assertContains(response, "Technical lead")
        self.assertContains(response, "Project Horizon")
        self.assertContains(response, "Architecture advisor")
        self.assertNotContains(response, "Cancelled Initiative")
        self.assertNotContains(response, "Completed Rollout")
        self.assertContains(response, "Annual leave")
        self.assertNotContains(response, "Sick leave")
        self.assertNotContains(response, "Other leave")
        self.assertContains(response, "Python")
        self.assertContains(response, "Level 4 of 5")
        self.assertContains(response, "6.5 years of experience")
        self.assertContains(response, "Leadership")

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_empty_related_sections_have_specific_empty_states(self, _localdate):
        empty_url = reverse(
            "frontend:employee_detail",
            args=[self.empty_employee.employee_id],
        )
        response = self.client.get(empty_url)

        self.assertContains(response, "No active or upcoming assignments")
        self.assertContains(response, "No skills recorded")
        self.assertContains(response, "No upcoming approved leave")

    def test_presenter_delegates_calculated_values_to_core_services(self):
        with (
            patch(
                "frontend.views.employees.timezone.localdate",
                return_value=self.AS_OF,
            ),
            patch(
                "frontend.presenters.employees.calculate_current_workload",
                return_value=Decimal("37.0"),
            ) as current_workload,
            patch(
                "frontend.presenters.employees.calculate_available_hours",
                return_value=Decimal("25.20"),
            ) as available_weekly,
            patch(
                "frontend.presenters.employees.calculate_daily_available_hours",
                return_value=Decimal("5.04"),
            ) as available_today,
        ):
            response = self.client.get(self.url)

        self.assertContains(response, "37.0%")
        self.assertContains(response, "25.20 h")
        self.assertContains(response, "5.04 h")
        for service in (current_workload, available_weekly, available_today):
            service.assert_called_once()
            called_employee, called_date = service.call_args.args
            self.assertEqual(called_employee, self.employee)
            self.assertEqual(called_date, self.AS_OF)

    def test_selector_loads_profile_collections_in_four_queries(self):
        with self.assertNumQueries(self.SELECTOR_QUERY_COUNT):
            employee = get_employee_profile(
                self.employee.employee_id,
                on_date=self.AS_OF,
            )
            assignment_names = [
                assignment.project.name for assignment in employee.profile_assignments
            ]
            leave_types = [leave.type for leave in employee.profile_upcoming_leaves]
            skill_names = [
                employee_skill.skill.name
                for employee_skill in employee.profile_skills
            ]

        self.assertEqual(assignment_names, ["Project Atlas", "Project Horizon"])
        self.assertEqual(leave_types, [Leave.Type.ANNUAL])
        self.assertEqual(skill_names, ["Python", "Leadership"])

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_populated_profile_query_count_matches_the_recorded_budget(
        self,
        _localdate,
    ):
        with self.assertNumQueries(self.EXPECTED_QUERY_COUNT):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_warm_profile_response_time_is_recorded(self, _localdate):
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

        p95_ms = statistics.quantiles(
            durations_ms,
            n=20,
            method="inclusive",
        )[18]
        print(
            "\nM2.2 employee-profile baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            "2 relevant assignments, "
            "1 upcoming approved leave, 2 skills):\n"
            f"  queries={self.EXPECTED_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )
