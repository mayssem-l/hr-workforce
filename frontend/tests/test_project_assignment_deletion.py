import re
from datetime import date, time
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import DatabaseError
from django.test import Client, TestCase
from django.urls import resolve, reverse

from core.models import (
    Assignment,
    AssignmentSkill,
    Attendance,
    Employee,
    EmployeeSkill,
    Leave,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from frontend.presenters.deletions import (
    build_assignment_deletion_impact,
    build_project_deletion_impact,
)
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)
from frontend.selectors.deletions import (
    get_assignment_deletion_target,
    get_project_deletion_target,
)


class ProjectAssignmentDeletionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.hr_admin = cls._group_user("planning-delete-hr", HR_ADMINISTRATOR_GROUP)
        cls.manager = cls._group_user(
            "planning-delete-manager",
            MANAGER_PLANNER_GROUP,
        )
        cls.viewer = cls._group_user("planning-delete-viewer", VIEWER_GROUP)
        cls.project_delete_only = cls._permission_user(
            "project-delete-only",
            "delete_project",
        )
        cls.assignment_delete_only = cls._permission_user(
            "assignment-delete-only",
            "delete_assignment",
        )

        cls.python = Skill.objects.create(name="Python", category="Engineering")
        cls.django = Skill.objects.create(name="Django", category="Engineering")
        cls.sql = Skill.objects.create(name="SQL", category="Data")

        cls.project = cls._create_project("Atlas Renewal")
        cls.python_requirement = cls._create_requirement(
            cls.project,
            cls.python,
            level=4,
            quantity=2,
            mandatory=True,
        )
        cls.django_requirement = cls._create_requirement(
            cls.project,
            cls.django,
            level=3,
            quantity=1,
            mandatory=False,
        )

        cls.jamie = cls._create_employee("Jamie", "Rivera")
        cls.morgan = cls._create_employee("Morgan", "Lee")
        cls.jamie_python = EmployeeSkill.objects.create(
            employee=cls.jamie,
            skill=cls.python,
            level=5,
            years_experience=Decimal("6.0"),
        )
        cls.jamie_django = EmployeeSkill.objects.create(
            employee=cls.jamie,
            skill=cls.django,
            level=4,
            years_experience=Decimal("5.0"),
        )
        cls.morgan_python = EmployeeSkill.objects.create(
            employee=cls.morgan,
            skill=cls.python,
            level=4,
            years_experience=Decimal("4.0"),
        )
        cls.jamie_assignment = cls._create_assignment(
            cls.project,
            cls.jamie,
            role="Platform lead",
            status=Assignment.Status.PLANNED,
        )
        cls.morgan_assignment = cls._create_assignment(
            cls.project,
            cls.morgan,
            role="Backend engineer",
            status=Assignment.Status.ACTIVE,
        )
        cls.jamie_python_coverage = AssignmentSkill.objects.create(
            assignment=cls.jamie_assignment,
            project_skill_requirement=cls.python_requirement,
        )
        cls.jamie_django_coverage = AssignmentSkill.objects.create(
            assignment=cls.jamie_assignment,
            project_skill_requirement=cls.django_requirement,
        )
        cls.morgan_python_coverage = AssignmentSkill.objects.create(
            assignment=cls.morgan_assignment,
            project_skill_requirement=cls.python_requirement,
        )
        cls.jamie_leave = Leave.objects.create(
            employee=cls.jamie,
            start_date=date(2026, 11, 2),
            end_date=date(2026, 11, 3),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )
        cls.jamie_attendance = Attendance.objects.create(
            employee=cls.jamie,
            date=date(2026, 9, 15),
            status=Attendance.Status.PRESENT,
            arrival_time=time(9, 0),
            departure_time=time(17, 0),
        )

        cls.other_project = cls._create_project("Beacon Expansion")
        cls.other_requirement = cls._create_requirement(
            cls.other_project,
            cls.sql,
            level=3,
            quantity=1,
            mandatory=True,
        )
        cls.taylor = cls._create_employee("Taylor", "Morgan")
        cls.taylor_sql = EmployeeSkill.objects.create(
            employee=cls.taylor,
            skill=cls.sql,
            level=4,
            years_experience=Decimal("4.0"),
        )
        cls.other_assignment = cls._create_assignment(
            cls.other_project,
            cls.taylor,
            role="Data engineer",
            status=Assignment.Status.PLANNED,
        )
        cls.other_coverage = AssignmentSkill.objects.create(
            assignment=cls.other_assignment,
            project_skill_requirement=cls.other_requirement,
        )

    @classmethod
    def _group_user(cls, username, group_name):
        user = get_user_model().objects.create_user(username=username)
        user.groups.add(Group.objects.get(name=group_name))
        return user

    @classmethod
    def _permission_user(cls, username, codename):
        user = get_user_model().objects.create_user(username=username)
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename=codename,
            )
        )
        return user

    @staticmethod
    def _create_project(name):
        return Project.objects.create(
            name=name,
            description=f"Plan {name}.",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 31),
            estimated_hours=Decimal("400.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )

    @staticmethod
    def _create_requirement(project, skill, *, level, quantity, mandatory):
        return ProjectSkillRequirement.objects.create(
            project=project,
            skill=skill,
            required_level=level,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=mandatory,
            required_quantity=quantity,
            estimated_effort_hours=Decimal("100.00"),
        )

    @staticmethod
    def _create_employee(first_name, last_name):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Engineering",
            position="Software Engineer",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("6.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )

    @staticmethod
    def _create_assignment(project, employee, *, role, status):
        return Assignment.objects.create(
            employee=employee,
            project=project,
            start_date=project.start_date,
            end_date=project.end_date,
            allocation_percentage=50,
            role_on_project=role,
            status=status,
        )

    def setUp(self):
        self.project_detail_url = reverse(
            "frontend:project_detail",
            args=[self.project.project_id],
        )
        self.project_delete_url = reverse(
            "frontend:project_delete",
            args=[self.project.project_id],
        )
        self.assignment_delete_url = reverse(
            "frontend:project_assignment_delete",
            args=[self.project.project_id, self.jamie_assignment.assignment_id],
        )
        self.client.force_login(self.hr_admin)

    def csrf_token_for_action(self, response, action_url):
        pattern = re.compile(
            rf'<form method="post" action="{re.escape(action_url)}" '
            rf'data-loading-form>\s*'
            rf'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)">'
        )
        match = pattern.search(response.content.decode("utf-8"))
        self.assertIsNotNone(
            match,
            f"The deletion form for {action_url} must render its own CSRF input.",
        )
        return match.group(1)

    def test_delete_routes_are_namespaced_and_linked_for_permitted_users(self):
        self.assertEqual(
            self.project_delete_url,
            f"/projects/{self.project.project_id}/delete/",
        )
        self.assertEqual(
            resolve(self.project_delete_url).view_name,
            "frontend:project_delete",
        )
        self.assertEqual(
            self.assignment_delete_url,
            f"/projects/{self.project.project_id}/assignments/"
            f"{self.jamie_assignment.assignment_id}/delete/",
        )
        self.assertEqual(
            resolve(self.assignment_delete_url).view_name,
            "frontend:project_assignment_delete",
        )

        response = self.client.get(self.project_detail_url)
        self.assertContains(response, self.project_delete_url)
        self.assertContains(response, "Delete project")
        self.assertContains(response, self.assignment_delete_url)

        manager_client = Client()
        manager_client.force_login(self.manager)
        manager_response = manager_client.get(self.project_detail_url)
        self.assertNotContains(manager_response, self.project_delete_url)
        self.assertNotContains(manager_response, self.assignment_delete_url)

    def test_deletion_selectors_have_fixed_queries_and_exact_context(self):
        with self.assertNumQueries(4):
            project = get_project_deletion_target(self.project.project_id)
        self.assertEqual(
            [item.skill.name for item in project.deletion_requirements],
            ["Python", "Django"],
        )
        self.assertEqual(
            [str(item.employee) for item in project.deletion_assignments],
            ["Morgan Lee", "Jamie Rivera"],
        )
        self.assertEqual(project.deletion_coverage_count, 3)

        with self.assertNumQueries(2):
            assignment = get_assignment_deletion_target(
                self.project.project_id,
                self.jamie_assignment.assignment_id,
            )
        self.assertEqual(
            [
                link.project_skill_requirement.skill.name
                for link in assignment.deletion_coverage
            ],
            ["Django", "Python"],
        )

    def test_project_confirmation_explains_deleted_and_retained_information(self):
        project = get_project_deletion_target(self.project.project_id)
        impact = build_project_deletion_impact(project)
        self.assertEqual(impact["coverage_count"], 3)
        self.assertEqual(len(impact["requirements"]), 2)
        self.assertEqual(len(impact["assignments"]), 2)

        response = self.client.get(self.project_delete_url)
        self.assertTemplateUsed(response, "frontend/projects/confirm_delete.html")
        self.assertContains(response, "Delete this project?")
        self.assertContains(response, "What will be deleted")
        self.assertContains(
            response,
            "Deleting this project will also remove its skill requirements, "
            "employee assignments, and requirement coverage shown below.",
        )
        self.assertContains(response, "Python &mdash; Level 4 · 2 people needed")
        self.assertContains(response, "Django &mdash; Level 3 · 1 person needed")
        self.assertContains(response, "Morgan Lee &mdash; Backend engineer · Active")
        self.assertContains(response, "Jamie Rivera &mdash; Platform lead · Planned")
        self.assertContains(response, "3 coverage links")
        self.assertContains(
            response,
            "Employee profiles, skill definitions, leave records, and "
            "attendance history will not be deleted.",
        )
        for technical_phrase in (
            "AssignmentSkill",
            "database constraint",
            "Django cascade",
            "related records",
            "ORM",
        ):
            self.assertNotContains(response, technical_phrase)
        self.csrf_token_for_action(response, self.project_delete_url)

    def test_assignment_confirmation_explains_deleted_and_retained_information(self):
        assignment = get_assignment_deletion_target(
            self.project.project_id,
            self.jamie_assignment.assignment_id,
        )
        impact = build_assignment_deletion_impact(assignment)
        self.assertEqual(impact["coverage_count"], 2)

        response = self.client.get(self.assignment_delete_url)
        self.assertTemplateUsed(
            response,
            "frontend/projects/assignments/confirm_delete.html",
        )
        self.assertContains(response, "Delete this assignment?")
        self.assertContains(response, "Jamie Rivera")
        self.assertContains(response, "Platform lead")
        self.assertContains(
            response,
            "Deleting this assignment will also remove its requirement coverage "
            "shown below.",
        )
        self.assertContains(response, "Django &mdash; Level 3 requirement")
        self.assertContains(response, "Python &mdash; Level 4 requirement")
        self.assertContains(
            response,
            "The employee profile, project, project requirements, and skill "
            "definitions will not be deleted.",
        )
        self.csrf_token_for_action(response, self.assignment_delete_url)

    def test_empty_project_and_assignment_confirm_only_the_target(self):
        empty_project = self._create_project("Quiet Project")
        empty_project_url = reverse(
            "frontend:project_delete",
            args=[empty_project.project_id],
        )
        project_response = self.client.get(empty_project_url)
        self.assertContains(
            project_response,
            "This project has no skill requirements, employee assignments, or "
            "requirement coverage. Only the project will be deleted.",
        )
        self.assertContains(project_response, "Project only")
        self.assertNotContains(project_response, "Skill requirements")

        assignment = self._create_assignment(
            self.project,
            self.taylor,
            role="Advisor",
            status=Assignment.Status.CANCELLED,
        )
        assignment_url = reverse(
            "frontend:project_assignment_delete",
            args=[self.project.project_id, assignment.assignment_id],
        )
        assignment_response = self.client.get(assignment_url)
        self.assertContains(
            assignment_response,
            "This assignment has no requirement coverage. Only the assignment "
            "will be deleted.",
        )
        self.assertContains(assignment_response, "Assignment only")

    def test_get_and_unsupported_methods_never_delete(self):
        self.assertEqual(self.client.get(self.project_delete_url).status_code, 200)
        self.assertEqual(
            self.client.get(self.assignment_delete_url).status_code,
            200,
        )
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
        self.assertTrue(
            Assignment.objects.filter(pk=self.jamie_assignment.pk).exists()
        )

        self.assertEqual(self.client.put(self.project_delete_url).status_code, 405)
        self.assertEqual(
            self.client.put(self.assignment_delete_url).status_code,
            405,
        )
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
        self.assertTrue(
            Assignment.objects.filter(pk=self.jamie_assignment.pk).exists()
        )

    def test_confirmed_project_deletion_removes_its_planning_graph_only(self):
        project_id = self.project.project_id
        response = self.client.post(self.project_delete_url, follow=True)

        self.assertRedirects(response, reverse("frontend:project_list"))
        self.assertFalse(Project.objects.filter(pk=project_id).exists())
        self.assertFalse(
            ProjectSkillRequirement.objects.filter(project_id=project_id).exists()
        )
        self.assertFalse(Assignment.objects.filter(project_id=project_id).exists())
        self.assertFalse(
            AssignmentSkill.objects.filter(
                assignment_id__in=[
                    self.jamie_assignment.assignment_id,
                    self.morgan_assignment.assignment_id,
                ]
            ).exists()
        )
        self.assertTrue(Employee.objects.filter(pk=self.jamie.pk).exists())
        self.assertTrue(Employee.objects.filter(pk=self.morgan.pk).exists())
        self.assertTrue(Skill.objects.filter(pk=self.python.pk).exists())
        self.assertTrue(EmployeeSkill.objects.filter(pk=self.jamie_python.pk).exists())
        self.assertTrue(Leave.objects.filter(pk=self.jamie_leave.pk).exists())
        self.assertTrue(Attendance.objects.filter(pk=self.jamie_attendance.pk).exists())
        self.assertTrue(Project.objects.filter(pk=self.other_project.pk).exists())
        self.assertTrue(
            ProjectSkillRequirement.objects.filter(pk=self.other_requirement.pk).exists()
        )
        self.assertTrue(Assignment.objects.filter(pk=self.other_assignment.pk).exists())
        self.assertTrue(AssignmentSkill.objects.filter(pk=self.other_coverage.pk).exists())
        self.assertContains(
            response,
            "Atlas Renewal and its project planning information were deleted.",
        )

    def test_confirmed_assignment_deletion_removes_its_coverage_only(self):
        assignment_id = self.jamie_assignment.assignment_id
        response = self.client.post(self.assignment_delete_url, follow=True)

        self.assertRedirects(response, self.project_detail_url)
        self.assertFalse(Assignment.objects.filter(pk=assignment_id).exists())
        self.assertFalse(
            AssignmentSkill.objects.filter(assignment_id=assignment_id).exists()
        )
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
        self.assertTrue(Employee.objects.filter(pk=self.jamie.pk).exists())
        self.assertTrue(
            ProjectSkillRequirement.objects.filter(pk=self.python_requirement.pk).exists()
        )
        self.assertTrue(Skill.objects.filter(pk=self.python.pk).exists())
        self.assertTrue(EmployeeSkill.objects.filter(pk=self.jamie_python.pk).exists())
        self.assertTrue(Assignment.objects.filter(pk=self.morgan_assignment.pk).exists())
        self.assertTrue(
            AssignmentSkill.objects.filter(pk=self.morgan_python_coverage.pk).exists()
        )
        self.assertContains(
            response,
            "The assignment for Jamie Rivera on Atlas Renewal and its "
            "requirement coverage were deleted.",
        )

    def test_viewer_and_manager_cannot_delete_projects_or_assignments(self):
        for user in (self.viewer, self.manager):
            client = Client()
            client.force_login(user)
            for url in (self.project_delete_url, self.assignment_delete_url):
                with self.subTest(user=user.username, url=url, method="get"):
                    self.assertEqual(client.get(url).status_code, 403)
                with self.subTest(user=user.username, url=url, method="post"):
                    self.assertEqual(client.post(url).status_code, 403)

        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
        self.assertTrue(
            Assignment.objects.filter(pk=self.jamie_assignment.pk).exists()
        )

    def test_delete_permissions_are_model_specific(self):
        project_client = Client()
        project_client.force_login(self.project_delete_only)
        self.assertEqual(project_client.get(self.project_delete_url).status_code, 200)
        self.assertEqual(
            project_client.get(self.assignment_delete_url).status_code,
            403,
        )

        assignment_client = Client()
        assignment_client.force_login(self.assignment_delete_only)
        self.assertEqual(
            assignment_client.get(self.project_delete_url).status_code,
            403,
        )
        self.assertEqual(
            assignment_client.get(self.assignment_delete_url).status_code,
            200,
        )

    def test_anonymous_users_are_redirected_before_confirmation(self):
        for url in (self.project_delete_url, self.assignment_delete_url):
            with self.subTest(url=url):
                response = Client().get(url)
                self.assertRedirects(
                    response,
                    f"{reverse('frontend:login')}?next={url}",
                    fetch_redirect_response=False,
                )

    def test_csrf_enforcement_rejects_project_and_assignment_deletion(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr_admin)

        self.assertEqual(csrf_client.post(self.project_delete_url).status_code, 403)
        self.assertEqual(
            csrf_client.post(self.assignment_delete_url).status_code,
            403,
        )
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
        self.assertTrue(
            Assignment.objects.filter(pk=self.jamie_assignment.pk).exists()
        )

    def test_rendered_csrf_tokens_allow_confirmed_deletions(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr_admin)

        assignment_confirmation = csrf_client.get(self.assignment_delete_url)
        assignment_response = csrf_client.post(
            self.assignment_delete_url,
            {
                "csrfmiddlewaretoken": self.csrf_token_for_action(
                    assignment_confirmation,
                    self.assignment_delete_url,
                )
            },
        )
        self.assertRedirects(
            assignment_response,
            self.project_detail_url,
            fetch_redirect_response=False,
        )
        self.assertFalse(
            Assignment.objects.filter(pk=self.jamie_assignment.pk).exists()
        )

        project_confirmation = csrf_client.get(self.project_delete_url)
        project_response = csrf_client.post(
            self.project_delete_url,
            {
                "csrfmiddlewaretoken": self.csrf_token_for_action(
                    project_confirmation,
                    self.project_delete_url,
                )
            },
        )
        self.assertRedirects(
            project_response,
            reverse("frontend:project_list"),
            fetch_redirect_response=False,
        )
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())

    def test_stale_project_has_clear_get_and_post_outcomes(self):
        stale_project = self._create_project("Stale Project")
        stale_url = reverse(
            "frontend:project_delete",
            args=[stale_project.project_id],
        )
        stale_project.delete()

        self.assertEqual(self.client.get(stale_url).status_code, 404)
        response = self.client.post(stale_url, follow=True)
        self.assertRedirects(response, reverse("frontend:project_list"))
        self.assertContains(
            response,
            "This project no longer exists. No deletion was needed.",
        )

    def test_stale_and_mismatched_assignment_context_is_safe(self):
        mismatched_url = reverse(
            "frontend:project_assignment_delete",
            args=[self.project.project_id, self.other_assignment.assignment_id],
        )
        self.assertEqual(self.client.get(mismatched_url).status_code, 404)
        mismatch_response = self.client.post(mismatched_url, follow=True)
        self.assertRedirects(mismatch_response, self.project_detail_url)
        self.assertContains(
            mismatch_response,
            "This assignment no longer exists on this project. No deletion "
            "was needed.",
        )
        self.assertTrue(
            Assignment.objects.filter(pk=self.other_assignment.pk).exists()
        )

        stale_assignment = self._create_assignment(
            self.project,
            self.taylor,
            role="Reviewer",
            status=Assignment.Status.CANCELLED,
        )
        stale_url = reverse(
            "frontend:project_assignment_delete",
            args=[self.project.project_id, stale_assignment.assignment_id],
        )
        stale_assignment.delete()
        self.assertEqual(self.client.get(stale_url).status_code, 404)
        stale_response = self.client.post(stale_url, follow=True)
        self.assertRedirects(stale_response, self.project_detail_url)
        self.assertContains(
            stale_response,
            "This assignment no longer exists on this project. No deletion "
            "was needed.",
        )

    def test_stale_assignment_with_missing_project_returns_to_directory(self):
        project = self._create_project("Removed Project")
        assignment = self._create_assignment(
            project,
            self.taylor,
            role="Reviewer",
            status=Assignment.Status.CANCELLED,
        )
        stale_url = reverse(
            "frontend:project_assignment_delete",
            args=[project.project_id, assignment.assignment_id],
        )
        project.delete()

        response = self.client.post(stale_url, follow=True)
        self.assertRedirects(response, reverse("frontend:project_list"))
        self.assertContains(
            response,
            "This project and assignment no longer exist. No deletion was needed.",
        )

    def test_failed_project_deletion_rolls_back_every_planning_record(self):
        original_delete = Project.delete

        def delete_then_fail(instance, *args, **kwargs):
            original_delete(instance, *args, **kwargs)
            raise DatabaseError("Simulated project deletion failure")

        with patch.object(Project, "delete", new=delete_then_fail):
            response = self.client.post(self.project_delete_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
        self.assertTrue(
            ProjectSkillRequirement.objects.filter(pk=self.python_requirement.pk).exists()
        )
        self.assertTrue(
            Assignment.objects.filter(pk=self.jamie_assignment.pk).exists()
        )
        self.assertTrue(
            AssignmentSkill.objects.filter(pk=self.jamie_python_coverage.pk).exists()
        )
        self.assertContains(
            response,
            "We could not delete this project. Nothing was deleted. Please try "
            "again.",
        )

    def test_failed_assignment_deletion_rolls_back_coverage(self):
        original_delete = Assignment.delete

        def delete_then_fail(instance, *args, **kwargs):
            original_delete(instance, *args, **kwargs)
            raise DatabaseError("Simulated assignment deletion failure")

        with patch.object(Assignment, "delete", new=delete_then_fail):
            response = self.client.post(self.assignment_delete_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Assignment.objects.filter(pk=self.jamie_assignment.pk).exists()
        )
        self.assertTrue(
            AssignmentSkill.objects.filter(pk=self.jamie_python_coverage.pk).exists()
        )
        self.assertTrue(
            AssignmentSkill.objects.filter(pk=self.jamie_django_coverage.pk).exists()
        )
        self.assertContains(
            response,
            "We could not delete this assignment. Nothing was deleted. Please "
            "try again.",
        )
