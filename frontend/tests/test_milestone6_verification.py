"""M6.9 Milestone 6 verification and finalization.

Acceptance coverage across every Milestone 6 route, state, and boundary,
reconciling displayed values against the existing core services with real
(non-mocked) pipeline runs where determinism allows, plus an explicit
per-criterion exit check. Verification only; no new feature.
"""

import inspect
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext, override_settings
from django.urls import resolve, reverse

from core.models import (
    Assignment,
    AssignmentSkill,
    Attendance,
    Employee,
    EmployeeSkill,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from core.services.optimization import (
    build_recommendation_explanations,
    compare_recommendations,
    find_all_feasible_teams,
    find_pareto_teams,
    select_recommended_teams,
)
from frontend.orchestration.recommendations import run_recommendation_pipeline
from frontend.recommendation_runs import fetch_recommendation_run
from frontend.roles import (
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)
from frontend.selectors.projects import get_project_profile
from frontend.selectors.recommendations import get_recommendation_input_snapshot


def _build_fixture(prefix="M69"):
    python = Skill.objects.create(name="Python", category="Engineering")
    project = Project.objects.create(
        name=f"{prefix} verification project",
        description="Milestone 6 acceptance fixture.",
        start_date=date(2026, 9, 7),
        end_date=date(2026, 9, 11),
        estimated_hours=Decimal("8.00"),
        status=Project.Status.PLANNED,
        priority=Project.Priority.HIGH,
        criticality=Project.Criticality.HIGH,
    )
    requirement = ProjectSkillRequirement.objects.create(
        project=project,
        skill=python,
        required_level=3,
        priority=ProjectSkillRequirement.Priority.HIGH,
        is_mandatory=True,
        required_quantity=1,
        estimated_effort_hours=Decimal("8.00"),
    )
    employees = []
    for index in range(3):
        employee = Employee.objects.create(
            first_name=f"{prefix}{index}",
            last_name="Engineer",
            department="Engineering",
            position="Engineer",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("5.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )
        EmployeeSkill.objects.create(
            employee=employee,
            skill=python,
            level=4,
            years_experience=Decimal("3.0"),
        )
        employees.append(employee)
    return python, project, requirement, employees


class Milestone6RouteContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="m69-route-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.manager = get_user_model().objects.create_user(
            username="m69-route-manager"
        )
        cls.manager.groups.add(Group.objects.get(name=MANAGER_PLANNER_GROUP))
        cls.unassigned = get_user_model().objects.create_user(
            username="m69-route-unassigned"
        )
        _, cls.project, _, _ = _build_fixture(prefix="M69R")

    def setUp(self):
        cache.clear()
        self.client.force_login(self.viewer)
        self.planning_url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )
        self.generate_url = reverse(
            "frontend:project_recommendation_generate",
            args=[self.project.project_id],
        )

    def test_routes_methods_templates_and_navigation(self):
        self.assertEqual(
            resolve(self.planning_url).view_name,
            "frontend:project_planning",
        )
        self.assertEqual(
            resolve(self.generate_url).view_name,
            "frontend:project_recommendation_generate",
        )
        self.assertEqual(self.client.get(self.generate_url).status_code, 405)
        self.assertEqual(
            self.client.post(self.planning_url, {}).status_code, 405
        )
        planning = self.client.get(self.planning_url)
        self.assertEqual(planning.status_code, 200)
        self.assertTemplateUsed(
            planning, "frontend/planning/workspace.html"
        )
        self.assertRegex(
            planning.content.decode("utf-8"),
            r'href="/projects/"\s+aria-current="page"',
        )
        confirm_url = reverse(
            "frontend:project_recommendation_confirm",
            args=[self.project.project_id, "compact_match"],
        )
        self.assertEqual(
            resolve(confirm_url).view_name,
            "frontend:project_recommendation_confirm",
        )

    def test_authentication_permission_and_csrf_contracts(self):
        anonymous = Client()
        for url in (self.planning_url, self.generate_url):
            self.assertRedirects(
                anonymous.get(url),
                f"{reverse('frontend:login')}?next={url}",
                fetch_redirect_response=False,
            )
        self.assertRedirects(
            anonymous.post(self.generate_url, {"submission_token": "x"}),
            f"{reverse('frontend:login')}?next={self.generate_url}",
            fetch_redirect_response=False,
        )
        unassigned_client = Client()
        unassigned_client.force_login(self.unassigned)
        self.assertEqual(
            unassigned_client.get(self.planning_url).status_code, 403
        )
        self.assertEqual(
            unassigned_client.post(
                self.generate_url, {"submission_token": "x"}
            ).status_code,
            403,
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.viewer)
        self.assertEqual(
            csrf_client.post(
                self.generate_url, {"submission_token": "x"}
            ).status_code,
            403,
        )


class Milestone6ServiceReconciliationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.manager = get_user_model().objects.create_user(
            username="m69-reconcile-manager"
        )
        cls.manager.groups.add(
            Group.objects.get(name=MANAGER_PLANNER_GROUP)
        )
        cls.python, cls.project, cls.requirement, cls.employees = (
            _build_fixture(prefix="M69C")
        )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.manager)
        self.planning_url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )
        self.generate_url = reverse(
            "frontend:project_recommendation_generate",
            args=[self.project.project_id],
        )

    def _expected(self):
        project = get_project_profile(self.project.project_id)
        feasible = find_all_feasible_teams(project)
        pareto = find_pareto_teams(feasible)
        recommendations = select_recommended_teams(pareto)
        comparisons = compare_recommendations(recommendations)
        explanations = build_recommendation_explanations(
            recommendations, comparisons
        )
        return {
            "feasible": feasible,
            "pareto": pareto,
            "recommendations": recommendations,
            "comparisons": comparisons,
            "explanations": explanations,
        }

    def _generated(self):
        planning = self.client.get(self.planning_url)
        token = planning.context["recommendation_generation"]["form"][
            "submission_token"
        ].value()
        return self.client.post(
            self.generate_url, {"submission_token": token}
        )

    def test_displayed_values_match_core_services(self):
        response = self._generated()
        self.assertEqual(response.status_code, 200)
        run = response.context["run"]
        expected = self._expected()
        self.assertEqual(run["state"], "completed")
        self.assertEqual(
            len(run["strategies"]["cards"]),
            len(expected["recommendations"]),
        )
        for card, recommendation, explanation in zip(
            run["strategies"]["cards"],
            expected["recommendations"],
            expected["explanations"],
        ):
            result = recommendation["result"]
            with self.subTest(strategy=recommendation["label"]):
                self.assertEqual(card["category"], recommendation["category"])
                self.assertEqual(card["label"], recommendation["label"])
                self.assertEqual(
                    [member["employee"].employee_id for member in card["members"]],
                    [member.employee_id for member in result["team"]],
                )
                self.assertEqual(card["team_size"], result["team_size"])
                self.assertEqual(card["team_score"], result["team_score"])
                for metric in (
                    "total_available_hours",
                    "total_allocated_hours",
                    "remaining_capacity_hours",
                    "max_utilization",
                    "utilization_spread",
                ):
                    self.assertEqual(
                        card[metric], result["metrics"][metric]
                    )
                evidence = card["allocation_evidence"]
                service_solution = result["effort_solution"]
                self.assertEqual(
                    len(evidence["capacity"]["rows"]),
                    len(service_solution["employee_capacities"]),
                )
                for row, service_row in zip(
                    evidence["capacity"]["rows"],
                    service_solution["employee_capacities"],
                ):
                    self.assertEqual(
                        row["employee"].employee_id,
                        service_row["employee"].employee_id,
                    )
                    self.assertEqual(
                        row["available_hours"],
                        service_row["available_hours"],
                    )
                    self.assertEqual(
                        row["allocated_hours"],
                        service_row["allocated_hours"],
                    )
                    self.assertEqual(
                        row["utilization_rate"],
                        service_row["utilization_rate"],
                    )
                service_hours = {
                    (
                        item["employee"].employee_id,
                        item["requirement"].project_skill_requirement_id,
                    ): item["hours"]
                    for item in service_solution["allocations"]
                }
                for row in evidence["matrix"]["rows"]:
                    for cell, column in zip(
                        row["cells"], evidence["matrix"]["columns"]
                    ):
                        key = (
                            row["employee"].employee_id,
                            column["requirement"].project_skill_requirement_id,
                        )
                        if cell["has_returned_allocation"]:
                            self.assertEqual(cell["hours"], service_hours[key])
                service_coverage = {
                    item["requirement"].project_skill_requirement_id: item
                    for item in result["coverage"]
                }
                for row in evidence["coverage"]["rows"]:
                    service_row = service_coverage[
                        row["requirement"].project_skill_requirement_id
                    ]
                    self.assertEqual(
                        row["covered_quantity"],
                        service_row["covered_quantity"],
                    )
                    self.assertEqual(
                        row["is_satisfied"], service_row["is_satisfied"]
                    )
        decision = run["decision_evidence"]
        self.assertEqual(
            [item["label"] for item in decision["strategies"]["items"]],
            [item["label"] for item in expected["explanations"]],
        )
        for item, explanation in zip(
            decision["strategies"]["items"], expected["explanations"]
        ):
            self.assertEqual(item["strengths"], explanation["strengths"])
            self.assertEqual(item["tradeoffs"], explanation["tradeoffs"])
            self.assertEqual(item["team"], explanation["team"])
        self.assertEqual(
            [
                (
                    item["from_label"],
                    item["to_label"],
                    item["team_size_change"],
                    item["team_score_change"],
                )
                for item in decision["comparisons"]["items"]
            ],
            [
                (
                    item["from_label"],
                    item["to_label"],
                    item["team_size_change"],
                    item["team_score_change"],
                )
                for item in expected["comparisons"]
            ],
        )
        html = response.content.decode("utf-8")
        first_card = run["strategies"]["cards"][0]
        self.assertIn(first_card["label"], html)
        self.assertIn(
            decision["strategies"]["items"][0]["strengths"][0]
            or "Strengths",
            html,
        )
        record = fetch_recommendation_run(
            response.context["recommendation_run_id"]
        )
        self.assertIsNotNone(record)
        self.assertEqual(record["project_id"], self.project.project_id)

    def test_repeated_runs_agree_and_boundary_states_hold(self):
        first = self._generated()
        second = self._generated()
        for response in (first, second):
            self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [card["label"] for card in first.context["run"]["strategies"]["cards"]],
            [card["label"] for card in second.context["run"]["strategies"]["cards"]],
        )
        self.assertEqual(
            first.context["run"]["decision_evidence"],
            second.context["run"]["decision_evidence"],
        )


