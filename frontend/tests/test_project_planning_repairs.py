import inspect
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
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
from frontend.navigation import get_planning_return_url
from frontend.presenters.planning_navigation import _readiness_actions
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)


class ProjectPlanningRepairNavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.hr = cls._group_user("repair-hr", HR_ADMINISTRATOR_GROUP)
        cls.manager = cls._group_user("repair-manager", MANAGER_PLANNER_GROUP)
        cls.viewer = cls._group_user("repair-viewer", VIEWER_GROUP)

        required_read_codenames = (
            "view_project",
            "view_projectskillrequirement",
            "view_assignment",
            "view_assignmentskill",
            "view_employee",
            "view_skill",
        )
        cls.restricted = get_user_model().objects.create_user(
            username="repair-without-leave"
        )
        cls.restricted.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="core",
                codename__in=required_read_codenames,
            )
        )

        cls.python = Skill.objects.create(name="Python", category="Engineering")
        cls.sql = Skill.objects.create(name="SQL", category="Data")
        cls.ruby = Skill.objects.create(name="Ruby", category="Engineering")
        cls.project = Project.objects.create(
            name="Repair navigation project",
            description="Test existing workflow continuity.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            estimated_hours=Decimal("20.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.MEDIUM,
        )
        cls.other_project = Project.objects.create(
            name="Other planning project",
            description="A cross-project return target.",
            start_date=date(2026, 10, 5),
            end_date=date(2026, 10, 9),
            estimated_hours=Decimal("10.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )
        cls.requirement = ProjectSkillRequirement.objects.create(
            project=cls.project,
            skill=cls.python,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=Decimal("20.00"),
        )
        cls.optional_requirement = ProjectSkillRequirement.objects.create(
            project=cls.project,
            skill=cls.sql,
            required_level=2,
            priority=ProjectSkillRequirement.Priority.MEDIUM,
            is_mandatory=False,
            required_quantity=1,
            estimated_effort_hours=Decimal("5.00"),
        )

        cls.qualified = cls._employee("Quinn", "Qualified", status="active")
        cls.qualified_skill = EmployeeSkill.objects.create(
            employee=cls.qualified,
            skill=cls.python,
            level=3,
            years_experience=Decimal("3.0"),
        )
        cls.unqualified = cls._employee("Uma", "Unqualified", status="active")
        cls.unqualified_skill = EmployeeSkill.objects.create(
            employee=cls.unqualified,
            skill=cls.python,
            level=2,
            years_experience=Decimal("1.0"),
        )
        cls.inactive = cls._employee("Ian", "Inactive", status="inactive")
        EmployeeSkill.objects.create(
            employee=cls.inactive,
            skill=cls.python,
            level=4,
            years_experience=Decimal("4.0"),
        )
        cls.second_qualified = cls._employee(
            "Sam",
            "Staffable",
            status="active",
        )
        EmployeeSkill.objects.create(
            employee=cls.second_qualified,
            skill=cls.python,
            level=3,
            years_experience=Decimal("2.0"),
        )
        cls.assignment = Assignment.objects.create(
            employee=cls.qualified,
            project=cls.project,
            start_date=cls.project.start_date,
            end_date=cls.project.end_date,
            allocation_percentage=25,
            role_on_project="Python engineer",
            status=Assignment.Status.ACTIVE,
        )
        cls.coverage = AssignmentSkill.objects.create(
            assignment=cls.assignment,
            project_skill_requirement=cls.requirement,
        )
        cls.leave = Leave.objects.create(
            employee=cls.qualified,
            start_date=date(2026, 9, 9),
            end_date=date(2026, 9, 9),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )

    @classmethod
    def _group_user(cls, username, group_name):
        user = get_user_model().objects.create_user(username=username)
        user.groups.add(Group.objects.get(name=group_name))
        return user

    @classmethod
    def _employee(cls, first_name, last_name, *, status):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Engineering",
            position="Engineer",
            hire_date=date(2021, 1, 4),
            experience_years=Decimal("4.0"),
            capacity_hours_week=Decimal("40.00"),
            status=status,
        )

    def setUp(self):
        self.planning_url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )
        self.return_query = urlencode({"return_to": self.planning_url})

    def _get_workspace(self, user=None):
        self.client.force_login(user or self.hr)
        response = self.client.get(self.planning_url)
        self.assertEqual(response.status_code, 200)
        return response, response.context["workspace"]

    def _assert_return_url(self, url, expected_route):
        parts = urlsplit(url)
        self.assertEqual(
            parse_qs(parts.query)["return_to"],
            [self.planning_url],
        )
        self.assertEqual(parts.path, expected_route)

    def test_workspace_maps_project_requirement_assignment_and_candidate_actions(self):
        response, workspace = self._get_workspace(self.hr)

        self._assert_return_url(
            workspace["repair"]["project_edit_url"],
            reverse("frontend:project_update", args=[self.project.pk]),
        )
        self._assert_return_url(
            workspace["repair"]["requirement_create_url"],
            reverse("frontend:project_requirement_create", args=[self.project.pk]),
        )
        self._assert_return_url(
            workspace["repair"]["assignment_create_url"],
            reverse("frontend:project_assignment_create", args=[self.project.pk]),
        )

        requirement_row = next(
            row
            for row in workspace["requirement_evidence"]["rows"]
            if row["requirement"].pk == self.requirement.pk
        )
        action_labels = [
            action["label"] for action in requirement_row["repair_actions"]
        ]
        self.assertIn("Edit requirement", action_labels)
        self.assertIn("Review employee skill evidence", action_labels)
        self.assertTrue(
            workspace["assignments"][0].repair_coverage_url.endswith(
                f"?{self.return_query}"
            )
        )
        self.assertTrue(workspace["assignments"][0].repair_edit_url)

        exclusions = {
            row["employee"]: row
            for row in workspace["candidate_exclusions"]["rows"]
        }
        self.assertEqual(
            exclusions[self.inactive]["repair_action"]["label"],
            "Update employee status",
        )
        self.assertEqual(
            exclusions[self.unqualified]["repair_action"]["label"],
            "Manage employee skills",
        )
        for row in workspace["candidates"]["rows"]:
            query = parse_qs(urlsplit(row["profile_url"]).query)
            self.assertEqual(query["start_date"], ["2026-09-07"])
            self.assertEqual(query["end_date"], ["2026-09-11"])
            self.assertEqual(query["return_to"], [self.planning_url])

        self.assertContains(
            response,
            "Repair links keep this workspace as your return point.",
        )
        self.assertContains(response, "Edit project details")
        self.assertContains(response, "Review assignment coverage")
        self.assertNotContains(response, "Saving requirement…")
        self.assertNotContains(response, "Saving assignment…")

    def test_incomplete_and_readiness_states_map_to_existing_workflows(self):
        self.client.force_login(self.hr)
        self.requirement.estimated_effort_hours = None
        self.requirement.save(update_fields=["estimated_effort_hours"])
        response = self.client.get(self.planning_url)
        blocker = next(
            blocker
            for blocker in response.context["workspace"]["readiness"]["blockers"]
            if blocker["code"] == "mandatory_effort_must_be_positive"
        )
        self.assertEqual(
            blocker["repair_actions"][0]["label"],
            "Enter requirement effort",
        )
        self._assert_return_url(
            blocker["repair_actions"][0]["url"],
            reverse(
                "frontend:project_requirement_update",
                args=[self.project.pk, self.requirement.pk],
            ),
        )

        self.requirement.estimated_effort_hours = Decimal("80.00")
        self.requirement.save(update_fields=["estimated_effort_hours"])
        response = self.client.get(self.planning_url)
        capacity_blocker = next(
            blocker
            for blocker in response.context["workspace"]["readiness"]["blockers"]
            if blocker["code"] == "insufficient_qualified_capacity"
        )
        labels = [action["label"] for action in capacity_blocker["repair_actions"]]
        self.assertEqual(
            labels,
            ["Review requirement evidence", "Review approved leave"],
        )
        leave_action = capacity_blocker["repair_actions"][1]
        leave_query = parse_qs(urlsplit(leave_action["url"]).query)
        self.assertEqual(leave_query["status"], ["approved"])
        self.assertEqual(leave_query["from_date"], ["2026-09-07"])
        self.assertEqual(leave_query["to_date"], ["2026-09-11"])
        self.assertEqual(leave_query["return_to"], [self.planning_url])

        self.requirement.is_mandatory = False
        self.requirement.save(update_fields=["is_mandatory"])
        response = self.client.get(self.planning_url)
        no_mandatory = next(
            blocker
            for blocker in response.context["workspace"]["readiness"]["blockers"]
            if blocker["code"] == "no_mandatory_requirements"
        )
        self.assertEqual(
            [action["label"] for action in no_mandatory["repair_actions"]],
            ["Add mandatory requirement", "Review stored requirements"],
        )

    def test_every_readiness_code_has_a_deterministic_destination(self):
        cases = (
            (
                {"code": "invalid_project_dates"},
                ["Edit project schedule"],
            ),
            (
                {
                    "code": "mandatory_effort_must_be_positive",
                    "requirement": self.requirement,
                },
                ["Enter requirement effort", "Review requirement evidence"],
            ),
            (
                {"code": "no_mandatory_requirements"},
                ["Add mandatory requirement", "Review stored requirements"],
            ),
            (
                {"code": "stale_planning_inputs"},
                ["Refresh planning workspace"],
            ),
            (
                {
                    "code": "insufficient_eligible_headcount",
                    "requirement": self.requirement,
                },
                ["Review requirement evidence"],
            ),
            (
                {
                    "code": "insufficient_qualified_capacity",
                    "requirement": self.requirement,
                },
                ["Review requirement evidence", "Review approved leave"],
            ),
        )
        for blocker, expected_labels in cases:
            with self.subTest(code=blocker["code"]):
                actions = _readiness_actions(
                    self.project,
                    blocker,
                    self.hr,
                    self.planning_url,
                )
                self.assertEqual(
                    [action["label"] for action in actions],
                    expected_labels,
                )
                for action in actions:
                    if action["url"].startswith("/"):
                        query = parse_qs(urlsplit(action["url"]).query)
                        if action["label"] != "Refresh planning workspace":
                            self.assertEqual(
                                query.get("return_to"),
                                [self.planning_url],
                            )

    def test_permission_combinations_hide_mutation_links_and_leave_evidence(self):
        viewer_response, viewer_workspace = self._get_workspace(self.viewer)
        self.assertTrue(viewer_workspace["repair"]["is_read_only"])
        self.assertIsNone(viewer_workspace["repair"]["project_edit_url"])
        self.assertIsNone(viewer_workspace["repair"]["requirement_create_url"])
        self.assertIsNone(viewer_workspace["repair"]["assignment_create_url"])
        self.assertNotContains(viewer_response, "Edit project details")
        self.assertNotContains(viewer_response, "Edit requirement")
        self.assertNotContains(viewer_response, "Edit assignment")
        self.assertNotContains(viewer_response, "Manage employee skills")
        self.assertContains(viewer_response, "Read-only access")

        self.requirement.estimated_effort_hours = Decimal("80.00")
        self.requirement.save(update_fields=["estimated_effort_hours"])
        restricted_response, restricted_workspace = self._get_workspace(self.restricted)
        self.assertTrue(restricted_workspace["repair"]["leave_restricted"])
        self.assertIsNone(restricted_workspace["repair"]["leave_url"])
        self.assertNotContains(restricted_response, reverse("frontend:leave_list"))
        self.assertContains(
            restricted_response,
            "your access does not include leave records",
        )

        manager_response, manager_workspace = self._get_workspace(self.manager)
        self.assertIsNotNone(manager_workspace["repair"]["project_edit_url"])
        self.assertIsNotNone(manager_workspace["repair"]["requirement_create_url"])
        self.assertIsNotNone(manager_workspace["repair"]["assignment_create_url"])
        self.assertNotContains(manager_response, "Manage employee skills")
        self.assertContains(manager_response, "Review approved leave")

    def test_project_requirement_and_assignment_saves_return_to_workspace(self):
        self.client.force_login(self.hr)
        project_update = reverse("frontend:project_update", args=[self.project.pk])
        response = self.client.post(
            f"{project_update}?{self.return_query}",
            {
                "name": "Repair navigation project updated",
                "description": self.project.description,
                "start_date": "2026-09-07",
                "end_date": "2026-09-11",
                "estimated_hours": "20.00",
                "status": Project.Status.PLANNED,
                "priority": Project.Priority.HIGH,
                "criticality": Project.Criticality.MEDIUM,
            },
        )
        self.assertRedirects(response, self.planning_url, fetch_redirect_response=False)

        requirement_update = reverse(
            "frontend:project_requirement_update",
            args=[self.project.pk, self.requirement.pk],
        )
        response = self.client.post(
            f"{requirement_update}?{self.return_query}",
            {
                "skill": self.python.pk,
                "required_level": "3",
                "priority": ProjectSkillRequirement.Priority.HIGH,
                "is_mandatory": "on",
                "required_quantity": "1",
                "estimated_effort_hours": "20.00",
            },
        )
        self.assertRedirects(response, self.planning_url, fetch_redirect_response=False)

        assignment_update = reverse(
            "frontend:project_assignment_update",
            args=[self.project.pk, self.assignment.pk],
        )
        response = self.client.post(
            f"{assignment_update}?{self.return_query}",
            {
                "employee": self.qualified.pk,
                "start_date": "2026-09-07",
                "end_date": "2026-09-08",
                "allocation_percentage": "30",
                "role_on_project": "Python lead",
                "status": Assignment.Status.ACTIVE,
            },
        )
        self.assertRedirects(response, self.planning_url, fetch_redirect_response=False)

    def test_coverage_employee_skill_and_leave_saves_return_to_workspace(self):
        self.client.force_login(self.hr)
        EmployeeSkill.objects.create(
            employee=self.qualified,
            skill=self.sql,
            level=3,
            years_experience=Decimal("2.0"),
        )
        coverage_create = reverse(
            "frontend:project_assignment_coverage_create",
            args=[self.project.pk, self.assignment.pk],
        )
        response = self.client.post(
            f"{coverage_create}?{self.return_query}",
            {"project_skill_requirement": self.optional_requirement.pk},
        )
        self.assertRedirects(response, self.planning_url, fetch_redirect_response=False)

        proficiency_update = reverse(
            "frontend:employee_skill_update",
            args=[self.unqualified.pk, self.unqualified_skill.pk],
        )
        response = self.client.post(
            f"{proficiency_update}?{self.return_query}",
            {"level": "3", "years_experience": "2.0"},
        )
        self.assertRedirects(response, self.planning_url, fetch_redirect_response=False)

        leave_update = reverse("frontend:leave_update", args=[self.leave.pk])
        response = self.client.post(
            f"{leave_update}?{self.return_query}",
            {
                "employee": self.qualified.pk,
                "type": Leave.Type.ANNUAL,
                "start_date": "2026-09-09",
                "end_date": "2026-09-09",
                "status": Leave.Status.PENDING,
            },
        )
        self.assertRedirects(response, self.planning_url, fetch_redirect_response=False)

    def test_create_status_and_delete_workflows_return_to_workspace(self):
        self.client.force_login(self.hr)
        requirement_create = reverse(
            "frontend:project_requirement_create",
            args=[self.project.pk],
        )
        response = self.client.post(
            f"{requirement_create}?{self.return_query}",
            {
                "skill": self.ruby.pk,
                "required_level": "2",
                "priority": ProjectSkillRequirement.Priority.LOW,
                "required_quantity": "1",
                "estimated_effort_hours": "4.00",
            },
        )
        self.assertRedirects(response, self.planning_url, fetch_redirect_response=False)

        assignment_create = reverse(
            "frontend:project_assignment_create",
            args=[self.project.pk],
        )
        response = self.client.post(
            f"{assignment_create}?{self.return_query}",
            {
                "employee": self.second_qualified.pk,
                "start_date": "2026-09-07",
                "end_date": "2026-09-11",
                "allocation_percentage": "25",
                "role_on_project": "Python support",
                "status": Assignment.Status.PLANNED,
            },
        )
        self.assertRedirects(response, self.planning_url, fetch_redirect_response=False)

        employee_update = reverse(
            "frontend:employee_update",
            args=[self.inactive.pk],
        )
        response = self.client.post(
            f"{employee_update}?{self.return_query}",
            {
                "first_name": self.inactive.first_name,
                "last_name": self.inactive.last_name,
                "department": self.inactive.department,
                "position": self.inactive.position,
                "hire_date": self.inactive.hire_date.isoformat(),
                "experience_years": str(self.inactive.experience_years),
                "capacity_hours_week": str(self.inactive.capacity_hours_week),
                "status": Employee.Status.ACTIVE,
            },
        )
        self.assertRedirects(response, self.planning_url, fetch_redirect_response=False)

        proficiency_create = reverse(
            "frontend:employee_skill_create",
            args=[self.unqualified.pk],
        )
        response = self.client.post(
            f"{proficiency_create}?{self.return_query}",
            {
                "employee": self.unqualified.pk,
                "skill": self.sql.pk,
                "level": "2",
                "years_experience": "1.0",
            },
        )
        self.assertRedirects(response, self.planning_url, fetch_redirect_response=False)

        leave_delete = reverse("frontend:leave_delete", args=[self.leave.pk])
        response = self.client.post(f"{leave_delete}?{self.return_query}")
        self.assertRedirects(response, self.planning_url, fetch_redirect_response=False)
        self.assertFalse(Leave.objects.filter(pk=self.leave.pk).exists())

    def test_destination_pages_keep_supported_context_and_handle_zero_results(self):
        self.client.force_login(self.hr)
        response, workspace = self._get_workspace(self.hr)
        profile_url = workspace["candidates"]["rows"][0]["profile_url"]
        profile = self.client.get(profile_url)
        self.assertContains(profile, "Project planning context preserved.")
        self.assertContains(profile, f'href="{self.planning_url}"')
        self.assertContains(
            profile,
            f'name="return_to" value="{self.planning_url}"',
        )
        self.assertIn(self.return_query, profile.context["employee_update_url"])

        leave_url = workspace["repair"]["leave_url"]
        Leave.objects.all().delete()
        empty_leave = self.client.get(leave_url)
        self.assertEqual(empty_leave.status_code, 200)
        self.assertContains(
            empty_leave,
            "No approved leave overlaps this project period",
        )
        self.assertContains(empty_leave, "Return to planning workspace")
        self.assertContains(
            empty_leave,
            f'name="return_to" value="{self.planning_url}"',
        )

        coverage_url = workspace["assignments"][0].repair_coverage_url
        coverage = self.client.get(coverage_url)
        self.assertContains(coverage, "Project planning context preserved.")
        self.assertContains(coverage, "Return to planning workspace")

    def test_return_allow_list_rejects_external_cross_project_and_stale_targets(self):
        self.client.force_login(self.hr)
        update_url = reverse("frontend:project_update", args=[self.project.pk])
        detail_url = reverse("frontend:project_detail", args=[self.project.pk])
        for invalid_return in (
            "https://example.com/steal",
            reverse("frontend:project_list"),
            reverse("frontend:project_planning", args=[self.other_project.pk]),
            f"{self.planning_url}?unexpected=1",
        ):
            with self.subTest(invalid_return=invalid_return):
                response = self.client.get(
                    f"{update_url}?{urlencode({'return_to': invalid_return})}"
                )
                self.assertEqual(response.context["cancel_url"], detail_url)
                self.assertNotContains(response, "Return to planning workspace")

        stale_project = Project.objects.create(
            name="Deleted return target",
            description="Deleted before navigation.",
            start_date=date(2026, 11, 2),
            end_date=date(2026, 11, 6),
            estimated_hours=Decimal("8.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.LOW,
            criticality=Project.Criticality.LOW,
        )
        stale_return = reverse(
            "frontend:project_planning",
            args=[stale_project.pk],
        )
        stale_project.delete()
        employee_update = reverse(
            "frontend:employee_update",
            args=[self.qualified.pk],
        )
        response = self.client.get(
            f"{employee_update}?{urlencode({'return_to': stale_return})}"
        )
        self.assertEqual(
            response.context["cancel_url"],
            reverse("frontend:employee_detail", args=[self.qualified.pk]),
        )

        missing_requirement = reverse(
            "frontend:project_requirement_update",
            args=[self.project.pk, 999999],
        )
        self.assertEqual(
            self.client.get(f"{missing_requirement}?{self.return_query}").status_code,
            404,
        )
        missing_assignment = reverse(
            "frontend:project_assignment_coverage",
            args=[self.project.pk, 999999],
        )
        self.assertEqual(
            self.client.get(f"{missing_assignment}?{self.return_query}").status_code,
            404,
        )

    def test_workspace_remains_get_only_and_navigation_adds_no_calculations(self):
        self.client.force_login(self.hr)
        counts_before = (
            Project.objects.count(),
            ProjectSkillRequirement.objects.count(),
            Assignment.objects.count(),
            AssignmentSkill.objects.count(),
            EmployeeSkill.objects.count(),
            Leave.objects.count(),
        )
        self.assertEqual(self.client.post(self.planning_url).status_code, 405)
        self.assertEqual(
            counts_before,
            (
                Project.objects.count(),
                ProjectSkillRequirement.objects.count(),
                Assignment.objects.count(),
                AssignmentSkill.objects.count(),
                EmployeeSkill.objects.count(),
                Leave.objects.count(),
            ),
        )

        source = inspect.getsource(get_planning_return_url).lower()
        self.assertNotIn("redirect_to_login", source)
        navigation_source = (
            Path(__file__).resolve().parents[1]
            / "presenters"
            / "planning_navigation.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "rank_employees_for_project(",
            "calculate_available_hours_for_project(",
            "get_fast_feasibility_issues(",
            "solve_team_effort_allocation(",
            "find_all_feasible_teams(",
            "select_recommended_teams(",
            "attendance.objects",
            "gemini",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, navigation_source)
