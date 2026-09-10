"""M6.8 performance, accessibility, and boundary hardening.

Measures the implemented Milestone 6 behavior and proves it stays fixed:
per-stage pipeline profiling on realistic fixtures, concurrent and
repeated submissions, deterministic results, large allocation tables with
fixed query budgets, stale detection across long-running requests,
keyboard/accessibility structure, and source audits. No new feature or
infrastructure is introduced.
"""

import threading
import time
from datetime import date
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

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
    find_all_feasible_teams,
    find_pareto_teams,
    select_recommended_teams,
)
from frontend.roles import MANAGER_PLANNER_GROUP, sync_role_permissions


class _StructureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.headings = []
        self.tables = []
        self._table_stack = []
        self.ids = []
        self.references = []
        self.onclick = 0
        self.positive_tabindex = 0
        self.forms = 0
        self.labeled_controls = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.headings.append(int(tag[1]))
        if tag == "table":
            self._table_stack.append(
                {"caption": False, "col_scope": False, "row_scope": False}
            )
        if tag == "caption" and self._table_stack:
            self._table_stack[-1]["caption"] = True
        if tag == "th" and self._table_stack:
            scope = attributes.get("scope")
            if scope == "col":
                self._table_stack[-1]["col_scope"] = True
            if scope == "row":
                self._table_stack[-1]["row_scope"] = True
        if "id" in attributes:
            self.ids.append(attributes["id"])
        for key in ("aria-labelledby", "aria-describedby"):
            if key in attributes:
                self.references.extend(attributes[key].split())
        if "onclick" in attributes:
            self.onclick += 1
        tabindex = attributes.get("tabindex")
        if tabindex is not None:
            try:
                if int(tabindex) > 0:
                    self.positive_tabindex += 1
            except ValueError:
                pass
        if tag == "form":
            self.forms += 1
        if tag in ("input", "select", "textarea") and (
            "aria-label" in attributes or "aria-labelledby" in attributes
        ):
            self.labeled_controls += 1

    def handle_endtag(self, tag):
        if tag == "table" and self._table_stack:
            self.tables.append(self._table_stack.pop())


def _parse(html):
    parser = _StructureParser()
    parser.feed(html)
    return parser


class RecommendationProfilingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.manager = get_user_model().objects.create_user(
            username="m68-profile-manager"
        )
        cls.manager.groups.add(
            Group.objects.get(name=MANAGER_PLANNER_GROUP)
        )
        cls.python = Skill.objects.create(
            name="Python", category="Engineering"
        )
        cls.project = Project.objects.create(
            name="M68 profiling project",
            description="Per-stage pipeline profiling fixture.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            estimated_hours=Decimal("8.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        ProjectSkillRequirement.objects.create(
            project=cls.project,
            skill=cls.python,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=Decimal("8.00"),
        )
        for index in range(4):
            employee = Employee.objects.create(
                first_name=f"Profile{index}",
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
                skill=cls.python,
                level=4,
                years_experience=Decimal("3.0"),
            )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.manager)

    def _stages(self, project):
        measured = {}
        started = time.perf_counter()
        feasible_teams = find_all_feasible_teams(project)
        measured["feasible_team_enumeration"] = (
            time.perf_counter() - started
        )
        started = time.perf_counter()
        pareto_teams = find_pareto_teams(feasible_teams)
        measured["pareto_filtering"] = time.perf_counter() - started
        started = time.perf_counter()
        recommendations = select_recommended_teams(pareto_teams)
        measured["recommendation_selection"] = time.perf_counter() - started
        started = time.perf_counter()
        comparisons = compare_recommendations(recommendations)
        measured["adjacent_comparison"] = time.perf_counter() - started
        started = time.perf_counter()
        explanations = build_recommendation_explanations(
            recommendations, comparisons
        )
        measured["deterministic_explanation"] = time.perf_counter() - started
        return measured, {
            "feasible_teams": feasible_teams,
            "pareto_teams": pareto_teams,
            "recommendations": recommendations,
            "comparisons": comparisons,
            "explanations": explanations,
        }

    def _signature(self, result):
        return [
            (
                item["category"],
                item["label"],
                tuple(
                    member.employee_id for member in item["result"]["team"]
                ),
                item["result"]["team_score"],
            )
            for item in result["recommendations"]
        ]

    def test_per_stage_profile_and_deterministic_repeat(self):
        measured, first = self._stages(self.project)
        _, second = self._stages(self.project)
        self.assertGreater(len(first["feasible_teams"]), 0)
        self.assertGreater(len(first["pareto_teams"]), 0)
        self.assertLessEqual(len(first["recommendations"]), 3)
        self.assertEqual(
            len(first["comparisons"]),
            max(0, len(first["recommendations"]) - 1),
        )
        self.assertEqual(
            len(first["explanations"]), len(first["recommendations"])
        )
        self.assertEqual(self._signature(first), self._signature(second))
        total = sum(measured.values())
        print(
            "\nM6.8 pipeline profile (real services, 4 employees, "
            "1 mandatory requirement):\n"
            + "\n".join(
                f"  {stage}={duration * 1000:.3f} ms"
                for stage, duration in measured.items()
            )
            + f"\n  total={total * 1000:.3f} ms, "
            f"feasible={len(first['feasible_teams'])}, "
            f"pareto={len(first['pareto_teams'])}, "
            f"recommendations={len(first['recommendations'])}"
        )
        self.assertEqual(
            (
                Project.objects.count(),
                ProjectSkillRequirement.objects.count(),
                Assignment.objects.count(),
                AssignmentSkill.objects.count(),
            ),
            (1, 1, 0, 0),
        )

