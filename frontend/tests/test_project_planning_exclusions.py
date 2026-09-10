import inspect
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
from frontend.presenters.planning import (
    build_candidate_exclusion_context,
    build_project_planning_workspace,
)
from frontend.roles import VIEWER_GROUP, sync_role_permissions
from frontend.selectors.planning import get_candidate_exclusion_workforce
from frontend.selectors.projects import get_project_profile


class ProjectPlanningExclusionTests(TestCase):
    EXPECTED_PAGE_QUERY_COUNT = 26
    EXPECTED_WORKFORCE_QUERY_COUNT = 2
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="exclusion-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.python = Skill.objects.create(name="Python", category="Engineering")
        cls.project = Project.objects.create(
            name="Exclusion project",
            description="Explain the exact candidate boundary.",
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
        cls.eligible = cls._employee("Avery", "Able", level=3)
        cls.fully_scheduled = cls._employee("Bailey", "Busy", level=4)
        cls.on_approved_leave = cls._employee("Cameron", "Away", level=3)
        cls.inactive = cls._employee(
            "Dana",
            "Inactive",
            level=5,
            status=Employee.Status.INACTIVE,
        )
        cls.on_leave_status = cls._employee(
            "Emery",
            "Status",
            level=5,
            status=Employee.Status.ON_LEAVE,
        )
        cls.unqualified = cls._employee("Finley", "Learner", level=2)
        cls.inactive_unqualified = cls._employee(
            "Gray",
            "Multiple",
            level=None,
            status=Employee.Status.INACTIVE,
        )

        competing_project = Project.objects.create(
            name="Competing project",
            description="Existing scheduled work.",
            start_date=cls.project.start_date,
            end_date=cls.project.end_date,
            estimated_hours=Decimal("40.00"),
            status=Project.Status.IN_PROGRESS,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )
        Assignment.objects.create(
            employee=cls.fully_scheduled,
            project=competing_project,
            start_date=cls.project.start_date,
            end_date=cls.project.end_date,
            allocation_percentage=100,
            role_on_project="Delivery",
            status=Assignment.Status.ACTIVE,
        )
        Leave.objects.create(
            employee=cls.on_approved_leave,
            start_date=cls.project.start_date,
            end_date=cls.project.end_date,
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )

    @classmethod
    def _employee(
        cls,
        first_name,
        last_name,
        *,
        level,
        status=Employee.Status.ACTIVE,
    ):
        employee = Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Engineering",
            position="Engineer",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("5.0"),
            capacity_hours_week=Decimal("40.00"),
            status=status,
        )
        if level is not None:
            EmployeeSkill.objects.create(
                employee=employee,
                skill=cls.python,
                level=level,
                years_experience=Decimal("3.0"),
            )
        return employee

    def setUp(self):
        self.client.force_login(self.viewer)
        self.url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )

    def _context(self):
        project = get_project_profile(self.project.project_id)
        workspace = build_project_planning_workspace(project)
        workforce = get_candidate_exclusion_workforce()
        return build_candidate_exclusion_context(
            project,
            workspace["readiness"],
            workspace["candidates"],
            workforce,
        ), workspace

    def test_exclusions_are_the_exact_workforce_minus_service_candidates(self):
        exclusions, workspace = self._context()
        candidate_ids = {
            result["employee"].employee_id
            for result in workspace["candidates"]["service_results"]
        }
        workforce_ids = set(
            Employee.objects.values_list("employee_id", flat=True)
        )
        excluded_ids = {row["employee"].employee_id for row in exclusions["rows"]}

        self.assertEqual(exclusions["state"], "explained")
        self.assertEqual(excluded_ids, workforce_ids - candidate_ids)
        self.assertNotIn(self.fully_scheduled.employee_id, excluded_ids)
        self.assertNotIn(self.on_approved_leave.employee_id, excluded_ids)

        service_by_id = {
            result["employee"].employee_id: result
            for result in workspace["candidates"]["service_results"]
        }
        self.assertEqual(
            service_by_id[self.fully_scheduled.employee_id]["workload_score"],
            0,
        )
        self.assertEqual(
            service_by_id[self.on_approved_leave.employee_id]["leave_score"],
            0.0,
        )

    def test_supported_reasons_are_deterministic_and_status_runs_first(self):
        exclusions, _workspace = self._context()
        rows = {row["employee"].employee_id: row for row in exclusions["rows"]}

        self.assertEqual(
            rows[self.inactive.employee_id]["reason_code"],
            "inactive_status",
        )
        self.assertEqual(
            rows[self.on_leave_status.employee_id]["reason_code"],
            "inactive_status",
        )
        self.assertEqual(
            rows[self.unqualified.employee_id]["reason_code"],
            "no_qualifying_requirement",
        )
        self.assertEqual(
            rows[self.inactive_unqualified.employee_id]["reason_code"],
            "inactive_status",
        )
        self.assertIn(
            "Current employee status is Inactive",
            rows[self.inactive.employee_id]["reason_message"],
        )
        self.assertIn(
            "Current employee status is On leave",
            rows[self.on_leave_status.employee_id]["reason_message"],
        )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "frontend/planning/_candidate_exclusion_row.html",
        )
        self.assertContains(response, "Why employees are not ranked")
        self.assertContains(response, "Not active for matching", count=3)
        self.assertContains(response, "No qualifying requirement", count=1)
        self.assertContains(
            response,
            'data-exclusion-reason="inactive_status"',
            count=3,
        )
        self.assertContains(
            response,
            "An employee shown here does not by itself make the project infeasible.",
        )
        self.assertContains(
            response,
            "Workload and approved dated leave shape candidate scores",
        )
        self.assertContains(response, "Review employee profile")
        self.assertContains(response, "Review project requirements")

    def test_incomplete_input_stops_ranking_workforce_and_exclusion_assessment(self):
        self.requirement.estimated_effort_hours = None
        self.requirement.save(update_fields=["estimated_effort_hours"])

        with (
            patch(
                "frontend.presenters.planning.rank_employees_for_project"
            ) as ranking,
            patch(
                "frontend.views.planning.get_candidate_exclusion_workforce"
            ) as workforce,
        ):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        ranking.assert_not_called()
        workforce.assert_not_called()
        self.assertContains(response, "Exclusion assessment paused")
        self.assertNotContains(
            response,
            "Current employees absent from the matching service candidate result",
        )

    def test_unexplained_service_absence_and_stale_candidate_data_are_not_guessed(self):
        project = get_project_profile(self.project.project_id)
        workspace = build_project_planning_workspace(project)
        workforce = tuple(get_candidate_exclusion_workforce())
        without_eligible = {
            **workspace["candidates"],
            "service_results": tuple(
                result
                for result in workspace["candidates"]["service_results"]
                if result["employee"].employee_id != self.eligible.employee_id
            ),
        }
        context = build_candidate_exclusion_context(
            project,
            workspace["readiness"],
            without_eligible,
            workforce,
        )
        row = next(
            row
            for row in context["rows"]
            if row["employee"].employee_id == self.eligible.employee_id
        )
        self.assertEqual(row["reason_code"], "eligibility_explanation_unavailable")
        self.assertIn("do not explain", row["reason_message"])

        stale = self._employee("Removed", "Record", level=4)
        stale_result = {"employee": stale}
        Employee.objects.filter(employee_id=stale.employee_id).delete()
        current_workforce = tuple(get_candidate_exclusion_workforce())
        stale_candidates = {
            **workspace["candidates"],
            "service_results": (
                workspace["candidates"]["service_results"] + (stale_result,)
            ),
        }
        stale_context = build_candidate_exclusion_context(
            project,
            workspace["readiness"],
            stale_candidates,
            current_workforce,
        )
        self.assertEqual(stale_context["state"], "unavailable")
        self.assertEqual(stale_context["rows"], ())
        self.assertIn(
            "no longer matches the current workforce",
            stale_context["message"],
        )
        self.assertNotIn(
            stale.employee_id,
            {employee.employee_id for employee in current_workforce},
        )

    def test_permission_and_get_only_boundaries_remain_unchanged(self):
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
            username="exclusion-without-employee-view"
        )
        restricted.user_permissions.add(*permissions)
        restricted_client = Client()
        restricted_client.force_login(restricted)
        with patch(
            "frontend.views.planning.get_candidate_exclusion_workforce"
        ) as workforce:
            self.assertEqual(restricted_client.get(self.url).status_code, 403)
        workforce.assert_not_called()

        counts_before = (
            Employee.objects.count(),
            EmployeeSkill.objects.count(),
            Project.objects.count(),
        )
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.assertEqual(
            (
                Employee.objects.count(),
                EmployeeSkill.objects.count(),
                Project.objects.count(),
            ),
            counts_before,
        )

    def test_fixed_queries_accessible_text_and_service_boundaries(self):
        with self.assertNumQueries(self.EXPECTED_WORKFORCE_QUERY_COUNT):
            workforce = tuple(get_candidate_exclusion_workforce())
            self.assertEqual(len(workforce), 7)
            self.assertEqual(
                sum(len(employee.planning_skills) for employee in workforce),
                6,
            )

        with self.assertNumQueries(self.EXPECTED_PAGE_QUERY_COUNT):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        planning_root = Path(__file__).resolve().parents[1]
        exclusion_sources = (
            planning_root / "selectors/planning.py",
            planning_root / "views/planning.py",
            planning_root / "templates/frontend/planning/_candidate_exclusion_row.html",
        )
        combined_source = "\n".join(
            source.read_text(encoding="utf-8").lower()
            for source in exclusion_sources
        )
        presenter_source = inspect.getsource(
            build_candidate_exclusion_context
        ).lower()
        for forbidden_call in (
            "calculate_employee_project_match(",
            "calculate_skill_score(",
            "calculate_min_available_capacity(",
            "calculate_leave_availability_rate(",
            "find_all_feasible_teams(",
            "solve_team_effort_allocation(",
            "select_recommended_teams(",
            "build_recommendation_explanations(",
            "attendance",
            "gemini",
        ):
            with self.subTest(forbidden_call=forbidden_call):
                self.assertNotIn(forbidden_call, combined_source + presenter_source)
        self.assertEqual(
            presenter_source.count("employee_can_cover_requirement("),
            1,
        )
        self.assertNotIn("weight", presenter_source)
        self.assertContains(response, "Current employee status is Inactive")
        self.assertContains(response, "Current employee status is On leave")

        warmup = self.client.get(self.url)
        self.assertEqual(warmup.status_code, 200)
        durations_ms = []
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as captured_queries:
                started_at = time.perf_counter()
                response = self.client.get(self.url)
                durations_ms.append((time.perf_counter() - started_at) * 1000)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(captured_queries), self.EXPECTED_PAGE_QUERY_COUNT)

        p95_ms = statistics.quantiles(durations_ms, n=20, method="inclusive")[18]
        print(
            "\nM5.4 candidate-exclusion baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            "3 eligible and 4 excluded employees):\n"
            f"  workforce_queries={self.EXPECTED_WORKFORCE_QUERY_COUNT}, "
            f"page_queries={self.EXPECTED_PAGE_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )
