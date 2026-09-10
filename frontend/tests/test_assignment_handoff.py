"""M6.7 reviewed assignment confirmation handoff.

Confirmation-only staffing writes from one current recommendation with
current-data revalidation, existing model rules, permissions, CSRF,
duplicate protection, atomic saves, and return continuity.
"""

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
from django.test import Client, TestCase
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
from frontend.assignment_handoff import issue_handoff_token
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)


class AssignmentHandoffTests(TestCase):
    TIMING_SAMPLE_COUNT = 7

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = cls._role_user("m67-viewer", VIEWER_GROUP)
        cls.manager = cls._role_user(
            "m67-manager", MANAGER_PLANNER_GROUP
        )
        cls.hr_user = cls._role_user("m67-hr", HR_ADMINISTRATOR_GROUP)
        cls.unassigned = get_user_model().objects.create_user(
            username="m67-unassigned"
        )

        cls.python = Skill.objects.create(
            name="Python", category="Engineering"
        )
        cls.project = Project.objects.create(
            name="M67 handoff project",
            description="Reviewed staffing confirmation fixture.",
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
        cls.unskilled = Employee.objects.create(
            first_name="Una",
            last_name="Unskilled",
            department="Engineering",
            position="Engineer",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("2.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )

    @staticmethod
    def _role_user(username, role):
        user = get_user_model().objects.create_user(username=username)
        user.groups.add(Group.objects.get(name=role))
        return user

    def setUp(self):
        cache.clear()
        self.client.force_login(self.manager)
        self.confirm_url = reverse(
            "frontend:project_recommendation_confirm",
            args=[self.project.project_id, "compact_match"],
        )
        self.planning_url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )

    def _pipeline_result(self, employee=None):
        employee = employee or self.employee
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

    def _get_review(self, client=None):
        client = client or self.client
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(),
        ):
            return client.get(self.confirm_url)

    def _review_token(self, client=None):
        response = self._get_review(client)
        self.assertEqual(response.status_code, 200)
        form = response.context["review"]["form"]
        self.assertIsNotNone(form)
        return form["submission_token"].value()

    def _counts(self):
        return (
            Assignment.objects.count(),
            AssignmentSkill.objects.count(),
        )

    def test_route_resolves_with_projects_navigation(self):
        match = resolve(self.confirm_url)
        self.assertEqual(
            match.view_name, "frontend:project_recommendation_confirm"
        )
        self.assertEqual(match.kwargs["project_id"], self.project.project_id)
        self.assertEqual(match.kwargs["category"], "compact_match")
        self.assertEqual(
            resolve(
                reverse(
                    "frontend:project_recommendation_confirm",
                    args=[self.project.project_id, "balanced"],
                )
            ).kwargs["category"],
            "balanced",
        )

    def test_unknown_category_returns_404_without_mutation(self):
        before = self._counts()
        unknown = reverse(
            "frontend:project_recommendation_confirm",
            args=[self.project.project_id, "unknown"],
        )
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline"
        ) as pipeline:
            self.assertEqual(self.client.get(unknown).status_code, 404)
            self.assertEqual(
                self.client.post(
                    unknown, {"submission_token": "anything"}
                ).status_code,
                404,
            )
        pipeline.assert_not_called()
        self.assertEqual(before, self._counts())

    def test_review_renders_proposal_without_mutation(self):
        before = self._counts()
        response = self._get_review()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "frontend/recommendations/confirm.html"
        )
        review = response.context["review"]
        self.assertEqual(review["label"], "Best compact match")
        self.assertEqual(len(review["rows"]), 1)
        row = review["rows"][0]
        self.assertEqual(row["label"], str(self.employee))
        self.assertEqual(row["start_date"], self.project.start_date)
        self.assertEqual(row["end_date"], self.project.end_date)
        self.assertEqual(row["allocation_percentage"], 25)
        self.assertEqual(row["status"], Assignment.Status.PLANNED)
        self.assertIn("Python", row["role_on_project"])
        self.assertEqual(row["coverage_labels"], ("Python",))
        self.assertFalse(review["has_error"])
        self.assertIsNotNone(review["form"])
        self.assertContains(response, "Confirm staffing records")
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'name="submission_token"')
        self.assertContains(
            response, f'href="{self.planning_url}"'
        )
        self.assertContains(
            response, "Nothing is saved until you confirm"
        )
        self.assertRegex(
            response.content.decode("utf-8"),
            r'href="/projects/"\s+aria-current="page"',
        )
        self.assertEqual(before, self._counts())

    def test_result_cards_expose_handoff_only_with_write_permissions(self):
        generate_url = reverse(
            "frontend:project_recommendation_generate",
            args=[self.project.project_id],
        )

        def generation_post(client, pipeline_result):
            planning = client.get(self.planning_url)
            token = planning.context["recommendation_generation"]["form"][
                "submission_token"
            ].value()
            with patch(
                "frontend.views.recommendations.run_recommendation_pipeline",
                return_value=pipeline_result,
            ):
                return client.post(
                    generate_url, {"submission_token": token}
                )

        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=self._pipeline_result(),
        ):
            viewer_response = generation_post(
                viewer_client, self._pipeline_result()
            )
        self.assertEqual(viewer_response.status_code, 200)
        self.assertNotContains(viewer_response, "Review staffing handoff")
        self.assertContains(
            viewer_response, "This run did not change staffing records."
        )
        self.assertNotContains(viewer_response, "Create assignment")

        manager_response = generation_post(
            self.client, self._pipeline_result()
        )
        self.assertEqual(manager_response.status_code, 200)
        self.assertContains(manager_response, "Review staffing handoff")
        self.assertContains(manager_response, self.confirm_url)

    def test_confirm_post_creates_exact_records_and_returns(self):
        before_assignments = Assignment.objects.count()
        before_coverage = AssignmentSkill.objects.count()
        token = self._review_token()
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(),
        ):
            response = self.client.post(
                self.confirm_url, {"submission_token": token}
            )
        self.assertRedirects(
            response, self.planning_url, fetch_redirect_response=False
        )
        self.assertEqual(Assignment.objects.count(), before_assignments + 1)
        self.assertEqual(
            AssignmentSkill.objects.count(), before_coverage + 1
        )
        assignment = Assignment.objects.latest("assignment_id")
        self.assertEqual(assignment.employee_id, self.employee.employee_id)
        self.assertEqual(assignment.project_id, self.project.project_id)
        self.assertEqual(assignment.start_date, self.project.start_date)
        self.assertEqual(assignment.end_date, self.project.end_date)
        self.assertEqual(assignment.allocation_percentage, 25)
        self.assertEqual(assignment.status, Assignment.Status.PLANNED)
        self.assertTrue(assignment.role_on_project)
        link = AssignmentSkill.objects.get(assignment=assignment)
        self.assertEqual(
            link.project_skill_requirement_id,
            self.requirement.project_skill_requirement_id,
        )

    def test_generation_and_review_never_create_without_confirm(self):
        before = self._counts()
        generate_url = reverse(
            "frontend:project_recommendation_generate",
            args=[self.project.project_id],
        )
        planning = self.client.get(self.planning_url)
        token = planning.context["recommendation_generation"]["form"][
            "submission_token"
        ].value()
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=self._pipeline_result(),
        ):
            generated = self.client.post(
                generate_url, {"submission_token": token}
            )
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(before, self._counts())

        review = self._get_review()
        self.assertEqual(review.status_code, 200)
        self.assertEqual(before, self._counts())

    def test_overlapping_assignment_blocks_review_and_save(self):
        Assignment.objects.create(
            employee=self.employee,
            project=self.project,
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            allocation_percentage=25,
            role_on_project="Existing work",
            status=Assignment.Status.ACTIVE,
        )
        before = self._counts()
        review = self._get_review()
        self.assertEqual(review.status_code, 422)
        self.assertTrue(review.context["review"]["has_error"])
        self.assertIsNone(review.context["review"]["form"])
        self.assertContains(
            review, "already has an overlapping assignment", status_code=422
        )

        from frontend.selectors.recommendations import (
            get_recommendation_input_snapshot,
        )
        from frontend.assignment_handoff import issue_handoff_token

        snapshot = get_recommendation_input_snapshot(
            self.project.project_id
        )
        token = issue_handoff_token(
            project_id=self.project.project_id,
            user_id=self.manager.pk,
            category="compact_match",
            input_signature=snapshot["signature"],
        )
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(),
        ):
            saved = self.client.post(
                self.confirm_url, {"submission_token": token}
            )
        self.assertEqual(saved.status_code, 422)
        self.assertEqual(before, self._counts())

    def test_approved_leave_blocks_confirmation(self):
        Leave.objects.create(
            employee=self.employee,
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            status=Leave.Status.APPROVED,
            type=Leave.Type.ANNUAL,
        )
        before = self._counts()
        review = self._get_review()
        self.assertEqual(review.status_code, 422)
        self.assertContains(
            review, "approved leave", status_code=422
        )
        self.assertEqual(before, self._counts())

    def test_unqualified_member_and_quantity_blocks_are_distinct(self):
        before = self._counts()
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(employee=self.unskilled),
        ):
            unqualified = self.client.get(self.confirm_url)
        self.assertEqual(unqualified.status_code, 422)
        self.assertContains(
            unqualified, "does not satisfy", status_code=422
        )
        self.assertEqual(before, self._counts())

        other_project = Project.objects.create(
            name="M67 other project",
            description="Quantity fixture.",
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            estimated_hours=Decimal("8.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        other_requirement = ProjectSkillRequirement.objects.create(
            project=other_project,
            skill=self.python,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=Decimal("8.00"),
        )
        other_assignment = Assignment.objects.create(
            employee=self.employee,
            project=other_project,
            start_date=other_project.start_date,
            end_date=other_project.end_date,
            allocation_percentage=10,
            role_on_project="Other work",
            status=Assignment.Status.PLANNED,
        )
        AssignmentSkill.objects.create(
            assignment=other_assignment,
            project_skill_requirement=other_requirement,
        )
        covering_assignment = Assignment.objects.create(
            employee=self.unskilled,
            project=self.project,
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            allocation_percentage=10,
            role_on_project="Covering work",
            status=Assignment.Status.PLANNED,
        )
        EmployeeSkill.objects.create(
            employee=self.unskilled,
            skill=self.python,
            level=4,
            years_experience=Decimal("3.0"),
        )
        AssignmentSkill.objects.create(
            assignment=covering_assignment,
            project_skill_requirement=self.requirement,
        )
        before_quantity = self._counts()
        review = self._get_review()
        self.assertEqual(review.status_code, 422)
        self.assertContains(
            review, "required quantity", status_code=422
        )
        self.assertEqual(before_quantity, self._counts())

    def test_compound_save_is_atomic_without_partial_records(self):
        second_employee = Employee.objects.create(
            first_name="Second",
            last_name="Member",
            department="Engineering",
            position="Engineer",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("4.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )
        EmployeeSkill.objects.create(
            employee=second_employee,
            skill=self.python,
            level=4,
            years_experience=Decimal("3.0"),
        )
        result = self._pipeline_result()
        recommendation = result["recommendations"][0]
        second_capacity = {
            "employee": second_employee,
            "available_hours": Decimal("32.00"),
            "allocated_hours": Decimal("8.00"),
            "utilization_rate": 25.0,
        }
        recommendation["result"]["team"] = [self.employee, second_employee]
        recommendation["result"]["team_size"] = 2
        recommendation["result"]["effort_solution"][
            "employee_capacities"
        ].append(second_capacity)
        recommendation["result"]["effort_solution"]["allocations"].append(
            {
                "employee": second_employee,
                "requirement": self.requirement,
                "skill": self.python,
                "hours": Decimal("8.00"),
            }
        )
        result["explanations"][0]["team"] = [
            str(self.employee),
            str(second_employee),
        ]

        before = self._counts()
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=result,
        ):
            review = self.client.get(self.confirm_url)
        self.assertEqual(review.status_code, 422)
        self.assertContains(
            review, "required quantity", status_code=422
        )
        self.assertEqual(before, self._counts())

        token = None
        if review.context["review"]["form"] is not None:
            token = review.context["review"]["form"][
                "submission_token"
            ].value()
        if token is not None:
            with patch(
                "frontend.views.assignment_handoff."
                "run_recommendation_pipeline",
                return_value=result,
            ):
                saved = self.client.post(
                    self.confirm_url, {"submission_token": token}
                )
            self.assertEqual(saved.status_code, 422)
            self.assertEqual(before, self._counts())

    def test_permission_boundaries(self):
        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline"
        ) as pipeline:
            self.assertEqual(
                viewer_client.get(self.confirm_url).status_code, 403
            )
            self.assertEqual(
                viewer_client.post(
                    self.confirm_url, {"submission_token": "x"}
                ).status_code,
                403,
            )
        pipeline.assert_not_called()

        unassigned_client = Client()
        unassigned_client.force_login(self.unassigned)
        self.assertEqual(
            unassigned_client.get(self.confirm_url).status_code, 403
        )

        for codename, model in (
            ("add_assignment", Assignment),
            ("add_assignmentskill", AssignmentSkill),
        ):
            restricted = get_user_model().objects.create_user(
                username=f"m67-without-{codename}"
            )
            assignment_perm = Permission.objects.get(
                content_type__app_label="core",
                codename="add_assignment",
            )
            coverage_perm = Permission.objects.get(
                content_type__app_label="core",
                codename="add_assignmentskill",
            )
            wanted = (
                coverage_perm if codename == "add_assignment" else assignment_perm
            )
            restricted.user_permissions.add(wanted)
            for view_model in (
                Project,
                ProjectSkillRequirement,
                Assignment,
                AssignmentSkill,
                Employee,
                Skill,
            ):
                restricted.user_permissions.add(
                    Permission.objects.get(
                        content_type__app_label="core",
                        codename=f"view_{view_model._meta.model_name}",
                    )
                )
            restricted_client = Client()
            restricted_client.force_login(restricted)
            with self.subTest(missing=codename):
                self.assertEqual(
                    restricted_client.get(self.confirm_url).status_code,
                    403,
                )

        for user in (self.manager, self.hr_user):
            role_client = Client()
            role_client.force_login(user)
            with patch(
                "frontend.views.assignment_handoff."
                "run_recommendation_pipeline",
                return_value=self._pipeline_result(),
            ):
                self.assertEqual(
                    role_client.get(self.confirm_url).status_code, 200
                )

    def test_csrf_and_duplicate_submit_protection(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.manager)
        signed = issue_handoff_token(
            project_id=self.project.pk,
            user_id=self.manager.pk,
            category="compact_match",
        )
        self.assertEqual(
            csrf_client.post(
                self.confirm_url, {"submission_token": signed}
            ).status_code,
            403,
        )
        planning = csrf_client.get(self.planning_url)
        csrf_token = re.search(
            r'name="csrfmiddlewaretoken" value="([^"]+)"', planning.content.decode("utf-8")
        ).group(1)
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(),
        ):
            review = csrf_client.get(self.confirm_url)
        token = review.context["review"]["form"][
            "submission_token"
        ].value()
        before = self._counts()
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(),
        ):
            first = csrf_client.post(
                self.confirm_url,
                {
                    "csrfmiddlewaretoken": csrf_token,
                    "submission_token": token,
                },
            )
            duplicate = csrf_client.post(
                self.confirm_url,
                {
                    "csrfmiddlewaretoken": csrf_token,
                    "submission_token": token,
                },
            )
        self.assertEqual(first.status_code, 302)
        self.assertEqual(duplicate.status_code, 409)
        duplicate_html = duplicate.content.decode("utf-8")
        self.assertTrue(
            "already submitted" in duplicate_html
            or "no longer matches current data" in duplicate_html
        )
        self.assertEqual(
            (Assignment.objects.count(), AssignmentSkill.objects.count()),
            (before[0] + 1, before[1] + 1),
        )

        app_js = (
            Path(__file__).resolve().parents[1] / "static/frontend/js/app.js"
        ).read_text(encoding="utf-8")
        self.assertIn('form.getAttribute("aria-busy") === "true"', app_js)

    def test_duplicate_token_without_save_returns_duplicate(self):
        token = self._review_token()
        before = self._counts()
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertLogs(
                "frontend.views.assignment_handoff", level="ERROR"
            ):
                first = self.client.post(
                    self.confirm_url, {"submission_token": token}
                )
        self.assertEqual(first.status_code, 503)
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(),
        ):
            duplicate = self.client.post(
                self.confirm_url, {"submission_token": token}
            )
        self.assertEqual(duplicate.status_code, 409)
        self.assertContains(
            duplicate, "already submitted", status_code=409
        )
        self.assertEqual(before, self._counts())

    def test_stale_inputs_between_review_and_save_create_nothing(self):
        token = self._review_token()
        before = self._counts()
        self.project.name = "M67 changed project"
        self.project.save()
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(),
        ):
            stale = self.client.post(
                self.confirm_url, {"submission_token": token}
            )
        self.assertEqual(stale.status_code, 409)
        self.assertContains(
            stale, "no longer matches current data", status_code=409
        )
        self.assertEqual(before, self._counts())

        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(),
        ):
            fresh_token = self._review_token()
            fresh = self.client.post(
                self.confirm_url, {"submission_token": fresh_token}
            )
        self.assertEqual(fresh.status_code, 302)
        self.assertEqual(
            Assignment.objects.count(), before[0] + 1
        )

    def test_safe_error_copy_and_no_leak(self):
        with (
            self.assertLogs(
                "frontend.views.assignment_handoff", level="ERROR"
            ),
            patch(
                "frontend.views.assignment_handoff."
                "run_recommendation_pipeline",
                side_effect=RuntimeError("private handoff detail"),
            ),
        ):
            failed = self.client.get(self.confirm_url)
        self.assertEqual(failed.status_code, 503)
        self.assertNotContains(failed, "private handoff detail", status_code=503)
        self.assertNotContains(failed, "Traceback", status_code=503)

    def test_accessibility_and_source_boundaries(self):
        response = self._get_review()
        html = response.content.decode("utf-8")
        self.assertContains(response, "<h1", status_code=200)
        self.assertContains(response, "<h2", status_code=200)
        self.assertContains(response, "<caption>", status_code=200)
        self.assertContains(response, 'scope="col"', status_code=200)
        self.assertContains(response, 'scope="row"', status_code=200)
        self.assertContains(response, 'aria-live="polite"', status_code=200)
        self.assertContains(response, "data-loading-form", status_code=200)
        self.assertIn("data-table-shell", html)

        handoff_sources = (
            Path(__file__).resolve().parents[1] / "orchestration/assignment_handoff.py",
            Path(__file__).resolve().parents[1] / "presenters/assignment_handoff.py",
            Path(__file__).resolve().parents[1] / "views/assignment_handoff.py",
            Path(__file__).resolve().parents[1]
            / "templates/frontend/recommendations/confirm.html",
            Path(__file__).resolve().parents[1] / "static/frontend/js/app.js",
        )
        combined = "\n".join(
            path.read_text(encoding="utf-8").lower() for path in handoff_sources
        )
        for forbidden in (
            "calculate_employee_project_match(",
            "calculate_team_score(",
            "find_all_feasible_teams(",
            "find_pareto_teams(",
            "select_recommended_teams(",
            "compare_recommendations(",
            "build_recommendation_explanations(",
            "solve_team_effort_allocation(",
            "generate_manager_summar",
            "attendance.objects",
            "ortools",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)

    def test_query_baselines_for_review_and_save(self):
        with patch(
            "frontend.views.assignment_handoff.run_recommendation_pipeline",
            return_value=self._pipeline_result(),
        ):
            with CaptureQueriesContext(connection) as review_queries:
                review = self.client.get(self.confirm_url)
            self.assertEqual(review.status_code, 200)
            review_count = len(review_queries)
            token = review.context["review"]["form"][
                "submission_token"
            ].value()
            with CaptureQueriesContext(connection) as save_queries:
                saved = self.client.post(
                    self.confirm_url, {"submission_token": token}
                )
            self.assertEqual(saved.status_code, 302)
            save_count = len(save_queries)

        durations = []
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with patch(
                "frontend.views.assignment_handoff."
                "run_recommendation_pipeline",
                return_value=self._pipeline_result(),
            ):
                Assignment.objects.filter(
                    project=self.project,
                    employee=self.employee,
                ).delete()
                started_at = time.perf_counter()
                response = self.client.get(self.confirm_url)
                durations.append((time.perf_counter() - started_at) * 1000)
                self.assertIn(response.status_code, (200, 422))
                if response.status_code == 200:
                    confirm_token = response.context["review"]["form"][
                        "submission_token"
                    ].value()
                    posted = self.client.post(
                        self.confirm_url,
                        {"submission_token": confirm_token},
                    )
                    self.assertEqual(posted.status_code, 302)
        print(
            "\nM6.7 staffing-confirmation baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm review GETs, pipeline mocked):\n"
            f"  review_queries={review_count}, save_queries={save_count}, "
            f"median={statistics.median(durations):.3f} ms, "
            f"response={len(review.content)} bytes"
        )
