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
from frontend.presenters import recommendations as recommendation_presenters
from frontend.presenters.recommendations import (
    build_recommendation_strategy_cards,
)
from frontend.recommendation_execution import (
    issue_recommendation_submission_token,
)
from frontend.roles import VIEWER_GROUP, sync_role_permissions


class RecommendationAllocationEvidenceTests(TestCase):
    EXPECTED_RESULT_QUERY_COUNT = 5
    TIMING_SAMPLE_COUNT = 7

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="m6-allocation-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.project = Project.objects.create(
            name="Allocation evidence project",
            description="Verify exact optimization evidence presentation.",
            start_date=date(2026, 10, 12),
            end_date=date(2026, 10, 16),
            estimated_hours=Decimal("12.50"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        cls.python = Skill.objects.create(name="Python", category="Engineering")
        cls.data = Skill.objects.create(name="Data", category="Engineering")
        cls.writing = Skill.objects.create(
            name="Technical writing",
            category="Delivery",
        )
        cls.python_requirement = cls._requirement(
            cls.python,
            effort="8.00",
            quantity=1,
            mandatory=True,
        )
        cls.data_requirement = cls._requirement(
            cls.data,
            effort="4.50",
            quantity=1,
            mandatory=True,
        )
        cls.optional_requirement = cls._requirement(
            cls.writing,
            effort="0.00",
            quantity=1,
            mandatory=False,
        )
        cls.alex = cls._employee("Alex", "Allocator")
        cls.bailey = cls._employee("Bailey", "Balancer")
        for employee, skill in (
            (cls.alex, cls.python),
            (cls.bailey, cls.python),
            (cls.bailey, cls.data),
        ):
            EmployeeSkill.objects.create(
                employee=employee,
                skill=skill,
                level=4,
                years_experience=Decimal("4.0"),
            )

    @classmethod
    def _requirement(cls, skill, *, effort, quantity, mandatory):
        return ProjectSkillRequirement.objects.create(
            project=cls.project,
            skill=skill,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=mandatory,
            required_quantity=quantity,
            estimated_effort_hours=Decimal(effort),
        )

    @staticmethod
    def _employee(first_name, last_name):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Engineering",
            position="Engineer",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("6.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.viewer)
        self.generate_url = reverse(
            "frontend:project_recommendation_generate",
            args=[self.project.pk],
        )

    def _team_result(self):
        allocations = [
            {
                "employee": self.alex,
                "requirement": self.python_requirement,
                "skill": self.python,
                "hours": Decimal("4.25"),
            },
            {
                "employee": self.bailey,
                "requirement": self.python_requirement,
                "skill": self.python,
                "hours": Decimal("3.75"),
            },
            {
                "employee": self.bailey,
                "requirement": self.data_requirement,
                "skill": self.data,
                "hours": Decimal("4.50"),
            },
            {
                "employee": self.alex,
                "requirement": self.data_requirement,
                "skill": self.data,
                "hours": Decimal("0.00"),
            },
        ]
        capacities = [
            {
                "employee": self.bailey,
                "available_hours": Decimal("40.00"),
                "allocated_hours": Decimal("8.25"),
                "utilization_rate": 20.625,
            },
            {
                "employee": self.alex,
                "available_hours": Decimal("25.50"),
                "allocated_hours": Decimal("4.25"),
                "utilization_rate": 16.67,
            },
        ]
        coverage = [
            {
                "requirement": self.data_requirement,
                "skill": self.data,
                "required_quantity": 1,
                "covered_quantity": 1,
                "is_mandatory": True,
                "is_satisfied": True,
                "qualified_employees": [self.bailey],
            },
            {
                "requirement": self.optional_requirement,
                "skill": self.writing,
                "required_quantity": 1,
                "covered_quantity": 0,
                "is_mandatory": False,
                "is_satisfied": False,
                "qualified_employees": [],
            },
            {
                "requirement": self.python_requirement,
                "skill": self.python,
                "required_quantity": 1,
                "covered_quantity": 2,
                "is_mandatory": True,
                "is_satisfied": True,
                "qualified_employees": [self.alex, self.bailey],
            },
        ]
        return {
            "team": [self.alex, self.bailey],
            "team_size": 2,
            "coverage": coverage,
            "effort_solution": {
                "is_feasible": True,
                "reason": "The team can absorb all mandatory effort.",
                "minimum_participations": 3,
                "allocations": allocations,
                "employee_capacities": capacities,
            },
            "team_score": 89.5,
            "members": [],
            "metrics": {
                "team_size": 2,
                "total_available_hours": Decimal("65.50"),
                "total_allocated_hours": Decimal("12.50"),
                "remaining_capacity_hours": Decimal("53.00"),
                "team_utilization_rate": 19.08,
                "average_utilization": 18.65,
                "max_utilization": 20.625,
                "min_utilization": 16.67,
                "utilization_spread": 3.955,
            },
        }

    def _pipeline_result(self, team_result=None):
        team_result = team_result or self._team_result()
        recommendation = {
            "category": "compact_match",
            "label": "Best compact match",
            "reason": "Existing selection reason.",
            "result": team_result,
        }
        return {
            "feasible_teams": [team_result],
            "pareto_teams": [team_result],
            "recommendations": [recommendation],
            "comparisons": [{"not": "rendered in M6.3"}],
            "explanations": [{"not": "rendered in M6.3"}],
            "elapsed_seconds": 1.25,
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

    def _presented_evidence(self, team_result=None):
        pipeline_result = self._pipeline_result(team_result)
        cards = build_recommendation_strategy_cards(
            self.project,
            pipeline_result["recommendations"],
            self.viewer,
        )["cards"]
        return cards[0]["allocation_evidence"]

    def test_matrix_preserves_solver_order_objects_and_exact_cell_values(self):
        team_result = self._team_result()
        allocations = team_result["effort_solution"]["allocations"]
        capacities = team_result["effort_solution"]["employee_capacities"]
        evidence = self._presented_evidence(team_result)
        matrix = evidence["matrix"]

        self.assertEqual(matrix["state"], "available")
        self.assertEqual(
            tuple(column["requirement"].pk for column in matrix["columns"]),
            (self.python_requirement.pk, self.data_requirement.pk),
        )
        self.assertEqual(
            tuple(row["employee"].pk for row in matrix["rows"]),
            (self.bailey.pk, self.alex.pk),
        )
        self.assertIs(matrix["columns"][0]["service_first_allocation"], allocations[0])
        self.assertIs(matrix["columns"][1]["service_first_allocation"], allocations[2])
        self.assertIs(matrix["rows"][0]["service_capacity"], capacities[0])
        self.assertIs(matrix["rows"][1]["service_capacity"], capacities[1])
        self.assertEqual(
            tuple(cell["hours"] for cell in matrix["rows"][0]["cells"]),
            (Decimal("3.75"), Decimal("4.50")),
        )
        self.assertEqual(
            tuple(cell["hours"] for cell in matrix["rows"][1]["cells"]),
            (Decimal("4.25"), Decimal("0.00")),
        )
        self.assertIs(matrix["rows"][0]["cells"][0]["allocation"], allocations[1])
        self.assertIs(matrix["rows"][0]["cells"][1]["allocation"], allocations[2])
        self.assertEqual(
            matrix["columns"][0]["required_effort_hours"],
            self.python_requirement.estimated_effort_hours,
        )

    def test_capacity_and_coverage_preserve_backend_values_and_boundaries(self):
        team_result = self._team_result()
        capacities = team_result["effort_solution"]["employee_capacities"]
        coverage_items = team_result["coverage"]
        evidence = self._presented_evidence(team_result)

        capacity_rows = evidence["capacity"]["rows"]
        for service_capacity, row in zip(capacities, capacity_rows, strict=True):
            self.assertIs(row["service_capacity"], service_capacity)
            self.assertEqual(row["available_hours"], service_capacity["available_hours"])
            self.assertEqual(row["allocated_hours"], service_capacity["allocated_hours"])
            self.assertEqual(row["utilization_rate"], service_capacity["utilization_rate"])

        coverage_rows = evidence["coverage"]["rows"]
        self.assertEqual(
            tuple(row["requirement"].pk for row in coverage_rows),
            (
                self.data_requirement.pk,
                self.optional_requirement.pk,
                self.python_requirement.pk,
            ),
        )
        for service_coverage, row in zip(
            coverage_items,
            coverage_rows,
            strict=True,
        ):
            self.assertIs(row["service_coverage"], service_coverage)
            self.assertEqual(
                row["required_quantity"],
                service_coverage["required_quantity"],
            )
            self.assertEqual(
                row["covered_quantity"],
                service_coverage["covered_quantity"],
            )
            self.assertEqual(row["is_mandatory"], service_coverage["is_mandatory"])
            self.assertEqual(row["is_satisfied"], service_coverage["is_satisfied"])
        self.assertEqual(coverage_rows[0]["outcome_label"], "Mandatory coverage met")
        self.assertEqual(coverage_rows[1]["outcome_label"], "Optional coverage not met")
        self.assertFalse(coverage_rows[1]["has_matrix_column"])
        self.assertEqual(coverage_rows[1]["qualified_members"], ())
        self.assertTrue(coverage_rows[2]["has_matrix_column"])

    def test_result_renders_exact_hours_units_matrix_and_coverage_semantics(self):
        response = self._post_result()
        html = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        for value in (
            "4.25 h",
            "3.75 h",
            "4.50 h",
            "0.00 h",
            "40.00 h",
            "8.25 h",
            "20.6%",
            "25.50 h",
            "16.7%",
        ):
            self.assertContains(response, value)
        self.assertContains(response, "Required effort 8.00 h")
        self.assertContains(response, "Required effort 4.50 h")
        self.assertContains(response, "1 of 1 required")
        self.assertContains(response, "2 of 1 required")
        self.assertContains(response, "Mandatory coverage met")
        self.assertContains(response, "Optional coverage not met")
        self.assertContains(
            response,
            "optional requirement is not covered and does not determine "
            "whole-team feasibility",
        )
        self.assertContains(response, "Not returned separately")
        self.assertContains(response, "The interface does not infer this total.")
        self.assertContains(response, '<caption>Exact employee-to-mandatory-requirement hours returned by OR-Tools')
        self.assertContains(response, '<th scope="col">Team member</th>', html=True)
        self.assertContains(response, '<th scope="row">', count=8)
        self.assertEqual(
            html.count('class="recommendation-allocation-evidence"'),
            1,
        )
        self.assertLess(
            html.index('id="recommendation-summary-title"'),
            html.index('class="recommendation-strategy-grid"'),
        )
        self.assertLess(
            html.index('class="recommendation-strategy-grid"'),
            html.index('id="recommendation-details-title"'),
        )
        self.assertLess(
            html.index('id="recommendation-details-title"'),
            html.index('class="recommendation-allocation-evidence"'),
        )
        self.assertNotContains(response, "not rendered in M6.3")
        self.assertNotContains(response, "Create assignment")

    def test_missing_cell_is_explicit_and_not_presented_as_a_calculated_zero(self):
        team_result = self._team_result()
        team_result["effort_solution"]["allocations"].pop()
        evidence = self._presented_evidence(team_result)
        missing_cell = evidence["matrix"]["rows"][1]["cells"][1]

        self.assertFalse(missing_cell["has_returned_allocation"])
        self.assertIsNone(missing_cell["hours"])
        response = self._post_result(self._pipeline_result(team_result))
        self.assertContains(response, 'aria-label="No allocation row returned"')
        self.assertContains(
            response,
            "A dash means no allocation row was returned; it is not a "
            "frontend-calculated zero.",
        )

    def test_empty_unavailable_and_non_feasible_evidence_stay_distinct(self):
        missing_result = self._team_result()
        missing_result.pop("effort_solution")
        missing_result.pop("coverage")
        missing = self._presented_evidence(missing_result)
        self.assertEqual(missing["solver"]["state"], "unavailable")
        self.assertEqual(missing["matrix"]["state"], "unavailable")
        self.assertEqual(missing["capacity"]["state"], "unavailable")
        self.assertEqual(missing["coverage"]["state"], "unavailable")

        empty_result = self._team_result()
        empty_result["effort_solution"] = {
            "is_feasible": True,
            "reason": "No positive allocation rows were needed.",
            "allocations": [],
            "employee_capacities": [],
        }
        empty_result["coverage"] = []
        empty = self._presented_evidence(empty_result)
        self.assertEqual(empty["solver"]["state"], "feasible")
        self.assertEqual(empty["matrix"]["state"], "empty")
        self.assertEqual(empty["capacity"]["state"], "empty")
        self.assertEqual(empty["coverage"]["state"], "empty")

        non_feasible_result = self._team_result()
        non_feasible_result["effort_solution"] = {
            "is_feasible": False,
            "reason": "Mandatory skill coverage is not satisfied.",
            "allocations": [],
        }
        non_feasible_result["coverage"][0]["is_satisfied"] = False
        non_feasible_result["coverage"][0]["covered_quantity"] = 0
        response = self._post_result(self._pipeline_result(non_feasible_result))
        self.assertContains(response, "Mandatory effort allocation is not feasible")
        self.assertContains(response, "Mandatory skill coverage is not satisfied.")
        self.assertContains(response, "Mandatory coverage not met")
        self.assertContains(response, "No allocation rows returned")
        self.assertContains(response, "Capacity usage unavailable")

    def test_deleted_related_objects_remain_readable_without_stale_links(self):
        deleted_skill = Skill.objects.create(
            name="Deleted evidence skill",
            category="Engineering",
        )
        deleted_requirement = self._requirement(
            deleted_skill,
            effort="2.00",
            quantity=1,
            mandatory=True,
        )
        deleted_employee = self._employee("Deleted", "Evidence")
        employee_id = deleted_employee.pk
        deleted_requirement.delete()
        deleted_employee.delete()
        team_result = self._team_result()
        allocation = {
            "employee": deleted_employee,
            "requirement": deleted_requirement,
            "skill": deleted_skill,
            "hours": Decimal("2.00"),
        }
        team_result["team"] = [deleted_employee]
        team_result["team_size"] = 1
        team_result["effort_solution"]["allocations"] = [allocation]
        team_result["effort_solution"]["employee_capacities"] = [
            {
                "employee": deleted_employee,
                "available_hours": Decimal("8.00"),
                "allocated_hours": Decimal("2.00"),
                "utilization_rate": 25.0,
            }
        ]
        team_result["coverage"] = [
            {
                "requirement": deleted_requirement,
                "skill": deleted_skill,
                "required_quantity": 1,
                "covered_quantity": 1,
                "is_mandatory": True,
                "is_satisfied": True,
                "qualified_employees": [deleted_employee],
            }
        ]

        response = self._post_result(self._pipeline_result(team_result))
        evidence = response.context["run"]["strategies"]["cards"][0][
            "allocation_evidence"
        ]
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Deleted evidence skill — requirement record unavailable",
        )
        self.assertNotContains(response, f"/employees/{employee_id}/")
        self.assertIsNone(evidence["matrix"]["rows"][0]["profile_url"])
        self.assertIsNone(evidence["coverage"]["rows"][0]["requirements_url"])

    def test_source_and_request_boundaries_prevent_frontend_recalculation_or_mutation(self):
        presenter_functions = (
            recommendation_presenters._build_allocation_matrix,
            recommendation_presenters._build_capacity_evidence,
            recommendation_presenters._build_coverage_evidence,
            recommendation_presenters.build_recommendation_allocation_evidence,
        )
        called_names = set()
        for function in presenter_functions:
            parsed = ast.parse(inspect.getsource(function))
            called_names.update(
                node.func.id
                for node in ast.walk(parsed)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            )
        for forbidden_call in (
            "sum",
            "len",
            "round",
            "min",
            "max",
            "calculate_team_metrics",
            "calculate_team_score",
            "evaluate_team_coverage",
            "employee_can_cover_requirement",
            "solve_team_effort_allocation",
        ):
            with self.subTest(forbidden_call=forbidden_call):
                self.assertNotIn(forbidden_call, called_names)

        frontend_root = Path(__file__).resolve().parents[1]
        template_source = (
            frontend_root
            / "templates/frontend/recommendations/_allocation_evidence.html"
        ).read_text(encoding="utf-8")
        javascript_source = (
            frontend_root / "static/frontend/js/app.js"
        ).read_text(encoding="utf-8")
        self.assertNotIn("{% widthratio", template_source)
        self.assertNotIn("|add:", template_source)
        for value_name in (
            "allocated_hours",
            "available_hours",
            "utilization_rate",
            "covered_quantity",
            "required_quantity",
        ):
            self.assertNotIn(value_name, javascript_source)

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

    def test_query_count_and_warm_allocation_rendering_overhead_remain_fixed(self):
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
            "\nM6.3 allocation-evidence rendering baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client POSTs, "
            "1 strategy / 2 employees / 2 allocation columns / 3 coverage "
            "rows, expensive pipeline mocked):\n"
            f"  queries={self.EXPECTED_RESULT_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"response={max(response_sizes)} bytes"
        )
