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
    AssignmentSkill,
    Employee,
    EmployeeSkill,
    Leave,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from core.services.optimization import (
    build_optimization_context,
    get_fast_feasibility_issues,
    get_requirement_capacity_evidence,
    units_to_hours,
)
from frontend.presenters.planning import (
    build_project_planning_workspace,
    build_requirement_evidence_context,
)
from frontend.roles import VIEWER_GROUP, sync_role_permissions
from frontend.selectors.projects import get_project_profile


class ProjectPlanningRequirementEvidenceTests(TestCase):
    EXPECTED_PAGE_QUERY_COUNT = 21
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="requirement-evidence-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))

        cls.python = Skill.objects.create(
            name="Python",
            category="Engineering",
        )
        cls.design = Skill.objects.create(
            name="Service Design",
            category="Design",
        )
        cls.sql = Skill.objects.create(
            name="SQL",
            category="Data",
        )
        cls.project = Project.objects.create(
            name="Requirement evidence project",
            description="Review requirement evidence without solving a team.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            estimated_hours=Decimal("40.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        cls.python_requirement = cls._requirement(
            cls.python,
            level=3,
            quantity=2,
            effort="40.00",
            mandatory=True,
        )
        cls.design_requirement = cls._requirement(
            cls.design,
            level=2,
            quantity=2,
            effort=None,
            mandatory=False,
        )
        cls.sql_requirement = cls._requirement(
            cls.sql,
            level=2,
            quantity=1,
            effort="10.00",
            mandatory=False,
        )

        cls.alice = cls._employee("Alice", "Able", skills=((cls.python, 3),))
        cls.bob = cls._employee("Bob", "Busy", skills=((cls.python, 4),))
        cls.designer = cls._employee(
            "Devon",
            "Designer",
            skills=((cls.design, 2),),
        )
        cls.learner = cls._employee(
            "Lee",
            "Learner",
            skills=((cls.python, 2),),
        )

        competing_project = Project.objects.create(
            name="Competing delivery",
            description="Existing workload evidence.",
            start_date=cls.project.start_date,
            end_date=cls.project.end_date,
            estimated_hours=Decimal("40.00"),
            status=Project.Status.IN_PROGRESS,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )
        Assignment.objects.create(
            employee=cls.bob,
            project=competing_project,
            start_date=cls.project.start_date,
            end_date=cls.project.end_date,
            allocation_percentage=50,
            role_on_project="Existing delivery",
            status=Assignment.Status.ACTIVE,
        )
        Leave.objects.create(
            employee=cls.bob,
            start_date=date(2026, 9, 9),
            end_date=date(2026, 9, 9),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )

        cls._coverage(
            cls.alice,
            cls.python_requirement,
            status=Assignment.Status.ACTIVE,
            role="Python lead",
        )
        cls._coverage(
            cls.bob,
            cls.python_requirement,
            status=Assignment.Status.PLANNED,
            role="Python support",
        )
        cls._coverage(
            cls.designer,
            cls.design_requirement,
            status=Assignment.Status.ACTIVE,
            role="Service designer",
        )
        cls._coverage(
            cls.designer,
            cls.design_requirement,
            status=Assignment.Status.COMPLETED,
            role="Past discovery",
        )
        cls._coverage(
            cls.bob,
            cls.python_requirement,
            status=Assignment.Status.CANCELLED,
            role="Cancelled support",
        )

    @classmethod
    def _requirement(cls, skill, *, level, quantity, effort, mandatory):
        return ProjectSkillRequirement.objects.create(
            project=cls.project,
            skill=skill,
            required_level=level,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=mandatory,
            required_quantity=quantity,
            estimated_effort_hours=(
                Decimal(effort) if effort is not None else None
            ),
        )

    @classmethod
    def _employee(cls, first_name, last_name, *, skills):
        employee = Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Delivery",
            position="Specialist",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("5.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )
        for skill, level in skills:
            EmployeeSkill.objects.create(
                employee=employee,
                skill=skill,
                level=level,
                years_experience=Decimal("3.0"),
            )
        return employee

    @classmethod
    def _coverage(cls, employee, requirement, *, status, role):
        assignment = Assignment.objects.create(
            employee=employee,
            project=cls.project,
            start_date=cls.project.start_date,
            end_date=cls.project.end_date,
            allocation_percentage=25,
            role_on_project=role,
            status=status,
        )
        AssignmentSkill.objects.create(
            assignment=assignment,
            project_skill_requirement=requirement,
        )
        return assignment

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

    def test_every_requirement_has_stored_coverage_and_qualification_evidence(self):
        workspace = self._workspace()
        evidence = workspace["requirement_evidence"]
        rows = {
            row["requirement"].project_skill_requirement_id: row
            for row in evidence["rows"]
        }

        self.assertEqual(workspace["readiness"]["is_ready"], True)
        self.assertEqual(evidence["state"], "assessed")
        self.assertEqual(
            [row["requirement"] for row in evidence["rows"]],
            list(workspace["requirements"]),
        )

        python = rows[self.python_requirement.project_skill_requirement_id]
        self.assertEqual(python["covered_quantity"], 2)
        self.assertEqual(python["remaining_quantity"], 0)
        self.assertEqual(
            python["coverage_state"]["code"],
            "coverage_quantity_met",
        )
        self.assertEqual(
            [row["employee"] for row in python["qualified_rows"]],
            [self.alice, self.bob],
        )
        self.assertEqual(
            [row["level"] for row in python["qualified_rows"]],
            [3, 4],
        )
        self.assertEqual(
            [row["available_hours"] for row in python["qualified_rows"]],
            [Decimal("40.00"), Decimal("16.00")],
        )
        self.assertEqual(python["qualified_capacity"], Decimal("56.00"))
        self.assertEqual(
            python["qualification_state"]["code"],
            "qualified_headcount_available",
        )
        self.assertEqual(
            python["capacity_state"]["code"],
            "qualified_capacity_available",
        )

        design = rows[self.design_requirement.project_skill_requirement_id]
        self.assertEqual(design["covered_quantity"], 1)
        self.assertEqual(design["remaining_quantity"], 1)
        self.assertEqual(design["coverage_state"]["code"], "partial_coverage")
        self.assertEqual(design["qualified_count"], 1)
        self.assertEqual(
            design["qualification_state"]["code"],
            "insufficient_qualified_headcount",
        )
        self.assertEqual(design["capacity_state"]["code"], "missing_effort")

        sql = rows[self.sql_requirement.project_skill_requirement_id]
        self.assertEqual(sql["covered_quantity"], 0)
        self.assertEqual(sql["coverage_state"]["code"], "no_current_coverage")
        self.assertEqual(sql["qualified_rows"], ())
        self.assertEqual(
            sql["qualification_state"]["code"],
            "no_qualified_employees",
        )
        self.assertEqual(
            sql["capacity_state"]["code"],
            "insufficient_qualified_capacity",
        )

    def test_page_renders_accessible_requirement_evidence_without_feasibility_claim(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "frontend/planning/_requirement_evidence.html",
        )
        self.assertTemplateUsed(
            response,
            "frontend/planning/_qualified_employee_row.html",
        )
        self.assertTemplateUsed(
            response,
            "frontend/planning/_requirement_coverage_row.html",
        )
        self.assertContains(
            response,
            "Qualification, capacity, and current coverage",
        )
        self.assertContains(response, "Mandatory requirement")
        self.assertContains(response, "Optional requirement", count=2)
        self.assertContains(response, "Current coverage quantity met")
        self.assertContains(response, "Current coverage is partial")
        self.assertContains(response, "No current assignment coverage")
        self.assertContains(response, "No qualified active employees")
        self.assertContains(response, "Capacity comparison unavailable")
        self.assertContains(response, "Available project capacity")
        self.assertContains(response, "56.00 h")
        self.assertContains(
            response,
            "This evidence is not a feasible-team result.",
        )
        self.assertContains(
            response,
            "neither view allocates effort or proves that one team can satisfy "
            "the whole project.",
        )
        self.assertNotContains(response, "This team is feasible")
        self.assertContains(
            response,
            "Active employees meeting this requirement and their "
            "service-calculated project capacity",
            count=2,
        )
        self.assertContains(
            response,
            "Planned or active assignments currently linked to this requirement",
            count=2,
        )

    def test_capacity_gap_matches_existing_readiness_and_service_evidence(self):
        self.python_requirement.estimated_effort_hours = Decimal("60.00")
        self.python_requirement.save(update_fields=["estimated_effort_hours"])
        workspace = self._workspace()
        python = next(
            row
            for row in workspace["requirement_evidence"]["rows"]
            if row["requirement"].skill_id == self.python.skill_id
        )

        self.assertEqual(workspace["requirement_evidence"]["state"], "assessed")
        self.assertEqual(
            python["capacity_state"]["code"],
            "insufficient_qualified_capacity",
        )
        self.assertEqual(python["qualified_capacity"], Decimal("56.00"))
        self.assertIn(
            "insufficient_qualified_capacity",
            [blocker["code"] for blocker in workspace["readiness"]["blockers"]],
        )

        context = build_optimization_context(self.project)
        service_evidence = get_requirement_capacity_evidence(
            context["requirements"][0],
            context["employees"],
            context["available_hours"],
            eligible_ids=context["eligible_by_requirement"][
                self.python_requirement.project_skill_requirement_id
            ],
        )
        issues = get_fast_feasibility_issues(context["employees"], context)
        capacity_issue = next(
            issue
            for issue in issues
            if issue["code"] == "insufficient_qualified_capacity"
        )
        self.assertEqual(
            service_evidence["qualified_capacity_units"],
            capacity_issue["available_units"],
        )
        self.assertEqual(
            service_evidence["required_units"],
            capacity_issue["required_units"],
        )
        self.assertEqual(
            units_to_hours(service_evidence["qualified_capacity_units"]),
            python["qualified_capacity"],
        )

    def test_missing_effort_pauses_service_assessment_but_keeps_stored_coverage(self):
        self.python_requirement.estimated_effort_hours = None
        self.python_requirement.save(update_fields=["estimated_effort_hours"])
        with patch(
            "frontend.presenters.planning.build_optimization_context"
        ) as optimization:
            workspace = self._workspace()
        optimization.assert_not_called()

        python = next(
            row
            for row in workspace["requirement_evidence"]["rows"]
            if row["requirement"].skill_id == self.python.skill_id
        )
        self.assertEqual(workspace["requirement_evidence"]["state"], "paused")
        self.assertEqual(python["covered_quantity"], 2)
        self.assertEqual(python["qualified_rows"], ())
        self.assertEqual(
            python["qualification_state"]["code"],
            "assessment_paused",
        )
        self.assertEqual(python["capacity_state"]["code"], "missing_effort")

        response = self.client.get(self.url)
        self.assertContains(response, "Requirement evidence partly available")
        self.assertContains(response, "Not entered")
        self.assertContains(response, "Qualification evidence not assessed")
        self.assertContains(response, "Capacity comparison unavailable")

    def test_no_requirements_has_a_distinct_empty_state(self):
        empty_project = Project.objects.create(
            name="Empty requirement project",
            description="No stored demand.",
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            estimated_hours=Decimal("0.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.LOW,
            criticality=Project.Criticality.LOW,
        )
        workspace = self._workspace(empty_project)
        self.assertEqual(workspace["requirement_evidence"]["state"], "empty")
        self.assertEqual(workspace["requirement_evidence"]["rows"], ())

        response = self.client.get(
            reverse(
                "frontend:project_planning",
                args=[empty_project.project_id],
            )
        )
        self.assertContains(response, "No requirement evidence available")
        self.assertNotContains(response, "Qualified employee evidence")

    def test_permission_and_get_only_contract_remain_unchanged(self):
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
            username="requirements-without-employee-view"
        )
        restricted.user_permissions.add(*permissions)
        restricted_client = Client()
        restricted_client.force_login(restricted)
        self.assertEqual(restricted_client.get(self.url).status_code, 403)

        counts_before = (
            ProjectSkillRequirement.objects.count(),
            AssignmentSkill.objects.count(),
            EmployeeSkill.objects.count(),
        )
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.assertEqual(
            (
                ProjectSkillRequirement.objects.count(),
                AssignmentSkill.objects.count(),
                EmployeeSkill.objects.count(),
            ),
            counts_before,
        )

    def test_fixed_queries_ordering_timing_and_source_boundaries(self):
        first = self._workspace()["requirement_evidence"]
        second = self._workspace()["requirement_evidence"]
        self.assertEqual(
            [row["requirement"].pk for row in first["rows"]],
            [row["requirement"].pk for row in second["rows"]],
        )
        self.assertEqual(
            [row["employee"].pk for row in first["rows"][0]["qualified_rows"]],
            [row["employee"].pk for row in second["rows"][0]["qualified_rows"]],
        )

        with self.assertNumQueries(self.EXPECTED_PAGE_QUERY_COUNT):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        frontend_root = Path(__file__).resolve().parents[1]
        frontend_sources = (
            frontend_root / "presenters/planning.py",
            frontend_root / "views/planning.py",
            frontend_root / "templates/frontend/planning/workspace.html",
            frontend_root / "templates/frontend/planning/_requirement_evidence.html",
            frontend_root / "templates/frontend/planning/_qualified_employee_row.html",
            frontend_root / "templates/frontend/planning/_requirement_coverage_row.html",
        )
        combined_source = "\n".join(
            source.read_text(encoding="utf-8").lower()
            for source in frontend_sources
        )
        for forbidden_call in (
            "calculate_available_hours_for_project(",
            "solve_team_effort_allocation(",
            "find_all_feasible_teams(",
            "select_recommended_teams(",
            "build_recommendation_explanations(",
            "attendance.objects",
            "gemini",
        ):
            with self.subTest(forbidden_call=forbidden_call):
                self.assertNotIn(forbidden_call, combined_source)
        presenter_source = inspect.getsource(
            build_requirement_evidence_context
        ).lower()
        self.assertEqual(
            presenter_source.count("get_requirement_capacity_evidence("),
            1,
        )
        requirement_template_source = (
            frontend_root / "templates/frontend/planning/_requirement_evidence.html"
        ).read_text(encoding="utf-8").lower()
        self.assertNotIn("team is feasible", requirement_template_source)

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
            "\nM5.5 requirement-evidence baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            "3 requirements, 4 active employees, 5 stored coverage links):\n"
            f"  page_queries={self.EXPECTED_PAGE_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )
