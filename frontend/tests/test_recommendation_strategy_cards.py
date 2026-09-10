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
from django.utils.html import conditional_escape

from core.models import (
    Employee,
    EmployeeSkill,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from frontend.presenters.recommendations import (
    build_recommendation_strategy_cards,
)
from frontend.recommendation_execution import (
    issue_recommendation_submission_token,
)
from frontend.roles import VIEWER_GROUP, sync_role_permissions


class RecommendationStrategyCardTests(TestCase):
    EXPECTED_RESULT_QUERY_COUNT = 5
    TIMING_SAMPLE_COUNT = 7

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="m6-strategy-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.unassigned = get_user_model().objects.create_user(
            username="m6-strategy-unassigned"
        )
        cls.skill = Skill.objects.create(
            name="Recommendation evidence",
            category="Engineering",
        )
        cls.project = Project.objects.create(
            name="Strategy evidence project",
            description="Verify selected strategy presentation.",
            start_date=date(2026, 10, 5),
            end_date=date(2026, 10, 9),
            estimated_hours=Decimal("12.35"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        ProjectSkillRequirement.objects.create(
            project=cls.project,
            skill=cls.skill,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=Decimal("12.35"),
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
                ("Avery", "Able"),
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
            args=[self.project.project_id],
        )
        self.planning_url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )

    def _recommendations(self, count=3):
        definitions = (
            {
                "category": "compact_match",
                "label": "Best compact match",
                "reason": "Smallest feasible team with the strongest match.",
                "team": self.employees[:1],
                "team_size": 1,
                "team_score": 91.25,
                "metrics": {
                    "team_size": 1,
                    "total_available_hours": Decimal("31.125"),
                    "total_allocated_hours": Decimal("12.345"),
                    "remaining_capacity_hours": Decimal("18.780"),
                    "max_utilization": 39.495,
                    "utilization_spread": 0.0,
                },
            },
            {
                "category": "balanced",
                "label": "Best balanced alternative",
                "reason": "Uses one additional employee to balance workload.",
                "team": self.employees[:2],
                "team_size": 2,
                "team_score": 91.25,
                "metrics": {
                    "team_size": 2,
                    "total_available_hours": Decimal("72.50"),
                    "total_allocated_hours": Decimal("12.35"),
                    "remaining_capacity_hours": Decimal("60.15"),
                    "max_utilization": 24.25,
                    "utilization_spread": 8.255,
                },
            },
            {
                "category": "capacity",
                "label": "Best capacity alternative",
                "reason": "Provides greater remaining capacity.",
                "team": self.employees,
                "team_size": 3,
                "team_score": 87.5,
                "metrics": {
                    "team_size": 3,
                    "total_available_hours": Decimal("110.00"),
                    "total_allocated_hours": Decimal("12.35"),
                    "remaining_capacity_hours": Decimal("97.65"),
                    "max_utilization": 18.0,
                    "utilization_spread": 5.5,
                },
            },
        )
        return [
            {
                "category": definition["category"],
                "label": definition["label"],
                "reason": definition["reason"],
                "result": {
                    "team": definition["team"],
                    "team_size": definition["team_size"],
                    "team_score": definition["team_score"],
                    "metrics": definition["metrics"],
                    "coverage": ["not rendered in M6.2"],
                    "effort_solution": {"allocations": ["not rendered in M6.2"]},
                },
            }
            for definition in definitions[:count]
        ]

    def _pipeline_result(self, count=3):
        recommendations = self._recommendations(count)
        return {
            "feasible_teams": [item["result"] for item in recommendations],
            "pareto_teams": [item["result"] for item in recommendations],
            "recommendations": recommendations,
            "comparisons": [{"not": "rendered in M6.2"}],
            "explanations": [{"not": "rendered in M6.2"}],
            "elapsed_seconds": 1.2345,
        }

    def _post_result(self, pipeline_result):
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

    def test_presenter_preserves_selection_order_objects_and_metric_values(self):
        recommendations = self._recommendations()
        presented = build_recommendation_strategy_cards(
            self.project,
            recommendations,
            self.viewer,
        )
        cards = presented["cards"]

        self.assertEqual(
            tuple(card["category"] for card in cards),
            ("compact_match", "balanced", "capacity"),
        )
        self.assertEqual(
            tuple(card["label"] for card in cards),
            (
                "Best compact match",
                "Best balanced alternative",
                "Best capacity alternative",
            ),
        )
        for recommendation, card in zip(recommendations, cards, strict=True):
            result = recommendation["result"]
            metrics = result["metrics"]
            self.assertIs(card["service_recommendation"], recommendation)
            self.assertIs(card["service_result"], result)
            self.assertIs(card["service_metrics"], metrics)
            self.assertEqual(card["team_score"], result["team_score"])
            self.assertEqual(card["team_size"], result["team_size"])
            for key in (
                "total_available_hours",
                "total_allocated_hours",
                "remaining_capacity_hours",
                "max_utilization",
                "utilization_spread",
            ):
                self.assertEqual(card[key], metrics[key])
        self.assertEqual(cards[0]["team_score"], cards[1]["team_score"])

    def test_zero_one_two_and_three_strategy_layouts_have_no_placeholders(self):
        labels = (
            "Best compact match",
            "Best balanced alternative",
            "Best capacity alternative",
        )
        for count in range(4):
            with self.subTest(count=count):
                response = self._post_result(self._pipeline_result(count))
                html = response.content.decode("utf-8")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    html.count('class="recommendation-strategy-card"'),
                    count,
                )
                for expected_label in labels[:count]:
                    self.assertContains(response, expected_label)
                for absent_label in labels[count:]:
                    self.assertNotContains(response, absent_label)
                positions = [html.index(label) for label in labels[:count]]
                self.assertEqual(positions, sorted(positions))
                if count:
                    self.assertContains(response, "Recommendation summary")
                    self.assertContains(response, "Allocation and requirement details")
                else:
                    self.assertNotContains(response, "Recommendation summary")
                    self.assertNotContains(response, "Allocation and requirement details")
                    self.assertNotContains(response, "recommendation-strategy-summary")

    def test_cards_render_exact_members_metrics_units_and_semantic_summary(self):
        pipeline_result = self._pipeline_result()
        response = self._post_result(pipeline_result)
        cards = response.context["run"]["strategies"]["cards"]

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Oct 5, 2026 through Oct 9, 2026",
        )
        self.assertContains(response, "91.25 out of 100")
        self.assertContains(response, "31.13 h")
        self.assertContains(response, "12.35 h")
        self.assertContains(response, "18.78 h")
        self.assertContains(response, "39.5%")
        self.assertContains(response, "8.26 percentage points")
        for employee in self.employees:
            self.assertContains(response, str(employee))
        self.assertContains(
            response,
            conditional_escape(cards[0]["members"][0]["profile_url"]),
        )
        self.assertContains(response, '<article class="recommendation-strategy-card"')
        self.assertContains(
            response,
            '<dl class="recommendation-strategy-metrics">',
        )
        self.assertContains(response, "<caption>")
        self.assertContains(response, '<th scope="col">Strategy</th>', html=True)
        self.assertContains(response, '<th scope="row">Best compact match</th>', html=True)
        self.assertContains(response, 'aria-labelledby="recommendation-strategy-1-title"')
        self.assertContains(response, 'id="recommendation-summary-title"')
        self.assertContains(response, 'id="recommendation-details-title"')
        self.assertNotContains(response, "not rendered in M6.2")

    def test_context_links_are_permission_aware_and_scoped_to_the_project(self):
        recommendations = self._recommendations(1)
        permitted = build_recommendation_strategy_cards(
            self.project,
            recommendations,
            self.viewer,
        )
        navigation = permitted["navigation"]
        self.assertEqual(
            navigation["project_url"],
            reverse("frontend:project_detail", args=[self.project.pk]),
        )
        self.assertEqual(
            navigation["requirements_url"],
            f"{self.planning_url}#planning-requirements-title",
        )
        self.assertEqual(
            navigation["candidates_url"],
            f"{self.planning_url}#planning-candidates-title",
        )
        profile_url = permitted["cards"][0]["members"][0]["profile_url"]
        self.assertIn(f"/employees/{self.employees[0].pk}/", profile_url)
        self.assertIn("start_date=2026-10-05", profile_url)
        self.assertIn("end_date=2026-10-09", profile_url)
        self.assertIn(
            f"return_to=%2Fprojects%2F{self.project.pk}%2Fplanning%2F",
            profile_url,
        )

        restricted = build_recommendation_strategy_cards(
            self.project,
            recommendations,
            self.unassigned,
        )
        self.assertEqual(
            restricted["navigation"],
            {
                "planning_url": None,
                "project_url": None,
                "requirements_url": None,
                "candidates_url": None,
            },
        )
        self.assertIsNone(restricted["cards"][0]["members"][0]["profile_url"])
        self.assertEqual(
            restricted["cards"][0]["team_score"],
            recommendations[0]["result"]["team_score"],
        )

    def test_missing_employee_references_remain_readable_and_unlinked(self):
        deleted_employee = Employee.objects.create(
            first_name="Deleted",
            last_name="Member",
            department="Engineering",
            position="Engineer",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("4.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )
        deleted_employee_id = deleted_employee.pk
        deleted_label = str(deleted_employee)
        deleted_employee.delete()
        pipeline_result = self._pipeline_result(1)
        pipeline_result["recommendations"][0]["result"]["team"] = (
            deleted_employee,
            None,
        )
        pipeline_result["recommendations"][0]["result"]["team_size"] = 2
        pipeline_result["recommendations"][0]["result"]["metrics"][
            "team_size"
        ] = 2

        response = self._post_result(pipeline_result)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, deleted_label)
        self.assertContains(response, "Employee record unavailable")
        self.assertNotContains(response, f'/employees/{deleted_employee_id}/')
        members = response.context["run"]["strategies"]["cards"][0]["members"]
        self.assertIsNone(members[0]["profile_url"])
        self.assertIsNone(members[1]["profile_url"])

    def test_rendering_is_advisory_and_does_not_mutate_staffing_records(self):
        counts_before = (
            Project.objects.count(),
            ProjectSkillRequirement.objects.count(),
            Employee.objects.count(),
            EmployeeSkill.objects.count(),
        )
        response = self._post_result(self._pipeline_result())
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
            ),
        )

    def test_responsive_and_source_boundaries_exclude_metric_recalculation(self):
        presenter_source = inspect.getsource(
            build_recommendation_strategy_cards
        )
        parsed = ast.parse(presenter_source)
        called_names = {
            node.func.id
            for node in ast.walk(parsed)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        for forbidden_call in (
            "sum",
            "len",
            "round",
            "min",
            "max",
            "calculate_team_metrics",
            "calculate_team_score",
        ):
            with self.subTest(forbidden_call=forbidden_call):
                self.assertNotIn(forbidden_call, called_names)

        frontend_root = Path(__file__).resolve().parents[1]
        result_template = (
            frontend_root / "templates/frontend/recommendations/result.html"
        ).read_text(encoding="utf-8")
        card_template = (
            frontend_root
            / "templates/frontend/recommendations/_strategy_card.html"
        ).read_text(encoding="utf-8")
        css_source = (
            frontend_root / "static/frontend/css/theme.css"
        ).read_text(encoding="utf-8")
        javascript_source = (
            frontend_root / "static/frontend/js/app.js"
        ).read_text(encoding="utf-8")
        combined_templates = result_template + card_template
        self.assertNotIn("{% widthratio", combined_templates)
        self.assertNotIn("|add:", combined_templates)
        self.assertNotIn("_allocation_evidence.html", card_template)
        self.assertIn("_allocation_evidence.html", result_template)
        self.assertIn("overflow-x: auto", css_source)
        self.assertIn(
            "grid-template-columns: repeat(3, minmax(0, 1fr))",
            css_source,
        )
        self.assertIn("grid-template-columns: 1fr", css_source)
        for metric_name in (
            "team_score",
            "total_available_hours",
            "total_allocated_hours",
            "remaining_capacity_hours",
            "max_utilization",
            "utilization_spread",
        ):
            self.assertNotIn(metric_name, javascript_source)

    def test_result_query_count_and_warm_rendering_overhead_remain_fixed(self):
        durations_ms = []
        response_sizes = []
        pipeline_result = self._pipeline_result()
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
            "\nM6.2 strategy-card rendering baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client POSTs, "
            "3 strategies / 6 rendered member rows, expensive pipeline mocked):\n"
            f"  queries={self.EXPECTED_RESULT_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"response={max(response_sizes)} bytes"
        )
