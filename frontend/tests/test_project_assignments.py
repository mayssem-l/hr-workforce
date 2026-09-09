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
    Employee,
    EmployeeSkill,
    Leave,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from frontend.roles import (
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)


class ProjectAssignmentManagementTests(TestCase):
    ASSIGNMENT_FORM_CSRF_PATTERN = re.compile(
        r'<form method="post" novalidate data-loading-form>\s*'
        r'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)">'
    )

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.manager = cls._group_user(
            "assignment-manager",
            MANAGER_PLANNER_GROUP,
        )
        cls.viewer = cls._group_user(
            "assignment-viewer",
            VIEWER_GROUP,
        )
        cls.add_only_user = cls._permission_user(
            "assignment-add-only",
            "add_assignment",
        )
        cls.change_only_user = cls._permission_user(
            "assignment-change-only",
            "change_assignment",
        )

        cls.python = Skill.objects.create(
            name="Python",
            category="Engineering",
        )
        cls.sql = Skill.objects.create(name="SQL", category="Data")
        cls.project = cls._create_project("Atlas Renewal")
        cls.other_project = cls._create_project("Beacon Launch")
        ProjectSkillRequirement.objects.create(
            project=cls.project,
            skill=cls.python,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=2,
            estimated_effort_hours=Decimal("200.00"),
        )

        cls.jamie = cls._create_employee("Jamie", "Rivera")
        cls.taylor = cls._create_employee("Taylor", "Morgan")
        cls.morgan = cls._create_employee("Morgan", "Lee")
        cls.avery = cls._create_employee("Avery", "Chen")
        cls.casey = cls._create_employee("Casey", "Patel")
        for employee, skill, level in (
            (cls.jamie, cls.python, 4),
            (cls.taylor, cls.python, 3),
            (cls.morgan, cls.sql, 5),
            (cls.avery, cls.python, 4),
            (cls.casey, cls.python, 4),
        ):
            EmployeeSkill.objects.create(
                employee=employee,
                skill=skill,
                level=level,
                years_experience=Decimal("4.0"),
            )

        cls.assignment = Assignment.objects.create(
            employee=cls.jamie,
            project=cls.project,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 12, 15),
            allocation_percentage=40,
            role_on_project="Platform lead",
            status=Assignment.Status.ACTIVE,
        )
        cls.other_assignment = Assignment.objects.create(
            employee=cls.avery,
            project=cls.other_project,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 31),
            allocation_percentage=80,
            role_on_project="Delivery lead",
            status=Assignment.Status.ACTIVE,
        )
        Leave.objects.create(
            employee=cls.casey,
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 10),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
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

    @classmethod
    def _create_project(cls, name):
        return Project.objects.create(
            name=name,
            description=f"Planning context for {name}.",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 31),
            estimated_hours=Decimal("200.00"),
            status=Project.Status.IN_PROGRESS,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.MEDIUM,
        )

    @classmethod
    def _create_employee(cls, first_name, last_name):
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

    def setUp(self):
        self.detail_url = reverse(
            "frontend:project_detail",
            args=[self.project.project_id],
        )
        self.create_url = reverse(
            "frontend:project_assignment_create",
            args=[self.project.project_id],
        )
        self.update_url = reverse(
            "frontend:project_assignment_update",
            args=[self.project.project_id, self.assignment.assignment_id],
        )
        self.client.force_login(self.manager)

    def valid_create_data(self, *, employee=None):
        return {
            "employee": (employee or self.taylor).employee_id,
            "start_date": "2026-09-15",
            "end_date": "2026-11-30",
            "allocation_percentage": "50",
            "role_on_project": "Backend engineer",
            "status": Assignment.Status.PLANNED,
        }

    def valid_update_data(self):
        return {
            "employee": self.jamie.employee_id,
            "start_date": "2026-09-20",
            "end_date": "2026-12-20",
            "allocation_percentage": "60",
            "role_on_project": "Technical lead",
            "status": Assignment.Status.ACTIVE,
        }

    def assignment_form_csrf_token(self, response):
        match = self.ASSIGNMENT_FORM_CSRF_PATTERN.search(
            response.content.decode("utf-8")
        )
        self.assertIsNotNone(
            match,
            "The project assignment POST form must render its own CSRF input.",
        )
        return match.group(1)

    def test_routes_are_project_scoped_namespaced_and_render_forms(self):
        self.assertEqual(
            self.create_url,
            f"/projects/{self.project.project_id}/assignments/add/",
        )
        self.assertEqual(
            self.update_url,
            f"/projects/{self.project.project_id}/assignments/"
            f"{self.assignment.assignment_id}/edit/",
        )
        self.assertEqual(
            resolve(self.create_url).view_name,
            "frontend:project_assignment_create",
        )
        update_match = resolve(self.update_url)
        self.assertEqual(
            update_match.view_name,
            "frontend:project_assignment_update",
        )
        self.assertEqual(update_match.kwargs["project_id"], self.project.project_id)
        self.assertEqual(
            update_match.kwargs["assignment_id"],
            self.assignment.assignment_id,
        )

        create_response = self.client.get(self.create_url)
        self.assertTemplateUsed(
            create_response,
            "frontend/projects/assignments/create.html",
        )
        self.assertTemplateUsed(
            create_response,
            "frontend/projects/assignments/_form.html",
        )
        self.assertContains(create_response, "<h1>Add assignment</h1>", html=True)
        self.assertContains(create_response, "Assignment planning")
        self.assertContains(create_response, "Employee selection guidance")
        self.assertContains(create_response, 'value="2026-09-01"')
        self.assertContains(create_response, 'value="2026-12-31"')
        self.assertContains(create_response, "Jamie Rivera")
        self.assertContains(
            create_response,
            "Matches at least one project skill",
        )
        self.assertContains(create_response, "Morgan Lee")
        self.assertContains(create_response, "No matching project skill found")
        self.assignment_form_csrf_token(create_response)

        update_response = self.client.get(self.update_url)
        self.assertTemplateUsed(
            update_response,
            "frontend/projects/assignments/edit.html",
        )
        self.assertContains(update_response, "<h1>Edit assignment</h1>", html=True)
        self.assertContains(update_response, "Platform lead")
        self.assertContains(update_response, "Save assignment")
        self.assignment_form_csrf_token(update_response)

        for response in (create_response, update_response):
            self.assertRegex(
                response.content.decode("utf-8"),
                r'href="/projects/"\s+aria-current="page"',
            )

    def test_employee_hints_delegate_to_existing_qualification_service(self):
        with patch(
            "frontend.presenters.assignments.employee_can_cover_requirement",
            return_value=True,
        ) as qualification_service:
            response = self.client.get(self.create_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(qualification_service.call_count, Employee.objects.count())
        for call in qualification_service.call_args_list:
            self.assertEqual(call.args[1], self.project)
        self.assertContains(
            response,
            "Skill-match notes are advisory; all assignment rules are checked "
            "when you save.",
        )

    def test_project_detail_connects_actions_for_writers_only(self):
        response = self.client.get(self.detail_url)
        self.assertContains(response, self.create_url)
        self.assertContains(response, self.update_url)
        self.assertContains(response, "Add assignment")

        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        viewer_response = viewer_client.get(self.detail_url)
        self.assertNotContains(viewer_response, "Add assignment")
        self.assertNotContains(viewer_response, self.update_url)

    def test_valid_create_saves_and_redirects_to_project_detail(self):
        response = self.client.post(
            self.create_url,
            self.valid_create_data(),
            follow=True,
        )

        assignment = Assignment.objects.get(
            project=self.project,
            employee=self.taylor,
        )
        self.assertRedirects(response, self.detail_url)
        self.assertEqual(assignment.start_date, date(2026, 9, 15))
        self.assertEqual(assignment.end_date, date(2026, 11, 30))
        self.assertEqual(assignment.allocation_percentage, 50)
        self.assertEqual(assignment.role_on_project, "Backend engineer")
        self.assertEqual(assignment.status, Assignment.Status.PLANNED)
        self.assertContains(
            response,
            "Taylor Morgan was assigned to Atlas Renewal.",
        )
        self.assertContains(response, "Backend engineer")

    def test_valid_update_saves_and_redirects_to_project_detail(self):
        response = self.client.post(
            self.update_url,
            self.valid_update_data(),
            follow=True,
        )

        self.assignment.refresh_from_db()
        self.assertRedirects(response, self.detail_url)
        self.assertEqual(self.assignment.start_date, date(2026, 9, 20))
        self.assertEqual(self.assignment.end_date, date(2026, 12, 20))
        self.assertEqual(self.assignment.allocation_percentage, 60)
        self.assertEqual(self.assignment.role_on_project, "Technical lead")
        self.assertEqual(self.assignment.status, Assignment.Status.ACTIVE)
        self.assertContains(
            response,
            "The assignment for Jamie Rivera on Atlas Renewal was updated.",
        )

    def test_reversed_dates_are_rejected_with_field_feedback(self):
        data = self.valid_create_data()
        data.update({"start_date": "2026-12-01", "end_date": "2026-11-01"})

        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("end_date", response.context["form"].errors)
        self.assertContains(response, 'id="id_end_date_error"')
        self.assertFalse(
            Assignment.objects.filter(
                project=self.project,
                employee=self.taylor,
            ).exists()
        )

    def test_unqualified_employee_is_rejected_by_assignment_validation(self):
        response = self.client.post(
            self.create_url,
            self.valid_create_data(employee=self.morgan),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("employee", response.context["form"].errors)
        self.assertContains(response, 'id="id_employee_error"')
        self.assertContains(
            response,
            "This employee does not satisfy any of the skill requirements for "
            "this project.",
        )
        self.assertFalse(
            Assignment.objects.filter(
                project=self.project,
                employee=self.morgan,
            ).exists()
        )

    def test_same_project_overlap_is_rejected_with_visible_feedback(self):
        data = self.valid_create_data(employee=self.jamie)
        data.update({"start_date": "2026-11-01", "end_date": "2026-12-20"})

        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("project", response.context["form"].errors)
        self.assertContains(response, 'id="id_project_error"')
        self.assertContains(
            response,
            "This employee already has an overlapping assignment for this "
            "project.",
        )
        self.assertEqual(
            Assignment.objects.filter(
                project=self.project,
                employee=self.jamie,
            ).count(),
            1,
        )

    def test_total_allocation_above_one_hundred_is_rejected(self):
        data = self.valid_create_data(employee=self.avery)
        data["allocation_percentage"] = "30"

        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("allocation_percentage", response.context["form"].errors)
        self.assertContains(response, 'id="id_allocation_percentage_error"')
        self.assertContains(response, "Maximum allowed workload is 100%.")
        self.assertFalse(
            Assignment.objects.filter(
                project=self.project,
                employee=self.avery,
            ).exists()
        )

    def test_approved_leave_overlap_is_rejected(self):
        response = self.client.post(
            self.create_url,
            self.valid_create_data(employee=self.casey),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("employee", response.context["form"].errors)
        self.assertContains(response, 'id="id_employee_error"')
        self.assertContains(
            response,
            "This employee has an approved leave that overlaps with the "
            "assignment period.",
        )
        self.assertFalse(
            Assignment.objects.filter(
                project=self.project,
                employee=self.casey,
            ).exists()
        )

    def test_invalid_field_values_and_update_leave_stored_data_unchanged(self):
        invalid_create = self.valid_create_data()
        invalid_create.update(
            {
                "allocation_percentage": "101",
                "role_on_project": "",
                "status": "not-a-status",
            }
        )
        create_response = self.client.post(self.create_url, invalid_create)
        for field_name in (
            "allocation_percentage",
            "role_on_project",
            "status",
        ):
            self.assertIn(field_name, create_response.context["form"].errors)
            self.assertContains(create_response, f'id="id_{field_name}_error"')

        invalid_update = self.valid_update_data()
        invalid_update["allocation_percentage"] = "101"
        update_response = self.client.post(self.update_url, invalid_update)
        self.assertIn(
            "allocation_percentage",
            update_response.context["form"].errors,
        )
        self.assertContains(
            update_response,
            "Please correct the highlighted fields before saving changes.",
        )

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.start_date, date(2026, 10, 1))
        self.assertEqual(self.assignment.end_date, date(2026, 12, 15))
        self.assertEqual(self.assignment.allocation_percentage, 40)
        self.assertEqual(self.assignment.role_on_project, "Platform lead")

    def test_stale_and_mismatched_project_context_returns_not_found(self):
        mismatched_url = reverse(
            "frontend:project_assignment_update",
            args=[
                self.project.project_id,
                self.other_assignment.assignment_id,
            ],
        )
        stale_urls = (
            reverse("frontend:project_assignment_create", args=[999999]),
            reverse(
                "frontend:project_assignment_update",
                args=[self.project.project_id, 999999],
            ),
        )
        for url in (mismatched_url, *stale_urls):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url).status_code, 404)

        self.assertTrue(
            Assignment.objects.filter(pk=self.other_assignment.pk).exists()
        )

    def test_anonymous_and_viewer_users_cannot_access_assignment_writes(self):
        for url in (self.create_url, self.update_url):
            with self.subTest(access="anonymous", url=url):
                response = Client().get(url)
                self.assertRedirects(
                    response,
                    f"{reverse('frontend:login')}?next={url}",
                    fetch_redirect_response=False,
                )

        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        assignment_count = Assignment.objects.count()
        self.assertEqual(viewer_client.get(self.create_url).status_code, 403)
        self.assertEqual(viewer_client.get(self.update_url).status_code, 403)
        self.assertEqual(
            viewer_client.post(
                self.create_url,
                self.valid_create_data(),
            ).status_code,
            403,
        )
        self.assertEqual(
            viewer_client.post(
                self.update_url,
                self.valid_update_data(),
            ).status_code,
            403,
        )
        self.assertEqual(Assignment.objects.count(), assignment_count)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.allocation_percentage, 40)

    def test_add_and_change_permissions_are_enforced_independently(self):
        add_client = Client()
        add_client.force_login(self.add_only_user)
        self.assertEqual(add_client.get(self.create_url).status_code, 200)
        self.assertEqual(add_client.get(self.update_url).status_code, 403)

        change_client = Client()
        change_client.force_login(self.change_only_user)
        self.assertEqual(change_client.get(self.create_url).status_code, 403)
        self.assertEqual(change_client.get(self.update_url).status_code, 200)

    def test_csrf_enforcement_rejects_create_and_update_without_tokens(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.manager)
        assignment_count = Assignment.objects.count()

        self.assertEqual(
            csrf_client.post(
                self.create_url,
                self.valid_create_data(),
            ).status_code,
            403,
        )
        self.assertEqual(
            csrf_client.post(
                self.update_url,
                self.valid_update_data(),
            ).status_code,
            403,
        )
        self.assertEqual(Assignment.objects.count(), assignment_count)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.allocation_percentage, 40)

    def test_rendered_csrf_tokens_allow_create_and_update(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.manager)

        create_form = csrf_client.get(self.create_url)
        create_data = self.valid_create_data()
        create_data["csrfmiddlewaretoken"] = self.assignment_form_csrf_token(
            create_form
        )
        create_response = csrf_client.post(self.create_url, create_data)
        created = Assignment.objects.get(
            project=self.project,
            employee=self.taylor,
        )
        self.assertRedirects(
            create_response,
            self.detail_url,
            fetch_redirect_response=False,
        )

        update_url = reverse(
            "frontend:project_assignment_update",
            args=[self.project.project_id, created.assignment_id],
        )
        update_form = csrf_client.get(update_url)
        update_data = self.valid_create_data()
        update_data.update(
            {
                "allocation_percentage": "65",
                "role_on_project": "Senior backend engineer",
                "csrfmiddlewaretoken": self.assignment_form_csrf_token(
                    update_form
                ),
            }
        )
        update_response = csrf_client.post(update_url, update_data)
        self.assertRedirects(
            update_response,
            self.detail_url,
            fetch_redirect_response=False,
        )
        created.refresh_from_db()
        self.assertEqual(created.allocation_percentage, 65)
        self.assertEqual(created.role_on_project, "Senior backend engineer")

    def test_failed_create_and_update_roll_back_with_feedback(self):
        original_save = Assignment.save

        def save_then_fail(instance, *args, **kwargs):
            original_save(instance, *args, **kwargs)
            raise DatabaseError("Simulated assignment save failure")

        with patch.object(Assignment, "save", new=save_then_fail):
            create_response = self.client.post(
                self.create_url,
                self.valid_create_data(),
            )
        self.assertEqual(create_response.status_code, 200)
        self.assertFalse(
            Assignment.objects.filter(
                project=self.project,
                employee=self.taylor,
            ).exists()
        )

        with patch.object(Assignment, "save", new=save_then_fail):
            update_response = self.client.post(
                self.update_url,
                self.valid_update_data(),
            )
        self.assertEqual(update_response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.start_date, date(2026, 10, 1))
        self.assertEqual(self.assignment.allocation_percentage, 40)
        self.assertEqual(self.assignment.role_on_project, "Platform lead")

        for response in (create_response, update_response):
            self.assertContains(
                response,
                "We could not save this assignment. No changes were applied. "
                "Please try again.",
            )
