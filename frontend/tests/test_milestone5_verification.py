import inspect
import statistics
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.template import engines
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from core.models import (
    Assignment,
    AssignmentSkill,
    Attendance,
    Employee,
    EmployeeSkill,
    Leave,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from core.services.matching import rank_employees_for_project
from core.services.optimization import (
    build_optimization_context,
    get_requirement_capacity_evidence,
    units_to_hours,
)
from core.services.recommendation_preflight import get_recommendation_preflight
from frontend.presenters.planning import (
    build_candidate_exclusion_context,
    build_project_planning_workspace,
    build_requirement_evidence_context,
)
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)
from frontend.selectors.planning import get_candidate_exclusion_workforce
from frontend.selectors.projects import get_project_profile


class Milestone5VerificationTests(TestCase):
    EXPECTED_SERVICE_QUERY_COUNT = 17
    EXPECTED_PAGE_QUERY_COUNT = 21
    AUTHENTICATED_SHELL_QUERY_COUNT = 4
    TIMING_SAMPLE_COUNT = 7
    REQUIRED_VIEW_CODENAMES = (
        "view_project",
        "view_projectskillrequirement",
        "view_assignment",
        "view_assignmentskill",
        "view_employee",
        "view_skill",
    )
    PLANNING_TEMPLATES = (
        "frontend/planning/workspace.html",
        "frontend/planning/_assignment_row.html",
        "frontend/planning/_candidate_exclusion_row.html",
        "frontend/planning/_candidate_row.html",
        "frontend/planning/_qualified_employee_row.html",
        "frontend/planning/_requirement_coverage_row.html",
        "frontend/planning/_requirement_evidence.html",
        "frontend/planning/_requirement_row.html",
    )

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = cls._role_user("m5-final-viewer", VIEWER_GROUP)
        cls.manager = cls._role_user(
            "m5-final-manager",
            MANAGER_PLANNER_GROUP,
        )
        cls.hr_user = cls._role_user("m5-final-hr", HR_ADMINISTRATOR_GROUP)
        cls.unassigned = get_user_model().objects.create_user(
            username="m5-final-unassigned"
        )

        cls.python = Skill.objects.create(name="Python", category="Engineering")
        cls.design = Skill.objects.create(
            name="Service design",
            category="Design",
        )
        cls.sql = Skill.objects.create(name="SQL", category="Data")
        cls.rust = Skill.objects.create(name="Rust", category="Engineering")

        cls.project = cls._project(
            "Milestone 5 acceptance project",
            estimated_hours="40.00",
        )
        cls.python_requirement = cls._requirement(
            cls.project,
            cls.python,
            quantity=2,
            effort="32.00",
        )
        cls.design_requirement = cls._requirement(
            cls.project,
            cls.design,
            quantity=1,
            effort="8.00",
            mandatory=False,
        )

        cls.alex = cls._employee("Alex", "Able")
        cls.blair = cls._employee("Blair", "Baker")
        cls.casey = cls._employee("Casey", "Clark")
        cls.inactive = cls._employee(
            "Inactive",
            "Dover",
            status=Employee.Status.INACTIVE,
        )
        cls.unqualified = cls._employee("Unqualified", "Evans")
        for employee, skill, level in (
            (cls.alex, cls.python, 4),
            (cls.blair, cls.python, 3),
            (cls.casey, cls.design, 3),
            (cls.inactive, cls.python, 5),
        ):
            EmployeeSkill.objects.create(
                employee=employee,
                skill=skill,
                level=level,
                years_experience=Decimal("4.0"),
            )

        cls.current_assignment = Assignment.objects.create(
            employee=cls.alex,
            project=cls.project,
            start_date=cls.project.start_date,
            end_date=cls.project.end_date,
            allocation_percentage=25,
            role_on_project="Python lead",
            status=Assignment.Status.ACTIVE,
        )
        cls.current_coverage = AssignmentSkill.objects.create(
            assignment=cls.current_assignment,
            project_skill_requirement=cls.python_requirement,
        )

        cls.competing_project = cls._project("Competing delivery")
        cls.competing_assignment = Assignment.objects.create(
            employee=cls.blair,
            project=cls.competing_project,
            start_date=cls.project.start_date,
            end_date=cls.project.end_date,
            allocation_percentage=50,
            role_on_project="Existing delivery",
            status=Assignment.Status.ACTIVE,
        )
        cls.approved_leave = Leave.objects.create(
            employee=cls.blair,
            start_date=date(2026, 9, 9),
            end_date=date(2026, 9, 9),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )

        cls.incomplete_project = cls._project("Incomplete acceptance project")
        cls.incomplete_requirement = cls._requirement(
            cls.incomplete_project,
            cls.sql,
            quantity=1,
            effort=None,
        )
        cls.no_eligible_project = cls._project("No eligible acceptance project")
        cls.no_eligible_requirement = cls._requirement(
            cls.no_eligible_project,
            cls.rust,
            quantity=1,
            effort="8.00",
        )
        cls.capacity_project = cls._project("Capacity acceptance project")
        cls.capacity_requirement = cls._requirement(
            cls.capacity_project,
            cls.python,
            quantity=2,
            effort="80.00",
        )
        cls.empty_project = cls._project("Empty acceptance project")

    @staticmethod
    def _role_user(username, role):
        user = get_user_model().objects.create_user(username=username)
        user.groups.add(Group.objects.get(name=role))
        return user

    @staticmethod
    def _project(name, *, estimated_hours="8.00"):
        return Project.objects.create(
            name=name,
            description="Milestone 5 final verification context.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            estimated_hours=Decimal(estimated_hours),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )

    @staticmethod
    def _requirement(
        project,
        skill,
        *,
        quantity,
        effort,
        mandatory=True,
    ):
        return ProjectSkillRequirement.objects.create(
            project=project,
            skill=skill,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=mandatory,
            required_quantity=quantity,
            estimated_effort_hours=Decimal(effort) if effort is not None else None,
        )

    @staticmethod
    def _employee(first_name, last_name, *, status=Employee.Status.ACTIVE):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Engineering",
            position="Planning specialist",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("6.0"),
            capacity_hours_week=Decimal("40.00"),
            status=status,
        )

    def setUp(self):
        self.client.force_login(self.viewer)
        self.url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )

    def _service_workspace(self, project=None):
        project = project or self.project
        selected = get_project_profile(project.project_id)
        workspace = build_project_planning_workspace(selected)
        workforce = ()
        if workspace["readiness"]["candidate_assessment_allowed"]:
            workforce = get_candidate_exclusion_workforce()
        workspace["candidate_exclusions"] = build_candidate_exclusion_context(
            selected,
            workspace["readiness"],
            workspace["candidates"],
            workforce,
        )
        return workspace

    @staticmethod
    def _planning_snapshot(workspace):
        return (
            workspace["readiness"]["is_ready"],
            tuple(
                (blocker["code"], getattr(blocker.get("requirement"), "pk", 0))
                for blocker in workspace["readiness"]["blockers"]
            ),
            tuple(
                (
                    row["employee"].pk,
                    row["skill_score"],
                    row["workload_score"],
                    row["leave_score"],
                    row["experience_score"],
                    row["final_score"],
                )
                for row in workspace["candidates"]["rows"]
            ),
            tuple(
                (
                    row["requirement"].pk,
                    row["qualified_count"],
                    row["qualified_capacity"],
                    row["covered_quantity"],
                    row["remaining_quantity"],
                    row["qualification_state"]["code"],
                    row["capacity_state"]["code"],
                    row["coverage_state"]["code"],
                )
                for row in workspace["requirement_evidence"]["rows"]
            ),
        )

    def test_route_templates_navigation_permissions_and_read_only_contract(self):
        self.assertEqual(
            self.url,
            f"/projects/{self.project.project_id}/planning/",
        )
        match = resolve(self.url)
        self.assertEqual(match.view_name, "frontend:project_planning")
        self.assertEqual(match.kwargs["project_id"], self.project.project_id)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for template_name in self.PLANNING_TEMPLATES:
            engines["django"].get_template(template_name)
            self.assertTemplateUsed(response, template_name)
        self.assertRegex(
            response.content.decode("utf-8"),
            r'href="/projects/"\s+aria-current="page"',
        )

        anonymous = Client().get(self.url)
        self.assertRedirects(
            anonymous,
            f"{reverse('frontend:login')}?next={self.url}",
            fetch_redirect_response=False,
        )
        unassigned_client = Client()
        unassigned_client.force_login(self.unassigned)
        self.assertEqual(unassigned_client.get(self.url).status_code, 403)
        for user in (self.viewer, self.manager, self.hr_user):
            role_client = Client()
            role_client.force_login(user)
            with self.subTest(role=user.username):
                self.assertEqual(role_client.get(self.url).status_code, 200)

        permissions = {
            permission.codename: permission
            for permission in Permission.objects.filter(
                content_type__app_label="core",
                codename__in=self.REQUIRED_VIEW_CODENAMES,
            )
        }
        self.assertEqual(set(permissions), set(self.REQUIRED_VIEW_CODENAMES))
        for omitted_codename in self.REQUIRED_VIEW_CODENAMES:
            restricted = get_user_model().objects.create_user(
                username=f"m5-final-without-{omitted_codename}"
            )
            restricted.user_permissions.add(
                *(
                    permission
                    for codename, permission in permissions.items()
                    if codename != omitted_codename
                )
            )
            restricted_client = Client()
            restricted_client.force_login(restricted)
            with self.subTest(missing=omitted_codename):
                self.assertEqual(restricted_client.get(self.url).status_code, 403)

        counts_before = (
            Project.objects.count(),
            ProjectSkillRequirement.objects.count(),
            Assignment.objects.count(),
            AssignmentSkill.objects.count(),
            EmployeeSkill.objects.count(),
            Leave.objects.count(),
        )
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.assertEqual(self.client.put(self.url).status_code, 405)
        self.assertEqual(
            counts_before,
            (
                Project.objects.count(),
                ProjectSkillRequirement.objects.count(),
                Assignment.objects.count(),
                AssignmentSkill.objects.count(),
                EmployeeSkill.objects.count(),
                Leave.objects.count(),
            ),
        )

    def test_workspace_values_reconcile_with_models_selectors_and_core_services(self):
        workspace = self._service_workspace()
        self.assertTrue(workspace["readiness"]["is_ready"])
        self.assertEqual(get_recommendation_preflight(self.project)["blockers"], [])
        self.assertEqual(workspace["project"], self.project)
        self.assertEqual(workspace["mandatory_effort_hours"], Decimal("32.00"))
        self.assertEqual(workspace["project"].estimated_hours, Decimal("40.00"))
        self.assertEqual(workspace["requirement_count"], 2)
        self.assertEqual(workspace["assignment_count"], 1)
        self.assertEqual(workspace["coverage_count"], 1)
        self.assertEqual(
            [requirement.pk for requirement in workspace["requirements"]],
            [self.python_requirement.pk, self.design_requirement.pk],
        )
        self.assertEqual(
            [assignment.pk for assignment in workspace["assignments"]],
            [self.current_assignment.pk],
        )
        self.assertNotIn(self.competing_assignment, workspace["assignments"])

        expected_candidates = rank_employees_for_project(self.project)
        self.assertEqual(
            workspace["candidates"]["service_results"],
            tuple(expected_candidates),
        )
        self.assertEqual(
            [row["employee"].pk for row in workspace["candidates"]["rows"]],
            [result["employee"].pk for result in expected_candidates],
        )

        optimization_context = build_optimization_context(self.project)
        evidence_by_requirement = {
            row["requirement"].pk: row
            for row in workspace["requirement_evidence"]["rows"]
        }
        for requirement in (self.python_requirement, self.design_requirement):
            core_evidence = get_requirement_capacity_evidence(
                requirement,
                optimization_context["employees"],
                optimization_context["available_hours"],
            )
            presented = evidence_by_requirement[requirement.pk]
            self.assertEqual(
                [row["employee"].pk for row in presented["qualified_rows"]],
                [employee.pk for employee in core_evidence["qualified_employees"]],
            )
            self.assertEqual(
                presented["qualified_capacity"],
                units_to_hours(core_evidence["qualified_capacity_units"]),
            )
        self.assertEqual(
            evidence_by_requirement[self.python_requirement.pk]["covered_quantity"],
            1,
        )
        self.assertEqual(
            evidence_by_requirement[self.python_requirement.pk]["remaining_quantity"],
            1,
        )
        self.assertEqual(
            evidence_by_requirement[self.design_requirement.pk]["covered_quantity"],
            0,
        )

        exclusion_by_employee = {
            row["employee"].pk: row["reason_code"]
            for row in workspace["candidate_exclusions"]["rows"]
        }
        self.assertEqual(
            exclusion_by_employee,
            {
                self.inactive.pk: "inactive_status",
                self.unqualified.pk: "no_qualifying_requirement",
            },
        )

    def test_incomplete_infeasible_stale_and_empty_states_are_truthful(self):
        incomplete = self._service_workspace(self.incomplete_project)
        self.assertEqual(
            [blocker["code"] for blocker in incomplete["readiness"]["blockers"]],
            ["mandatory_effort_must_be_positive"],
        )
        self.assertEqual(incomplete["candidates"]["state"], "blocked")
        self.assertEqual(incomplete["candidate_exclusions"]["state"], "blocked")
        self.assertEqual(incomplete["requirement_evidence"]["state"], "paused")

        no_eligible = self._service_workspace(self.no_eligible_project)
        self.assertEqual(
            [blocker["code"] for blocker in no_eligible["readiness"]["blockers"]],
            ["insufficient_eligible_headcount"],
        )
        self.assertFalse(no_eligible["readiness"]["is_ready"])

        capacity = self._service_workspace(self.capacity_project)
        self.assertEqual(
            [blocker["code"] for blocker in capacity["readiness"]["blockers"]],
            ["insufficient_qualified_capacity"],
        )
        self.assertFalse(capacity["readiness"]["is_ready"])

        empty = self._service_workspace(self.empty_project)
        self.assertEqual(empty["requirement_count"], 0)
        self.assertEqual(empty["assignment_count"], 0)
        self.assertEqual(
            [blocker["code"] for blocker in empty["readiness"]["blockers"]],
            ["no_mandatory_requirements"],
        )
        self.assertEqual(empty["requirement_evidence"]["state"], "empty")

        selected = get_project_profile(self.project.pk)
        self.python_requirement.required_quantity = 1
        self.python_requirement.save(update_fields=["required_quantity"])
        stale = build_project_planning_workspace(selected)
        self.assertEqual(
            [blocker["code"] for blocker in stale["readiness"]["blockers"]],
            ["stale_planning_inputs"],
        )
        self.assertEqual(stale["readiness"]["label"], "Refresh planning inputs")

        for project in (
            self.no_eligible_project,
            self.capacity_project,
            self.empty_project,
        ):
            response = self.client.get(
                reverse("frontend:project_planning", args=[project.pk])
            )
            self.assertContains(
                response,
                "This is a readiness check, not a feasibility result.",
            )
            self.assertNotContains(response, "No feasible team exists")

    def test_candidate_exclusion_evidence_and_repair_links_preserve_context(self):
        self.client.force_login(self.hr_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        workspace = response.context["workspace"]
        planning_path = self.url

        for repair_url, expected_path in (
            (
                workspace["repair"]["project_edit_url"],
                reverse("frontend:project_update", args=[self.project.pk]),
            ),
            (
                workspace["repair"]["requirement_create_url"],
                reverse(
                    "frontend:project_requirement_create",
                    args=[self.project.pk],
                ),
            ),
            (
                workspace["repair"]["assignment_create_url"],
                reverse(
                    "frontend:project_assignment_create",
                    args=[self.project.pk],
                ),
            ),
            (
                workspace["assignments"][0].repair_coverage_url,
                reverse(
                    "frontend:project_assignment_coverage",
                    args=[self.project.pk, self.current_assignment.pk],
                ),
            ),
        ):
            parts = urlsplit(repair_url)
            self.assertEqual(parts.path, expected_path)
            self.assertEqual(parse_qs(parts.query)["return_to"], [planning_path])

        for row in workspace["candidates"]["rows"]:
            query = parse_qs(urlsplit(row["profile_url"]).query)
            self.assertEqual(query["start_date"], ["2026-09-07"])
            self.assertEqual(query["end_date"], ["2026-09-11"])
            self.assertEqual(query["return_to"], [planning_path])

        exclusions = {
            row["employee"].pk: row
            for row in workspace["candidate_exclusions"]["rows"]
        }
        self.assertEqual(
            exclusions[self.inactive.pk]["repair_action"]["label"],
            "Update employee status",
        )
        self.assertEqual(
            exclusions[self.unqualified.pk]["repair_action"]["label"],
            "Manage employee skills",
        )
        python_evidence = next(
            row
            for row in workspace["requirement_evidence"]["rows"]
            if row["requirement"].pk == self.python_requirement.pk
        )
        self.assertEqual(
            [action["label"] for action in python_evidence["repair_actions"]],
            [
                "Edit requirement",
                "Review employee skill evidence",
                "Add project assignment",
            ],
        )
        self.assertContains(
            response,
            "Repair links keep this workspace as your return point.",
        )

        self.client.force_login(self.viewer)
        read_only = self.client.get(self.url).context["workspace"]
        self.assertTrue(read_only["repair"]["is_read_only"])
        self.assertIsNone(read_only["repair"]["project_edit_url"])
        self.assertIsNone(read_only["repair"]["requirement_create_url"])
        self.assertIsNone(read_only["repair"]["assignment_create_url"])
        self.assertTrue(
            all(
                row.repair_edit_url is None
                for row in read_only["requirements"]
            )
        )
        self.assertTrue(
            all(
                row.repair_edit_url is None
                for row in read_only["assignments"]
            )
        )

    def test_attendance_and_later_pipeline_are_absent_from_planning(self):
        before = self._planning_snapshot(self._service_workspace())
        Attendance.objects.create(
            employee=self.alex,
            date=self.project.start_date,
            status=Attendance.Status.ABSENT,
        )
        after = self._planning_snapshot(self._service_workspace())
        self.assertEqual(after, before)

        with (
            patch("core.services.optimization.find_all_feasible_teams") as teams,
            patch("core.services.optimization.solve_team_effort_allocation") as solve,
            patch("core.services.optimization.select_recommended_teams") as select,
            patch(
                "core.services.optimization.build_recommendation_explanations"
            ) as explanations,
            patch("core.services.llm_explanations.generate_manager_summaries") as llm,
            patch(
                "frontend.presenters.planning.rank_employees_for_project",
                wraps=rank_employees_for_project,
            ) as rank,
        ):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        rank.assert_called_once()
        teams.assert_not_called()
        solve.assert_not_called()
        select.assert_not_called()
        explanations.assert_not_called()
        llm.assert_not_called()
        self.assertContains(
            response,
            "This is a readiness check, not a feasibility result.",
        )
        self.assertContains(
            response,
            "This ranking does not select or recommend a team.",
        )
        self.assertContains(
            response,
            "This evidence is not a feasible-team result.",
        )

        frontend_root = Path(__file__).resolve().parents[1]
        python_sources = (
            frontend_root / "views/planning.py",
            frontend_root / "presenters/planning.py",
            frontend_root / "presenters/planning_navigation.py",
            frontend_root / "selectors/planning.py",
        )
        template_sources = tuple(
            (frontend_root / "templates/frontend/planning").glob("*.html")
        )
        python_source = "\n".join(
            source.read_text(encoding="utf-8").lower()
            for source in python_sources
        )
        combined_source = python_source + "\n" + "\n".join(
            source.read_text(encoding="utf-8").lower()
            for source in template_sources
        )
        for forbidden_call in (
            "calculate_employee_project_match(",
            "calculate_skill_score(",
            "calculate_current_workload(",
            "calculate_available_hours_for_project(",
            "calculate_leave_availability_rate(",
            "calculate_daily_available_hours(",
            "find_all_feasible_teams(",
            "solve_team_effort_allocation(",
            "select_recommended_teams(",
            "build_recommendation_explanations(",
            "compare_recommendations(",
            "generate_manager_summar",
            "attendance.objects",
            "from core.models import attendance",
            "gemini",
            "ortools",
        ):
            with self.subTest(forbidden_call=forbidden_call):
                self.assertNotIn(forbidden_call, combined_source)
        self.assertEqual(python_source.count("get_recommendation_preflight("), 1)
        self.assertEqual(python_source.count("build_optimization_context("), 1)
        self.assertEqual(python_source.count("rank_employees_for_project("), 1)
        self.assertEqual(
            inspect.getsource(build_requirement_evidence_context)
            .lower()
            .count("get_requirement_capacity_evidence("),
            1,
        )
        app_js = (frontend_root / "static/frontend/js/app.js").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("planning", app_js.lower())

    def test_final_query_service_and_warm_response_baseline(self):
        self.assertEqual(
            self.EXPECTED_PAGE_QUERY_COUNT - self.EXPECTED_SERVICE_QUERY_COUNT,
            self.AUTHENTICATED_SHELL_QUERY_COUNT,
        )
        warm_service = self._service_workspace()
        self.assertTrue(warm_service["readiness"]["is_ready"])
        warm_response = self.client.get(self.url)
        self.assertEqual(warm_response.status_code, 200)

        service_durations = []
        response_durations = []
        response_sizes = []
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as service_queries:
                started_at = time.perf_counter()
                workspace = self._service_workspace()
                service_durations.append((time.perf_counter() - started_at) * 1000)
            self.assertTrue(workspace["readiness"]["is_ready"])
            self.assertEqual(
                len(service_queries),
                self.EXPECTED_SERVICE_QUERY_COUNT,
            )

            with CaptureQueriesContext(connection) as page_queries:
                started_at = time.perf_counter()
                response = self.client.get(self.url)
                response_durations.append((time.perf_counter() - started_at) * 1000)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(page_queries), self.EXPECTED_PAGE_QUERY_COUNT)
            response_sizes.append(len(response.content))

        service_p95 = statistics.quantiles(
            service_durations,
            n=20,
            method="inclusive",
        )[18]
        response_p95 = statistics.quantiles(
            response_durations,
            n=20,
            method="inclusive",
        )[18]
        print(
            "\nM5.8 final acceptance baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm samples, 2 requirements, "
            "5 employees, competing workload, approved leave, 1 coverage link):\n"
            f"  service_queries={self.EXPECTED_SERVICE_QUERY_COUNT}, "
            f"service_median={statistics.median(service_durations):.3f} ms, "
            f"service_p95={service_p95:.3f} ms\n"
            f"  page_queries={self.EXPECTED_PAGE_QUERY_COUNT} "
            f"({self.AUTHENTICATED_SHELL_QUERY_COUNT} shell + "
            f"{self.EXPECTED_SERVICE_QUERY_COUNT} planning), "
            f"response_median={statistics.median(response_durations):.3f} ms, "
            f"response_p95={response_p95:.3f} ms, "
            f"response={max(response_sizes)} bytes"
        )
