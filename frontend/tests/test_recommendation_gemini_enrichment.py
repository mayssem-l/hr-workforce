import ast
import inspect
import json
import statistics
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, call, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import (
    Assignment,
    AssignmentSkill,
    Employee,
    EmployeeSkill,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from core.services.llm_explanations import generate_manager_summary
from core.services.optimization import (
    build_recommendation_explanations,
    compare_recommendations,
)
from frontend.orchestration.recommendation_enrichment import (
    MAX_MANAGER_SUMMARY_CHARACTERS,
    _validated_manager_summary,
)
from frontend.recommendation_execution import (
    issue_recommendation_submission_token,
)
from frontend.roles import VIEWER_GROUP, sync_role_permissions


class RecommendationGeminiEnrichmentTests(TestCase):
    EXPECTED_RESULT_QUERY_COUNT = 37
    TIMING_SAMPLE_COUNT = 7

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="m6-gemini-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.project = Project.objects.create(
            name="Optional summary project",
            description="Verify isolated Gemini wording enrichment.",
            start_date=date(2026, 10, 26),
            end_date=date(2026, 10, 30),
            estimated_hours=Decimal("20.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        cls.skill = Skill.objects.create(
            name="Summary evidence",
            category="Engineering",
        )
        ProjectSkillRequirement.objects.create(
            project=cls.project,
            skill=cls.skill,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=Decimal("20.00"),
        )
        cls.employees = tuple(
            Employee.objects.create(
                first_name=first_name,
                last_name=last_name,
                department="Engineering",
                position="Engineer",
                hire_date=date(2020, 1, 6),
                experience_years=Decimal("6.0"),
                capacity_hours_week=Decimal("40.00"),
                status=Employee.Status.ACTIVE,
            )
            for first_name, last_name in (
                ("Avery", "Compact"),
                ("Blair", "Balanced"),
                ("Casey", "Capacity"),
            )
        )
        for employee in cls.employees:
            EmployeeSkill.objects.create(
                employee=employee,
                skill=cls.skill,
                level=4,
                years_experience=Decimal("4.0"),
            )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.viewer)
        self.generate_url = reverse(
            "frontend:project_recommendation_generate",
            args=[self.project.pk],
        )

    def _recommendations(self, count=3):
        definitions = (
            (
                "compact_match",
                "Best compact match",
                self.employees[:1],
                92.0,
                Decimal("10.00"),
                50.0,
                0.0,
            ),
            (
                "balanced",
                "Best balanced alternative",
                self.employees[:2],
                90.0,
                Decimal("30.00"),
                30.0,
                10.0,
            ),
            (
                "capacity",
                "Best capacity alternative",
                self.employees,
                90.0,
                Decimal("50.00"),
                20.0,
                10.0,
            ),
        )
        recommendations = []
        for category, label, team, score, remaining, maximum, spread in (
            definitions[:count]
        ):
            team_size = len(team)
            recommendations.append(
                {
                    "category": category,
                    "label": label,
                    "reason": f"Existing reason for {label}.",
                    "result": {
                        "team": team,
                        "team_size": team_size,
                        "team_score": score,
                        "metrics": {
                            "team_size": team_size,
                            "total_available_hours": Decimal("70.00"),
                            "total_allocated_hours": Decimal("20.00"),
                            "remaining_capacity_hours": remaining,
                            "max_utilization": maximum,
                            "utilization_spread": spread,
                        },
                        "coverage": [],
                        "effort_solution": {
                            "is_feasible": True,
                            "reason": "The team can absorb all mandatory effort.",
                            "allocations": [],
                            "employee_capacities": [],
                        },
                    },
                }
            )
        return recommendations

    def _pipeline_result(self, count=3):
        recommendations = self._recommendations(count)
        comparisons = compare_recommendations(recommendations)
        explanations = build_recommendation_explanations(
            recommendations,
            comparisons,
        )
        return {
            "feasible_teams": [item["result"] for item in recommendations],
            "pareto_teams": [item["result"] for item in recommendations],
            "recommendations": recommendations,
            "comparisons": comparisons,
            "explanations": explanations,
            "elapsed_seconds": 1.5,
        }

    def _post_result(self, pipeline_result=None):
        pipeline_result = pipeline_result or self._pipeline_result()
        token = issue_recommendation_submission_token(
            project_id=self.project.pk,
            user_id=self.viewer.pk,
        )
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=pipeline_result,
        ) as pipeline:
            response = self.client.post(
                self.generate_url,
                {"submission_token": token},
            )
        pipeline.assert_called_once_with(self.project)
        return response

    @override_settings(GEMINI_MANAGER_SUMMARIES_ENABLED=False)
    def test_disabled_setting_skips_provider_and_keeps_deterministic_result(self):
        pipeline_result = self._pipeline_result()
        with patch(
            "frontend.orchestration.recommendation_enrichment.generate_manager_summary"
        ) as provider:
            response = self._post_result(pipeline_result)

        self.assertEqual(response.status_code, 200)
        provider.assert_not_called()
        self.assertContains(response, "Optional Gemini summaries are off")
        self.assertContains(
            response,
            pipeline_result["explanations"][0]["strengths"][0],
        )
        self.assertNotContains(response, 'class="recommendation-gemini-summary"')
        self.assertIs(response.context["run"]["pipeline_result"], pipeline_result)

    @override_settings(
        GEMINI_MANAGER_SUMMARIES_ENABLED=True,
        GEMINI_MANAGER_SUMMARY_TIMEOUT_MS=10000,
    )
    def test_successful_summaries_render_without_changing_service_evidence(self):
        pipeline_result = self._pipeline_result()
        summaries = (
            "This compact option is useful when a smaller team is preferred.",
            "This balanced option is useful when spreading workload matters.",
            "This capacity option is useful when more remaining capacity matters.",
        )
        counts_before = (
            Project.objects.count(),
            ProjectSkillRequirement.objects.count(),
            Employee.objects.count(),
            EmployeeSkill.objects.count(),
            Assignment.objects.count(),
            AssignmentSkill.objects.count(),
        )
        with patch(
            "frontend.orchestration.recommendation_enrichment.generate_manager_summary",
            side_effect=summaries,
        ) as provider:
            response = self._post_result(pipeline_result)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            provider.call_args_list,
            [
                call(explanation, timeout_ms=10000)
                for explanation in pipeline_result["explanations"]
            ],
        )
        self.assertNotContains(response, "Optional Gemini summaries available")
        self.assertNotContains(response, "Optional Gemini wording is available")
        self.assertContains(
            response,
            'aria-label="Manager summary"',
            count=3,
        )
        self.assertContains(
            response,
            "<span>Manager summary</span>",
            count=3,
            html=True,
        )
        self.assertNotContains(response, "Optional Gemini summary</span>")
        self.assertNotContains(
            response,
            "Supplemental wording only. The deterministic evidence below "
            "remains authoritative.",
        )
        for summary in summaries:
            self.assertContains(response, summary)
        run = response.context["run"]
        self.assertIs(run["pipeline_result"], pipeline_result)
        self.assertEqual(
            tuple(
                item["category"]
                for item in run["decision_evidence"]["strategies"]["items"]
            ),
            tuple(
                recommendation["category"]
                for recommendation in pipeline_result["recommendations"]
            ),
        )
        for item, explanation in zip(
            run["decision_evidence"]["strategies"]["items"],
            pipeline_result["explanations"],
            strict=True,
        ):
            self.assertIs(item["service_explanation"], explanation)
            self.assertIs(item["strengths"], explanation["strengths"])
            self.assertIs(item["tradeoffs"], explanation["tradeoffs"])
        self.assertEqual(
            counts_before,
            (
                Project.objects.count(),
                ProjectSkillRequirement.objects.count(),
                Employee.objects.count(),
                EmployeeSkill.objects.count(),
                Assignment.objects.count(),
                AssignmentSkill.objects.count(),
            ),
        )

    @override_settings(GEMINI_MANAGER_SUMMARIES_ENABLED=True)
    def test_timeout_rate_limit_and_missing_credentials_use_generic_fallback(self):
        failures = (
            TimeoutError("provider timeout with secret detail"),
            RuntimeError("429 provider rate-limit detail"),
            ValueError("missing API key provider detail"),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                pipeline_result = self._pipeline_result(1)
                with self.assertLogs(
                    "frontend.orchestration.recommendation_enrichment",
                    level="WARNING",
                ) as provider_logs:
                    with patch(
                        "frontend.orchestration.recommendation_enrichment.generate_manager_summary",
                        side_effect=failure,
                    ):
                        response = self._post_result(pipeline_result)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Optional Gemini summaries unavailable")
                self.assertContains(
                    response,
                    pipeline_result["explanations"][0]["strengths"][0],
                )
                self.assertContains(response, "Use the deterministic strengths")
                self.assertNotContains(response, str(failure))
                self.assertNotContains(response, "traceback")
                self.assertNotContains(response, "API key")
                logged_text = " ".join(provider_logs.output)
                self.assertNotIn(str(failure), logged_text)
                self.assertNotIn("API key", logged_text)
                self.assertNotIn("traceback", logged_text.lower())

    @override_settings(GEMINI_MANAGER_SUMMARIES_ENABLED=True)
    def test_partial_and_invalid_responses_keep_every_deterministic_strategy(self):
        pipeline_result = self._pipeline_result()
        valid_summary = "This compact option keeps the team focused."
        invalid_summary = "This option has a fabricated score of 999.00."
        with patch(
            "frontend.orchestration.recommendation_enrichment.generate_manager_summary",
            side_effect=(
                valid_summary,
                TimeoutError("private provider failure"),
                invalid_summary,
            ),
        ):
            response = self._post_result(pipeline_result)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Some optional Gemini summaries unavailable")
        self.assertContains(response, valid_summary)
        self.assertNotContains(response, invalid_summary)
        self.assertNotContains(response, "private provider failure")
        self.assertContains(
            response,
            'class="recommendation-explanation-card"',
            count=3,
        )
        self.assertContains(
            response,
            'aria-label="Gemini summary unavailable"',
            count=2,
        )
        for explanation in pipeline_result["explanations"]:
            for message in explanation["strengths"] + explanation["tradeoffs"]:
                self.assertContains(response, message)

    def test_summary_validation_accepts_only_short_plain_supported_numbers(self):
        explanation = self._pipeline_result(1)["explanations"][0]
        explanation["strengths"].append("Team score evidence: 92.00.")

        self.assertEqual(
            _validated_manager_summary(
                "This option retains the 92.00 team score evidence.",
                explanation,
            ),
            "This option retains the 92.00 team score evidence.",
        )
        for invalid in (
            None,
            "",
            "x" * (MAX_MANAGER_SUMMARY_CHARACTERS + 1),
            "<strong>Provider markup</strong>",
            "Two lines are not accepted.\nSecond line.",
            "This option has an unsupported score of 92.",
            "This option invents a score of 999.00.",
        ):
            with self.subTest(invalid=repr(invalid)[:40]):
                self.assertIsNone(
                    _validated_manager_summary(invalid, explanation)
                )

    def test_existing_gemini_client_receives_timeout_minimal_payload_and_rules(self):
        explanation = self._pipeline_result(1)["explanations"][0]
        client = Mock()
        client.models.generate_content.return_value.text = (
            "  This compact option is useful for a focused team.  "
        )
        with patch(
            "core.services.llm_explanations.genai.Client",
            return_value=client,
        ) as client_factory:
            result = generate_manager_summary(explanation, timeout_ms=10000)

        self.assertEqual(
            result,
            "This compact option is useful for a focused team.",
        )
        http_options = client_factory.call_args.kwargs["http_options"]
        self.assertEqual(http_options.timeout, 10000)
        self.assertEqual(http_options.retry_options.attempts, 1)
        self.assertNotIn("api_key", client_factory.call_args.kwargs)
        generate_call = client.models.generate_content.call_args
        self.assertEqual(generate_call.kwargs["model"], "gemini-3.1-flash-lite")
        payload = json.loads(generate_call.kwargs["contents"])
        self.assertEqual(
            set(payload),
            {"category", "label", "team", "strengths", "tradeoffs"},
        )
        self.assertNotIn("metrics", payload)
        self.assertNotIn("project", payload)
        instructions = generate_call.kwargs["config"].system_instruction
        self.assertIn("Write only in English", instructions)
        self.assertIn("Do not recalculate any value", instructions)
        self.assertIn("Do not invent any information", instructions)

    def test_enrichment_runs_after_pipeline_and_frontend_has_no_decision_logic(self):
        from frontend.orchestration.recommendation_enrichment import (
            build_optional_manager_summaries,
        )
        from frontend.views import recommendations as recommendation_views

        view_source = inspect.getsource(
            recommendation_views.project_recommendation_generate
        )
        self.assertLess(
            view_source.index("run_recommendation_pipeline(project)"),
            view_source.index("build_optional_manager_summaries("),
        )
        self.assertLess(
            view_source.index("build_optional_manager_summaries("),
            view_source.index("build_recommendation_result_foundation("),
        )

        enrichment_source = inspect.getsource(build_optional_manager_summaries)
        parsed = ast.parse(enrichment_source)
        called_names = {
            node.func.id
            for node in ast.walk(parsed)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        for forbidden_call in (
            "find_all_feasible_teams",
            "find_pareto_teams",
            "select_recommended_teams",
            "compare_recommendations",
            "build_recommendation_explanations",
            "solve_team_effort_allocation",
            "calculate_team_metrics",
            "calculate_team_score",
        ):
            with self.subTest(forbidden_call=forbidden_call):
                self.assertNotIn(forbidden_call, called_names)

        frontend_root = Path(__file__).resolve().parents[1]
        template_source = (
            frontend_root
            / "templates/frontend/recommendations/_decision_evidence.html"
        ).read_text(encoding="utf-8")
        javascript_source = (
            frontend_root / "static/frontend/js/app.js"
        ).read_text(encoding="utf-8")
        self.assertNotIn("{% widthratio", template_source)
        self.assertNotIn("|add:", template_source)
        self.assertNotIn("manager_summary", javascript_source)
        self.assertNotIn("gemini", javascript_source.lower())

    @override_settings(
        GEMINI_MANAGER_SUMMARIES_ENABLED=True,
        GEMINI_MANAGER_SUMMARY_TIMEOUT_MS=10000,
    )
    def test_query_count_and_warm_mocked_provider_overhead_remain_fixed(self):
        pipeline_result = self._pipeline_result()
        durations_ms = []
        response_sizes = []
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=pipeline_result,
        ), patch(
            "frontend.orchestration.recommendation_enrichment.generate_manager_summary",
            return_value="This optional summary uses deterministic evidence.",
        ) as provider:
            for _ in range(self.TIMING_SAMPLE_COUNT):
                token = issue_recommendation_submission_token(
                    project_id=self.project.pk,
                    user_id=self.viewer.pk,
                )
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
        self.assertEqual(
            provider.call_count,
            self.TIMING_SAMPLE_COUNT * 3,
        )

        p95_ms = statistics.quantiles(
            durations_ms,
            n=20,
            method="inclusive",
        )[18]
        print(
            "\nM6.5 Gemini-enrichment presentation baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client POSTs, "
            "3 successful summaries, deterministic pipeline and provider "
            "mocked):\n"
            f"  queries={self.EXPECTED_RESULT_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"response={max(response_sizes)} bytes"
        )
