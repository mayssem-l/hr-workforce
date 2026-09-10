import ast
import inspect
import statistics
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
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
from core.services.optimization import (
    build_recommendation_explanations,
    compare_recommendations,
)
from frontend.presenters.recommendations import (
    build_recommendation_decision_evidence,
)
from frontend.recommendation_execution import (
    issue_recommendation_submission_token,
)
from frontend.roles import VIEWER_GROUP, sync_role_permissions


class RecommendationDecisionEvidenceTests(TestCase):
    EXPECTED_RESULT_QUERY_COUNT = 5
    TIMING_SAMPLE_COUNT = 7

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="m6-decision-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.project = Project.objects.create(
            name="Decision evidence project",
            description="Verify deterministic recommendation evidence.",
            start_date=date(2026, 10, 19),
            end_date=date(2026, 10, 23),
            estimated_hours=Decimal("20.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        cls.skill = Skill.objects.create(
            name="Decision evidence",
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

    def test_presenter_preserves_service_objects_order_lists_and_delta_values(self):
        pipeline_result = self._pipeline_result()
        evidence = build_recommendation_decision_evidence(
            pipeline_result["recommendations"],
            pipeline_result["comparisons"],
            pipeline_result["explanations"],
        )

        self.assertEqual(evidence["strategies"]["state"], "available")
        self.assertEqual(evidence["comparisons"]["state"], "available")
        self.assertIs(
            evidence["strategies"]["service_explanations"],
            pipeline_result["explanations"],
        )
        self.assertIs(
            evidence["comparisons"]["service_comparisons"],
            pipeline_result["comparisons"],
        )
        self.assertEqual(
            tuple(item["label"] for item in evidence["strategies"]["items"]),
            tuple(item["label"] for item in pipeline_result["recommendations"]),
        )
        for item, explanation in zip(
            evidence["strategies"]["items"],
            pipeline_result["explanations"],
            strict=True,
        ):
            self.assertIs(item["service_explanation"], explanation)
            self.assertIs(item["team"], explanation["team"])
            self.assertIs(item["strengths"], explanation["strengths"])
            self.assertIs(item["tradeoffs"], explanation["tradeoffs"])

        comparison_items = evidence["comparisons"]["items"]
        for item, comparison in zip(
            comparison_items,
            pipeline_result["comparisons"],
            strict=True,
        ):
            self.assertIs(item["service_comparison"], comparison)
            for field in (
                "from_label",
                "to_label",
                "team_size_change",
                "team_score_change",
                "remaining_capacity_change",
                "max_utilization_change",
                "utilization_spread_change",
            ):
                self.assertEqual(item[field], comparison[field])
        self.assertIs(
            comparison_items[0]["from_team"],
            pipeline_result["explanations"][0]["team"],
        )
        self.assertIs(
            comparison_items[0]["to_team"],
            pipeline_result["explanations"][1]["team"],
        )

    def test_backend_explanations_are_english_and_deterministic(self):
        first = self._pipeline_result()
        second = self._pipeline_result()

        self.assertEqual(first["explanations"], second["explanations"])
        explanation_text = " ".join(
            message
            for explanation in first["explanations"]
            for message in explanation["strengths"] + explanation["tradeoffs"]
        )
        self.assertIn("Uses the smallest feasible team: 1 person.", explanation_text)
        self.assertIn("Adds 20.00 h of remaining capacity.", explanation_text)
        self.assertIn(
            "Reduces maximum utilization by 20.00 percentage points.",
            explanation_text,
        )
        self.assertNotRegex(
            explanation_text,
            r"Mobilise|employé|Améliore|Réduit|Augmente|capacité|équilibre",
        )

    def test_page_renders_authoritative_explanations_and_exact_comparisons(self):
        pipeline_result = self._pipeline_result()
        response = self._post_result(pipeline_result)
        html = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Why these strategies differ")
        self.assertContains(response, "Authoritative evidence")
        self.assertContains(response, "Strengths")
        self.assertContains(response, "Trade-offs")
        for explanation in pipeline_result["explanations"]:
            for message in explanation["strengths"] + explanation["tradeoffs"]:
                self.assertContains(response, message)
        self.assertContains(
            response,
            "Best compact match to Best balanced alternative",
        )
        self.assertContains(
            response,
            "Best balanced alternative to Best capacity alternative",
        )
        self.assertContains(response, "Team size change (people)")
        self.assertContains(response, "-2.00 points")
        self.assertContains(response, "20.00 h")
        self.assertContains(response, "-20.00 percentage points")
        self.assertContains(response, "10.00 percentage points")
        self.assertContains(response, "0.00 points")
        self.assertContains(response, "0.00 percentage points")
        self.assertEqual(
            html.count('class="recommendation-explanation-card"'),
            3,
        )
        self.assertEqual(
            html.count('class="recommendation-comparison-card"'),
            2,
        )
        self.assertContains(response, "Earlier strategy team")
        self.assertContains(response, "Later strategy team")
        for employee in self.employees:
            self.assertContains(response, str(employee))
        self.assertContains(response, '<dl class="recommendation-comparison-metrics">')
        self.assertContains(response, 'aria-labelledby="recommendation-decision-title"')
        self.assertLess(
            html.index('id="recommendation-summary-title"'),
            html.index('id="recommendation-decision-title"'),
        )
        self.assertLess(
            html.index('id="recommendation-decision-title"'),
            html.index('id="recommendation-details-title"'),
        )

    def test_zero_one_two_and_three_results_render_only_returned_evidence(self):
        for count in range(4):
            with self.subTest(count=count):
                response = self._post_result(self._pipeline_result(count))
                html = response.content.decode("utf-8")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    html.count('class="recommendation-explanation-card"'),
                    count,
                )
                self.assertEqual(
                    html.count('class="recommendation-comparison-card"'),
                    count - 1 if count else 0,
                )
                if count == 0:
                    self.assertNotContains(response, "Why these strategies differ")
                elif count == 1:
                    self.assertContains(response, "No adjacent comparison returned")
                else:
                    self.assertNotContains(response, "No adjacent comparison returned")

    def test_empty_lists_and_unreadable_evidence_are_not_inferred(self):
        recommendations = self._recommendations(1)
        empty_explanation = {
            "category": recommendations[0]["category"],
            "label": recommendations[0]["label"],
            "team": [str(self.employees[0])],
            "strengths": [],
            "tradeoffs": [],
        }
        pipeline_result = self._pipeline_result(1)
        pipeline_result["explanations"] = [empty_explanation]
        response = self._post_result(pipeline_result)
        self.assertContains(response, "No deterministic strength was returned")
        self.assertContains(response, "No deterministic trade-off was returned")

        unreadable = build_recommendation_decision_evidence(
            recommendations,
            [{"not": "a comparison"}],
            [{"not": "an explanation"}],
        )
        self.assertEqual(unreadable["strategies"]["state"], "unavailable")
        self.assertEqual(
            unreadable["strategies"]["items"][0]["state"],
            "unavailable",
        )
        self.assertEqual(unreadable["comparisons"]["state"], "unavailable")
        self.assertEqual(unreadable["comparisons"]["items"], ())

    def test_comparison_order_and_full_team_lists_follow_service_output(self):
        pipeline_result = self._pipeline_result()
        evidence = build_recommendation_decision_evidence(
            pipeline_result["recommendations"],
            pipeline_result["comparisons"],
            pipeline_result["explanations"],
        )
        items = evidence["comparisons"]["items"]

        self.assertEqual(
            tuple((item["from_label"], item["to_label"]) for item in items),
            (
                ("Best compact match", "Best balanced alternative"),
                ("Best balanced alternative", "Best capacity alternative"),
            ),
        )
        self.assertEqual(
            items[0]["from_team"],
            [str(self.employees[0])],
        )
        self.assertEqual(
            items[0]["to_team"],
            [str(self.employees[0]), str(self.employees[1])],
        )
        self.assertEqual(
            items[1]["to_team"],
            [str(employee) for employee in self.employees],
        )

    def test_frontend_contains_no_comparison_calculation_and_makes_no_mutation(self):
        presenter_source = inspect.getsource(
            build_recommendation_decision_evidence
        )
        parsed = ast.parse(presenter_source)
        self.assertFalse(
            any(isinstance(node, ast.BinOp) for node in ast.walk(parsed))
        )
        called_names = {
            node.func.id
            for node in ast.walk(parsed)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        for forbidden_call in (
            "abs",
            "sum",
            "round",
            "min",
            "max",
            "compare_recommendations",
            "build_recommendation_explanations",
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
        for comparison_field in (
            "team_size_change",
            "team_score_change",
            "remaining_capacity_change",
            "max_utilization_change",
            "utilization_spread_change",
        ):
            self.assertNotIn(comparison_field, javascript_source)

        counts_before = (
            Project.objects.count(),
            ProjectSkillRequirement.objects.count(),
            Employee.objects.count(),
            EmployeeSkill.objects.count(),
            Assignment.objects.count(),
            AssignmentSkill.objects.count(),
        )
        response = self._post_result()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This run did not change staffing records.")
        self.assertNotContains(response, "Create assignment")
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

    def test_query_count_and_warm_decision_evidence_overhead_remain_fixed(self):
        pipeline_result = self._pipeline_result()
        durations_ms = []
        response_sizes = []
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=pipeline_result,
        ) as pipeline:
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
        self.assertEqual(pipeline.call_count, self.TIMING_SAMPLE_COUNT)

        p95_ms = statistics.quantiles(
            durations_ms,
            n=20,
            method="inclusive",
        )[18]
        print(
            "\nM6.4 deterministic-evidence rendering baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client POSTs, "
            "3 explanations / 2 adjacent comparisons, expensive pipeline "
            "mocked):\n"
            f"  queries={self.EXPECTED_RESULT_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"response={max(response_sizes)} bytes"
        )