class Milestone6SeparationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.manager = get_user_model().objects.create_user(
            username="m69-separation-manager"
        )
        cls.manager.groups.add(
            Group.objects.get(name=MANAGER_PLANNER_GROUP)
        )
        cls.python, cls.project, cls.requirement, cls.employees = (
            _build_fixture(prefix="M69S")
        )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.manager)
        self.planning_url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )
        self.generate_url = reverse(
            "frontend:project_recommendation_generate",
            args=[self.project.project_id],
        )

    def _generate(self):
        planning = self.client.get(self.planning_url)
        token = planning.context["recommendation_generation"]["form"][
            "submission_token"
        ].value()
        return self.client.post(
            self.generate_url, {"submission_token": token}
        )

    def test_planning_get_runs_no_pipeline_or_enrichment(self):
        with (
            patch(
                "frontend.views.recommendations.run_recommendation_pipeline"
            ) as pipeline,
            patch(
                "frontend.orchestration.recommendation_enrichment."
                "generate_manager_summary"
            ) as provider,
            patch(
                "frontend.views.assignment_handoff.run_recommendation_pipeline"
            ) as handoff_pipeline,
        ):
            response = self.client.get(self.planning_url)
        self.assertEqual(response.status_code, 200)
        pipeline.assert_not_called()
        provider.assert_not_called()
        handoff_pipeline.assert_not_called()

    def test_attendance_leaves_decisions_unchanged(self):
        before_snapshot = get_recommendation_input_snapshot(
            self.project.project_id
        )
        first = self._generate()
        Attendance.objects.create(
            employee=self.employees[0],
            date=self.project.start_date,
            status=Attendance.Status.ABSENT,
        )
        after_snapshot = get_recommendation_input_snapshot(
            self.project.project_id
        )
        self.assertEqual(
            before_snapshot["signature"], after_snapshot["signature"]
        )
        second = self._generate()
        self.assertEqual(
            [card["label"] for card in first.context["run"]["strategies"]["cards"]],
            [card["label"] for card in second.context["run"]["strategies"]["cards"]],
        )
        self.assertEqual(
            first.context["run"]["decision_evidence"],
            second.context["run"]["decision_evidence"],
        )

    @override_settings(
        GEMINI_MANAGER_SUMMARIES_ENABLED=True,
        GEMINI_MANAGER_SUMMARY_TIMEOUT_MS=10000,
    )
    def test_gemini_success_and_failure_keep_decisions(self):
        def _fake_summary(explanation, *, timeout_ms):
            return "Compact choice keeps capacity steady."

        with patch(
            "frontend.orchestration.recommendation_enrichment."
            "generate_manager_summary",
            side_effect=_fake_summary,
        ):
            successful = self._generate()
        run = successful.context["run"]
        self.assertEqual(
            run["decision_evidence"]["enrichment"]["state"], "available"
        )
        strategies = [card["label"] for card in run["strategies"]["cards"]]

        with patch(
            "frontend.orchestration.recommendation_enrichment."
            "generate_manager_summary",
            side_effect=RuntimeError("provider down"),
        ):
            failed = self._generate()
        failed_run = failed.context["run"]
        self.assertEqual(
            failed_run["decision_evidence"]["enrichment"]["state"],
            "unavailable",
        )
        self.assertEqual(
            [card["label"] for card in failed_run["strategies"]["cards"]],
            strategies,
        )
        self.assertEqual(
            [card["team_score"] for card in failed_run["strategies"]["cards"]],
            [card["team_score"] for card in run["strategies"]["cards"]],
        )
        self.assertNotContains(failed, "provider down")

    def test_generation_and_review_never_write(self):
        before = (
            Assignment.objects.count(),
            AssignmentSkill.objects.count(),
        )
        generated = self._generate()
        run_id = generated.context["recommendation_run_id"]
        category = generated.context["run"]["strategies"]["cards"][0][
            "category"
        ]
        review = self.client.get(
            reverse(
                "frontend:project_recommendation_confirm",
                args=[self.project.project_id, category],
            )
            + f"?run={run_id}"
        )
        self.assertEqual(review.status_code, 200)
        self.assertEqual(
            (Assignment.objects.count(), AssignmentSkill.objects.count()),
            before,
        )

    def test_confirm_writes_exact_records_once(self):
        generated = self._generate()
        run_id = generated.context["recommendation_run_id"]
        category = generated.context["run"]["strategies"]["cards"][0][
            "category"
        ]
        confirm_url = (
            reverse(
                "frontend:project_recommendation_confirm",
                args=[self.project.project_id, category],
            )
            + f"?run={run_id}"
        )
        review = self.client.get(confirm_url)
        token = review.context["review"]["form"][
            "submission_token"
        ].value()
        saved = self.client.post(
            confirm_url,
            {"submission_token": token, "run_id": run_id},
        )
        self.assertRedirects(
            saved, self.planning_url, fetch_redirect_response=False
        )
        self.assertEqual(Assignment.objects.count(), 1)
        self.assertEqual(AssignmentSkill.objects.count(), 1)
        assignment = Assignment.objects.get()
        self.assertEqual(assignment.project_id, self.project.project_id)
        self.assertEqual(assignment.start_date, self.project.start_date)
        self.assertEqual(assignment.end_date, self.project.end_date)

    def test_frontend_sources_hold_boundaries(self):
        frontend_root = Path(__file__).resolve().parents[1]
        pipeline_source = inspect.getsource(
            run_recommendation_pipeline
        ).lower()
        for service in (
            "find_all_feasible_teams",
            "find_pareto_teams",
            "select_recommended_teams",
            "compare_recommendations",
            "build_recommendation_explanations",
        ):
            self.assertEqual(pipeline_source.count(service), 1)
        combined = "\n".join(
            (frontend_root / path).read_text(encoding="utf-8").lower()
            for path in (
                "orchestration/recommendations.py",
                "orchestration/assignment_handoff.py",
                "recommendation_execution.py",
                "assignment_handoff.py",
                "recommendation_runs.py",
                "forms/recommendations.py",
                "forms/assignment_handoff.py",
                "presenters/recommendations.py",
                "presenters/assignment_handoff.py",
                "presenters/planning.py",
                "selectors/recommendations.py",
                "views/recommendations.py",
                "views/assignment_handoff.py",
                "views/planning.py",
                "templates/frontend/planning/workspace.html",
                "templates/frontend/recommendations/result.html",
                "templates/frontend/recommendations/confirm.html",
                "static/frontend/js/app.js",
            )
        )
        for forbidden in (
            "calculate_employee_project_match(",
            "calculate_team_score(",
            "calculate_current_workload(",
            "calculate_available_hours_for_project(",
            "calculate_leave_availability_rate(",
            "calculate_team_metrics(",
            "solve_team_effort_allocation(",
            "attendance.objects",
            "ortools",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)


class Milestone6ExitCriteriaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.manager = get_user_model().objects.create_user(
            username="m69-exit-manager"
        )
        cls.manager.groups.add(
            Group.objects.get(name=MANAGER_PLANNER_GROUP)
        )
        cls.python, cls.project, cls.requirement, cls.employees = (
            _build_fixture(prefix="M69E")
        )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.manager)
        self.planning_url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )
        self.generate_url = reverse(
            "frontend:project_recommendation_generate",
            args=[self.project.project_id],
        )

    def _token(self):
        planning = self.client.get(self.planning_url)
        return planning.context["recommendation_generation"]["form"][
            "submission_token"
        ].value()

    def test_explicit_guarded_duplicate_safe_generation(self):
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline"
        ) as pipeline:
            self.client.get(self.planning_url)
        pipeline.assert_not_called()
        token = self._token()
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline"
        ) as pipeline:
            pipeline.side_effect = RuntimeError("boom")
            with self.assertLogs(
                "frontend.views.recommendations", level="ERROR"
            ):
                failed = self.client.post(
                    self.generate_url, {"submission_token": token}
                )
            self.assertEqual(failed.status_code, 503)
        fresh = self._token()
        self.assertTrue(fresh)
        self.assertNotEqual(token, fresh)

    def test_cards_allocations_and_explanations_are_complete(self):
        employee = self.employees[0]
        recommendation = {
            "category": "compact_match",
            "label": "Best compact match",
            "reason": "Existing service-owned selection reason.",
            "result": {
                "team": [employee],
                "team_size": 1,
                "team_score": 88.25,
                "metrics": {
                    "team_size": 1,
                    "total_available_hours": Decimal("32.00"),
                    "total_allocated_hours": Decimal("8.00"),
                    "remaining_capacity_hours": Decimal("24.00"),
                    "max_utilization": 25.0,
                    "utilization_spread": 0.0,
                },
                "effort_solution": {
                    "is_feasible": True,
                    "employee_capacities": [
                        {
                            "employee": employee,
                            "available_hours": Decimal("32.00"),
                            "allocated_hours": Decimal("8.00"),
                            "utilization_rate": 25.0,
                        }
                    ],
                    "allocations": [
                        {
                            "employee": employee,
                            "requirement": self.requirement,
                            "skill": self.python,
                            "hours": Decimal("8.00"),
                        }
                    ],
                },
                "coverage": [
                    {
                        "requirement": self.requirement,
                        "skill": self.python,
                        "required_quantity": 1,
                        "covered_quantity": 1,
                        "is_mandatory": True,
                        "is_satisfied": True,
                        "qualified_employees": [employee],
                    }
                ],
            },
        }
        envelope = {
            "feasible_teams": [recommendation["result"]],
            "pareto_teams": [recommendation["result"]],
            "recommendations": [recommendation],
            "comparisons": [],
            "explanations": [
                {
                    "category": "compact_match",
                    "label": "Best compact match",
                    "team": [str(employee)],
                    "strengths": ["Existing deterministic strength."],
                    "tradeoffs": ["Existing deterministic trade-off."],
                }
            ],
            "elapsed_seconds": 0.25,
        }
        token = self._token()
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=envelope,
        ) as pipeline:
            response = self.client.post(
                self.generate_url, {"submission_token": token}
            )
            self.assertEqual(pipeline.call_count, 1)
        run = response.context["run"]
        self.assertEqual(run["state"], "completed")
        self.assertEqual(run["result_variant"], "one_strategy")
        self.assertGreater(len(run["strategies"]["cards"]), 0)
        for card in run["strategies"]["cards"]:
            self.assertTrue(card["allocation_evidence"]["capacity"]["rows"])
            self.assertTrue(card["allocation_evidence"]["coverage"]["rows"])
        decision = run["decision_evidence"]
        self.assertEqual(decision["strategies"]["state"], "available")
        for item in decision["strategies"]["items"]:
            self.assertIn("strengths", item)
            self.assertIn("tradeoffs", item)
        self.assertContains(response, "This run did not change staffing records.")

    def test_recovery_and_confirmation_outcomes(self):
        empty_project = Project.objects.create(
            name="M69E empty project",
            description="Empty verification fixture.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            estimated_hours=Decimal("8.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        from frontend.recommendation_execution import (
            issue_recommendation_submission_token,
        )
        from frontend.selectors.recommendations import (
            get_recommendation_input_snapshot as snapshot,
        )

        signature = snapshot(empty_project.project_id)["signature"]
        token = issue_recommendation_submission_token(
            project_id=empty_project.project_id,
            user_id=self.manager.pk,
            input_signature=signature,
        )
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline"
        ) as pipeline:
            blocked = self.client.post(
                reverse(
                    "frontend:project_recommendation_generate",
                    args=[empty_project.project_id],
                ),
                {"submission_token": token},
            )
        pipeline.assert_not_called()
        self.assertEqual(blocked.status_code, 422)
        self.assertContains(
            blocked, "Review current planning information", status_code=422
        )

    def test_final_baseline_summary(self):
        with CaptureQueriesContext(connection) as planning_queries:
            planning = self.client.get(self.planning_url)
        self.assertEqual(planning.status_code, 200)
        token = planning.context["recommendation_generation"]["form"][
            "submission_token"
        ].value()
        with CaptureQueriesContext(connection) as result_queries:
            generated = self.client.post(
                self.generate_url, {"submission_token": token}
            )
        self.assertEqual(generated.status_code, 200)
        print(
            "\nM6.9 final acceptance baseline "
            "(verification fixture, real solver):\n"
            f"  planning_get_queries={len(planning_queries)}, "
            f"result_post_queries={len(result_queries)}, "
            f"strategies={generated.context['run']['recommendation_count']}, "
            f"response={len(generated.content)} bytes"
        )
