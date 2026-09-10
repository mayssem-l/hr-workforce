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
    Project,
    ProjectSkillRequirement,
    Skill,
)
from frontend.presenters.planning import build_project_planning_foundation
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)
from frontend.selectors.projects import get_project_profile


class ProjectPlanningWorkspaceTests(TestCase):
    EXPECTED_QUERY_COUNT = 14
    SELECTOR_QUERY_COUNT = 4
    TIMING_SAMPLE_COUNT = 25
    REQUIRED_VIEW_CODENAMES = (
        "view_project",
        "view_projectskillrequirement",
        "view_assignment",
        "view_assignmentskill",
        "view_employee",
        "view_skill",
    )

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = cls._group_user("planning-viewer", VIEWER_GROUP)
        cls.manager = cls._group_user(
            "planning-manager",
            MANAGER_PLANNER_GROUP,
        )
        cls.hr_administrator = cls._group_user(
            "planning-hr",
            HR_ADMINISTRATOR_GROUP,
        )
        cls.unassigned = get_user_model().objects.create_user(
            username="planning-unassigned"
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
        cls.jamie = cls._employee(
            "Jamie",
            "Rivera",
            "Platform Engineer",
        )
        cls.morgan = cls._employee(
            "Morgan",
            "Lee",
            "Delivery Manager",
        )

        cls.project = cls._project(
            "Atlas Renewal",
            "Modernize the workforce planning platform.",
            "200.00",
            status=Project.Status.IN_PROGRESS,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        cls.python_requirement = cls._requirement(
            cls.project,
            cls.python,
            required_level=3,
            required_quantity=2,
            estimated_effort="120.00",
            mandatory=True,
        )
        cls.sql_requirement = cls._requirement(
            cls.project,
            cls.sql,
            required_level=3,
            required_quantity=1,
            estimated_effort="80.00",
            mandatory=True,
        )
        cls._requirement(
            cls.project,
            cls.leadership,
            required_level=2,
            required_quantity=1,
            estimated_effort="40.00",
            mandatory=False,
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

        cls.incomplete_project = cls._project(
            "Cedar Migration",
            "Prepare migration demand.",
            "160.00",
        )
        cls._requirement(
            cls.incomplete_project,
            cls.sql,
            required_level=2,
            required_quantity=1,
            estimated_effort=None,
            mandatory=True,
        )
        cls.empty_project = cls._project(
            "Dormant Initiative",
            "No planning context yet.",
            "0.00",
        )

    @staticmethod
    def _group_user(username, group_name):
        user = get_user_model().objects.create_user(username=username)
        user.groups.add(Group.objects.get(name=group_name))
        return user

    @staticmethod
    def _employee(first_name, last_name, position):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Engineering",
            position=position,
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("6.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )

    @staticmethod
    def _project(
        name,
        description,
        estimated_hours,
        *,
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

    @staticmethod
    def _requirement(
        project,
        skill,
        *,
        required_level,
        required_quantity,
        estimated_effort,
        mandatory,
    ):
        return ProjectSkillRequirement.objects.create(
            project=project,
            skill=skill,
            required_level=required_level,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=mandatory,
            required_quantity=required_quantity,
            estimated_effort_hours=(
                Decimal(estimated_effort)
                if estimated_effort is not None
                else None
            ),
        )

    def setUp(self):
        self.url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )
        self.client.force_login(self.viewer)

    def test_route_template_navigation_and_project_profile_entry_point(self):
        self.assertEqual(
            self.url,
            f"/projects/{self.project.project_id}/planning/",
        )
        match = resolve(self.url)
        self.assertEqual(match.view_name, "frontend:project_planning")
        self.assertEqual(match.namespace, "frontend")
        self.assertEqual(match.kwargs["project_id"], self.project.project_id)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/planning/workspace.html")
        self.assertTemplateUsed(
            response,
            "frontend/planning/_requirement_row.html",
        )
        self.assertTemplateUsed(
            response,
            "frontend/planning/_assignment_row.html",
        )
        self.assertRegex(
            response.content.decode("utf-8"),
            r'href="/projects/"\s+aria-current="page"',
        )

        detail_url = reverse(
            "frontend:project_detail",
            args=[self.project.project_id],
        )
        detail_response = self.client.get(detail_url)
        self.assertContains(detail_response, f'href="{self.url}"')
        self.assertContains(detail_response, "Open planning workspace")

    def test_complete_model_permission_contract_and_get_only_behavior(self):
        anonymous_response = Client().get(self.url)
        self.assertRedirects(
            anonymous_response,
            f"{reverse('frontend:login')}?next={self.url}",
            fetch_redirect_response=False,
        )

        unassigned_client = Client()
        unassigned_client.force_login(self.unassigned)
        self.assertEqual(unassigned_client.get(self.url).status_code, 403)

        permissions = {
            permission.codename: permission
            for permission in Permission.objects.filter(
                content_type__app_label="core",
                codename__in=self.REQUIRED_VIEW_CODENAMES,
            )
        }
        self.assertEqual(set(permissions), set(self.REQUIRED_VIEW_CODENAMES))
        for omitted_codename in self.REQUIRED_VIEW_CODENAMES:
            user = get_user_model().objects.create_user(
                username=f"planning-without-{omitted_codename}"
            )
            user.user_permissions.add(
                *(
                    permission
                    for codename, permission in permissions.items()
                    if codename != omitted_codename
                )
            )
            client = Client()
            client.force_login(user)
            with self.subTest(missing=omitted_codename):
                self.assertEqual(client.get(self.url).status_code, 403)

        for user in (self.viewer, self.manager, self.hr_administrator):
            client = Client()
            client.force_login(user)
            with self.subTest(role=user.username):
                self.assertEqual(client.get(self.url).status_code, 200)

        counts_before = (
            Project.objects.count(),
            ProjectSkillRequirement.objects.count(),
            Assignment.objects.count(),
            AssignmentSkill.objects.count(),
        )
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.assertEqual(self.client.put(self.url).status_code, 405)
        self.assertEqual(
            (
                Project.objects.count(),
                ProjectSkillRequirement.objects.count(),
                Assignment.objects.count(),
                AssignmentSkill.objects.count(),
            ),
            counts_before,
        )

    def test_workspace_renders_only_stored_foundation_context(self):
        with patch(
            "frontend.presenters.projects.get_recommendation_preflight"
        ) as profile_preflight:
            selected = get_project_profile(self.project.project_id)
            foundation = build_project_planning_foundation(selected)

        profile_preflight.assert_not_called()
        self.assertEqual(foundation["project"], self.project)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        workspace = response.context["workspace"]
        self.assertEqual(workspace["project"], self.project)
        self.assertEqual(workspace["requirement_count"], 3)
        self.assertEqual(workspace["mandatory_requirement_count"], 2)
        self.assertEqual(workspace["mandatory_effort_hours"], Decimal("200.00"))
        self.assertEqual(workspace["mandatory_effort_unset_count"], 0)
        self.assertEqual(workspace["assignment_count"], 2)
        self.assertEqual(workspace["coverage_count"], 2)

        self.assertContains(response, "<h1>Atlas Renewal</h1>", html=True)
        self.assertContains(response, "Modernize the workforce planning platform.")
        self.assertContains(response, "Sep 1, 2026")
        self.assertContains(response, "Dec 31, 2026")
        self.assertContains(response, "200.00 h", count=2)
        self.assertContains(response, "Python")
        self.assertContains(response, "SQL")
        self.assertContains(response, "Leadership")
        self.assertContains(response, "Jamie Rivera")
        self.assertContains(response, "Morgan Lee")
        self.assertContains(response, "60.0%")
        self.assertContains(response, "No requirements linked")
        self.assertContains(
            response,
            "It does not enumerate teams, run optimization, or generate "
            "recommendations.",
        )
        for action_label in (
            "Add requirement",
            "Edit requirement",
            "Add assignment",
            "Edit assignment",
        ):
            self.assertNotContains(response, action_label)
        self.assertContains(response, "Review coverage")

    def test_incomplete_empty_missing_and_presenter_states_are_explicit(self):
        incomplete_url = reverse(
            "frontend:project_planning",
            args=[self.incomplete_project.project_id],
        )
        incomplete = self.client.get(incomplete_url)
        self.assertEqual(incomplete.status_code, 200)
        self.assertContains(incomplete, "Not entered")
        self.assertContains(
            incomplete,
            "1 mandatory requirement has no estimated effort entered and "
            "remains visible below.",
        )
        self.assertNotContains(incomplete, "Planning input needed")

        empty_url = reverse(
            "frontend:project_planning",
            args=[self.empty_project.project_id],
        )
        empty = self.client.get(empty_url)
        self.assertEqual(empty.status_code, 200)
        self.assertContains(empty, "No skill requirements defined")
        self.assertContains(empty, "No employees assigned")
        self.assertEqual(empty.context["workspace"]["requirement_count"], 0)
        self.assertEqual(empty.context["workspace"]["assignment_count"], 0)
        self.assertEqual(
            empty.context["workspace"]["mandatory_effort_hours"],
            Decimal("0"),
        )

        missing_url = reverse("frontend:project_planning", args=[999999])
        self.assertEqual(self.client.get(missing_url).status_code, 404)

        selected = get_project_profile(self.project.project_id)
        presented = build_project_planning_foundation(selected)
        self.assertEqual(presented["project"], selected)
        self.assertIs(presented["requirements"], selected.profile_requirements)
        self.assertIs(presented["assignments"], selected.profile_assignments)

    def test_selector_query_budget_source_boundary_and_warm_response_time(self):
        with self.assertNumQueries(self.SELECTOR_QUERY_COUNT):
            selected = get_project_profile(self.project.project_id)
            requirement_names = [
                requirement.skill.name
                for requirement in selected.profile_requirements
            ]
            assignment_evidence = [
                (
                    assignment.employee.first_name,
                    tuple(
                        coverage.project_skill_requirement.skill.name
                        for coverage in assignment.profile_coverage
                    ),
                )
                for assignment in selected.profile_assignments
            ]
        self.assertEqual(requirement_names, ["SQL", "Python", "Leadership"])
        self.assertEqual(assignment_evidence[0], ("Jamie", ("SQL", "Python")))
        self.assertEqual(assignment_evidence[1], ("Morgan", ()))

        with self.assertNumQueries(self.EXPECTED_QUERY_COUNT):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        planning_root = Path(__file__).resolve().parents[1]
        planning_sources = (
            planning_root / "views/planning.py",
            planning_root / "presenters/planning.py",
            planning_root / "templates/frontend/planning/workspace.html",
            planning_root / "templates/frontend/planning/_requirement_row.html",
            planning_root / "templates/frontend/planning/_assignment_row.html",
        )
        forbidden_calls = (
            "find_all_feasible_teams(",
            "solve_team_effort_allocation(",
            "select_recommended_teams(",
            "build_recommendation_explanations(",
            "calculate_daily_available_hours(",
            "gemini",
        )
        for source_path in planning_sources:
            source = source_path.read_text(encoding="utf-8").lower()
            with self.subTest(source=source_path.name):
                self.assertFalse(any(call in source for call in forbidden_calls))

        warmup = self.client.get(self.url)
        self.assertEqual(warmup.status_code, 200)
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
            "\nM5.2 project-planning readiness baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            "3 requirements, 2 assignments, 2 coverage links):\n"
            f"  queries={self.EXPECTED_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )
