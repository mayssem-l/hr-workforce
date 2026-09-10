import inspect
import re
import statistics
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.db import connection
from django.test import Client, SimpleTestCase, TestCase
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
from frontend.orchestration.recommendations import run_recommendation_pipeline
from frontend.recommendation_execution import (
    issue_recommendation_submission_token,
)
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)


class RecommendationOrchestrationTests(SimpleTestCase):
    def test_pipeline_delegates_once_in_the_documented_order(self):
        project = object()
        feasible_teams = [object()]
        pareto_teams = [object()]
        recommendations = [object()]
        comparisons = [object()]
        explanations = [object()]
        calls = []

        def record(name, expected_argument, result):
            def delegated(argument, *extra):
                self.assertIs(argument, expected_argument)
                if name == "explanations":
                    self.assertEqual(extra, (comparisons,))
                else:
                    self.assertEqual(extra, ())
                calls.append(name)
                return result

            return delegated

        with (
            patch(
                "frontend.orchestration.recommendations.find_all_feasible_teams",
                side_effect=record("feasible", project, feasible_teams),
            ) as feasible_service,
            patch(
                "frontend.orchestration.recommendations.find_pareto_teams",
                side_effect=record("pareto", feasible_teams, pareto_teams),
            ) as pareto_service,
            patch(
                "frontend.orchestration.recommendations.select_recommended_teams",
                side_effect=record("selection", pareto_teams, recommendations),
            ) as selection_service,
            patch(
                "frontend.orchestration.recommendations.compare_recommendations",
                side_effect=record("comparison", recommendations, comparisons),
            ) as comparison_service,
            patch(
                "frontend.orchestration.recommendations."
                "build_recommendation_explanations",
                side_effect=record(
                    "explanations",
                    recommendations,
                    explanations,
                ),
            ) as explanation_service,
            patch(
                "frontend.orchestration.recommendations.perf_counter",
                side_effect=(10.0, 11.25),
            ),
        ):
            result = run_recommendation_pipeline(project)

        self.assertEqual(
            calls,
            ["feasible", "pareto", "selection", "comparison", "explanations"],
        )
        for service in (
            feasible_service,
            pareto_service,
            selection_service,
            comparison_service,
            explanation_service,
        ):
            service.assert_called_once()
        self.assertIs(result["feasible_teams"], feasible_teams)
        self.assertIs(result["pareto_teams"], pareto_teams)
        self.assertIs(result["recommendations"], recommendations)
        self.assertIs(result["comparisons"], comparisons)
        self.assertIs(result["explanations"], explanations)
        self.assertEqual(result["elapsed_seconds"], 1.25)


class RecommendationExecutionTests(TestCase):
    EXPECTED_PLANNING_QUERY_COUNT = 21
    EXPECTED_RESULT_QUERY_COUNT = 5
    TIMING_SAMPLE_COUNT = 7
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
        cls.viewer = cls._role_user("m6-execution-viewer", VIEWER_GROUP)
        cls.manager = cls._role_user(
            "m6-execution-manager",
            MANAGER_PLANNER_GROUP,
        )
        cls.hr_user = cls._role_user(
            "m6-execution-hr",
            HR_ADMINISTRATOR_GROUP,
        )
        cls.unassigned = get_user_model().objects.create_user(
            username="m6-execution-unassigned"
        )

        cls.python = Skill.objects.create(name="Python", category="Engineering")
        cls.project = Project.objects.create(
            name="M6 execution project",
            description="Verify explicit recommendation execution.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            estimated_hours=Decimal("8.00"),
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
            estimated_effort_hours=Decimal("8.00"),
        )
        cls.employee = Employee.objects.create(
            first_name="Alex",
            last_name="Able",
            department="Engineering",
            position="Engineer",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("6.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )
        EmployeeSkill.objects.create(
            employee=cls.employee,
            skill=cls.python,
            level=4,
            years_experience=Decimal("4.0"),
        )
        cls.assignment = Assignment.objects.create(
            employee=cls.employee,
            project=cls.project,
            start_date=cls.project.start_date,
            end_date=cls.project.end_date,
            allocation_percentage=25,
            role_on_project="Technical lead",
            status=Assignment.Status.ACTIVE,
        )
        AssignmentSkill.objects.create(
            assignment=cls.assignment,
            project_skill_requirement=cls.requirement,
        )

        cls.incomplete_project = Project.objects.create(
            name="M6 blocked project",
            description="Recommendation generation remains unavailable.",
            start_date=cls.project.start_date,
            end_date=cls.project.end_date,
            estimated_hours=Decimal("8.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )
        ProjectSkillRequirement.objects.create(
            project=cls.incomplete_project,
            skill=cls.python,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=None,
        )

    @staticmethod
    def _role_user(username, role):
        user = get_user_model().objects.create_user(username=username)
        user.groups.add(Group.objects.get(name=role))
        return user

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

    def _pipeline_result(self, *, count=1, elapsed=0.25):
        strategy_definitions = (
            ("compact_match", "Best compact match"),
            ("balanced", "Best balanced alternative"),
            ("capacity", "Best capacity alternative"),
        )
        return {
            "feasible_teams": ["feasible"] if count else [],
            "pareto_teams": ["pareto"] if count else [],
            "recommendations": [
                {
                    "category": strategy_definitions[index][0],
                    "label": strategy_definitions[index][1],
                    "reason": "Existing service-owned selection reason.",
                    "result": {
                        "team": [self.employee],
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
                    },
                }
                for index in range(count)
            ],
            "comparisons": [],
            "explanations": [],
            "elapsed_seconds": elapsed,
        }

    def _submission_token(self, client=None, project=None):
        client = client or self.client
        project = project or self.project
        response = client.get(
            reverse(
                "frontend:project_planning",
                args=[project.project_id],
            )
        )
        self.assertEqual(response.status_code, 200)
        return response.context["recommendation_generation"]["form"][
            "submission_token"
        ].value()

    def test_planning_workspace_exposes_only_an_explicit_ready_action(self):
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline"
        ) as pipeline:
            response = self.client.get(self.planning_url)
            method_response = self.client.get(self.generate_url)
        pipeline.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(method_response.status_code, 405)
        self.assertContains(response, "Team recommendation generation")
        self.assertContains(response, f'action="{self.generate_url}"')
        self.assertContains(response, 'method="post"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'name="submission_token"')
        self.assertContains(response, "Generate recommendations")
        self.assertContains(
            response,
            'data-loading-label="Generating recommendations…"',
        )
        self.assertContains(response, 'role="status" aria-live="polite"')
        self.assertContains(response, "It does not request optional generated summaries")
        self.assertNotContains(response, "recommendation-card")

        blocked_url = reverse(
            "frontend:project_planning",
            args=[self.incomplete_project.project_id],
        )
        blocked = self.client.get(blocked_url)
        self.assertEqual(blocked.status_code, 200)
        self.assertContains(blocked, "Recommendation generation is not available")
        self.assertNotContains(blocked, "Generate recommendations")
        self.assertNotContains(
            blocked,
            reverse(
                "frontend:project_recommendation_generate",
                args=[self.incomplete_project.project_id],
            ),
        )

    def test_route_authentication_permissions_and_csrf_contract(self):
        self.assertEqual(
            self.generate_url,
            f"/projects/{self.project.project_id}/recommendations/generate/",
        )
        match = resolve(self.generate_url)
        self.assertEqual(
            match.view_name,
            "frontend:project_recommendation_generate",
        )
        self.assertEqual(match.kwargs["project_id"], self.project.project_id)

        anonymous = Client().post(self.generate_url, {})
        self.assertRedirects(
            anonymous,
            f"{reverse('frontend:login')}?next={self.generate_url}",
            fetch_redirect_response=False,
        )
        unassigned_client = Client()
        unassigned_client.force_login(self.unassigned)
        self.assertEqual(unassigned_client.post(self.generate_url, {}).status_code, 403)

        permissions = {
            permission.codename: permission
            for permission in Permission.objects.filter(
                content_type__app_label="core",
                codename__in=self.REQUIRED_VIEW_CODENAMES,
            )
        }
        for omitted_codename in self.REQUIRED_VIEW_CODENAMES:
            restricted = get_user_model().objects.create_user(
                username=f"m6-without-{omitted_codename}"
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
                self.assertEqual(
                    restricted_client.post(self.generate_url, {}).status_code,
                    403,
                )

        for user in (self.viewer, self.manager, self.hr_user):
            role_client = Client()
            role_client.force_login(user)
            token = self._submission_token(role_client)
            with (
                self.subTest(role=user.username),
                patch(
                    "frontend.views.recommendations.run_recommendation_pipeline",
                    return_value=self._pipeline_result(),
                ),
            ):
                self.assertEqual(
                    role_client.post(
                        self.generate_url,
                        {"submission_token": token},
                    ).status_code,
                    200,
                )

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.viewer)
        signed_token = issue_recommendation_submission_token(
            project_id=self.project.pk,
            user_id=self.viewer.pk,
        )
        self.assertEqual(
            csrf_client.post(
                self.generate_url,
                {"submission_token": signed_token},
            ).status_code,
            403,
        )
        planning = csrf_client.get(self.planning_url)
        html = planning.content.decode("utf-8")
        csrf_token = re.search(
            r'name="csrfmiddlewaretoken" value="([^"]+)"',
            html,
        ).group(1)
        submission_token = planning.context["recommendation_generation"]["form"][
            "submission_token"
        ].value()
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=self._pipeline_result(),
        ):
            accepted = csrf_client.post(
                self.generate_url,
                {
                    "csrfmiddlewaretoken": csrf_token,
                    "submission_token": submission_token,
                },
            )
        self.assertEqual(accepted.status_code, 200)

    def test_single_use_token_prevents_duplicate_pipeline_runs(self):
        token = self._submission_token()
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=self._pipeline_result(),
        ) as pipeline:
            first = self.client.post(
                self.generate_url,
                {"submission_token": token},
            )
            duplicate = self.client.post(
                self.generate_url,
                {"submission_token": token},
            )
            new_token = self._submission_token()
            fresh = self.client.post(
                self.generate_url,
                {"submission_token": new_token},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(duplicate.status_code, 409)
        self.assertContains(
            duplicate,
            "This recommendation request was already submitted.",
            status_code=409,
        )
        self.assertContains(
            duplicate,
            "A second pipeline run was not started.",
            status_code=409,
        )
        self.assertNotEqual(token, new_token)
        self.assertEqual(fresh.status_code, 200)
        self.assertEqual(pipeline.call_count, 2)

        app_js = (
            Path(__file__).resolve().parents[1] / "static/frontend/js/app.js"
        ).read_text(encoding="utf-8")
        self.assertIn('form.getAttribute("aria-busy") === "true"', app_js)
        self.assertIn("event.preventDefault();", app_js)
        self.assertIn("loadingStatus.hidden = false;", app_js)
        self.assertIn("button.textContent = loadingLabel;", app_js)

    def test_success_empty_invalid_error_missing_and_no_mutation_results(self):
        counts_before = (
            Project.objects.count(),
            ProjectSkillRequirement.objects.count(),
            Assignment.objects.count(),
            AssignmentSkill.objects.count(),
            Employee.objects.count(),
            EmployeeSkill.objects.count(),
            Leave.objects.count(),
        )
        completed_result = self._pipeline_result(count=2, elapsed=1.2345)
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=completed_result,
        ):
            completed = self.client.post(
                self.generate_url,
                {"submission_token": self._submission_token()},
            )
        self.assertEqual(completed.status_code, 200)
        self.assertTemplateUsed(completed, "frontend/recommendations/result.html")
        self.assertEqual(completed.context["run"]["state"], "completed")
        self.assertIs(
            completed.context["run"]["pipeline_result"],
            completed_result,
        )
        self.assertContains(completed, "2 selected strategies")
        self.assertContains(completed, "1.235 seconds")
        self.assertContains(completed, "This run did not change staffing records.")
        self.assertContains(completed, f'href="{self.planning_url}"')
        self.assertRegex(
            completed.content.decode("utf-8"),
            r'href="/projects/"\s+aria-current="page"',
        )

        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=self._pipeline_result(count=0),
        ):
            empty = self.client.post(
                self.generate_url,
                {"submission_token": self._submission_token()},
            )
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.context["run"]["state"], "empty")
        self.assertContains(empty, "No recommendation strategy was returned.")
        self.assertContains(empty, "does not infer which planning condition")
        self.assertNotContains(empty, "No feasible team exists")

        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline"
        ) as pipeline:
            invalid = self.client.post(
                self.generate_url,
                {"submission_token": "invalid-token"},
            )
            wrong_project = self.client.post(
                self.generate_url,
                {
                    "submission_token": issue_recommendation_submission_token(
                        project_id=self.incomplete_project.pk,
                        user_id=self.viewer.pk,
                    )
                },
            )
            wrong_user = self.client.post(
                self.generate_url,
                {
                    "submission_token": issue_recommendation_submission_token(
                        project_id=self.project.pk,
                        user_id=self.manager.pk,
                    )
                },
            )
        pipeline.assert_not_called()
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(wrong_project.status_code, 400)
        self.assertEqual(wrong_user.status_code, 400)
        self.assertContains(
            invalid,
            "This recommendation request is no longer valid.",
            status_code=400,
        )

        with (
            self.assertLogs("frontend.views.recommendations", level="ERROR"),
            patch(
                "frontend.views.recommendations.run_recommendation_pipeline",
                side_effect=RuntimeError("private failure detail"),
            ),
        ):
            failed = self.client.post(
                self.generate_url,
                {"submission_token": self._submission_token()},
            )
        self.assertEqual(failed.status_code, 503)
        self.assertContains(
            failed,
            "Recommendation generation could not be completed.",
            status_code=503,
        )
        self.assertNotContains(failed, "private failure detail", status_code=503)

        missing_url = reverse(
            "frontend:project_recommendation_generate",
            args=[999999],
        )
        self.assertEqual(
            self.client.post(
                missing_url,
                {
                    "submission_token": issue_recommendation_submission_token(
                        project_id=999999,
                        user_id=self.viewer.pk,
                    )
                },
            ).status_code,
            404,
        )
        deleted_project = Project.objects.create(
            name="Deleted recommendation target",
            description="Verify a stale action cannot run after deletion.",
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            estimated_hours=Decimal("8.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )
        deleted_project_id = deleted_project.pk
        deleted_token = issue_recommendation_submission_token(
            project_id=deleted_project_id,
            user_id=self.viewer.pk,
        )
        deleted_project.delete()
        deleted_url = reverse(
            "frontend:project_recommendation_generate",
            args=[deleted_project_id],
        )
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline"
        ) as pipeline:
            deleted = self.client.post(
                deleted_url,
                {"submission_token": deleted_token},
            )
        pipeline.assert_not_called()
        self.assertEqual(deleted.status_code, 404)
        self.assertEqual(
            counts_before,
            (
                Project.objects.count(),
                ProjectSkillRequirement.objects.count(),
                Assignment.objects.count(),
                AssignmentSkill.objects.count(),
                Employee.objects.count(),
                EmployeeSkill.objects.count(),
                Leave.objects.count(),
            ),
        )

    def test_fixed_request_queries_and_warm_response_overhead(self):
        with self.assertNumQueries(self.EXPECTED_PLANNING_QUERY_COUNT):
            planning = self.client.get(self.planning_url)
        self.assertEqual(planning.status_code, 200)

        durations_ms = []
        response_sizes = []
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=self._pipeline_result(),
        ) as pipeline:
            for _ in range(self.TIMING_SAMPLE_COUNT):
                token = self._submission_token()
                with CaptureQueriesContext(connection) as queries:
                    started_at = time.perf_counter()
                    response = self.client.post(
                        self.generate_url,
                        {"submission_token": token},
                    )
                    durations_ms.append((time.perf_counter() - started_at) * 1000)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(queries), self.EXPECTED_RESULT_QUERY_COUNT)
                response_sizes.append(len(response.content))
        self.assertEqual(pipeline.call_count, self.TIMING_SAMPLE_COUNT)

        p95_ms = statistics.quantiles(
            durations_ms,
            n=20,
            method="inclusive",
        )[18]
        print(
            "\nM6.1 recommendation-response foundation baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client POSTs with "
            "the expensive pipeline mocked):\n"
            f"  planning_get_queries={self.EXPECTED_PLANNING_QUERY_COUNT}, "
            f"result_post_queries={self.EXPECTED_RESULT_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"response={max(response_sizes)} bytes"
        )

    def test_frontend_sources_do_not_duplicate_pipeline_or_calculations(self):
        frontend_root = Path(__file__).resolve().parents[1]
        orchestrator_source = inspect.getsource(run_recommendation_pipeline).lower()
        for call in (
            "find_all_feasible_teams(",
            "find_pareto_teams(",
            "select_recommended_teams(",
            "compare_recommendations(",
            "build_recommendation_explanations(",
        ):
            with self.subTest(call=call):
                self.assertEqual(orchestrator_source.count(call), 1)
        self.assertNotIn("gemini", orchestrator_source)
        self.assertNotIn("generate_manager_summar", orchestrator_source)

        application_sources = (
            frontend_root / "orchestration/recommendations.py",
            frontend_root / "recommendation_execution.py",
            frontend_root / "forms/recommendations.py",
            frontend_root / "presenters/recommendations.py",
            frontend_root / "views/recommendations.py",
            frontend_root / "views/planning.py",
            frontend_root / "templates/frontend/planning/workspace.html",
            frontend_root / "templates/frontend/recommendations/result.html",
            frontend_root / "static/frontend/js/app.js",
        )
        combined_source = "\n".join(
            path.read_text(encoding="utf-8").lower()
            for path in application_sources
        )
        for forbidden in (
            "calculate_employee_project_match(",
            "calculate_team_score(",
            "calculate_skill_score(",
            "calculate_current_workload(",
            "calculate_available_hours_for_project(",
            "calculate_leave_availability_rate(",
            "calculate_team_metrics(",
            "solve_team_effort_allocation(",
            "attendance.objects",
            "from core.models import attendance",
            "ortools",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined_source)
        view_source = (
            frontend_root / "views/recommendations.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("core.services.optimization", view_source)
