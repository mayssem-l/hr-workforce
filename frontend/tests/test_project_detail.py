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

from core.models import (
    Assignment,
    AssignmentSkill,
    Employee,
    EmployeeSkill,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from frontend.roles import VIEWER_GROUP, sync_role_permissions
from frontend.selectors.projects import get_project_profile


class ProjectDetailTests(TestCase):
    EXPECTED_QUERY_COUNT = 9
    SELECTOR_QUERY_COUNT = 4
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="project-profile-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.unassigned = get_user_model().objects.create_user(
            username="project-profile-unassigned"
        )
        cls.project_only_viewer = get_user_model().objects.create_user(
            username="project-only-viewer"
        )
        cls.project_only_viewer.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename="view_project",
            )
        )

        cls.python = Skill.objects.create(
            name="Python",
            category="Engineering",
        )
        cls.sql = Skill.objects.create(
            name="SQL",
            category="Data",
        )
        cls.leadership = Skill.objects.create(
            name="Leadership",
            category="Management",
        )
        cls.jamie = cls._create_employee(
            first_name="Jamie",
            last_name="Rivera",
            position="Platform Engineer",
        )
        cls.morgan = cls._create_employee(
            first_name="Morgan",
            last_name="Lee",
            position="Delivery Manager",
        )
        EmployeeSkill.objects.create(
            employee=cls.jamie,
            skill=cls.python,
            level=4,
            years_experience=Decimal("6.0"),
        )
        EmployeeSkill.objects.create(
            employee=cls.jamie,
            skill=cls.sql,
            level=3,
            years_experience=Decimal("4.0"),
        )

        cls.project = cls._create_project(
            name="Atlas Renewal",
            description="Modernize the workforce planning platform.",
            estimated_hours="200.00",
            status=Project.Status.IN_PROGRESS,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        cls.python_requirement = cls._create_requirement(
            project=cls.project,
            skill=cls.python,
            required_level=3,
            required_quantity=2,
            estimated_effort_hours="120.00",
            is_mandatory=True,
        )
        cls.sql_requirement = cls._create_requirement(
            project=cls.project,
            skill=cls.sql,
            required_level=3,
            required_quantity=1,
            estimated_effort_hours="80.00",
            is_mandatory=True,
        )
        cls._create_requirement(
            project=cls.project,
            skill=cls.leadership,
            required_level=2,
            required_quantity=1,
            estimated_effort_hours="40.00",
            is_mandatory=False,
        )
        cls.jamie_assignment = Assignment.objects.create(
            employee=cls.jamie,
            project=cls.project,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 11, 30),
            allocation_percentage=60,
            role_on_project="Technical lead",
            status=Assignment.Status.ACTIVE,
        )
        Assignment.objects.create(
            employee=cls.morgan,
            project=cls.project,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 12, 15),
            allocation_percentage=40,
            role_on_project="Delivery manager",
            status=Assignment.Status.PLANNED,
        )
        AssignmentSkill.objects.create(
            assignment=cls.jamie_assignment,
            project_skill_requirement=cls.python_requirement,
        )
        AssignmentSkill.objects.create(
            assignment=cls.jamie_assignment,
            project_skill_requirement=cls.sql_requirement,
        )

        cls.mismatch_project = cls._create_project(
            name="Beacon Expansion",
            description="Expand delivery capacity.",
            estimated_hours="300.00",
        )
        cls._create_requirement(
            project=cls.mismatch_project,
            skill=cls.python,
            required_level=3,
            required_quantity=1,
            estimated_effort_hours="100.00",
            is_mandatory=True,
        )
        cls.incomplete_project = cls._create_project(
            name="Cedar Migration",
            description="Prepare migration demand.",
            estimated_hours="160.00",
        )
        cls._create_requirement(
            project=cls.incomplete_project,
            skill=cls.sql,
            required_level=2,
            required_quantity=1,
            estimated_effort_hours=None,
            is_mandatory=True,
        )
        cls.empty_project = cls._create_project(
            name="Dormant Initiative",
            description="No planning context yet.",
            estimated_hours="0.00",
        )

    @classmethod
    def _create_employee(cls, *, first_name, last_name, position):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Engineering",
            position=position,
            hire_date=date(2020, 1, 15),
            experience_years=Decimal("6.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )

    @classmethod
    def _create_project(
        cls,
        *,
        name,
        description,
        estimated_hours,
        status=Project.Status.PLANNED,
        priority=Project.Priority.MEDIUM,
        criticality=Project.Criticality.MEDIUM,
    ):
        return Project.objects.create(
            name=name,
            description=description,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 31),
            estimated_hours=Decimal(estimated_hours),
            status=status,
            priority=priority,
            criticality=criticality,
        )

    @classmethod
    def _create_requirement(
        cls,
        *,
        project,
        skill,
        required_level,
        required_quantity,
        estimated_effort_hours,
        is_mandatory,
    ):
        return ProjectSkillRequirement.objects.create(
            project=project,
            skill=skill,
            required_level=required_level,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=is_mandatory,
            required_quantity=required_quantity,
            estimated_effort_hours=(
                Decimal(estimated_effort_hours)
                if estimated_effort_hours is not None
                else None
            ),
        )

    def setUp(self):
        self.url = reverse(
            "frontend:project_detail",
            args=[self.project.project_id],
        )
        self.client.force_login(self.viewer)

    def test_route_is_namespaced_and_directory_entries_link_to_detail(self):
        self.assertEqual(self.url, f"/projects/{self.project.project_id}/")
        match = resolve(self.url)
        self.assertEqual(match.view_name, "frontend:project_detail")
        self.assertEqual(match.namespace, "frontend")
        self.assertEqual(match.kwargs["project_id"], self.project.project_id)

        directory_response = self.client.get(reverse("frontend:project_list"))
        self.assertContains(directory_response, f'href="{self.url}"')

    def test_read_permissions_cover_project_and_related_planning_context(self):
        anonymous_response = Client().get(self.url)
        self.assertRedirects(
            anonymous_response,
            f"{reverse('frontend:login')}?next={self.url}",
            fetch_redirect_response=False,
        )

        for user in (self.unassigned, self.project_only_viewer):
            with self.subTest(user=user.username):
                client = Client()
                client.force_login(user)
                self.assertEqual(client.get(self.url).status_code, 403)

        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_missing_project_returns_not_found(self):
        missing_url = reverse("frontend:project_detail", args=[999999])
        self.assertEqual(self.client.get(missing_url).status_code, 404)

    def test_profile_renders_requirements_assignments_and_coverage(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/projects/detail.html")
        self.assertTemplateUsed(
            response,
            "frontend/projects/_requirement_row.html",
        )
        self.assertTemplateUsed(
            response,
            "frontend/projects/_assignment_row.html",
        )
        self.assertContains(response, "<h1>Atlas Renewal</h1>", html=True)
        self.assertContains(response, "Modernize the workforce planning platform.")
        self.assertContains(response, "Sep 1, 2026")
        self.assertContains(response, "Dec 31, 2026")
        self.assertContains(response, "200.00 h", count=2)
        self.assertContains(response, "Planning inputs aligned")
        self.assertContains(response, "Python")
        self.assertContains(response, "SQL")
        self.assertContains(response, "Leadership")
        self.assertContains(response, "Level 3 of 5", count=2)
        self.assertContains(response, "Jamie Rivera")
        self.assertContains(response, "Technical lead")
        self.assertContains(response, "60.0%")
        self.assertContains(response, "Morgan Lee")
        self.assertContains(response, "No requirements linked")
        self.assertRegex(
            response.content.decode("utf-8"),
            r'href="/projects/"\s+aria-current="page"',
        )
        self.assertNotContains(response, "Edit project")
        self.assertNotContains(response, "Delete project")

    def test_planning_input_states_cover_mismatch_incomplete_and_empty(self):
        mismatch_response = self.client.get(
            reverse(
                "frontend:project_detail",
                args=[self.mismatch_project.project_id],
            )
        )
        self.assertContains(mismatch_response, "Review project estimates")
        self.assertContains(mismatch_response, "300.00 h")
        self.assertContains(mismatch_response, "100.00 h")

        incomplete_response = self.client.get(
            reverse(
                "frontend:project_detail",
                args=[self.incomplete_project.project_id],
            )
        )
        self.assertContains(incomplete_response, "Planning input needed")
        self.assertContains(
            incomplete_response,
            "Enter estimated effort greater than 0 hours for the mandatory "
            "SQL requirement before generating recommendations.",
        )

        empty_response = self.client.get(
            reverse(
                "frontend:project_detail",
                args=[self.empty_project.project_id],
            )
        )
        self.assertContains(empty_response, "No mandatory requirements")
        self.assertContains(empty_response, "No skill requirements defined")
        self.assertContains(empty_response, "No employees assigned")

    def test_presenter_delegates_readiness_to_recommendation_preflight(self):
        preflight_result = {
            "can_generate_recommendations": True,
            "blockers": [],
        }
        with patch(
            "frontend.presenters.projects.get_recommendation_preflight",
            return_value=preflight_result,
        ) as preflight:
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        preflight.assert_called_once()
        self.assertEqual(preflight.call_args.args[0], self.project)
        self.assertIs(response.context["profile"]["preflight"], preflight_result)

    def test_selector_loads_all_profile_context_in_four_queries(self):
        with self.assertNumQueries(self.SELECTOR_QUERY_COUNT):
            project = get_project_profile(self.project.project_id)
            requirement_names = [
                requirement.skill.name
                for requirement in project.profile_requirements
            ]
            assignments = [
                (
                    assignment.employee.first_name,
                    [
                        coverage.project_skill_requirement.skill.name
                        for coverage in assignment.profile_coverage
                    ],
                )
                for assignment in project.profile_assignments
            ]

        self.assertEqual(requirement_names, ["SQL", "Python", "Leadership"])
        self.assertEqual(assignments[0], ("Jamie", ["SQL", "Python"]))
        self.assertEqual(assignments[1], ("Morgan", []))

    def test_populated_profile_query_count_matches_recorded_budget(self):
        with self.assertNumQueries(self.EXPECTED_QUERY_COUNT):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

    def test_warm_profile_response_time_is_recorded(self):
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
            "\nM3.2 project-profile baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            "3 requirements, 2 assignments, 2 coverage links):\n"
            f"  queries={self.EXPECTED_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )
