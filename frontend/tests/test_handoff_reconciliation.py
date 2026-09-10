"""Handoff refinement: result continuity plus staffing reconciliation.

Covers back-to-results without a pipeline rerun, CURRENT vs RECOMMENDED
diffs (KEEP/UPDATE/ADD/REMOVE plus coverage KEEP/ADD/REMOVE), stale and
duplicate protection across the new flow, permission gates including the
coverage-remove rule, atomic rollback, and untouched other-project work.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.db import DatabaseError
from django.test import Client, TestCase
from django.urls import reverse

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
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)


def _member_entry(employee, requirement, skill, utilization):
    return {
        "employee": employee,
        "requirement": requirement,
        "skill": skill,
        "utilization": utilization,
    }


class HandoffReconciliationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = cls._role_user("m68-viewer", VIEWER_GROUP)
        cls.manager = cls._role_user("m68-manager", MANAGER_PLANNER_GROUP)
        cls.hr_user = cls._role_user("m68-hr", HR_ADMINISTRATOR_GROUP)

        cls.python = Skill.objects.create(
            name="Python", category="Engineering"
        )
        cls.data = Skill.objects.create(name="Data", category="Engineering")
        cls.project = Project.objects.create(
            name="M68 staffed project",
            description="Reconciliation fixture.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            estimated_hours=Decimal("16.00"),
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
            required_quantity=2,
            estimated_effort_hours=Decimal("16.00"),
        )
        cls.lucie = cls._employee("Lucie", "Marie")
        cls.andre = cls._employee("Andre", "Traore")
        cls.margaret = cls._employee("Margaret", "Diallo")
        cls.jeanne = cls._employee("Jeanne", "Sow")

    @staticmethod
    def _role_user(username, role):
        user = get_user_model().objects.create_user(username=username)
        user.groups.add(Group.objects.get(name=role))
        return user

    @classmethod
    def _employee(cls, first_name, last_name):
        employee = Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
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
        return employee

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

    def _pipeline_result(self, members):
        recommendations = [
            {
                "category": "compact_match",
                "label": "Best compact match",
                "reason": "Existing service-owned selection reason.",
                "result": {
                    "team": [entry["employee"] for entry in members],
                    "team_size": len(members),
                    "team_score": 90.0,
                    "metrics": {
                        "team_size": len(members),
                        "total_available_hours": Decimal("80.00"),
                        "total_allocated_hours": Decimal("16.00"),
                        "remaining_capacity_hours": Decimal("64.00"),
                        "max_utilization": 68.0,
                        "utilization_spread": 0.0,
                    },
                    "effort_solution": {
                        "is_feasible": True,
                        "employee_capacities": [
                            {
                                "employee": entry["employee"],
                                "available_hours": Decimal("40.00"),
                                "allocated_hours": Decimal("16.00"),
                                "utilization_rate": entry["utilization"],
                            }
                            for entry in members
                        ],
                        "allocations": [
                            {
                                "employee": entry["employee"],
                                "requirement": entry["requirement"],
                                "skill": entry["skill"],
                                "hours": Decimal("8.00"),
                            }
                            for entry in members
                        ],
                    },
                    "coverage": [
                        {
                            "requirement": self.requirement,
                            "skill": self.python,
                            "required_quantity": 2,
                            "covered_quantity": 2,
                            "is_mandatory": True,
                            "is_satisfied": True,
                            "qualified_employees": [
                                entry["employee"] for entry in members
                            ],
                        }
                    ],
                },
            }
        ]
        return {
            "feasible_teams": [recommendations[0]["result"]],
            "pareto_teams": [recommendations[0]["result"]],
            "recommendations": recommendations,
            "comparisons": [],
            "explanations": [
                {
                    "category": "compact_match",
                    "label": "Best compact match",
                    "team": [
                        str(entry["employee"]) for entry in members
                    ],
                    "strengths": ["Existing deterministic strength."],
                    "tradeoffs": ["Existing deterministic trade-off."],
                }
            ],
            "elapsed_seconds": 0.5,
        }

    def _members(self, *employees, utilization=68.0):
        return [
            _member_entry(
                employee, self.requirement, self.python, utilization
            )
            for employee in employees
        ]

    def _confirm_url(self, category="compact_match"):
        return reverse(
            "frontend:project_recommendation_confirm",
            args=[self.project.project_id, category],
        )

    def _generate(self, pipeline_result):
        planning = self.client.get(self.planning_url)
        token = planning.context["recommendation_generation"]["form"][
            "submission_token"
        ].value()
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=pipeline_result,
        ):
            return self.client.post(
                self.generate_url, {"submission_token": token}
            )

    def _review_token(self, url):
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(
                self._members(self.lucie, self.andre)
            ),
        ):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.context["review"]["form"][
            "submission_token"
        ].value()

    def _seed_current_staffing(self):
        lucie_assignment = Assignment.objects.create(
            employee=self.lucie,
            project=self.project,
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            allocation_percentage=50,
            role_on_project="Existing lucie work",
            status=Assignment.Status.ACTIVE,
        )
        AssignmentSkill.objects.create(
            assignment=lucie_assignment,
            project_skill_requirement=self.requirement,
        )
        andre_assignment = Assignment.objects.create(
            employee=self.andre,
            project=self.project,
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            allocation_percentage=40,
            role_on_project="Existing andre work",
            status=Assignment.Status.ACTIVE,
        )
        margaret_assignment = Assignment.objects.create(
            employee=self.margaret,
            project=self.project,
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            allocation_percentage=30,
            role_on_project="Existing margaret work",
            status=Assignment.Status.ACTIVE,
        )
        AssignmentSkill.objects.create(
            assignment=margaret_assignment,
            project_skill_requirement=self.requirement,
        )
        return lucie_assignment, andre_assignment, margaret_assignment

    def test_update_remove_diff_before_confirm(self):
        lucie_assignment, andre_assignment, margaret_assignment = (
            self._seed_current_staffing()
        )
        before = (
            Assignment.objects.count(),
            AssignmentSkill.objects.count(),
        )
        members = self._members(self.lucie, self.andre)
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            review = self.client.get(self._confirm_url())
        self.assertEqual(review.status_code, 200)
        rows = {
            row["label"]: row for row in review.context["review"]["rows"]
        }
        self.assertEqual(rows[str(self.lucie)]["action"], "UPDATE")
        self.assertEqual(rows[str(self.lucie)]["current_allocation"], 50)
        self.assertEqual(rows[str(self.lucie)]["allocation_percentage"], 68)
        self.assertEqual(rows[str(self.andre)]["action"], "UPDATE")
        self.assertEqual(rows[str(self.andre)]["current_allocation"], 40)
        self.assertEqual(rows[str(self.margaret)]["action"], "REMOVE")
        self.assertEqual(rows[str(self.margaret)]["current_allocation"], 30)
        self.assertContains(review, "UPDATE")
        self.assertContains(review, "REMOVE")
        self.assertEqual(
            (Assignment.objects.count(), AssignmentSkill.objects.count()),
            before,
        )
        lucie_assignment.refresh_from_db()
        self.assertEqual(lucie_assignment.allocation_percentage, 50)
        margaret_assignment.refresh_from_db()
        self.assertEqual(margaret_assignment.status, Assignment.Status.ACTIVE)

    def test_confirm_applies_reconciliation_atomically(self):
        lucie_assignment, andre_assignment, margaret_assignment = (
            self._seed_current_staffing()
        )
        members = self._members(self.lucie, self.andre)
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            review = self.client.get(self._confirm_url())
            token = review.context["review"]["form"][
                "submission_token"
            ].value()
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            saved = self.client.post(
                self._confirm_url(), {"submission_token": token}
            )
        self.assertRedirects(
            saved, self.planning_url, fetch_redirect_response=False
        )
        lucie_assignment.refresh_from_db()
        andre_assignment.refresh_from_db()
        margaret_assignment.refresh_from_db()
        self.assertEqual(lucie_assignment.allocation_percentage, 68)
        self.assertEqual(andre_assignment.allocation_percentage, 68)
        self.assertEqual(
            margaret_assignment.status, Assignment.Status.CANCELLED
        )
        self.assertEqual(Assignment.objects.count(), 3)
        live_links = AssignmentSkill.objects.filter(
            assignment__status__in=[
                Assignment.Status.PLANNED,
                Assignment.Status.ACTIVE,
            ]
        ).count()
        self.assertEqual(live_links, 2)

    def test_keep_avoids_unnecessary_write(self):
        assignment = Assignment.objects.create(
            employee=self.lucie,
            project=self.project,
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            allocation_percentage=68,
            role_on_project="Python",
            status=Assignment.Status.PLANNED,
        )
        AssignmentSkill.objects.create(
            assignment=assignment,
            project_skill_requirement=self.requirement,
        )
        members = self._members(self.lucie)
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            review = self.client.get(self._confirm_url())
        self.assertEqual(review.status_code, 200)
        rows = review.context["review"]["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "KEEP")
        before_updated = Assignment.objects.get(pk=assignment.pk)
        token = review.context["review"]["form"][
            "submission_token"
        ].value()
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            saved = self.client.post(
                self._confirm_url(), {"submission_token": token}
            )
        self.assertEqual(saved.status_code, 302)
        self.assertEqual(Assignment.objects.count(), 1)
        self.assertEqual(AssignmentSkill.objects.count(), 1)
        before_updated.refresh_from_db()
        self.assertEqual(before_updated.allocation_percentage, 68)

    def test_remove_needs_explicit_confirm_and_cancels(self):
        margaret_assignment = Assignment.objects.create(
            employee=self.margaret,
            project=self.project,
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            allocation_percentage=30,
            role_on_project="Existing margaret work",
            status=Assignment.Status.ACTIVE,
        )
        members = self._members(self.lucie)
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            review = self.client.get(self._confirm_url())
        actions = {
            row["label"]: row["action"]
            for row in review.context["review"]["rows"]
        }
        self.assertEqual(actions[str(self.lucie)], "ADD")
        self.assertEqual(actions[str(self.margaret)], "REMOVE")
        margaret_assignment.refresh_from_db()
        self.assertEqual(
            margaret_assignment.status, Assignment.Status.ACTIVE
        )
        token = review.context["review"]["form"][
            "submission_token"
        ].value()
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            saved = self.client.post(
                self._confirm_url(), {"submission_token": token}
            )
        self.assertEqual(saved.status_code, 302)
        margaret_assignment.refresh_from_db()
        self.assertEqual(
            margaret_assignment.status, Assignment.Status.CANCELLED
        )

    def test_coverage_replace_uses_delete_permission(self):
        solo_requirement = ProjectSkillRequirement.objects.create(
            project=self.project,
            skill=self.data,
            required_level=2,
            priority=ProjectSkillRequirement.Priority.MEDIUM,
            is_mandatory=False,
            required_quantity=1,
            estimated_effort_hours=Decimal("4.00"),
        )
        EmployeeSkill.objects.create(
            employee=self.lucie,
            skill=self.data,
            level=3,
            years_experience=Decimal("2.0"),
        )
        lucie_assignment = Assignment.objects.create(
            employee=self.lucie,
            project=self.project,
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            allocation_percentage=10,
            role_on_project="Existing lucie work",
            status=Assignment.Status.PLANNED,
        )
        AssignmentSkill.objects.create(
            assignment=lucie_assignment,
            project_skill_requirement=solo_requirement,
        )
        members = [
            _member_entry(
                self.lucie, self.requirement, self.python, 68.0
            )
        ]
        review_url = self._confirm_url()
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            review = self.client.get(review_url)
        self.assertEqual(review.status_code, 200)
        token = review.context["review"]["form"][
            "submission_token"
        ].value()
        before = (
            Assignment.objects.count(),
            AssignmentSkill.objects.count(),
        )
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            denied = self.client.post(
                review_url, {"submission_token": token}
            )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(
            (Assignment.objects.count(), AssignmentSkill.objects.count()),
            before,
        )

        hr_client = Client()
        hr_client.force_login(self.hr_user)
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            hr_review = hr_client.get(review_url)
        hr_token = hr_review.context["review"]["form"][
            "submission_token"
        ].value()
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            hr_saved = hr_client.post(
                review_url, {"submission_token": hr_token}
            )
        self.assertEqual(hr_saved.status_code, 302)
        self.assertFalse(
            AssignmentSkill.objects.filter(
                assignment=lucie_assignment,
                project_skill_requirement=solo_requirement,
            ).exists()
        )
        self.assertTrue(
            AssignmentSkill.objects.filter(
                assignment=lucie_assignment,
                project_skill_requirement=self.requirement,
            ).exists()
        )

    def test_back_to_results_without_pipeline_rerun(self):
        members = self._members(self.lucie, self.andre)
        pipeline_result = self._pipeline_result(members)
        generated = self._generate(pipeline_result)
        self.assertEqual(generated.status_code, 200)
        run_id = generated.context["recommendation_run_id"]
        self.assertTrue(run_id)
        result_url = reverse(
            "frontend:project_recommendation_result",
            args=[self.project.project_id, run_id],
        )
        confirm_url = f"{self._confirm_url()}?run={run_id}"
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=pipeline_result,
        ) as handoff_pipeline:
            review = self.client.get(confirm_url)
        self.assertEqual(review.status_code, 200)
        self.assertContains(review, "Back to recommendation results")
        self.assertContains(review, result_url)
        self.assertEqual(handoff_pipeline.call_count, 1)

        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline"
        ) as result_pipeline:
            from django.db import connection
            from django.test.utils import CaptureQueriesContext

            with CaptureQueriesContext(connection) as result_queries:
                reread = self.client.get(result_url)
        result_pipeline.assert_not_called()
        self.assertEqual(reread.status_code, 200)
        self.assertEqual(
            reread.context["run"]["recommendation_count"],
            generated.context["run"]["recommendation_count"],
        )
        self.assertEqual(
            [card["label"] for card in reread.context["run"]["strategies"]["cards"]],
            [card["label"] for card in generated.context["run"]["strategies"]["cards"]],
        )
        self.assertEqual(
            reread.context["run"]["decision_evidence"],
            generated.context["run"]["decision_evidence"],
        )
        self.assertContains(reread, "Best compact match")
        print(
            "\nM6.7 cached-result baseline "
            "(warm GET re-render, pipeline never rerun):\n"
            f"  result_get_queries={len(result_queries)}, "
            f"response={len(reread.content)} bytes"
        )

    def test_review_two_strategies_from_same_run(self):
        first = _member_entry(
            self.lucie, self.requirement, self.python, 25.0
        )
        second = _member_entry(
            self.andre, self.requirement, self.python, 30.0
        )
        pipeline_result = self._pipeline_result([first])
        second_recommendation = {
            "category": "balanced",
            "label": "Best balanced alternative",
            "reason": "Existing service-owned selection reason.",
            "result": dict(pipeline_result["recommendations"][0]["result"]),
        }
        pipeline_result["recommendations"].append(second_recommendation)
        pipeline_result["explanations"].append(
            {
                "category": "balanced",
                "label": "Best balanced alternative",
                "team": [str(self.andre)],
                "strengths": ["Existing deterministic strength."],
                "tradeoffs": ["Existing deterministic trade-off."],
            }
        )
        generated = self._generate(pipeline_result)
        run_id = generated.context["recommendation_run_id"]
        for category in ("compact_match", "balanced"):
            confirm_url = (
                reverse(
                    "frontend:project_recommendation_confirm",
                    args=[self.project.project_id, category],
                )
                + f"?run={run_id}"
            )
            with patch(
                "frontend.views.assignment_handoff."
                "run_recommendation_pipeline",
                return_value=pipeline_result,
            ):
                review = self.client.get(confirm_url)
            self.assertEqual(review.status_code, 200)
            self.assertContains(review, "Back to recommendation results")
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline"
        ) as result_pipeline:
            reread = self.client.get(
                reverse(
                    "frontend:project_recommendation_result",
                    args=[self.project.project_id, run_id],
                )
            )
        result_pipeline.assert_not_called()
        self.assertEqual(reread.status_code, 200)

    def test_stale_run_falls_back_to_planning(self):
        generated = self._generate(
            self._pipeline_result(self._members(self.lucie))
        )
        run_id = generated.context["recommendation_run_id"]
        result_url = reverse(
            "frontend:project_recommendation_result",
            args=[self.project.project_id, run_id],
        )
        self.project.name = "M68 renamed project"
        self.project.save()
        reread = self.client.get(result_url)
        self.assertRedirects(
            reread, self.planning_url, fetch_redirect_response=False
        )
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(
                self._members(self.lucie)
            ),
        ):
            review = self.client.get(f"{self._confirm_url()}?run={run_id}")
        self.assertEqual(review.status_code, 200)
        self.assertNotContains(review, "Back to recommendation results")
        self.assertContains(review, "Return to planning workspace")

    def test_confirm_invalidates_run(self):
        members = self._members(self.lucie)
        generated = self._generate(self._pipeline_result(members))
        run_id = generated.context["recommendation_run_id"]
        result_url = reverse(
            "frontend:project_recommendation_result",
            args=[self.project.project_id, run_id],
        )
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            review = self.client.get(f"{self._confirm_url()}?run={run_id}")
            token = review.context["review"]["form"][
                "submission_token"
            ].value()
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            saved = self.client.post(
                self._confirm_url(),
                {
                    "submission_token": token,
                    "run_id": run_id,
                },
            )
        self.assertEqual(saved.status_code, 302)
        reread = self.client.get(result_url)
        self.assertRedirects(
            reread, self.planning_url, fetch_redirect_response=False
        )

    def test_missing_change_permission_denied(self):
        restricted = get_user_model().objects.create_user(
            username="m68-without-change"
        )
        for codename in (
            "add_assignment",
            "add_assignmentskill",
            "view_project",
            "view_projectskillrequirement",
            "view_assignment",
            "view_assignmentskill",
            "view_employee",
            "view_skill",
        ):
            restricted.user_permissions.add(
                Permission.objects.get(
                    content_type__app_label="core", codename=codename
                )
            )
        restricted_client = Client()
        restricted_client.force_login(restricted)
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline"
        ) as pipeline:
            self.assertEqual(
                restricted_client.get(self._confirm_url()).status_code,
                403,
            )
        pipeline.assert_not_called()

    def test_other_project_work_is_untouched(self):
        other_project = Project.objects.create(
            name="M68 other project",
            description="Untouched fixture.",
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            estimated_hours=Decimal("8.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        other_assignment = Assignment.objects.create(
            employee=self.jeanne,
            project=other_project,
            start_date=other_project.start_date,
            end_date=other_project.end_date,
            allocation_percentage=20,
            role_on_project="Other work",
            status=Assignment.Status.ACTIVE,
        )
        members = self._members(self.lucie)
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            review = self.client.get(self._confirm_url())
            token = review.context["review"]["form"][
                "submission_token"
            ].value()
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            saved = self.client.post(
                self._confirm_url(), {"submission_token": token}
            )
        self.assertEqual(saved.status_code, 302)
        other_assignment.refresh_from_db()
        self.assertEqual(other_assignment.allocation_percentage, 20)
        self.assertEqual(other_assignment.status, Assignment.Status.ACTIVE)
        self.assertTrue(
            Assignment.objects.filter(
                employee=self.lucie, project=self.project
            ).exists()
        )

    def test_failed_reconciliation_rolls_back(self):
        self._seed_current_staffing()
        members = self._members(self.lucie, self.andre)
        before = (
            Assignment.objects.count(),
            AssignmentSkill.objects.count(),
        )
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            review = self.client.get(self._confirm_url())
            token = review.context["review"]["form"][
                "submission_token"
            ].value()
        real_save = Assignment.save

        def _failing_save(instance, *args, **kwargs):
            if instance.employee_id == self.andre.employee_id:
                raise DatabaseError("simulated save failure")
            return real_save(instance, *args, **kwargs)

        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(members),
        ):
            with patch.object(
                Assignment, "save", autospec=True, side_effect=_failing_save
            ):
                failed = self.client.post(
                    self._confirm_url(), {"submission_token": token}
                )
        self.assertEqual(failed.status_code, 422)
        self.assertEqual(
            (Assignment.objects.count(), AssignmentSkill.objects.count()),
            before,
        )

    def test_viewer_cannot_use_run_links(self):
        generated = self._generate(
            self._pipeline_result(self._members(self.lucie))
        )
        run_id = generated.context["recommendation_run_id"]
        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        self.assertEqual(
            viewer_client.get(self._confirm_url()).status_code, 403
        )
        reread = viewer_client.get(
            reverse(
                "frontend:project_recommendation_result",
                args=[self.project.project_id, run_id],
            )
        )
        self.assertRedirects(
            reread, self.planning_url, fetch_redirect_response=False
        )

    def test_expired_run_needs_fresh_recommendation(self):
        generated = self._generate(
            self._pipeline_result(self._members(self.lucie))
        )
        run_id = generated.context["recommendation_run_id"]
        cache.clear()
        reread = self.client.get(
            reverse(
                "frontend:project_recommendation_result",
                args=[self.project.project_id, run_id],
            )
        )
        self.assertRedirects(
            reread, self.planning_url, fetch_redirect_response=False
        )
