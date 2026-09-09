import re
from datetime import date
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
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)
from frontend.selectors.deletions import (
    get_employee_deletion_target,
    get_skill_deletion_target,
)


class SafeEmployeeAndSkillDeletionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.hr_admin = get_user_model().objects.create_user(username="deletion-hr")
        cls.hr_admin.groups.add(Group.objects.get(name=HR_ADMINISTRATOR_GROUP))
        cls.viewer = get_user_model().objects.create_user(username="deletion-viewer")
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.employee_delete_only = cls._permission_user(
            "employee-delete-only",
            "delete_employee",
        )
        cls.skill_delete_only = cls._permission_user(
            "skill-delete-only",
            "delete_skill",
        )

        cls.employee = cls._create_employee("Jamie", "Rivera")
        cls.other_employee = cls._create_employee("Morgan", "Lee")
        cls.python = Skill.objects.create(name="Python", category="Engineering")
        cls.django = Skill.objects.create(name="Django", category="Engineering")

        cls.project_one = cls._create_project("Project Atlas")
        cls.project_two = cls._create_project("Project Horizon")
        cls.python_requirement_one = cls._create_requirement(
            cls.project_one,
            cls.python,
        )
        cls.python_requirement_two = cls._create_requirement(
            cls.project_two,
            cls.python,
        )
        cls.django_requirement = cls._create_requirement(
            cls.project_one,
            cls.django,
        )

        cls.employee_python = EmployeeSkill.objects.create(
            employee=cls.employee,
            skill=cls.python,
            level=4,
            years_experience=Decimal("6.5"),
        )
        cls.employee_django = EmployeeSkill.objects.create(
            employee=cls.employee,
            skill=cls.django,
            level=3,
            years_experience=Decimal("3.0"),
        )
        cls.other_python = EmployeeSkill.objects.create(
            employee=cls.other_employee,
            skill=cls.python,
            level=2,
            years_experience=Decimal("1.5"),
        )

        cls.assignment = cls._create_assignment(
            cls.employee,
            cls.project_one,
        )
        cls.other_assignment = cls._create_assignment(
            cls.other_employee,
            cls.project_two,
        )
        cls.employee_python_coverage = AssignmentSkill.objects.create(
            assignment=cls.assignment,
            project_skill_requirement=cls.python_requirement_one,
        )
        cls.employee_django_coverage = AssignmentSkill.objects.create(
            assignment=cls.assignment,
            project_skill_requirement=cls.django_requirement,
        )
        cls.other_python_coverage = AssignmentSkill.objects.create(
            assignment=cls.other_assignment,
            project_skill_requirement=cls.python_requirement_two,
        )

        cls.leave = Leave.objects.create(
            employee=cls.employee,
            start_date=date(2026, 10, 5),
            end_date=date(2026, 10, 7),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )
        cls.attendance = Attendance.objects.create(
            employee=cls.employee,
            date=date(2026, 9, 8),
            status=Attendance.Status.PRESENT,
        )

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

    @classmethod
    def _create_employee(cls, first_name, last_name):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Engineering",
            position="Platform Engineer",
            hire_date=date(2019, 4, 15),
            experience_years=Decimal("7.5"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )

    @classmethod
    def _create_project(cls, name):
        return Project.objects.create(
            name=name,
            description=f"Planning context for {name}.",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 31),
            estimated_hours=Decimal("80.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )

    @classmethod
    def _create_requirement(cls, project, skill):
        return ProjectSkillRequirement.objects.create(
            project=project,
            skill=skill,
            required_level=2,
            priority=ProjectSkillRequirement.Priority.MEDIUM,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=Decimal("40.00"),
        )

    @classmethod
    def _create_assignment(cls, employee, project):
        return Assignment.objects.create(
            employee=employee,
            project=project,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 31),
            allocation_percentage=50,
            role_on_project="Engineer",
            status=Assignment.Status.PLANNED,
        )

    def setUp(self):
        self.employee_delete_url = reverse(
            "frontend:employee_delete",
            args=[self.employee.employee_id],
        )
        self.skill_delete_url = reverse(
            "frontend:skill_delete",
            args=[self.python.skill_id],
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

    def test_delete_routes_are_namespaced_and_linked_from_details(self):
        self.assertEqual(
            self.employee_delete_url,
            f"/employees/{self.employee.employee_id}/delete/",
        )
        self.assertEqual(
            resolve(self.employee_delete_url).view_name,
            "frontend:employee_delete",
        )
        self.assertEqual(
            self.skill_delete_url,
            f"/skills/{self.python.skill_id}/delete/",
        )
        self.assertEqual(
            resolve(self.skill_delete_url).view_name,
            "frontend:skill_delete",
        )

        employee_detail = self.client.get(
            reverse(
                "frontend:employee_detail",
                args=[self.employee.employee_id],
            )
        )
        skill_detail = self.client.get(
            reverse("frontend:skill_detail", args=[self.python.skill_id])
        )
        self.assertContains(employee_detail, self.employee_delete_url)
        self.assertContains(employee_detail, "Delete employee")
        self.assertContains(skill_detail, self.skill_delete_url)
        self.assertContains(skill_detail, "Delete skill")

        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        self.assertNotContains(
            viewer_client.get(
                reverse(
                    "frontend:employee_detail",
                    args=[self.employee.employee_id],
                )
            ),
            self.employee_delete_url,
        )
        self.assertNotContains(
            viewer_client.get(
                reverse("frontend:skill_detail", args=[self.python.skill_id])
            ),
            self.skill_delete_url,
        )

    def test_business_impact_selectors_and_confirmation_pages_are_exact(self):
        with self.assertNumQueries(2):
            employee = get_employee_deletion_target(self.employee.employee_id)
        self.assertEqual(employee.assignment_count, 1)
        self.assertEqual(employee.leave_count, 1)
        self.assertEqual(employee.attendance_count, 1)
        self.assertEqual(
            [
                {
                    "name": employee_skill.skill.name,
                    "level": employee_skill.level,
                }
                for employee_skill in employee.deletion_employee_skills
            ],
            [
                {"name": "Django", "level": 3},
                {"name": "Python", "level": 4},
            ],
        )

        employee_response = self.client.get(self.employee_delete_url)
        employee_impact = employee_response.context["impact"]
        self.assertTrue(employee_impact["has_related_information"])
        self.assertEqual(employee_impact["assignment_count"], 1)
        self.assertEqual(employee_impact["leave_count"], 1)
        self.assertEqual(employee_impact["attendance_count"], 1)
        self.assertContains(employee_response, "What will be deleted")
        self.assertContains(
            employee_response,
            "Deleting this employee will also remove their skills, project "
            "assignments, leave history, and attendance history shown below.",
        )
        self.assertContains(employee_response, "Employee skills")
        self.assertContains(employee_response, "Django &mdash; Level 3 of 5")
        self.assertContains(employee_response, "Python &mdash; Level 4 of 5")
        self.assertContains(employee_response, "Project assignments")
        self.assertContains(employee_response, "1 assignment")
        self.assertContains(employee_response, "Leave")
        self.assertContains(employee_response, "1 leave entry")
        self.assertContains(employee_response, "Attendance history")
        self.assertContains(employee_response, "1 attendance entry")
        self.assertContains(
            employee_response,
            "Projects and skill definitions will not be deleted.",
        )
        self.assertNotContains(employee_response, "Django cascade rules")
        self.assertNotContains(employee_response, "related records")
        self.assertNotContains(employee_response, "Assignment skill coverage")
        self.csrf_token_for_action(employee_response, self.employee_delete_url)

        with self.assertNumQueries(2):
            skill = get_skill_deletion_target(self.python.skill_id)
        self.assertEqual(skill.project_requirement_count, 2)
        self.assertEqual(
            [
                {
                    "name": str(employee_skill.employee),
                    "level": employee_skill.level,
                }
                for employee_skill in skill.deletion_employee_skills
            ],
            [
                {"name": "Morgan Lee", "level": 2},
                {"name": "Jamie Rivera", "level": 4},
            ],
        )

        skill_response = self.client.get(self.skill_delete_url)
        skill_impact = skill_response.context["impact"]
        self.assertTrue(skill_impact["has_related_information"])
        self.assertEqual(skill_impact["project_requirement_count"], 2)
        self.assertContains(skill_response, "What will be deleted")
        self.assertContains(
            skill_response,
            "Deleting this skill will remove it from the employee profiles "
            "shown below and from the project requirements that use it.",
        )
        self.assertContains(skill_response, "Employees with this skill")
        self.assertContains(skill_response, "Morgan Lee &mdash; Level 2 of 5")
        self.assertContains(skill_response, "Jamie Rivera &mdash; Level 4 of 5")
        self.assertContains(skill_response, "Project requirements")
        self.assertContains(skill_response, "2 project requirements")
        self.assertContains(
            skill_response,
            "Employee profiles and projects will not be deleted.",
        )
        self.assertNotContains(skill_response, "Django cascade rules")
        self.assertNotContains(skill_response, "related records")
        self.assertNotContains(skill_response, "Assignment skill coverage")
        self.csrf_token_for_action(skill_response, self.skill_delete_url)

    def test_confirmation_pages_explain_when_only_the_target_will_be_deleted(self):
        employee = self._create_employee("Taylor", "Quiet")
        employee_response = self.client.get(
            reverse(
                "frontend:employee_delete",
                args=[employee.employee_id],
            )
        )
        self.assertContains(
            employee_response,
            "This employee has no related information. Only the employee "
            "profile will be deleted.",
        )
        self.assertContains(employee_response, "Profile only")
        self.assertNotContains(employee_response, "Employee skills")

        skill = Skill.objects.create(name="Unused skill", category="Test")
        skill_response = self.client.get(
            reverse("frontend:skill_delete", args=[skill.skill_id])
        )
        self.assertContains(
            skill_response,
            "This skill is not used by any employee profile or project "
            "requirement. Only the skill will be deleted.",
        )
        self.assertContains(skill_response, "Skill only")
        self.assertNotContains(skill_response, "Employees with this skill")

    def test_get_only_renders_confirmation_and_never_deletes(self):
        employee_response = self.client.get(self.employee_delete_url)
        skill_response = self.client.get(self.skill_delete_url)

        self.assertEqual(employee_response.status_code, 200)
        self.assertEqual(skill_response.status_code, 200)
        self.assertTemplateUsed(
            employee_response,
            "frontend/employees/confirm_delete.html",
        )
        self.assertTemplateUsed(
            skill_response,
            "frontend/skills/confirm_delete.html",
        )
        self.assertTrue(Employee.objects.filter(pk=self.employee.pk).exists())
        self.assertTrue(Skill.objects.filter(pk=self.python.pk).exists())
        self.assertEqual(self.client.put(self.employee_delete_url).status_code, 405)
        self.assertEqual(self.client.put(self.skill_delete_url).status_code, 405)

    def test_permitted_employee_deletion_cascades_related_records(self):
        response = self.client.post(self.employee_delete_url, follow=True)

        self.assertRedirects(response, reverse("frontend:employee_list"))
        self.assertFalse(Employee.objects.filter(pk=self.employee.pk).exists())
        self.assertFalse(
            EmployeeSkill.objects.filter(employee_id=self.employee.pk).exists()
        )
        self.assertFalse(
            Assignment.objects.filter(employee_id=self.employee.pk).exists()
        )
        self.assertFalse(
            AssignmentSkill.objects.filter(assignment=self.assignment).exists()
        )
        self.assertFalse(Leave.objects.filter(employee_id=self.employee.pk).exists())
        self.assertFalse(
            Attendance.objects.filter(employee_id=self.employee.pk).exists()
        )
        self.assertTrue(Employee.objects.filter(pk=self.other_employee.pk).exists())
        self.assertTrue(Project.objects.filter(pk=self.project_one.pk).exists())
        self.assertTrue(Skill.objects.filter(pk=self.python.pk).exists())
        self.assertTrue(
            AssignmentSkill.objects.filter(pk=self.other_python_coverage.pk).exists()
        )
        self.assertContains(
            response,
            "Jamie Rivera and their related workforce information were deleted.",
        )

    def test_permitted_skill_deletion_cascades_related_records(self):
        response = self.client.post(self.skill_delete_url, follow=True)

        self.assertRedirects(response, reverse("frontend:skill_list"))
        self.assertFalse(Skill.objects.filter(pk=self.python.pk).exists())
        self.assertFalse(
            EmployeeSkill.objects.filter(skill_id=self.python.pk).exists()
        )
        self.assertFalse(
            ProjectSkillRequirement.objects.filter(skill_id=self.python.pk).exists()
        )
        self.assertFalse(
            AssignmentSkill.objects.filter(
                project_skill_requirement__skill_id=self.python.pk
            ).exists()
        )
        self.assertTrue(Employee.objects.filter(pk=self.employee.pk).exists())
        self.assertTrue(Project.objects.filter(pk=self.project_one.pk).exists())
        self.assertTrue(Assignment.objects.filter(pk=self.assignment.pk).exists())
        self.assertTrue(Skill.objects.filter(pk=self.django.pk).exists())
        self.assertTrue(
            EmployeeSkill.objects.filter(pk=self.employee_django.pk).exists()
        )
        self.assertTrue(
            AssignmentSkill.objects.filter(pk=self.employee_django_coverage.pk).exists()
        )
        self.assertContains(
            response,
            "Python was deleted from the skill directory and removed from the "
            "employee profiles and project requirements that used it.",
        )

    def test_forbidden_employee_deletion_preserves_every_record(self):
        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        employee_count = Employee.objects.count()
        related_count = EmployeeSkill.objects.filter(employee=self.employee).count()

        self.assertEqual(
            viewer_client.get(self.employee_delete_url).status_code,
            403,
        )
        self.assertEqual(
            viewer_client.post(self.employee_delete_url).status_code,
            403,
        )
        self.assertEqual(Employee.objects.count(), employee_count)
        self.assertEqual(
            EmployeeSkill.objects.filter(employee=self.employee).count(),
            related_count,
        )

    def test_forbidden_skill_deletion_preserves_every_record(self):
        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        skill_count = Skill.objects.count()
        related_count = EmployeeSkill.objects.filter(skill=self.python).count()

        self.assertEqual(viewer_client.get(self.skill_delete_url).status_code, 403)
        self.assertEqual(viewer_client.post(self.skill_delete_url).status_code, 403)
        self.assertEqual(Skill.objects.count(), skill_count)
        self.assertEqual(
            EmployeeSkill.objects.filter(skill=self.python).count(),
            related_count,
        )

    def test_delete_permissions_are_model_specific(self):
        employee_client = Client()
        employee_client.force_login(self.employee_delete_only)
        self.assertEqual(employee_client.get(self.employee_delete_url).status_code, 200)
        self.assertEqual(employee_client.get(self.skill_delete_url).status_code, 403)

        skill_client = Client()
        skill_client.force_login(self.skill_delete_only)
        self.assertEqual(skill_client.get(self.employee_delete_url).status_code, 403)
        self.assertEqual(skill_client.get(self.skill_delete_url).status_code, 200)

    def test_anonymous_users_are_redirected_before_confirmation(self):
        for url in (self.employee_delete_url, self.skill_delete_url):
            with self.subTest(url=url):
                response = Client().get(url)
                self.assertRedirects(
                    response,
                    f"{reverse('frontend:login')}?next={url}",
                    fetch_redirect_response=False,
                )

    def test_csrf_enforcement_rejects_employee_and_skill_deletion(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr_admin)

        self.assertEqual(csrf_client.post(self.employee_delete_url).status_code, 403)
        self.assertEqual(csrf_client.post(self.skill_delete_url).status_code, 403)
        self.assertTrue(Employee.objects.filter(pk=self.employee.pk).exists())
        self.assertTrue(Skill.objects.filter(pk=self.python.pk).exists())

    def test_rendered_csrf_tokens_allow_confirmed_deletions(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr_admin)

        employee_confirmation = csrf_client.get(self.employee_delete_url)
        employee_response = csrf_client.post(
            self.employee_delete_url,
            {
                "csrfmiddlewaretoken": self.csrf_token_for_action(
                    employee_confirmation,
                    self.employee_delete_url,
                )
            },
        )
        self.assertRedirects(
            employee_response,
            reverse("frontend:employee_list"),
            fetch_redirect_response=False,
        )
        self.assertFalse(Employee.objects.filter(pk=self.employee.pk).exists())

        skill_confirmation = csrf_client.get(self.skill_delete_url)
        skill_response = csrf_client.post(
            self.skill_delete_url,
            {
                "csrfmiddlewaretoken": self.csrf_token_for_action(
                    skill_confirmation,
                    self.skill_delete_url,
                )
            },
        )
        self.assertRedirects(
            skill_response,
            reverse("frontend:skill_list"),
            fetch_redirect_response=False,
        )
        self.assertFalse(Skill.objects.filter(pk=self.python.pk).exists())

    def test_stale_records_return_clear_outcomes(self):
        stale_employee = self._create_employee("Stale", "Employee")
        stale_employee_url = reverse(
            "frontend:employee_delete",
            args=[stale_employee.employee_id],
        )
        stale_employee.delete()

        stale_employee_response = self.client.post(
            stale_employee_url,
            follow=True,
        )
        self.assertRedirects(stale_employee_response, reverse("frontend:employee_list"))
        self.assertContains(
            stale_employee_response,
            "This employee no longer exists. No deletion was needed.",
        )
        self.assertEqual(self.client.get(stale_employee_url).status_code, 404)

        stale_skill = Skill.objects.create(name="Stale skill", category="Test")
        stale_skill_url = reverse(
            "frontend:skill_delete",
            args=[stale_skill.skill_id],
        )
        stale_skill.delete()

        stale_skill_response = self.client.post(stale_skill_url, follow=True)
        self.assertRedirects(stale_skill_response, reverse("frontend:skill_list"))
        self.assertContains(
            stale_skill_response,
            "This skill no longer exists. No deletion was needed.",
        )
        self.assertEqual(self.client.get(stale_skill_url).status_code, 404)

    def test_failed_employee_deletion_rolls_back_and_shows_feedback(self):
        original_delete = Employee.delete

        def delete_then_fail(instance, *args, **kwargs):
            original_delete(instance, *args, **kwargs)
            raise DatabaseError("Simulated employee deletion failure")

        with patch.object(Employee, "delete", new=delete_then_fail):
            response = self.client.post(self.employee_delete_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Employee.objects.filter(pk=self.employee.pk).exists())
        self.assertTrue(
            EmployeeSkill.objects.filter(pk=self.employee_python.pk).exists()
        )
        self.assertTrue(Assignment.objects.filter(pk=self.assignment.pk).exists())
        self.assertContains(
            response,
            "We could not delete this employee. Nothing was deleted. "
            "Please try again.",
        )

    def test_failed_skill_deletion_rolls_back_and_shows_feedback(self):
        original_delete = Skill.delete

        def delete_then_fail(instance, *args, **kwargs):
            original_delete(instance, *args, **kwargs)
            raise DatabaseError("Simulated skill deletion failure")

        with patch.object(Skill, "delete", new=delete_then_fail):
            response = self.client.post(self.skill_delete_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Skill.objects.filter(pk=self.python.pk).exists())
        self.assertTrue(
            EmployeeSkill.objects.filter(pk=self.employee_python.pk).exists()
        )
        self.assertTrue(
            ProjectSkillRequirement.objects.filter(
                pk=self.python_requirement_one.pk
            ).exists()
        )
        self.assertContains(
            response,
            "We could not delete this skill. Nothing was deleted. "
            "Please try again.",
        )
