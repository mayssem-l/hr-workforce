import re
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import NON_FIELD_ERRORS
from django.db import DatabaseError
from django.test import Client, TestCase
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
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)


class ProjectRequirementManagementTests(TestCase):
    REQUIREMENT_FORM_CSRF_PATTERN = re.compile(
        r'<form method="post" novalidate data-loading-form>\s*'
        r'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)">'
    )

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.hr_admin = cls._group_user(
            "requirement-hr",
            HR_ADMINISTRATOR_GROUP,
        )
        cls.manager = cls._group_user(
            "requirement-manager",
            MANAGER_PLANNER_GROUP,
        )
        cls.viewer = cls._group_user(
            "requirement-viewer",
            VIEWER_GROUP,
        )
        cls.add_only_user = cls._permission_user(
            "requirement-add-only",
            "add_projectskillrequirement",
        )
        cls.change_only_user = cls._permission_user(
            "requirement-change-only",
            "change_projectskillrequirement",
        )
        cls.delete_only_user = cls._permission_user(
            "requirement-delete-only",
            "delete_projectskillrequirement",
        )

        cls.python = Skill.objects.create(
            name="Python",
            category="Engineering",
        )
        cls.django = Skill.objects.create(
            name="Django",
            category="Engineering",
        )
        cls.sql = Skill.objects.create(name="SQL", category="Data")
        cls.leadership = Skill.objects.create(
            name="Leadership",
            category="Management",
        )
        cls.project = cls._create_project("Atlas Renewal")
        cls.other_project = cls._create_project("Beacon Launch")
        cls.requirement = cls._create_requirement(
            project=cls.project,
            skill=cls.python,
            required_level=3,
            required_quantity=2,
            estimated_effort_hours="120.00",
            is_mandatory=True,
        )
        cls.django_requirement = cls._create_requirement(
            project=cls.project,
            skill=cls.django,
            required_level=2,
            required_quantity=1,
            estimated_effort_hours="40.00",
            is_mandatory=False,
        )
        cls.other_requirement = cls._create_requirement(
            project=cls.other_project,
            skill=cls.sql,
            required_level=2,
            required_quantity=1,
            estimated_effort_hours="80.00",
            is_mandatory=True,
        )

        employee = Employee.objects.create(
            first_name="Jamie",
            last_name="Rivera",
            department="Engineering",
            position="Platform Engineer",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("6.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )
        EmployeeSkill.objects.create(
            employee=employee,
            skill=cls.python,
            level=4,
            years_experience=Decimal("5.0"),
        )
        cls.assignment = Assignment.objects.create(
            employee=employee,
            project=cls.project,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 31),
            allocation_percentage=50,
            role_on_project="Technical lead",
            status=Assignment.Status.ACTIVE,
        )
        cls.coverage = AssignmentSkill.objects.create(
            assignment=cls.assignment,
            project_skill_requirement=cls.requirement,
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
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.MEDIUM,
        )

    @classmethod
    def _create_requirement(
        cls,
        *,
        project,
        skill,
        required_level,
        required_quantity,
        estimated_effort_hours,
        is_mandatory,
    ):
        return ProjectSkillRequirement.objects.create(
            project=project,
            skill=skill,
            required_level=required_level,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=is_mandatory,
            required_quantity=required_quantity,
            estimated_effort_hours=(
                Decimal(estimated_effort_hours)
                if estimated_effort_hours is not None
                else None
            ),
        )

    def setUp(self):
        self.detail_url = reverse(
            "frontend:project_detail",
            args=[self.project.project_id],
        )
        self.create_url = reverse(
            "frontend:project_requirement_create",
            args=[self.project.project_id],
        )
        self.update_url = reverse(
            "frontend:project_requirement_update",
            args=[
                self.project.project_id,
                self.requirement.project_skill_requirement_id,
            ],
        )
        self.remove_url = reverse(
            "frontend:project_requirement_remove",
            args=[
                self.project.project_id,
                self.requirement.project_skill_requirement_id,
            ],
        )
        self.client.force_login(self.hr_admin)

    def valid_create_data(
        self,
        *,
        skill=None,
        effort="60.00",
        mandatory=True,
    ):
        data = {
            "skill": (skill or self.sql).skill_id,
            "required_level": "4",
            "priority": ProjectSkillRequirement.Priority.MEDIUM,
            "required_quantity": "2",
            "estimated_effort_hours": effort,
        }
        if mandatory:
            data["is_mandatory"] = "on"
        return data

    def valid_update_data(self, *, skill=None):
        return {
            "skill": (skill or self.leadership).skill_id,
            "required_level": "4",
            "priority": ProjectSkillRequirement.Priority.MEDIUM,
            "is_mandatory": "on",
            "required_quantity": "3",
            "estimated_effort_hours": "180.50",
        }

    def current_requirement_update_data(self, *, required_quantity):
        return {
            "skill": self.python.skill_id,
            "required_level": "3",
            "priority": ProjectSkillRequirement.Priority.HIGH,
            "is_mandatory": "on",
            "required_quantity": str(required_quantity),
            "estimated_effort_hours": "120.00",
        }

    def add_requirement_coverage(self, *, first_name, last_name):
        employee = Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Engineering",
            position="Software Engineer",
            hire_date=date(2021, 2, 1),
            experience_years=Decimal("5.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )
        EmployeeSkill.objects.create(
            employee=employee,
            skill=self.python,
            level=4,
            years_experience=Decimal("4.0"),
        )
        assignment = Assignment.objects.create(
            employee=employee,
            project=self.project,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 31),
            allocation_percentage=50,
            role_on_project="Software engineer",
            status=Assignment.Status.ACTIVE,
        )
        return AssignmentSkill.objects.create(
            assignment=assignment,
            project_skill_requirement=self.requirement,
        )

    def requirement_form_csrf_token(self, response):
        match = self.REQUIREMENT_FORM_CSRF_PATTERN.search(
            response.content.decode("utf-8")
        )
        self.assertIsNotNone(
            match,
            "The project requirement POST form must render its own CSRF input.",
        )
        return match.group(1)

    def removal_form_csrf_token(self, response):
        pattern = re.compile(
            rf'<form method="post" action="{re.escape(self.remove_url)}" '
            rf'data-loading-form>\s*'
            rf'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)">'
        )
        match = pattern.search(response.content.decode("utf-8"))
        self.assertIsNotNone(
            match,
            "The requirement removal form must render its own CSRF input.",
        )
        return match.group(1)

    def test_routes_are_project_scoped_namespaced_and_render(self):
        self.assertEqual(
            self.create_url,
            f"/projects/{self.project.project_id}/requirements/add/",
        )
        self.assertEqual(
            self.update_url,
            f"/projects/{self.project.project_id}/requirements/"
            f"{self.requirement.project_skill_requirement_id}/edit/",
        )
        self.assertEqual(
            self.remove_url,
            f"/projects/{self.project.project_id}/requirements/"
            f"{self.requirement.project_skill_requirement_id}/remove/",
        )
        self.assertEqual(
            resolve(self.create_url).view_name,
            "frontend:project_requirement_create",
        )
        self.assertEqual(
            resolve(self.update_url).view_name,
            "frontend:project_requirement_update",
        )
        self.assertEqual(
            resolve(self.remove_url).view_name,
            "frontend:project_requirement_remove",
        )

        create_response = self.client.get(self.create_url)
        self.assertTemplateUsed(
            create_response,
            "frontend/projects/requirements/create.html",
        )
        self.assertTemplateUsed(
            create_response,
            "frontend/projects/requirements/_form.html",
        )
        self.assertContains(
            create_response,
            "<h1>Add skill requirement</h1>",
            html=True,
        )
        self.assertContains(create_response, "Atlas Renewal")
        self.assertContains(create_response, "SQL — Data")
        self.assertNotContains(create_response, "Python — Engineering")
        self.assertNotContains(create_response, "Django — Engineering")
        self.requirement_form_csrf_token(create_response)

        update_response = self.client.get(self.update_url)
        self.assertTemplateUsed(
            update_response,
            "frontend/projects/requirements/edit.html",
        )
        self.assertContains(
            update_response,
            "<h1>Edit skill requirement</h1>",
            html=True,
        )
        self.assertContains(update_response, "Python — Engineering")
        self.assertNotContains(update_response, "Django — Engineering")
        self.assertContains(update_response, "Save requirement")
        self.requirement_form_csrf_token(update_response)

        confirmation = self.client.get(self.remove_url)
        self.assertTemplateUsed(
            confirmation,
            "frontend/projects/requirements/confirm_remove.html",
        )
        self.assertContains(confirmation, "Remove this skill requirement?")
        self.assertContains(confirmation, "1 linked assignment")
        self.assertContains(
            confirmation,
            "Any assignment coverage linked to this requirement will also be "
            "removed.",
        )
        self.removal_form_csrf_token(confirmation)

        for response in (create_response, update_response, confirmation):
            self.assertRegex(
                response.content.decode("utf-8"),
                r'href="/projects/"\s+aria-current="page"',
            )

    def test_project_detail_connects_only_permitted_requirement_actions(self):
        hr_response = self.client.get(self.detail_url)
        self.assertContains(hr_response, self.create_url)
        self.assertContains(hr_response, self.update_url)
        self.assertContains(hr_response, self.remove_url)

        manager_client = Client()
        manager_client.force_login(self.manager)
        manager_response = manager_client.get(self.detail_url)
        self.assertContains(manager_response, self.create_url)
        self.assertContains(manager_response, self.update_url)
        self.assertNotContains(manager_response, self.remove_url)

        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        viewer_response = viewer_client.get(self.detail_url)
        self.assertNotContains(viewer_response, "Add requirement")
        self.assertNotContains(viewer_response, self.update_url)
        self.assertNotContains(viewer_response, self.remove_url)

    def test_valid_requirement_creation_adds_project_skill_demand(self):
        response = self.client.post(
            self.create_url,
            self.valid_create_data(),
            follow=True,
        )

        requirement = ProjectSkillRequirement.objects.get(
            project=self.project,
            skill=self.sql,
        )
        self.assertRedirects(response, self.detail_url)
        self.assertEqual(requirement.required_level, 4)
        self.assertEqual(requirement.priority, ProjectSkillRequirement.Priority.MEDIUM)
        self.assertTrue(requirement.is_mandatory)
        self.assertEqual(requirement.required_quantity, 2)
        self.assertEqual(requirement.estimated_effort_hours, Decimal("60.00"))
        self.assertContains(
            response,
            "SQL was added to Atlas Renewal&#x27;s skill demand.",
        )
        self.assertContains(response, "Level 4 of 5")

    def test_duplicate_skill_is_prevented_by_existing_model_constraint(self):
        requirement_count = ProjectSkillRequirement.objects.count()
        response = self.client.post(
            self.create_url,
            self.valid_create_data(skill=self.django),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProjectSkillRequirement.objects.count(), requirement_count)
        self.assertIn(NON_FIELD_ERRORS, response.context["form"].errors)
        self.assertContains(response, "This project already requires this skill.")
        self.assertContains(
            response,
            "Skill requirement details could not be saved.",
        )

    def test_invalid_level_quantity_and_effort_have_field_feedback(self):
        invalid_values = (
            ("required_level", "0"),
            ("required_level", "6"),
            ("required_quantity", "0"),
            ("estimated_effort_hours", "-0.01"),
        )
        for field_name, value in invalid_values:
            with self.subTest(field=field_name, value=value):
                data = self.valid_create_data()
                data[field_name] = value
                response = self.client.post(self.create_url, data)

                self.assertEqual(response.status_code, 200)
                self.assertIn(field_name, response.context["form"].errors)
                self.assertContains(response, f'id="id_{field_name}_error"')
                self.assertContains(response, 'aria-invalid="true"')
                self.assertFalse(
                    ProjectSkillRequirement.objects.filter(
                        project=self.project,
                        skill=self.sql,
                    ).exists()
                )

    def test_missing_or_zero_mandatory_effort_uses_service_preflight_feedback(self):
        for skill, effort in ((self.sql, ""), (self.leadership, "0")):
            with self.subTest(skill=skill.name, effort=effort or "blank"):
                response = self.client.post(
                    self.create_url,
                    self.valid_create_data(skill=skill, effort=effort),
                    follow=True,
                )

                self.assertRedirects(response, self.detail_url)
                requirement = ProjectSkillRequirement.objects.get(
                    project=self.project,
                    skill=skill,
                )
                expected_effort = None if effort == "" else Decimal("0")
                self.assertEqual(
                    requirement.estimated_effort_hours,
                    expected_effort,
                )
                self.assertContains(response, "Planning input needed")
                self.assertContains(
                    response,
                    "Enter estimated effort greater than 0 hours for the mandatory "
                    f"{skill.name} requirement before generating recommendations.",
                )

    def test_maintenance_form_renders_existing_service_preflight_blockers(self):
        preflight = {
            "can_generate_recommendations": False,
            "blockers": [{"message": "Service-owned planning guidance."}],
        }
        with patch(
            "frontend.views.requirements.get_recommendation_preflight",
            return_value=preflight,
        ) as service:
            response = self.client.get(self.create_url)

        self.assertContains(response, "Existing planning input needs attention")
        self.assertContains(response, "Service-owned planning guidance.")
        service.assert_called_once_with(self.project)
        self.assertIs(response.context["preflight"], preflight)

    def test_valid_update_changes_the_requirement_through_model_form(self):
        response = self.client.post(
            self.update_url,
            self.valid_update_data(),
            follow=True,
        )

        self.requirement.refresh_from_db()
        self.assertRedirects(response, self.detail_url)
        self.assertEqual(self.requirement.skill, self.leadership)
        self.assertEqual(self.requirement.required_level, 4)
        self.assertEqual(self.requirement.required_quantity, 3)
        self.assertEqual(
            self.requirement.priority,
            ProjectSkillRequirement.Priority.MEDIUM,
        )
        self.assertTrue(self.requirement.is_mandatory)
        self.assertEqual(
            self.requirement.estimated_effort_hours,
            Decimal("180.50"),
        )
        self.assertContains(
            response,
            "The Leadership requirement for Atlas Renewal was updated.",
        )

    def test_quantity_equal_to_current_coverage_is_allowed(self):
        response = self.client.post(
            self.update_url,
            self.current_requirement_update_data(required_quantity=1),
            follow=True,
        )

        self.requirement.refresh_from_db()
        self.assertRedirects(response, self.detail_url)
        self.assertEqual(self.requirement.required_quantity, 1)
        self.assertTrue(
            AssignmentSkill.objects.filter(pk=self.coverage.pk).exists()
        )

    def test_quantity_below_current_coverage_is_rejected(self):
        second_coverage = self.add_requirement_coverage(
            first_name="Maurice",
            last_name="Joly",
        )

        response = self.client.post(
            self.update_url,
            self.current_requirement_update_data(required_quantity=1),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("required_quantity", response.context["form"].errors)
        self.assertTrue(
            AssignmentSkill.objects.filter(pk=second_coverage.pk).exists()
        )

    def test_quantity_can_be_reduced_after_coverage_is_manually_removed(self):
        second_coverage = self.add_requirement_coverage(
            first_name="Maurice",
            last_name="Joly",
        )
        remove_url = reverse(
            "frontend:project_assignment_coverage_remove",
            args=[
                self.project.project_id,
                second_coverage.assignment_id,
                second_coverage.assignment_skill_id,
            ],
        )

        removal_response = self.client.post(remove_url)
        self.assertEqual(removal_response.status_code, 302)
        self.assertFalse(
            AssignmentSkill.objects.filter(pk=second_coverage.pk).exists()
        )

        update_response = self.client.post(
            self.update_url,
            self.current_requirement_update_data(required_quantity=1),
            follow=True,
        )

        self.requirement.refresh_from_db()
        self.assertRedirects(update_response, self.detail_url)
        self.assertEqual(self.requirement.required_quantity, 1)

    def test_rejected_quantity_shows_coverage_guidance_and_preserves_value(self):
        self.add_requirement_coverage(
            first_name="Maurice",
            last_name="Joly",
        )

        response = self.client.post(
            self.update_url,
            self.current_requirement_update_data(required_quantity=1),
        )

        self.requirement.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.requirement.required_quantity, 2)
        self.assertContains(
            response,
            "This requirement is currently covered by 2 employees. To reduce "
            "the required quantity to 1, first remove one employee from this "
            "requirement&#x27;s coverage.",
        )
        self.assertContains(response, "Currently covering this requirement:")
        self.assertContains(response, "Maurice Joly")
        self.assertContains(response, "Jamie Rivera")
        self.assertContains(response, 'id="id_required_quantity_error"')
        self.assertContains(response, 'aria-invalid="true"')

    def test_invalid_and_duplicate_updates_preserve_stored_requirement(self):
        invalid_response = self.client.post(
            self.update_url,
            {
                **self.valid_update_data(),
                "required_level": "6",
                "required_quantity": "0",
                "estimated_effort_hours": "-1.00",
            },
        )
        self.assertIn("required_level", invalid_response.context["form"].errors)
        self.assertIn("required_quantity", invalid_response.context["form"].errors)
        self.assertIn(
            "estimated_effort_hours",
            invalid_response.context["form"].errors,
        )

        duplicate_response = self.client.post(
            self.update_url,
            self.valid_update_data(skill=self.django),
        )
        self.assertIn(NON_FIELD_ERRORS, duplicate_response.context["form"].errors)
        self.assertContains(
            duplicate_response,
            "This project already requires this skill.",
        )

        self.requirement.refresh_from_db()
        self.assertEqual(self.requirement.skill, self.python)
        self.assertEqual(self.requirement.required_level, 3)
        self.assertEqual(self.requirement.required_quantity, 2)
        self.assertEqual(
            self.requirement.estimated_effort_hours,
            Decimal("120.00"),
        )

    def test_confirmed_removal_deletes_requirement_and_its_coverage_only(self):
        confirmation = self.client.get(self.remove_url)
        self.assertEqual(confirmation.status_code, 200)
        self.assertTrue(
            ProjectSkillRequirement.objects.filter(pk=self.requirement.pk).exists()
        )

        response = self.client.post(self.remove_url, follow=True)

        self.assertRedirects(response, self.detail_url)
        self.assertFalse(
            ProjectSkillRequirement.objects.filter(pk=self.requirement.pk).exists()
        )
        self.assertFalse(AssignmentSkill.objects.filter(pk=self.coverage.pk).exists())
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
        self.assertTrue(Skill.objects.filter(pk=self.python.pk).exists())
        self.assertTrue(Assignment.objects.filter(pk=self.assignment.pk).exists())
        self.assertContains(
            response,
            "The Python requirement was removed from Atlas Renewal.",
        )

    def test_stale_and_mismatched_project_relationships_return_not_found(self):
        mismatched_urls = (
            reverse(
                "frontend:project_requirement_update",
                args=[
                    self.project.project_id,
                    self.other_requirement.project_skill_requirement_id,
                ],
            ),
            reverse(
                "frontend:project_requirement_remove",
                args=[
                    self.project.project_id,
                    self.other_requirement.project_skill_requirement_id,
                ],
            ),
        )
        stale_urls = (
            reverse(
                "frontend:project_requirement_update",
                args=[self.project.project_id, 999999],
            ),
            reverse(
                "frontend:project_requirement_remove",
                args=[self.project.project_id, 999999],
            ),
            reverse(
                "frontend:project_requirement_create",
                args=[999999],
            ),
        )
        for url in (*mismatched_urls, *stale_urls):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url).status_code, 404)

        self.assertTrue(
            ProjectSkillRequirement.objects.filter(
                pk=self.other_requirement.pk
            ).exists()
        )

    def test_anonymous_and_viewer_users_cannot_access_mutations(self):
        urls = (self.create_url, self.update_url, self.remove_url)
        for url in urls:
            with self.subTest(access="anonymous", url=url):
                response = Client().get(url)
                self.assertRedirects(
                    response,
                    f"{reverse('frontend:login')}?next={url}",
                    fetch_redirect_response=False,
                )

        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        requirement_count = ProjectSkillRequirement.objects.count()
        for url, data in (
            (self.create_url, self.valid_create_data()),
            (self.update_url, self.valid_update_data()),
            (self.remove_url, {}),
        ):
            with self.subTest(access="viewer", url=url):
                self.assertEqual(viewer_client.get(url).status_code, 403)
                self.assertEqual(viewer_client.post(url, data).status_code, 403)

        self.assertEqual(ProjectSkillRequirement.objects.count(), requirement_count)
        self.requirement.refresh_from_db()
        self.assertEqual(self.requirement.skill, self.python)

    def test_requirement_permissions_are_enforced_independently(self):
        permission_matrix = (
            (self.add_only_user, (200, 403, 403)),
            (self.change_only_user, (403, 200, 403)),
            (self.delete_only_user, (403, 403, 200)),
            (self.manager, (200, 200, 403)),
        )
        for user, expected_statuses in permission_matrix:
            client = Client()
            client.force_login(user)
            actual_statuses = tuple(
                client.get(url).status_code
                for url in (self.create_url, self.update_url, self.remove_url)
            )
            with self.subTest(user=user.username):
                self.assertEqual(actual_statuses, expected_statuses)

    def test_csrf_enforcement_rejects_all_requirement_mutations(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr_admin)
        requirement_count = ProjectSkillRequirement.objects.count()

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
        self.assertEqual(csrf_client.post(self.remove_url).status_code, 403)
        self.assertEqual(ProjectSkillRequirement.objects.count(), requirement_count)
        self.requirement.refresh_from_db()
        self.assertEqual(self.requirement.skill, self.python)

    def test_rendered_csrf_tokens_allow_create_update_and_removal(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr_admin)

        create_form = csrf_client.get(self.create_url)
        create_data = self.valid_create_data(skill=self.sql)
        create_data["csrfmiddlewaretoken"] = self.requirement_form_csrf_token(
            create_form
        )
        create_response = csrf_client.post(self.create_url, create_data)
        created = ProjectSkillRequirement.objects.get(
            project=self.project,
            skill=self.sql,
        )
        self.assertRedirects(
            create_response,
            self.detail_url,
            fetch_redirect_response=False,
        )

        update_url = reverse(
            "frontend:project_requirement_update",
            args=[self.project.project_id, created.project_skill_requirement_id],
        )
        update_form = csrf_client.get(update_url)
        update_data = {
            **self.valid_create_data(skill=self.sql, mandatory=False),
            "required_level": "2",
            "csrfmiddlewaretoken": self.requirement_form_csrf_token(update_form),
        }
        update_response = csrf_client.post(update_url, update_data)
        self.assertRedirects(
            update_response,
            self.detail_url,
            fetch_redirect_response=False,
        )
        created.refresh_from_db()
        self.assertEqual(created.required_level, 2)
        self.assertFalse(created.is_mandatory)

        remove_url = reverse(
            "frontend:project_requirement_remove",
            args=[self.project.project_id, created.project_skill_requirement_id],
        )
        remove_form = csrf_client.get(remove_url)
        remove_pattern = re.compile(
            rf'<form method="post" action="{re.escape(remove_url)}" '
            rf'data-loading-form>\s*'
            rf'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)">'
        )
        token_match = remove_pattern.search(remove_form.content.decode("utf-8"))
        self.assertIsNotNone(token_match)
        remove_response = csrf_client.post(
            remove_url,
            {"csrfmiddlewaretoken": token_match.group(1)},
        )
        self.assertRedirects(
            remove_response,
            self.detail_url,
            fetch_redirect_response=False,
        )
        self.assertFalse(
            ProjectSkillRequirement.objects.filter(pk=created.pk).exists()
        )

    def test_failed_create_update_and_removal_roll_back(self):
        original_save = ProjectSkillRequirement.save

        def save_then_fail(instance, *args, **kwargs):
            original_save(instance, *args, **kwargs)
            raise DatabaseError("Simulated requirement save failure")

        with patch.object(ProjectSkillRequirement, "save", new=save_then_fail):
            create_response = self.client.post(
                self.create_url,
                self.valid_create_data(),
            )
        self.assertEqual(create_response.status_code, 200)
        self.assertFalse(
            ProjectSkillRequirement.objects.filter(
                project=self.project,
                skill=self.sql,
            ).exists()
        )

        with patch.object(ProjectSkillRequirement, "save", new=save_then_fail):
            update_response = self.client.post(
                self.update_url,
                self.valid_update_data(),
            )
        self.assertEqual(update_response.status_code, 200)
        self.requirement.refresh_from_db()
        self.assertEqual(self.requirement.skill, self.python)
        self.assertEqual(self.requirement.required_level, 3)

        original_delete = ProjectSkillRequirement.delete

        def delete_then_fail(instance, *args, **kwargs):
            original_delete(instance, *args, **kwargs)
            raise DatabaseError("Simulated requirement removal failure")

        with patch.object(
            ProjectSkillRequirement,
            "delete",
            new=delete_then_fail,
        ):
            remove_response = self.client.post(self.remove_url)
        self.assertEqual(remove_response.status_code, 200)
        self.assertTrue(
            ProjectSkillRequirement.objects.filter(pk=self.requirement.pk).exists()
        )
        self.assertTrue(AssignmentSkill.objects.filter(pk=self.coverage.pk).exists())

        for response in (create_response, update_response):
            self.assertContains(
                response,
                "We could not save this skill requirement. No changes were "
                "applied. Please try again.",
            )
        self.assertContains(
            remove_response,
            "We could not remove this skill requirement. No changes were "
            "applied. Please try again.",
        )
