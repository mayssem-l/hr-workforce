from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models import Employee, EmployeeSkill, Project, ProjectSkillRequirement, Skill
from core.services.matching import (
    calculate_employee_project_match,
    rank_employees_for_project,
)
from core.services.optimization import (
    build_optimization_context,
    build_recommendation_explanations,
    compare_recommendations,
    find_all_feasible_teams,
    find_pareto_teams,
    select_recommended_teams,
)
from core.services.recommendation_preflight import (
    MANDATORY_EFFORT_BLOCKER_CODE,
    get_recommendation_preflight,
)


class RecommendationServiceContractTests(TestCase):
    """Protect the data shapes consumed by the planned frontend."""

    def setUp(self):
        self.project = Project.objects.create(
            name="Contract project",
            description="Small deterministic recommendation fixture.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            estimated_hours=Decimal("40.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        self.skill = Skill.objects.create(name="Python", category="Engineering")
        self.requirement = ProjectSkillRequirement.objects.create(
            project=self.project,
            skill=self.skill,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=Decimal("40.00"),
        )

        self.qualified_employees = [
            self._create_employee("Ada", "Alpha", Decimal("7.0")),
            self._create_employee("Bea", "Beta", Decimal("5.0")),
            self._create_employee("Cyd", "Gamma", Decimal("3.0")),
        ]
        for employee in self.qualified_employees:
            EmployeeSkill.objects.create(
                employee=employee,
                skill=self.skill,
                level=3,
                years_experience=employee.experience_years,
            )

        self.inactive_employee = self._create_employee(
            "Inez",
            "Inactive",
            Decimal("10.0"),
            status=Employee.Status.INACTIVE,
        )
        EmployeeSkill.objects.create(
            employee=self.inactive_employee,
            skill=self.skill,
            level=5,
            years_experience=Decimal("10.0"),
        )
        self.unqualified_employee = self._create_employee(
            "Uma",
            "Unqualified",
            Decimal("9.0"),
        )

    def _create_employee(
        self,
        first_name,
        last_name,
        experience_years,
        status=Employee.Status.ACTIVE,
    ):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Engineering",
            position="Developer",
            hire_date=date(2020, 1, 1),
            experience_years=experience_years,
            capacity_hours_week=Decimal("40.00"),
            status=status,
        )

    def test_matching_contract_returns_components_and_ranked_eligible_employees(self):
        match = calculate_employee_project_match(
            self.qualified_employees[0],
            self.project,
        )

        self.assertEqual(
            set(match),
            {
                "employee",
                "skill_score",
                "workload_score",
                "leave_score",
                "experience_score",
                "final_score",
            },
        )
        self.assertIs(match["employee"], self.qualified_employees[0])
        self.assertEqual(match["skill_score"], 90)
        self.assertEqual(match["workload_score"], 100)
        self.assertEqual(match["leave_score"], 100.0)
        self.assertEqual(match["experience_score"], 70.0)
        self.assertEqual(match["final_score"], 91.5)
        self.assertIsNone(
            calculate_employee_project_match(self.inactive_employee, self.project),
        )
        self.assertIsNone(
            calculate_employee_project_match(self.unqualified_employee, self.project),
        )

        ranked = rank_employees_for_project(self.project)

        self.assertEqual(
            [result["employee"] for result in ranked],
            self.qualified_employees,
        )
        self.assertEqual(
            [result["final_score"] for result in ranked],
            [91.5, 89.5, 87.5],
        )
        self.assertTrue(
            all(set(result) == set(match) for result in ranked),
        )

    def test_deterministic_recommendation_pipeline_contract(self):
        self.assertEqual(
            get_recommendation_preflight(self.project),
            {
                "can_generate_recommendations": True,
                "blockers": [],
            },
        )

        feasible_teams = find_all_feasible_teams(self.project)
        pareto_teams = find_pareto_teams(feasible_teams)
        recommendations = select_recommended_teams(pareto_teams)
        comparisons = compare_recommendations(recommendations)
        explanations = build_recommendation_explanations(
            recommendations,
            comparisons,
        )

        self.assertEqual(len(feasible_teams), 7)
        for result in feasible_teams:
            self.assertEqual(
                set(result),
                {
                    "team",
                    "team_size",
                    "coverage",
                    "effort_solution",
                    "team_score",
                    "members",
                    "metrics",
                },
            )
            self.assertEqual(result["team_size"], len(result["team"]))
            self.assertEqual(len(result["members"]), result["team_size"])
            self.assertEqual(
                set(result["members"][0]),
                {
                    "employee",
                    "skill_score",
                    "workload_score",
                    "leave_score",
                    "experience_score",
                    "final_score",
                },
            )

            self.assertEqual(len(result["coverage"]), 1)
            self.assertEqual(
                set(result["coverage"][0]),
                {
                    "requirement",
                    "skill",
                    "required_quantity",
                    "covered_quantity",
                    "is_mandatory",
                    "is_satisfied",
                    "qualified_employees",
                },
            )
            self.assertTrue(result["coverage"][0]["is_satisfied"])

            effort_solution = result["effort_solution"]
            self.assertEqual(
                set(effort_solution),
                {
                    "is_feasible",
                    "reason",
                    "minimum_participations",
                    "allocations",
                    "employee_capacities",
                },
            )
            self.assertTrue(effort_solution["is_feasible"])
            self.assertEqual(
                sum(
                    allocation["hours"]
                    for allocation in effort_solution["allocations"]
                ),
                Decimal("40.00"),
            )
            self.assertTrue(
                all(
                    set(allocation)
                    == {"employee", "requirement", "skill", "hours"}
                    for allocation in effort_solution["allocations"]
                ),
            )
            self.assertTrue(
                all(
                    set(capacity)
                    == {
                        "employee",
                        "available_hours",
                        "allocated_hours",
                        "utilization_rate",
                    }
                    for capacity in effort_solution["employee_capacities"]
                ),
            )

            self.assertEqual(
                set(result["metrics"]),
                {
                    "team_size",
                    "total_available_hours",
                    "total_allocated_hours",
                    "remaining_capacity_hours",
                    "team_utilization_rate",
                    "average_utilization",
                    "max_utilization",
                    "min_utilization",
                    "utilization_spread",
                },
            )
            self.assertEqual(result["metrics"]["team_size"], result["team_size"])
            self.assertEqual(
                result["metrics"]["total_allocated_hours"],
                Decimal("40.00"),
            )

        self.assertEqual(len(pareto_teams), 3)
        self.assertEqual({result["team_size"] for result in pareto_teams}, {1, 2, 3})

        self.assertEqual(
            [recommendation["category"] for recommendation in recommendations],
            ["compact_match", "balanced", "capacity"],
        )
        self.assertTrue(
            all(
                set(recommendation) == {"category", "label", "reason", "result"}
                for recommendation in recommendations
            ),
        )

        self.assertEqual(len(comparisons), 2)
        self.assertTrue(
            all(
                set(comparison)
                == {
                    "from_label",
                    "to_label",
                    "team_size_change",
                    "team_score_change",
                    "remaining_capacity_change",
                    "max_utilization_change",
                    "utilization_spread_change",
                }
                for comparison in comparisons
            ),
        )

        self.assertEqual(len(explanations), 3)
        self.assertEqual(
            [explanation["category"] for explanation in explanations],
            ["compact_match", "balanced", "capacity"],
        )
        self.assertTrue(
            all(
                set(explanation)
                == {"category", "label", "team", "strengths", "tradeoffs"}
                for explanation in explanations
            ),
        )
        self.assertTrue(all(explanation["strengths"] for explanation in explanations))

        explanation_text = " ".join(
            message
            for explanation in explanations
            for message in explanation["strengths"] + explanation["tradeoffs"]
        )
        self.assertIn("employé", explanation_text)
        self.assertNotRegex(explanation_text, r"Ã|Â|â€|�")

    def test_preflight_blocks_missing_or_zero_mandatory_effort_before_team_search(self):
        secondary_skill = Skill.objects.create(
            name="Django",
            category="Engineering",
        )
        invalid_requirement = ProjectSkillRequirement.objects.create(
            project=self.project,
            skill=secondary_skill,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=None,
        )
        for employee in self.qualified_employees:
            EmployeeSkill.objects.create(
                employee=employee,
                skill=secondary_skill,
                level=3,
                years_experience=employee.experience_years,
            )

        for effort in (None, Decimal("0.00")):
            with self.subTest(effort=effort):
                invalid_requirement.estimated_effort_hours = effort
                invalid_requirement.save(update_fields=["estimated_effort_hours"])

                preflight = get_recommendation_preflight(self.project)

                self.assertFalse(preflight["can_generate_recommendations"])
                self.assertEqual(len(preflight["blockers"]), 1)
                blocker = preflight["blockers"][0]
                self.assertEqual(
                    set(blocker),
                    {"code", "field", "requirement", "message"},
                )
                self.assertEqual(blocker["code"], MANDATORY_EFFORT_BLOCKER_CODE)
                self.assertEqual(blocker["field"], "estimated_effort_hours")
                self.assertEqual(blocker["requirement"], invalid_requirement)
                self.assertIn("greater than 0 hours", blocker["message"])
                self.assertIn("Django", blocker["message"])

                context = build_optimization_context(self.project)

                self.assertEqual(context["requirements"], [self.requirement])
                self.assertNotIn(
                    invalid_requirement.project_skill_requirement_id,
                    context["eligible_by_requirement"],
                )
                self.assertEqual(context["total_required_effort"], 4000)
                self.assertEqual(find_all_feasible_teams(self.project), [])

    def test_preflight_allows_zero_effort_for_an_optional_requirement(self):
        optional_skill = Skill.objects.create(
            name="Documentation",
            category="Delivery",
        )
        ProjectSkillRequirement.objects.create(
            project=self.project,
            skill=optional_skill,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.LOW,
            is_mandatory=False,
            required_quantity=1,
            estimated_effort_hours=Decimal("0.00"),
        )

        self.assertEqual(
            get_recommendation_preflight(self.project),
            {
                "can_generate_recommendations": True,
                "blockers": [],
            },
        )
        self.assertEqual(len(find_all_feasible_teams(self.project)), 7)

    def test_valid_effort_can_still_have_no_feasible_team(self):
        self.project.estimated_hours = Decimal("121.00")
        self.project.save(update_fields=["estimated_hours"])
        self.requirement.estimated_effort_hours = Decimal("121.00")
        self.requirement.save(update_fields=["estimated_effort_hours"])

        feasible_teams = find_all_feasible_teams(self.project)
        pareto_teams = find_pareto_teams(feasible_teams)
        recommendations = select_recommended_teams(pareto_teams)

        self.assertEqual(feasible_teams, [])
        self.assertEqual(pareto_teams, [])
        self.assertEqual(recommendations, [])
        self.assertEqual(compare_recommendations(recommendations), [])
        self.assertEqual(build_recommendation_explanations([], []), [])
