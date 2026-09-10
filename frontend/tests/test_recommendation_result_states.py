"""M6.6 result states and recovery paths.

Covers the remaining M6.6 scope around the existing pipeline without
recalculating backend values: distinct readiness blockers, no-feasible-team,
no-recommendation, one/two/three outcomes, stale/deleted detection, stage and
enrichment failures, permission-aware recovery, retry behaviour, safe copy,
and proof that cheap preflight stops expensive work.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import Client, TestCase
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
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)
from frontend.selectors.recommendations import get_recommendation_input_snapshot


class RecommendationResultStateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = cls._role_user("m66-state-viewer", VIEWER_GROUP)
        cls.manager = cls._role_user(
            "m66-state-manager", MANAGER_PLANNER_GROUP
        )
        cls.hr_user = cls._role_user(
            "m66-state-hr", HR_ADMINISTRATOR_GROUP
        )
        cls.unassigned = get_user_model().objects.create_user(
            username="m66-state-unassigned"
        )

        cls.python = Skill.objects.create(
            name="Python", category="Engineering"
        )
        cls.go_skill = Skill.objects.create(
            name="Go", category="Engineering"
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
        cls.inactive_employee = Employee.objects.create(
            first_name="Ina",
            last_name="Inactive",
            department="Engineering",
            position="Engineer",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("6.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.INACTIVE,
        )
        EmployeeSkill.objects.create(
            employee=cls.inactive_employee,
            skill=cls.python,
            level=4,
            years_experience=Decimal("4.0"),
        )

        cls.project = cls._project(name="M66 valid project")
        cls.requirement = cls._requirement(cls.project)

        cls.missing_effort_project = cls._project(
            name="M66 missing effort"
        )
        ProjectSkillRequirement.objects.create(
            project=cls.missing_effort_project,
            skill=cls.python,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=None,
        )

        cls.no_mandatory_project = cls._project(name="M66 optional only")
        ProjectSkillRequirement.objects.create(
            project=cls.no_mandatory_project,
            skill=cls.python,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=False,
            required_quantity=1,
            estimated_effort_hours=Decimal("8.00"),
        )

        cls.empty_project = cls._project(name="M66 no requirements")

        cls.no_eligible_project = cls._project(name="M66 no eligible")
        ProjectSkillRequirement.objects.create(
            project=cls.no_eligible_project,
            skill=cls.go_skill,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=Decimal("8.00"),
        )

        cls.headcount_project = cls._project(name="M66 headcount gap")
        ProjectSkillRequirement.objects.create(
            project=cls.headcount_project,
            skill=cls.python,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=2,
            estimated_effort_hours=Decimal("8.00"),
        )

        cls.capacity_project = cls._project(name="M66 capacity gap")
        ProjectSkillRequirement.objects.create(
            project=cls.capacity_project,
            skill=cls.python,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=Decimal("80.00"),
        )

    @staticmethod
    def _role_user(username, role):
        user = get_user_model().objects.create_user(username=username)
        user.groups.add(Group.objects.get(name=role))
        return user

    @staticmethod
    def _project(
        *,
        name,
        start_date=date(2026, 9, 7),
        end_date=date(2026, 9, 11),
    ):
        return Project.objects.create(
            name=name,
            description="M6.6 result-state fixture.",
            start_date=start_date,
            end_date=end_date,
            estimated_hours=Decimal("8.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )

    @classmethod
    def _requirement(cls, project, **overrides):
        values = {
            "skill": cls.python,
            "required_level": 3,
            "priority": ProjectSkillRequirement.Priority.HIGH,
            "is_mandatory": True,
            "required_quantity": 1,
            "estimated_effort_hours": Decimal("8.00"),
        }
        values.update(overrides)
        return ProjectSkillRequirement.objects.create(
            project=project, **values
        )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.viewer)

    def _generate_url(self, project):
        return reverse(
            "frontend:project_recommendation_generate",
            args=[project.project_id],
        )

    def _planning_url(self, project):
        return reverse(
            "frontend:project_planning",
            args=[project.project_id],
        )

    def _submission_token(self, project, client=None):
        client = client or self.client
        response = client.get(self._planning_url(project))
        self.assertEqual(response.status_code, 200)
        form = response.context["recommendation_generation"]["form"]
        self.assertIsNotNone(form)
        return form["submission_token"].value()

    def _direct_token(self, project, user=None):
        from frontend.recommendation_execution import (
            issue_recommendation_submission_token,
        )

        user = user or self.viewer
        snapshot = get_recommendation_input_snapshot(project.project_id)
        return issue_recommendation_submission_token(
            project_id=project.project_id,
            user_id=user.pk,
            input_signature=snapshot["signature"],
        )

    def _pipeline_result(self, *, count=1, feasible=("feasible",)):
        definitions = (
            ("compact_match", "Best compact match"),
            ("balanced", "Best balanced alternative"),
            ("capacity", "Best capacity alternative"),
        )
        recommendations = [
            {
                "category": definitions[index][0],
                "label": definitions[index][1],
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
        ]
        return {
            "feasible_teams": list(feasible),
            "pareto_teams": ["pareto"] if count or feasible else [],
            "recommendations": recommendations,
            "comparisons": [],
            "explanations": [
                {
                    "category": item["category"],
                    "label": item["label"],
                    "team": [str(self.employee)],
                    "strengths": ["Existing deterministic strength."],
                    "tradeoffs": ["Existing deterministic trade-off."],
                }
                for item in recommendations
            ],
            "elapsed_seconds": 0.25,
        }

    def _post(self, project, token):
        return self.client.post(
            self._generate_url(project),
            {"submission_token": token},
        )

    def test_readiness_blockers_return_distinct_truthful_states(self):
        cases = (
            (
                self.missing_effort_project,
                "mandatory_effort_must_be_positive",
                "Requirement effort needed",
            ),
            (
                self.no_mandatory_project,
                "no_mandatory_requirements",
                "Mandatory requirements needed",
            ),
            (
                self.empty_project,
                "no_mandatory_requirements",
                "Mandatory requirements needed",
            ),
            (
                self.no_eligible_project,
                "no_eligible_employees",
                "No eligible employees",
            ),
            (
                self.headcount_project,
                "insufficient_eligible_headcount",
                "Qualified headcount is insufficient",
            ),
            (
                self.capacity_project,
                "insufficient_qualified_capacity",
                "Qualified capacity is insufficient",
            ),
        )
        for project, state, label in cases:
            with (
                self.subTest(project=project.name),
                patch(
                    "frontend.views.recommendations.run_recommendation_pipeline"
                ) as pipeline,
                patch(
                    "frontend.views.recommendations."
                    "build_optional_manager_summaries"
                ) as enrichment,
            ):
                response = self._post(
                    project, self._direct_token(project)
                )
            pipeline.assert_not_called()
            enrichment.assert_not_called()
            self.assertEqual(response.status_code, 422)
            run = response.context["run"]
            self.assertEqual(run["state"], state)
            self.assertEqual(run["result_variant"], "planning_blocked")
            self.assertIsNone(run["recommendation_count"])
            self.assertIsNone(run["elapsed_seconds"])
            self.assertIsNone(run["pipeline_result"])
            self.assertContains(response, label, status_code=422)
            self.assertContains(
                response,
                "stopped before team search",
                status_code=422,
            )
            self.assertContains(
                response,
                "Review current planning information",
                status_code=422,
            )
            self.assertContains(
                response,
                f"{self._planning_url(project)}#",
                status_code=422,
            )
            self.assertContains(
                response,
                "This run did not change staffing records.",
                status_code=422,
            )

    def test_invalid_dates_blocker_without_storing_invalid_row(self):
        blocker = {
            "code": "invalid_project_dates",
            "message": "Project dates are invalid.",
        }
        assessment = {
            "stored_context": {},
            "readiness": {
                "candidate_assessment_allowed": False,
                "blockers": [blocker],
            },
            "requirement_assessment_context": None,
        }
        with (
            patch(
                "frontend.views.recommendations."
                "build_project_planning_readiness",
                return_value=assessment,
            ),
            patch(
                "frontend.views.recommendations.run_recommendation_pipeline"
            ) as pipeline,
            patch(
                "frontend.views.recommendations."
                "build_optional_manager_summaries"
            ) as enrichment,
        ):
            response = self._post(
                self.project, self._submission_token(self.project)
            )
        pipeline.assert_not_called()
        enrichment.assert_not_called()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.context["run"]["state"], "invalid_project_dates"
        )
        self.assertContains(
            response, "Project schedule needs review", status_code=422
        )

    def test_cheap_preflight_stops_expensive_services(self):
        with (
            patch(
                "frontend.views.recommendations.run_recommendation_pipeline"
            ) as pipeline,
            patch(
                "frontend.views.recommendations."
                "build_optional_manager_summaries"
            ) as enrichment,
        ):
            response = self._post(
                self.missing_effort_project,
                self._direct_token(self.missing_effort_project),
            )
        self.assertEqual(response.status_code, 422)
        pipeline.assert_not_called()
        enrichment.assert_not_called()

    def test_no_feasible_team_and_no_recommendation_are_distinct(self):
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=self._pipeline_result(count=0, feasible=()),
        ):
            empty = self._post(
                self.project, self._submission_token(self.project)
            )
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.context["run"]["state"], "no_feasible_team")
        self.assertEqual(
            empty.context["run"]["result_variant"], "no_feasible_team"
        )
        self.assertContains(empty, "No feasible team is available")
        self.assertContains(empty, "all mandatory coverage")
        self.assertContains(empty, "planning-requirement-evidence-title")

        feasible_only = self._pipeline_result(count=0, feasible=("feasible",))
        feasible_only["pareto_teams"] = ["pareto"]
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=feasible_only,
        ):
            missing = self._post(
                self.project, self._submission_token(self.project)
            )
        self.assertEqual(missing.status_code, 200)
        self.assertEqual(missing.context["run"]["state"], "no_recommendation")
        self.assertContains(missing, "No comparison strategy selected")
        self.assertContains(missing, "planning-candidates-title")
        self.assertNotEqual(
            empty.context["run"]["title"],
            missing.context["run"]["title"],
        )

    def test_one_two_three_strategy_outcomes_preserve_order(self):
        for count, variant in (
            (1, "one_strategy"),
            (2, "two_strategies"),
            (3, "three_strategies"),
        ):
            with self.subTest(count=count):
                result = self._pipeline_result(count=count)
                with patch(
                    "frontend.views.recommendations."
                    "run_recommendation_pipeline",
                    return_value=result,
                ):
                    response = self._post(
                        self.project, self._submission_token(self.project)
                    )
                self.assertEqual(response.status_code, 200)
                run = response.context["run"]
                self.assertEqual(run["state"], "completed")
                self.assertEqual(run["result_variant"], variant)
                self.assertEqual(run["recommendation_count"], count)
                self.assertIs(run["pipeline_result"], result)
                self.assertEqual(
                    [card["label"] for card in run["strategies"]["cards"]],
                    [item["label"] for item in result["recommendations"]],
                )
                self.assertIsNone(run["recovery"])

    def test_changed_inputs_return_stale_without_pipeline_work(self):
        token = self._submission_token(self.project)
        self.project.name = "M66 valid project changed"
        self.project.save()
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline"
        ) as pipeline:
            response = self._post(self.project, token)
        pipeline.assert_not_called()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.context["run"]["state"], "stale")
        self.assertContains(
            response,
            "no longer matches current data",
            status_code=409,
        )
        self.assertContains(
            response,
            "No mixed or outdated recommendation evidence",
            status_code=409,
        )

    def test_changed_snapshot_before_run_returns_stale(self):
        token = self._submission_token(self.project)
        starting = get_recommendation_input_snapshot(
            self.project.project_id
        )
        changed = dict(starting)
        changed["signature"] = f"{starting['signature']}-changed"
        with (
            patch(
                "frontend.views.recommendations."
                "get_recommendation_input_snapshot",
                side_effect=[starting, changed],
            ),
            patch(
                "frontend.views.recommendations.run_recommendation_pipeline"
            ) as pipeline,
        ):
            response = self._post(self.project, token)
        pipeline.assert_not_called()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.context["run"]["state"], "stale")

    def test_changed_snapshot_after_run_returns_stale(self):
        starting = get_recommendation_input_snapshot(
            self.project.project_id
        )
        changed = dict(starting)
        changed["signature"] = f"{starting['signature']}-changed"
        result = self._pipeline_result(count=1)
        with (
            patch(
                "frontend.views.recommendations."
                "get_recommendation_input_snapshot",
                side_effect=[starting, starting, changed],
            ),
            patch(
                "frontend.views.recommendations.run_recommendation_pipeline",
                return_value=result,
            ),
        ):
            response = self._post(
                self.project, self._submission_token(self.project)
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.context["run"]["state"], "stale")

    def test_deleted_project_during_run_returns_project_changed(self):
        starting = get_recommendation_input_snapshot(
            self.project.project_id
        )
        result = self._pipeline_result(count=1)
        with (
            patch(
                "frontend.views.recommendations."
                "get_recommendation_input_snapshot",
                side_effect=[
                    starting,
                    starting,
                    Project.DoesNotExist,
                ],
            ),
            patch(
                "frontend.views.recommendations.run_recommendation_pipeline",
                return_value=result,
            ),
        ):
            response = self._post(
                self.project, self._submission_token(self.project)
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.context["run"]["state"], "project_changed")
        self.assertContains(
            response, "Project no longer available", status_code=409
        )
        self.assertContains(
            response, "Return to projects", status_code=409
        )
        self.assertNotContains(
            response, "Return to planning workspace", status_code=409
        )

    def test_unknown_reference_in_result_returns_stale(self):
        result = self._pipeline_result(count=1)
        result["recommendations"][0]["result"]["team"] = [
            self.inactive_employee
        ]
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=result,
        ):
            response = self._post(
                self.project, self._submission_token(self.project)
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.context["run"]["state"], "stale")

    def test_each_pipeline_stage_failure_returns_safe_error(self):
        stages = (
            "frontend.orchestration.recommendations."
            "find_all_feasible_teams",
            "frontend.orchestration.recommendations.find_pareto_teams",
            "frontend.orchestration.recommendations.select_recommended_teams",
            "frontend.orchestration.recommendations.compare_recommendations",
            "frontend.orchestration.recommendations."
            "build_recommendation_explanations",
        )
        counts_before = (
            Project.objects.count(),
            ProjectSkillRequirement.objects.count(),
            Assignment.objects.count(),
            AssignmentSkill.objects.count(),
        )
        for stage in stages:
            with (
                self.subTest(stage=stage),
                self.assertLogs(
                    "frontend.views.recommendations", level="ERROR"
                ),
                patch(stage, side_effect=RuntimeError("private detail")),
            ):
                response = self._post(
                    self.project, self._submission_token(self.project)
                )
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.context["run"]["state"], "error")
            self.assertContains(
                response,
                "Recommendation generation could not be completed.",
                status_code=503,
            )
            self.assertNotContains(
                response, "private detail", status_code=503
            )
            self.assertNotContains(response, "Traceback", status_code=503)
        self.assertEqual(
            counts_before,
            (
                Project.objects.count(),
                ProjectSkillRequirement.objects.count(),
                Assignment.objects.count(),
                AssignmentSkill.objects.count(),
            ),
        )

    def test_incomplete_pipeline_envelope_returns_incomplete(self):
        result = self._pipeline_result(count=1)
        result["explanations"] = []
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=result,
        ):
            response = self._post(
                self.project, self._submission_token(self.project)
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.context["run"]["state"], "incomplete")
        self.assertContains(
            response,
            "could not be completed",
            status_code=503,
        )
        self.assertContains(
            response,
            "No partial recommendation is shown",
            status_code=503,
        )

    def test_enrichment_failure_keeps_deterministic_result(self):
        result = self._pipeline_result(count=1)
        with (
            patch(
                "frontend.views.recommendations.run_recommendation_pipeline",
                return_value=result,
            ),
            patch(
                "frontend.views.recommendations."
                "build_optional_manager_summaries",
                side_effect=RuntimeError("provider down"),
            ),
        ):
            response = self._post(
                self.project, self._submission_token(self.project)
            )
        self.assertEqual(response.status_code, 200)
        run = response.context["run"]
        self.assertEqual(run["state"], "completed")
        self.assertEqual(
            run["decision_evidence"]["enrichment"]["state"], "unavailable"
        )
        self.assertContains(response, "Existing deterministic strength.")
        self.assertNotContains(response, "provider down")

    def test_presentation_failure_returns_incomplete(self):
        with (
            patch(
                "frontend.views.recommendations.run_recommendation_pipeline",
                return_value=self._pipeline_result(count=1),
            ),
            patch(
                "frontend.views.recommendations."
                "build_recommendation_result_foundation",
                side_effect=RuntimeError("presenter down"),
            ),
            self.assertLogs(
                "frontend.views.recommendations", level="ERROR"
            ),
        ):
            response = self._post(
                self.project, self._submission_token(self.project)
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.context["run"]["state"], "incomplete")

    def test_stale_request_can_be_retried_with_fresh_token(self):
        stale_token = self._submission_token(self.project)
        self.project.name = "M66 retry fixture changed"
        self.project.save()
        stale = self._post(self.project, stale_token)
        self.assertEqual(stale.status_code, 409)

        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=self._pipeline_result(count=1),
        ):
            fresh = self._post(
                self.project, self._submission_token(self.project)
            )
        self.assertEqual(fresh.status_code, 200)
        self.assertEqual(fresh.context["run"]["state"], "completed")

    def test_recovery_links_are_permission_aware_with_return_context(self):
        manager_client = Client()
        manager_client.force_login(self.manager)

        def manager_token(project):
            return self._direct_token(project, user=self.manager)

        blocker = {
            "code": "invalid_project_dates",
            "message": "Project dates are invalid.",
        }
        assessment = {
            "stored_context": {},
            "readiness": {
                "candidate_assessment_allowed": False,
                "blockers": [blocker],
            },
            "requirement_assessment_context": None,
        }
        with patch(
            "frontend.views.recommendations."
            "build_project_planning_readiness",
            return_value=assessment,
        ):
            with patch(
                "frontend.views.recommendations.run_recommendation_pipeline"
            ) as pipeline:
                viewer_dates = self._post(
                    self.project,
                    self._submission_token(self.project),
                )
            pipeline.assert_not_called()
            self.assertEqual(viewer_dates.status_code, 422)
            self.assertContains(
                viewer_dates, "Review this planning evidence", status_code=422
            )
            self.assertNotContains(
                viewer_dates, "Edit project schedule", status_code=422
            )
            self.assertNotContains(
                viewer_dates, "return_to=", status_code=422
            )

            with patch(
                "frontend.views.recommendations.run_recommendation_pipeline"
            ) as pipeline:
                manager_dates = manager_client.post(
                    self._generate_url(self.project),
                    {"submission_token": manager_token(self.project)},
                )
            pipeline.assert_not_called()
            self.assertEqual(manager_dates.status_code, 422)
            self.assertContains(
                manager_dates, "Edit project schedule", status_code=422
            )
            self.assertContains(manager_dates, "return_to=", status_code=422)

        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline"
        ) as pipeline:
            viewer_effort = self._post(
                self.missing_effort_project,
                self._direct_token(self.missing_effort_project),
            )
        pipeline.assert_not_called()
        self.assertEqual(viewer_effort.status_code, 422)
        self.assertNotContains(
            viewer_effort, "Enter requirement effort", status_code=422
        )

        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline"
        ) as pipeline:
            manager_effort = manager_client.post(
                self._generate_url(self.missing_effort_project),
                {"submission_token": manager_token(
                    self.missing_effort_project
                )},
            )
        pipeline.assert_not_called()
        self.assertEqual(manager_effort.status_code, 422)
        self.assertContains(
            manager_effort, "Enter requirement effort", status_code=422
        )
        self.assertContains(manager_effort, "return_to=", status_code=422)

    def test_canonical_roles_and_unassigned_behaviour(self):
        for user in (self.viewer, self.manager, self.hr_user):
            role_client = Client()
            role_client.force_login(user)
            with patch(
                "frontend.views.recommendations.run_recommendation_pipeline",
                return_value=self._pipeline_result(count=1),
            ):
                response = role_client.post(
                    self._generate_url(self.project),
                    {
                        "submission_token": self._submission_token(
                            self.project, client=role_client
                        )
                    },
                )
            self.assertEqual(response.status_code, 200)

        unassigned_client = Client()
        unassigned_client.force_login(self.unassigned)
        self.assertEqual(
            unassigned_client.post(
                self._generate_url(self.project),
                {"submission_token": "anything"},
            ).status_code,
            403,
        )

    def test_recovery_preserves_canonical_return_destinations(self):
        with patch(
            "frontend.views.recommendations.run_recommendation_pipeline",
            return_value=self._pipeline_result(count=0, feasible=()),
        ):
            response = self._post(
                self.project, self._submission_token(self.project)
            )
        self.assertEqual(response.status_code, 200)
        recovery = response.context["run"]["recovery"]
        self.assertIsNotNone(recovery)
        planning_url = self._planning_url(self.project)
        self.assertTrue(
            recovery["actions"][0]["url"].startswith(planning_url)
        )
        self.assertContains(response, 'href="/projects/"')
        self.assertContains(
            response, "This run did not change staffing records."
        )
