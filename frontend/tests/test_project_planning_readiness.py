from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Assignment,
    Employee,
    EmployeeSkill,
    Leave,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from core.services.effective_availability import calculate_available_hours_for_project
from core.services.optimization import (
    build_optimization_context,
    get_fast_feasibility_issues,
    passes_fast_feasibility_checks,
    units_to_hours,
)
from frontend.presenters.planning import build_project_planning_workspace
from frontend.roles import VIEWER_GROUP, sync_role_permissions
from frontend.selectors.projects import get_project_profile


class ProjectPlanningReadinessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="readiness-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.python = Skill.objects.create(
            name="Python",
            category="Engineering",
        )
        cls.sql = Skill.objects.create(
            name="SQL",
            category="Data",
        )
        cls.employee = Employee.objects.create(
            first_name="Alex",
            last_name="Morgan",
            department="Engineering",
            position="Engineer",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("6.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )

    def setUp(self):
        self.client.force_login(self.viewer)
        self.project = self._project()
        self.requirement = self._requirement(self.project)
        EmployeeSkill.objects.create(
            employee=self.employee,
            skill=self.python,
            level=3,
            years_experience=Decimal("4.0"),
        )
        self.url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )

    @staticmethod
    def _project(
        *,
        name="Readiness project",
        start_date=date(2026, 9, 7),
        end_date=date(2026, 9, 11),
        estimated_hours="40.00",
    ):
        return Project.objects.create(
            name=name,
            description="A focused planning-readiness fixture.",
            start_date=start_date,
            end_date=end_date,
            estimated_hours=Decimal(estimated_hours),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )

    def _requirement(
        self,
        project,
        *,
        skill=None,
        quantity=1,
        effort="40.00",
        mandatory=True,
    ):
        return ProjectSkillRequirement.objects.create(
            project=project,
            skill=skill or self.python,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=mandatory,
            required_quantity=quantity,
            estimated_effort_hours=(
                Decimal(effort) if effort is not None else None
            ),
        )

    def _workspace(self, project=None):
        project = project or self.project
        return build_project_planning_workspace(
            get_project_profile(project.project_id)
        )

    def test_complete_readiness_delegates_in_order_without_running_pipeline(self):
        selected = get_project_profile(self.project.project_id)
        real_preflight = {
            "can_generate_recommendations": True,
            "blockers": [],
        }
        real_context = build_optimization_context(self.project)
        events = []

        def preflight(project):
            events.append("preflight")
            self.assertEqual(project, selected)
            return real_preflight

        def context(project):
            events.append("context")
            self.assertEqual(project, selected)
            return real_context

        def rank(project):
            events.append("rank")
            self.assertEqual(project, selected)
            return []

        with (
            patch(
                "frontend.presenters.planning.get_recommendation_preflight",
                side_effect=preflight,
            ) as preflight_service,
            patch(
                "frontend.presenters.planning.build_optimization_context",
                side_effect=context,
            ) as context_service,
            patch(
                "core.services.optimization.cp_model.CpSolver"
            ) as solver,
            patch(
                "frontend.presenters.planning.rank_employees_for_project",
                side_effect=rank,
            ) as rank_employees,
        ):
            workspace = build_project_planning_workspace(selected)

        self.assertEqual(events, ["preflight", "context", "rank"])
        preflight_service.assert_called_once_with(selected)
        context_service.assert_called_once_with(selected)
        solver.assert_not_called()
        rank_employees.assert_called_once_with(selected)
        self.assertTrue(workspace["readiness"]["is_ready"])
        self.assertTrue(
            workspace["readiness"]["candidate_assessment_allowed"]
        )
        self.assertEqual(workspace["readiness"]["blockers"], ())

        response = self.client.get(self.url)
        self.assertContains(response, "Ready for candidate assessment")
        self.assertContains(
            response,
            "This is a readiness check, not a feasibility result.",
        )
        self.assertContains(response, "Monday-to-Friday model")
        self.assertContains(
            response,
            "Attendance remains descriptive only and does not affect staffing "
            "readiness.",
        )
        self.assertNotContains(response, "Explain candidate exclusions")

    def test_incomplete_invalid_and_empty_inputs_stop_capacity_assessment(self):
        for effort in (None, "0.00"):
            self.requirement.estimated_effort_hours = (
                Decimal(effort) if effort is not None else None
            )
            self.requirement.save(update_fields=["estimated_effort_hours"])
            with patch(
                "frontend.presenters.planning.build_optimization_context"
            ) as context_service:
                workspace = self._workspace()
            context_service.assert_not_called()
            self.assertEqual(
                workspace["readiness"]["blockers"][0]["code"],
                "mandatory_effort_must_be_positive",
            )

        self.requirement.estimated_effort_hours = Decimal("40.00")
        self.requirement.save(update_fields=["estimated_effort_hours"])
        selected = get_project_profile(self.project.project_id)
        selected.end_date = date(2026, 9, 6)
        with patch(
            "frontend.presenters.planning.build_optimization_context"
        ) as context_service:
            invalid = build_project_planning_workspace(selected)
        context_service.assert_not_called()
        self.assertEqual(
            invalid["readiness"]["blockers"][0]["code"],
            "invalid_project_dates",
        )

        self.requirement.delete()
        with patch(
            "frontend.presenters.planning.build_optimization_context"
        ) as context_service:
            empty = self._workspace()
        context_service.assert_not_called()
        self.assertEqual(
            empty["readiness"]["blockers"][0]["code"],
            "no_mandatory_requirements",
        )

    def test_insufficient_headcount_and_capacity_are_distinct(self):
        self.requirement.required_quantity = 2
        self.requirement.save(update_fields=["required_quantity"])
        headcount = self._workspace()["readiness"]
        self.assertFalse(headcount["is_ready"])
        self.assertEqual(
            [blocker["code"] for blocker in headcount["blockers"]],
            ["insufficient_eligible_headcount"],
        )
        self.assertIn(
            "needs 2 qualified active employees, but 1 currently meets level 3",
            headcount["blockers"][0]["message"],
        )

        self.requirement.required_quantity = 1
        self.requirement.estimated_effort_hours = Decimal("40.01")
        self.requirement.save(
            update_fields=["required_quantity", "estimated_effort_hours"]
        )
        capacity = self._workspace()["readiness"]
        self.assertEqual(
            [blocker["code"] for blocker in capacity["blockers"]],
            ["insufficient_qualified_capacity"],
        )
        self.assertIn("needs 40.01 hours", capacity["blockers"][0]["message"])
        self.assertIn(
            "40.00 hours of effective capacity",
            capacity["blockers"][0]["message"],
        )

    def test_inclusive_boundary_dates_use_existing_weekday_capacity(self):
        self.project.end_date = self.project.start_date
        self.project.estimated_hours = Decimal("8.00")
        self.project.save(update_fields=["end_date", "estimated_hours"])
        self.requirement.estimated_effort_hours = Decimal("8.00")
        self.requirement.save(update_fields=["estimated_effort_hours"])
        monday = self._workspace()
        self.assertTrue(monday["readiness"]["is_ready"])

        sunday_project = self._project(
            name="Sunday boundary",
            start_date=date(2026, 9, 6),
            end_date=date(2026, 9, 6),
            estimated_hours="1.00",
        )
        self._requirement(sunday_project, effort="1.00")
        sunday = self._workspace(sunday_project)
        self.assertEqual(
            sunday["readiness"]["blockers"][0]["code"],
            "insufficient_qualified_capacity",
        )
        self.assertIn("0.00 hours", sunday["readiness"]["blockers"][0]["message"])

    def test_fresh_changes_are_reassessed_and_stale_snapshots_are_rejected(self):
        self.requirement.estimated_effort_hours = None
        self.requirement.save(update_fields=["estimated_effort_hours"])
        blocked = self.client.get(self.url)
        self.assertContains(blocked, "Planning review needed")
        self.assertContains(blocked, "greater than 0 hours")

        self.requirement.estimated_effort_hours = Decimal("40.00")
        self.requirement.save(update_fields=["estimated_effort_hours"])
        refreshed = self.client.get(self.url)
        self.assertContains(refreshed, "Ready for candidate assessment")

        selected = get_project_profile(self.project.project_id)
        self.requirement.estimated_effort_hours = Decimal("39.00")
        self.requirement.save(update_fields=["estimated_effort_hours"])
        stale = build_project_planning_workspace(selected)["readiness"]
        self.assertFalse(stale["is_ready"])
        self.assertEqual(
            [blocker["code"] for blocker in stale["blockers"]],
            ["stale_planning_inputs"],
        )
        self.assertEqual(stale["label"], "Refresh planning inputs")

    def test_blocker_order_is_deterministic_and_estimates_remain_separate(self):
        sql_requirement = self._requirement(
            self.project,
            skill=self.sql,
            quantity=2,
            effort="10.00",
        )
        self.requirement.required_quantity = 2
        self.requirement.save(update_fields=["required_quantity"])

        first = self._workspace()
        second = self._workspace()
        first_blockers = [
            (
                blocker["code"],
                blocker.get("requirement").project_skill_requirement_id,
            )
            for blocker in first["readiness"]["blockers"]
        ]
        second_blockers = [
            (
                blocker["code"],
                blocker.get("requirement").project_skill_requirement_id,
            )
            for blocker in second["readiness"]["blockers"]
        ]
        self.assertEqual(first_blockers, second_blockers)
        self.assertEqual(
            first_blockers,
            [
                ("insufficient_eligible_headcount", self.requirement.pk),
                ("insufficient_eligible_headcount", sql_requirement.pk),
            ],
        )
        self.assertFalse(first["estimates_match"])
        self.assertEqual(first["project"].estimated_hours, Decimal("40.00"))
        self.assertEqual(first["mandatory_effort_hours"], Decimal("50.00"))
        self.assertIn("remain separate stored values", first["estimate_message"])

    def test_fast_issue_details_preserve_the_existing_boolean_contract(self):
        context = build_optimization_context(self.project)
        team = context["employees"]
        self.assertEqual(get_fast_feasibility_issues(team, context), [])
        self.assertTrue(passes_fast_feasibility_checks(team, context))

        self.requirement.estimated_effort_hours = Decimal("40.01")
        self.requirement.save(update_fields=["estimated_effort_hours"])
        context = build_optimization_context(self.project)
        issues = get_fast_feasibility_issues(context["employees"], context)
        self.assertEqual(
            [issue["code"] for issue in issues],
            [
                "insufficient_total_capacity",
                "insufficient_qualified_capacity",
            ],
        )
        self.assertFalse(
            passes_fast_feasibility_checks(context["employees"], context)
        )

        planning_source = (
            Path(__file__).resolve().parents[1] / "presenters/planning.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden_call in (
            "find_all_feasible_teams(",
            "solve_team_effort_allocation(",
            "select_recommended_teams(",
            "build_recommendation_explanations(",
            "attendance.objects",
            "gemini",
        ):
            with self.subTest(forbidden_call=forbidden_call):
                self.assertNotIn(forbidden_call, planning_source)

    def test_prefetched_context_preserves_assignment_and_leave_capacity_rules(self):
        competing_project = self._project(name="Competing project")
        Assignment.objects.create(
            employee=self.employee,
            project=competing_project,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            allocation_percentage=50,
            role_on_project="Support",
            status=Assignment.Status.ACTIVE,
        )
        Assignment.objects.create(
            employee=self.employee,
            project=self.project,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            allocation_percentage=100,
            role_on_project="Proposed team",
            status=Assignment.Status.ACTIVE,
        )
        Leave.objects.create(
            employee=self.employee,
            start_date=date(2026, 9, 9),
            end_date=date(2026, 9, 9),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )

        legacy_hours = calculate_available_hours_for_project(
            self.employee,
            self.project,
        )
        context = build_optimization_context(self.project)

        self.assertEqual(legacy_hours, Decimal("16.00"))
        self.assertEqual(
            units_to_hours(context["available_hours"][self.employee.pk]),
            legacy_hours,
        )