class RecommendationRealJourneyTests(TestCase):
    """One tiny real-solver journey; the 4-employee class above profiles."""

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.manager = get_user_model().objects.create_user(
            username="m68-journey-manager"
        )
        cls.manager.groups.add(
            Group.objects.get(name=MANAGER_PLANNER_GROUP)
        )
        cls.python = Skill.objects.create(
            name="Python", category="Engineering"
        )
        cls.project = Project.objects.create(
            name="M68 journey project",
            description="Tiny real-solver journey fixture.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            estimated_hours=Decimal("8.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        ProjectSkillRequirement.objects.create(
            project=cls.project,
            skill=cls.python,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=Decimal("8.00"),
        )
        for index in range(2):
            employee = Employee.objects.create(
                first_name=f"Journey{index}",
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
                skill=cls.python,
                level=4,
                years_experience=Decimal("3.0"),
            )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.manager)

    def test_real_generation_review_and_confirm(self):
        self.assertEqual(Assignment.objects.count(), 0)
        planning_url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )
        generate_url = reverse(
            "frontend:project_recommendation_generate",
            args=[self.project.project_id],
        )
        planning = self.client.get(planning_url)
        token = planning.context["recommendation_generation"]["form"][
            "submission_token"
        ].value()
        started = time.perf_counter()
        generated = self.client.post(
            generate_url, {"submission_token": token}
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(generated.context["run"]["state"], "completed")
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
        self.assertEqual(review.status_code, 200)
        self.assertContains(review, "Back to recommendation results")
        confirm_token = review.context["review"]["form"][
            "submission_token"
        ].value()
        saved = self.client.post(
            confirm_url, {"submission_token": confirm_token, "run_id": run_id}
        )
        self.assertEqual(saved.status_code, 302)
        self.assertEqual(Assignment.objects.count(), 1)
        self.assertGreaterEqual(AssignmentSkill.objects.count(), 1)
        print(
            "\nM6.8 real end-to-end baseline (generate plus confirm, "
            "real solver, 2 employees):\n"
            f"  generation_response={elapsed_ms:.3f} ms, "
            f"assignments={Assignment.objects.count()}, "
            f"coverage={AssignmentSkill.objects.count()}"
        )


class RecommendationConcurrencyTests(TransactionTestCase):
    """Threads need real commits; TestCase locks stay in one thread."""

    def setUp(self):
        cache.clear()
        sync_role_permissions()
        self.manager = get_user_model().objects.create_user(
            username="m68-concurrency-manager"
        )
        self.manager.groups.add(
            Group.objects.get(name=MANAGER_PLANNER_GROUP)
        )
        self.python = Skill.objects.create(
            name="Python", category="Engineering"
        )
        self.project = Project.objects.create(
            name="M68 concurrency project",
            description="Concurrent submission fixture.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            estimated_hours=Decimal("8.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        ProjectSkillRequirement.objects.create(
            project=self.project,
            skill=self.python,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=Decimal("8.00"),
        )
        employee = Employee.objects.create(
            first_name="Concurrent",
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
            skill=self.python,
            level=4,
            years_experience=Decimal("3.0"),
        )
        self.client.force_login(self.manager)
        self.generate_url = reverse(
            "frontend:project_recommendation_generate",
            args=[self.project.project_id],
        )

    def _token(self, client):
        planning = client.get(
            reverse(
                "frontend:project_planning",
                args=[self.project.project_id],
            )
        )
        return planning.context["recommendation_generation"]["form"][
            "submission_token"
        ].value()

    def test_parallel_same_token_yields_single_run(self):
        client_a = Client()
        client_a.force_login(self.manager)
        client_b = Client()
        client_b.force_login(self.manager)
        token = self._token(self.client)
        barrier = threading.Barrier(2)
        outcomes = []

        def _post(client):
            barrier.wait()
            with patch(
                "frontend.views.recommendations."
                "run_recommendation_pipeline",
                return_value=self._small_result(),
            ):
                outcomes.append(
                    client.post(
                        self.generate_url, {"submission_token": token}
                    ).status_code
                )

        threads = [
            threading.Thread(target=_post, args=(client_a,)),
            threading.Thread(target=_post, args=(client_b,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(outcomes), [200, 409])

    def test_parallel_fresh_tokens_agree_deterministically(self):
        clients = []
        tokens = []
        for _ in range(2):
            client = Client()
            client.force_login(self.manager)
            clients.append(client)
            tokens.append(self._token(client))
        barrier = threading.Barrier(2)
        outcomes = []

        def _post(client, token):
            barrier.wait()
            with patch(
                "frontend.views.recommendations."
                "run_recommendation_pipeline",
                return_value=self._small_result(),
            ):
                response = client.post(
                    self.generate_url, {"submission_token": token}
                )
            outcomes.append(
                (
                    response.status_code,
                    response.context["run"]["recommendation_count"],
                    tuple(
                        card["label"]
                        for card in response.context["run"]["strategies"][
                            "cards"
                        ]
                    ),
                )
            )

        threads = [
            threading.Thread(target=_post, args=(client, token))
            for client, token in zip(clients, tokens)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(
            [outcome[0] for outcome in outcomes], [200, 200]
        )
        self.assertEqual(outcomes[0][1:], outcomes[1][1:])

    def _small_result(self):
        from decimal import Decimal as _Decimal

        employee = Employee.objects.get(first_name="Concurrent")
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
                    "total_available_hours": _Decimal("32.00"),
                    "total_allocated_hours": _Decimal("8.00"),
                    "remaining_capacity_hours": _Decimal("24.00"),
                    "max_utilization": 25.0,
                    "utilization_spread": 0.0,
                },
            },
        }
        return {
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


class RecommendationScaleAndStaleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.manager = get_user_model().objects.create_user(
            username="m68-scale-manager"
        )
        cls.manager.groups.add(
            Group.objects.get(name=MANAGER_PLANNER_GROUP)
        )
        cls.skills = [
            Skill.objects.create(
                name=f"Scale skill {index}", category="Engineering"
            )
            for index in range(6)
        ]
        cls.project = Project.objects.create(
            name="M68 scale project",
            description="Large allocation table fixture.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            estimated_hours=Decimal("48.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        cls.requirements = [
            ProjectSkillRequirement.objects.create(
                project=cls.project,
                skill=skill,
                required_level=2,
                priority=ProjectSkillRequirement.Priority.MEDIUM,
                is_mandatory=True,
                required_quantity=1,
                estimated_effort_hours=Decimal("8.00"),
            )
            for skill in cls.skills
        ]
        cls.employees = []
        for index in range(8):
            employee = Employee.objects.create(
                first_name=f"Scale{index}",
                last_name="Engineer",
                department="Engineering",
                position="Engineer",
                hire_date=date(2020, 1, 6),
                experience_years=Decimal("5.0"),
                capacity_hours_week=Decimal("40.00"),
                status=Employee.Status.ACTIVE,
            )
            for skill in cls.skills:
                EmployeeSkill.objects.create(
                    employee=employee,
                    skill=skill,
                    level=3,
                    years_experience=Decimal("2.0"),
                )
            cls.employees.append(employee)

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

    def _large_result(self, *, strategies=3):
        from decimal import Decimal as _Decimal

        definitions = (
            ("compact_match", "Best compact match"),
            ("balanced", "Best balanced alternative"),
            ("capacity", "Best capacity alternative"),
        )
        recommendations = []
        for index in range(strategies):
            team = self.employees[index : index + 4]
            allocations = [
                {
                    "employee": employee,
                    "requirement": requirement,
                    "skill": requirement.skill,
                    "hours": _Decimal("2.00"),
                }
                for employee in team
                for requirement in self.requirements
            ]
            result = {
                "team": team,
                "team_size": len(team),
                "team_score": 90.0 - index,
                "metrics": {
                    "team_size": len(team),
                    "total_available_hours": _Decimal("160.00"),
                    "total_allocated_hours": _Decimal("48.00"),
                    "remaining_capacity_hours": _Decimal("112.00"),
                    "max_utilization": 30.0,
                    "utilization_spread": 2.5,
                },
                "effort_solution": {
                    "is_feasible": True,
                    "employee_capacities": [
                        {
                            "employee": employee,
                            "available_hours": _Decimal("40.00"),
                            "allocated_hours": _Decimal("12.00"),
                            "utilization_rate": 30.0,
                        }
                        for employee in team
                    ],
                    "allocations": allocations,
                },
                "coverage": [
                    {
                        "requirement": requirement,
                        "skill": requirement.skill,
                        "required_quantity": 1,
                        "covered_quantity": 1,
                        "is_mandatory": True,
                        "is_satisfied": True,
                        "qualified_employees": list(team),
                    }
                    for requirement in self.requirements
                ],
            }
            recommendations.append(
                {
                    "category": definitions[index][0],
                    "label": definitions[index][1],
                    "reason": "Existing service-owned selection reason.",
                    "result": result,
                }
            )
        return {
            "feasible_teams": [item["result"] for item in recommendations],
            "pareto_teams": [item["result"] for item in recommendations],
            "recommendations": recommendations,
            "comparisons": [],
            "explanations": [
                {
                    "category": item["category"],
                    "label": item["label"],
                    "team": [str(member) for member in item["result"]["team"]],
                    "strengths": ["Existing deterministic strength."],
                    "tradeoffs": ["Existing deterministic trade-off."],
                }
                for item in recommendations
            ],
            "elapsed_seconds": 1.5,
        }

    def _post(self, pipeline_result):
        planning = self.client.get(self.planning_url)
        token = planning.context["recommendation_generation"]["form"][
            "submission_token"
        ].value()
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=pipeline_result,
        ):
            with CaptureQueriesContext(connection) as queries:
                response = self.client.post(
                    self.generate_url, {"submission_token": token}
                )
        return response, len(queries)

    def test_large_tables_keep_fixed_query_budgets(self):
        small, small_queries = self._post(self._large_result(strategies=1))
        large, large_queries = self._post(self._large_result(strategies=3))
        self.assertEqual(small.status_code, 200)
        self.assertEqual(large.status_code, 200)
        self.assertEqual(small_queries, large_queries)
        self.assertEqual(
            large.context["run"]["recommendation_count"], 3
        )
        html = large.content.decode("utf-8")
        self.assertIn("data-table-shell", html)
        print(
            "\nM6.8 large-table baseline (mocked pipeline, 3 strategies, "
            "4 members each, 6 allocation columns, 6 coverage rows):\n"
            f"  result_post_queries={large_queries}, "
            f"response={len(large.content)} bytes"
        )

    def test_mid_run_change_is_stale_without_save(self):
        before = (
            Project.objects.count(),
            Assignment.objects.count(),
            AssignmentSkill.objects.count(),
        )
        valid_result = self._large_result(strategies=1)

        def _changing_pipeline(project):
            Assignment.objects.create(
                employee=self.employees[0],
                project=self.project,
                start_date=self.project.start_date,
                end_date=self.project.end_date,
                allocation_percentage=10,
                role_on_project="Mid-run change",
                status=Assignment.Status.PLANNED,
            )
            return valid_result

        planning = self.client.get(self.planning_url)
        token = planning.context["recommendation_generation"]["form"][
            "submission_token"
        ].value()
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            side_effect=_changing_pipeline,
        ):
            response = self.client.post(
                self.generate_url, {"submission_token": token}
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.context["run"]["state"], "stale")
        Assignment.objects.filter(role_on_project="Mid-run change").delete()
        self.assertEqual(
            (Project.objects.count(), AssignmentSkill.objects.count()),
            (before[0], before[2]),
        )


class RecommendationAccessibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.manager = get_user_model().objects.create_user(
            username="m68-access-manager"
        )
        cls.manager.groups.add(
            Group.objects.get(name=MANAGER_PLANNER_GROUP)
        )
        cls.python = Skill.objects.create(
            name="Python", category="Engineering"
        )
        cls.project = Project.objects.create(
            name="M68 access project",
            description="Accessibility fixture.",
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
            first_name="Access",
            last_name="Engineer",
            department="Engineering",
            position="Engineer",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("5.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )
        EmployeeSkill.objects.create(
            employee=cls.employee,
            skill=cls.python,
            level=4,
            years_experience=Decimal("3.0"),
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

    def _result(self):
        from decimal import Decimal as _Decimal

        recommendation = {
            "category": "compact_match",
            "label": "Best compact match",
            "reason": "Existing service-owned selection reason.",
            "result": {
                "team": [self.employee],
                "team_size": 1,
                "team_score": 88.25,
                "metrics": {
                    "team_size": 1,
                    "total_available_hours": _Decimal("32.00"),
                    "total_allocated_hours": _Decimal("8.00"),
                    "remaining_capacity_hours": _Decimal("24.00"),
                    "max_utilization": 25.0,
                    "utilization_spread": 0.0,
                },
                "effort_solution": {
                    "is_feasible": True,
                    "employee_capacities": [
                        {
                            "employee": self.employee,
                            "available_hours": _Decimal("32.00"),
                            "allocated_hours": _Decimal("8.00"),
                            "utilization_rate": 25.0,
                        }
                    ],
                    "allocations": [
                        {
                            "employee": self.employee,
                            "requirement": self.requirement,
                            "skill": self.python,
                            "hours": _Decimal("8.00"),
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
                        "qualified_employees": [self.employee],
                    }
                ],
            },
        }
        return {
            "feasible_teams": [recommendation["result"]],
            "pareto_teams": [recommendation["result"]],
            "recommendations": [recommendation],
            "comparisons": [],
            "explanations": [
                {
                    "category": "compact_match",
                    "label": "Best compact match",
                    "team": [str(self.employee)],
                    "strengths": ["Existing deterministic strength."],
                    "tradeoffs": ["Existing deterministic trade-off."],
                }
            ],
            "elapsed_seconds": 0.25,
        }

    def _pages(self):
        planning = self.client.get(self.planning_url)
        token = planning.context["recommendation_generation"]["form"][
            "submission_token"
        ].value()
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=self._result(),
        ):
            generated = self.client.post(
                self.generate_url, {"submission_token": token}
            )
        run_id = generated.context["recommendation_run_id"]
        confirm_url = (
            reverse(
                "frontend:project_recommendation_confirm",
                args=[self.project.project_id, "compact_match"],
            )
            + f"?run={run_id}"
        )
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._result(),
        ):
            review = self.client.get(confirm_url)
        result_url = reverse(
            "frontend:project_recommendation_result",
            args=[self.project.project_id, run_id],
        )
        reread = self.client.get(result_url)
        return {
            "planning": planning.content.decode("utf-8"),
            "result": generated.content.decode("utf-8"),
            "review": review.content.decode("utf-8"),
            "cached_result": reread.content.decode("utf-8"),
        }

    def test_heading_table_form_and_navigation_structure(self):
        pages = self._pages()
        for name, html in pages.items():
            with self.subTest(page=name):
                parsed = _parse(html)
                self.assertEqual(
                    parsed.headings.count(1),
                    1,
                    f"{name} must render exactly one h1",
                )
                for previous, current in zip(
                    parsed.headings, parsed.headings[1:]
                ):
                    self.assertLessEqual(
                        current,
                        previous + 1,
                        f"{name} heading level jumps from h{previous} "
                        f"to h{current}",
                    )
                self.assertGreater(len(parsed.tables), 0)
                for table in parsed.tables:
                    self.assertTrue(table["caption"])
                    self.assertTrue(table["col_scope"])
                self.assertEqual(parsed.onclick, 0)
                self.assertEqual(parsed.positive_tabindex, 0)
                missing = set(parsed.references) - set(parsed.ids)
                self.assertEqual(missing, set())
                self.assertIn('href="#main-content"', html)
                self.assertIn('id="main-content"', html)
        self.assertIn('aria-live="polite"', pages["planning"])
        self.assertIn("data-loading-form", pages["review"])
        self.assertIn("Back to recommendation results", pages["review"])
        self.assertIn("Strengths", pages["result"])
        self.assertIn("Trade-offs", pages["result"])
        self.assertIn("Team score", pages["result"])
        for banner in (
            "Optional Gemini summaries are off",
            "Optional Gemini summaries unavailable",
            "Some optional Gemini summaries unavailable",
        ):
            if banner in pages["result"]:
                break
        else:
            self.fail("deterministic fallback wording is missing")

    def test_stylesheets_cover_focus_motion_and_overflow(self):
        theme = (
            Path(__file__).resolve().parents[1]
            / "static/frontend/css/theme.css"
        ).read_text(encoding="utf-8")
        self.assertIn(":focus-visible", theme)
        self.assertIn("@media (prefers-reduced-motion: reduce)", theme)
        self.assertIn("overflow-x", theme)
        self.assertIn(".data-table-shell", theme)
        self.assertIn(".skip-link:focus", theme)


class RecommendationBoundaryAuditTests(TestCase):
    def test_views_use_orchestration_boundary_without_service_calls(self):
        frontend_root = Path(__file__).resolve().parents[1]
        for view_name in (
            "views/recommendations.py",
            "views/assignment_handoff.py",
        ):
            source = (frontend_root / view_name).read_text(encoding="utf-8")
            self.assertIn("run_recommendation_pipeline(", source)
            for service_call in (
                "find_all_feasible_teams(",
                "find_pareto_teams(",
                "select_recommended_teams(",
                "compare_recommendations(",
                "build_recommendation_explanations(",
                "solve_team_effort_allocation(",
            ):
                with self.subTest(view=view_name, call=service_call):
                    self.assertNotIn(service_call, source)
            self.assertNotIn("core.services.optimization", source)

    def test_frontend_has_no_calculation_attendance_or_solver_copies(self):
        frontend_root = Path(__file__).resolve().parents[1]
        application_sources = (
            frontend_root / "orchestration/recommendations.py",
            frontend_root / "orchestration/assignment_handoff.py",
            frontend_root / "recommendation_execution.py",
            frontend_root / "assignment_handoff.py",
            frontend_root / "recommendation_runs.py",
            frontend_root / "forms/recommendations.py",
            frontend_root / "forms/assignment_handoff.py",
            frontend_root / "presenters/recommendations.py",
            frontend_root / "presenters/assignment_handoff.py",
            frontend_root / "presenters/planning.py",
            frontend_root / "selectors/recommendations.py",
            frontend_root / "views/recommendations.py",
            frontend_root / "views/assignment_handoff.py",
            frontend_root / "views/planning.py",
            frontend_root / "templates/frontend/planning/workspace.html",
            frontend_root / "templates/frontend/recommendations/result.html",
            frontend_root / "templates/frontend/recommendations/confirm.html",
            frontend_root / "static/frontend/js/app.js",
        )
        combined = "\n".join(
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
                self.assertNotIn(forbidden, combined)

    def test_gemini_stays_optional_and_outside_decisions(self):
        frontend_root = Path(__file__).resolve().parents[1]
        orchestrator = (
            frontend_root / "orchestration/recommendations.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("gemini", orchestrator.lower())
        self.assertNotIn("generate_manager_summar", orchestrator.lower())
        handoff_orchestrator = (
            frontend_root / "orchestration/assignment_handoff.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("gemini", handoff_orchestrator.lower())
        self.assertNotIn("genai", handoff_orchestrator.lower())

    def test_handoff_save_path_keeps_validation_and_atomicity(self):
        frontend_root = Path(__file__).resolve().parents[1]
        view_source = (
            frontend_root / "views/assignment_handoff.py"
        ).read_text(encoding="utf-8")
        self.assertIn("full_clean", view_source)
        self.assertIn("transaction.atomic", view_source)
        self.assertIn("claim_handoff_submission", view_source)
        confirm_template = (
            frontend_root / "templates/frontend/recommendations/confirm.html"
        ).read_text(encoding="utf-8")
        self.assertIn("csrf_token", confirm_template)
        from django.conf import settings as django_settings

        self.assertIn(
            "django.middleware.csrf.CsrfViewMiddleware",
            django_settings.MIDDLEWARE,
        )

    def test_milestone_routes_stay_resolvable(self):
        project_id = 1
        for name, args in (
            ("frontend:project_list", ()),
            ("frontend:project_planning", (project_id,)),
            ("frontend:project_recommendation_generate", (project_id,)),
            ("frontend:project_assignment_create", (project_id,)),
            ("frontend:project_requirement_create", (project_id,)),
        ):
            with self.subTest(route=name):
                self.assertTrue(reverse(name, args=args))
                self.assertEqual(resolve(reverse(name, args=args)).view_name, name)

    def test_no_new_infrastructure_without_measurement(self):
        frontend_root = Path(__file__).resolve().parents[1]
        combined = "\n".join(
            (frontend_root / path).read_text(encoding="utf-8").lower()
            for path in (
                "views/recommendations.py",
                "views/assignment_handoff.py",
                "orchestration/recommendations.py",
            )
        )
        for infrastructure in (
            "celery",
            "background_task",
            "threadpool",
            "asyncio",
        ):
            with self.subTest(infrastructure=infrastructure):
                self.assertNotIn(infrastructure, combined)
