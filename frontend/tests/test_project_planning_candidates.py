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
from django.urls import reverse

from core.models import (
    Assignment,
    Employee,
    EmployeeSkill,
    Leave,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from core.services.matching import (
    calculate_employee_project_match,
    rank_employees_for_project,
)
from frontend.presenters.planning import build_project_planning_workspace
from frontend.roles import VIEWER_GROUP, sync_role_permissions
from frontend.selectors.projects import get_project_profile


class ProjectPlanningCandidateTests(TestCase):
    EXPECTED_PAGE_QUERY_COUNT = 26
    EXPECTED_RANKING_QUERY_COUNT = 5
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="candidate-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.python = Skill.objects.create(
            name="Python",
            category="Engineering",
        )
        cls.project = Project.objects.create(
            name="Candidate project",
            description="Compare existing matching evidence.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            estimated_hours=Decimal("40.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        cls.requirement = ProjectSkillRequirement.objects.create(
            project=cls.project,
            skill=cls.python,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=Decimal("40.00"),
        )
        cls.casey = cls._employee(
            "Casey",
            "Clark",
            experience="10.0",
            level=5,
        )
        cls.alex = cls._employee(
            "Alex",
            "Archer",
            experience="7.0",
            level=3,
        )
        cls.blair = cls._employee(
            "Blair",
            "Baker",
            experience="7.0",
            level=3,
        )
        cls.inactive = cls._employee(
            "Inactive",
            "Candidate",
            experience="10.0",
            level=5,
            status=Employee.Status.INACTIVE,
        )
        cls.unqualified = cls._employee(
            "Unqualified",
            "Employee",
            experience="10.0",
            level=None,
        )

    @classmethod
    def _employee(
        cls,
        first_name,
        last_name,
        *,
        experience,
        level,
        status=Employee.Status.ACTIVE,
    ):
        employee = Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Engineering",
            position="Engineer",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal(experience),
            capacity_hours_week=Decimal("40.00"),
            status=status,
        )
        if level is not None:
            EmployeeSkill.objects.create(
                employee=employee,
                skill=cls.python,
                level=level,
                years_experience=Decimal("5.0"),
            )
        return employee

    def setUp(self):
        self.client.force_login(self.viewer)
        self.url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )

    def _workspace(self, project=None):
        project = project or self.project
        return build_project_planning_workspace(
            get_project_profile(project.project_id)
        )

    def test_candidate_rows_have_exact_service_order_values_and_links(self):
        expected = rank_employees_for_project(self.project)
        workspace = self._workspace()
        candidates = workspace["candidates"]

        self.assertEqual(candidates["state"], "ranked")
        self.assertEqual(candidates["service_results"], tuple(expected))
        self.assertEqual(
            [row["employee"] for row in candidates["rows"]],
            [result["employee"] for result in expected],
        )
        for position, (row, result) in enumerate(
            zip(candidates["rows"], expected, strict=True),
            start=1,
        ):
            self.assertEqual(row["rank"], position)
            for component in (
                "skill_score",
                "workload_score",
                "leave_score",
                "experience_score",
                "final_score",
            ):
                self.assertEqual(row[component], result[component])
            self.assertEqual(
                row["profile_url"],
                reverse(
                    "frontend:employee_detail",
                    args=[row["employee"].employee_id],
                )
                + "?start_date=2026-09-07&end_date=2026-09-11",
            )
            self.assertEqual(
                row["requirements_url"],
                "#planning-requirements-title",
            )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "frontend/planning/_candidate_row.html",
        )
        self.assertContains(response, "Eligible candidates")
        self.assertContains(response, "Skill match")
        self.assertContains(response, "Workload")
        self.assertContains(response, "Leave")
        self.assertContains(response, "Experience")
        self.assertContains(response, "Project fit")
        self.assertContains(response, "Score out of 100")
        self.assertContains(response, "Sep 7, 2026 through Sep 11, 2026")
        self.assertContains(response, "This ranking does not select or recommend a team.")
        self.assertContains(response, "attendance is not a score component")
        self.assertContains(response, 'href="#planning-requirements-title"')
        self.assertContains(response, "How to read the candidate scores")
        self.assertContains(
            response,
            "Each heading matches a column in the candidate table above.",
        )
        self.assertContains(
            response,
            'class="candidate-score-guide__card',
            count=5,
        )
        self.assertContains(
            response,
            "candidate-score-guide__card--overall",
            count=1,
        )
        self.assertNotContains(response, "Why excluded")

        profile_response = self.client.get(candidates["rows"][0]["profile_url"])
        self.assertEqual(profile_response.status_code, 200)

    def test_ties_keep_the_service_deterministic_order_without_rescoring(self):
        service_results = rank_employees_for_project(self.project)
        tied = [
            result
            for result in service_results
            if result["employee"] in (self.alex, self.blair)
        ]
        self.assertEqual(
            [result["employee"] for result in tied],
            [self.alex, self.blair],
        )
        self.assertEqual(tied[0]["final_score"], tied[1]["final_score"])

        repeated = rank_employees_for_project(self.project)
        self.assertEqual(
            [result["employee"] for result in repeated],
            [result["employee"] for result in service_results],
        )

        with patch(
            "frontend.presenters.planning.rank_employees_for_project",
            return_value=[tied[1], tied[0]],
        ):
            candidates = self._workspace()["candidates"]
        self.assertEqual(
            [row["employee"] for row in candidates["rows"]],
            [self.blair, self.alex],
        )
        self.assertEqual([row["rank"] for row in candidates["rows"]], [1, 2])

    def test_inactive_and_unqualified_employees_remain_absent(self):
        candidates = self._workspace()["candidates"]
        employees = [row["employee"] for row in candidates["rows"]]
        self.assertNotIn(self.inactive, employees)
        self.assertNotIn(self.unqualified, employees)
        self.assertEqual(
            employees,
            [result["employee"] for result in rank_employees_for_project(self.project)],
        )

    def test_workload_and_leave_boundaries_match_scalar_service_results(self):
        competing_project = Project.objects.create(
            name="Competing delivery",
            description="Existing scheduled work.",
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            estimated_hours=Decimal("40.00"),
            status=Project.Status.IN_PROGRESS,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )
        Assignment.objects.create(
            employee=self.alex,
            project=competing_project,
            start_date=self.project.start_date,
            end_date=self.project.start_date,
            allocation_percentage=100,
            role_on_project="Support",
            status=Assignment.Status.ACTIVE,
        )
        Leave.objects.create(
            employee=self.blair,
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )

        alex_scalar = calculate_employee_project_match(self.alex, self.project)
        blair_scalar = calculate_employee_project_match(self.blair, self.project)
        ranked = rank_employees_for_project(self.project)
        by_employee = {result["employee"]: result for result in ranked}

        self.assertEqual(alex_scalar["workload_score"], 0)
        self.assertEqual(blair_scalar["leave_score"], 0.0)
        self.assertEqual(by_employee[self.alex], alex_scalar)
        self.assertEqual(by_employee[self.blair], blair_scalar)

    def test_blocked_and_empty_states_do_not_render_missing_scores_as_zero(self):
        self.requirement.estimated_effort_hours = None
        self.requirement.save(update_fields=["estimated_effort_hours"])
        with patch(
            "frontend.presenters.planning.rank_employees_for_project"
        ) as ranking_service:
            blocked = self.client.get(self.url)
        ranking_service.assert_not_called()
        self.assertContains(blocked, "Candidate assessment paused")
        self.assertNotContains(blocked, "0.00 / 100")

        self.requirement.estimated_effort_hours = Decimal("40.00")
        self.requirement.save(update_fields=["estimated_effort_hours"])
        with patch(
            "frontend.presenters.planning.rank_employees_for_project",
            return_value=[],
        ) as ranking_service:
            empty = self.client.get(self.url)
        ranking_service.assert_called_once()
        self.assertContains(empty, "No eligible candidates returned")
        self.assertNotContains(empty, "0.00 / 100")
        self.assertNotContains(
            empty,
            "Eligible employees in current matching rank order",
        )

    def test_permission_boundary_and_get_only_contract_remain_unchanged(self):
        permissions = Permission.objects.filter(
            content_type__app_label="core",
            codename__in=(
                "view_project",
                "view_projectskillrequirement",
                "view_assignment",
                "view_assignmentskill",
                "view_skill",
            ),
        )
        restricted = get_user_model().objects.create_user(
            username="candidate-without-employee-view"
        )
        restricted.user_permissions.add(*permissions)
        restricted_client = Client()
        restricted_client.force_login(restricted)
        self.assertEqual(restricted_client.get(self.url).status_code, 403)

        counts_before = (
            Employee.objects.count(),
            EmployeeSkill.objects.count(),
            Project.objects.count(),
            ProjectSkillRequirement.objects.count(),
        )
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.assertEqual(
            (
                Employee.objects.count(),
                EmployeeSkill.objects.count(),
                Project.objects.count(),
                ProjectSkillRequirement.objects.count(),
            ),
            counts_before,
        )

    def test_fixed_query_service_and_page_baselines_and_source_boundary(self):
        with self.assertNumQueries(self.EXPECTED_RANKING_QUERY_COUNT):
            ranked = rank_employees_for_project(self.project)
            self.assertEqual(len(ranked), 3)

        with self.assertNumQueries(self.EXPECTED_PAGE_QUERY_COUNT):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        planning_root = Path(__file__).resolve().parents[1]
        sources = (
            planning_root / "presenters/planning.py",
            planning_root / "views/planning.py",
            planning_root / "templates/frontend/planning/workspace.html",
            planning_root / "templates/frontend/planning/_candidate_row.html",
        )
        forbidden_calls = (
            "calculate_employee_project_match(",
            "calculate_skill_score(",
            "calculate_min_available_capacity(",
            "calculate_leave_availability_rate(",
            "find_all_feasible_teams(",
            "solve_team_effort_allocation(",
            "select_recommended_teams(",
            "build_recommendation_explanations(",
            "attendance.objects",
            "gemini",
        )
        combined_source = "\n".join(
            source.read_text(encoding="utf-8").lower() for source in sources
        )
        for forbidden_call in forbidden_calls:
            with self.subTest(forbidden_call=forbidden_call):
                self.assertNotIn(forbidden_call, combined_source)
        self.assertEqual(combined_source.count("rank_employees_for_project("), 1)

        theme_source = (
            planning_root / "static/frontend/css/theme.css"
        ).read_text(encoding="utf-8")
        self.assertIn(".candidate-score-guide__grid", theme_source)
        self.assertIn(
            "grid-template-columns: repeat(2, minmax(0, 1fr));",
            theme_source,
        )
        self.assertIn(".candidate-score-guide__card--overall", theme_source)
        self.assertIn("grid-column: 1 / -1;", theme_source)

        warmup = self.client.get(self.url)
        self.assertEqual(warmup.status_code, 200)
        durations_ms = []
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as captured_queries:
                started_at = time.perf_counter()
                response = self.client.get(self.url)
                durations_ms.append((time.perf_counter() - started_at) * 1000)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                len(captured_queries),
                self.EXPECTED_PAGE_QUERY_COUNT,
            )

        p95_ms = statistics.quantiles(
            durations_ms,
            n=20,
            method="inclusive",
        )[18]
        print(
            "\nM5.3 ranked-candidate baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            "3 eligible, 1 inactive, 1 unqualified employee):\n"
            f"  service_queries={self.EXPECTED_RANKING_QUERY_COUNT}, "
            f"page_queries={self.EXPECTED_PAGE_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )
