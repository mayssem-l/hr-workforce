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

from core.models import Employee, EmployeeSkill, Skill
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)


class EmployeeProficiencyManagementTests(TestCase):
    PROFICIENCY_FORM_CSRF_PATTERN = re.compile(
        r'<form method="post" novalidate data-loading-form>\s*'
        r'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)">'
    )

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.hr_admin = get_user_model().objects.create_user(
            username="proficiency-hr"
        )
        cls.hr_admin.groups.add(Group.objects.get(name=HR_ADMINISTRATOR_GROUP))
        cls.viewer = get_user_model().objects.create_user(
            username="proficiency-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))

        cls.add_only_user = cls._permission_user(
            "proficiency-add-only",
            "add_employeeskill",
        )
        cls.change_only_user = cls._permission_user(
            "proficiency-change-only",
            "change_employeeskill",
        )
        cls.delete_only_user = cls._permission_user(
            "proficiency-delete-only",
            "delete_employeeskill",
        )

        cls.employee = cls._create_employee("Jamie", "Rivera")
        cls.other_employee = cls._create_employee("Morgan", "Lee")
        cls.python = Skill.objects.create(name="Python", category="Engineering")
        cls.django = Skill.objects.create(name="Django", category="Engineering")
        cls.sql = Skill.objects.create(name="SQL", category="Data")
        cls.employee_skill = EmployeeSkill.objects.create(
            employee=cls.employee,
            skill=cls.python,
            level=4,
            years_experience=Decimal("6.5"),
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

    def setUp(self):
        self.detail_url = reverse(
            "frontend:employee_detail",
            args=[self.employee.employee_id],
        )
        self.create_url = reverse(
            "frontend:employee_skill_create",
            args=[self.employee.employee_id],
        )
        self.update_url = reverse(
            "frontend:employee_skill_update",
            args=[
                self.employee.employee_id,
                self.employee_skill.employee_skill_id,
            ],
        )
        self.remove_url = reverse(
            "frontend:employee_skill_remove",
            args=[
                self.employee.employee_id,
                self.employee_skill.employee_skill_id,
            ],
        )
        self.client.force_login(self.hr_admin)

    def valid_create_data(self, *, skill=None):
        return {
            "skill": (skill or self.django).skill_id,
            "level": "5",
            "years_experience": "3.5",
        }

    @staticmethod
    def valid_update_data():
        return {"level": "3", "years_experience": "7.0"}

    def proficiency_form_csrf_token(self, response):
        match = self.PROFICIENCY_FORM_CSRF_PATTERN.search(
            response.content.decode("utf-8")
        )
        self.assertIsNotNone(
            match,
            "The employee proficiency POST form must render its own CSRF input.",
        )
        return match.group(1)

    def removal_form_csrf_token(self, response, action_url):
        pattern = re.compile(
            rf'<form method="post" action="{re.escape(action_url)}" '
            rf'data-loading-form>\s*'
            rf'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)">'
        )
        match = pattern.search(response.content.decode("utf-8"))
        self.assertIsNotNone(
            match,
            "The proficiency removal form must render its own CSRF input.",
        )
        return match.group(1)

    def test_routes_are_employee_scoped_namespaced_and_render(self):
        self.assertEqual(
            self.create_url,
            f"/employees/{self.employee.employee_id}/skills/add/",
        )
        self.assertEqual(
            self.update_url,
            f"/employees/{self.employee.employee_id}/skills/"
            f"{self.employee_skill.employee_skill_id}/edit/",
        )
        self.assertEqual(
            self.remove_url,
            f"/employees/{self.employee.employee_id}/skills/"
            f"{self.employee_skill.employee_skill_id}/remove/",
        )
        self.assertEqual(
            resolve(self.create_url).view_name,
            "frontend:employee_skill_create",
        )
        self.assertEqual(
            resolve(self.update_url).view_name,
            "frontend:employee_skill_update",
        )
        self.assertEqual(
            resolve(self.remove_url).view_name,
            "frontend:employee_skill_remove",
        )

        create_response = self.client.get(self.create_url)
        self.assertTemplateUsed(
            create_response,
            "frontend/employees/proficiencies/create.html",
        )
        self.assertTemplateUsed(
            create_response,
            "frontend/employees/proficiencies/_form.html",
        )
        self.assertContains(create_response, "<h1>Add skill</h1>", html=True)
        self.assertContains(create_response, "Jamie Rivera")
        self.assertContains(create_response, "Django — Engineering")
        self.assertNotContains(create_response, "Python — Engineering")
        self.proficiency_form_csrf_token(create_response)

        update_response = self.client.get(self.update_url)
        self.assertTemplateUsed(
            update_response,
            "frontend/employees/proficiencies/edit.html",
        )
        self.assertContains(
            update_response,
            "<h1>Edit proficiency</h1>",
            html=True,
        )
        self.assertContains(update_response, "Python")
        self.assertNotContains(update_response, 'name="skill"')
        self.proficiency_form_csrf_token(update_response)

        remove_response = self.client.get(self.remove_url)
        self.assertTemplateUsed(
            remove_response,
            "frontend/employees/proficiencies/confirm_remove.html",
        )
        self.assertContains(remove_response, "Remove this proficiency?")
        self.assertContains(remove_response, "Level 4 of 5")
        self.removal_form_csrf_token(remove_response, self.remove_url)

    def test_employee_profile_connects_authorized_actions_naturally(self):
        response = self.client.get(self.detail_url)

        self.assertContains(response, self.create_url)
        self.assertContains(response, "Add skill")
        self.assertContains(response, self.update_url)
        self.assertContains(response, "Edit")
        self.assertContains(response, self.remove_url)
        self.assertContains(response, "Remove")

        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        viewer_response = viewer_client.get(self.detail_url)
        self.assertNotContains(viewer_response, "Add skill")
        self.assertNotContains(viewer_response, self.update_url)
        self.assertNotContains(viewer_response, self.remove_url)

    def test_valid_proficiency_creation_adds_skill_to_employee_profile(self):
        response = self.client.post(
            self.create_url,
            self.valid_create_data(),
            follow=True,
        )

        proficiency = EmployeeSkill.objects.get(
            employee=self.employee,
            skill=self.django,
        )
        self.assertRedirects(response, self.detail_url)
        self.assertEqual(proficiency.level, 5)
        self.assertEqual(proficiency.years_experience, Decimal("3.5"))
        self.assertContains(
            response,
            "Django was added to Jamie Rivera&#x27;s skill profile.",
        )
        self.assertContains(response, "Level 5 of 5")
        self.assertContains(response, "3.5 years of experience")

    def test_duplicate_skill_is_prevented_by_existing_model_constraint(self):
        proficiency_count = EmployeeSkill.objects.count()
        response = self.client.post(
            self.create_url,
            self.valid_create_data(skill=self.python),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(EmployeeSkill.objects.count(), proficiency_count)
        self.assertIn(NON_FIELD_ERRORS, response.context["form"].errors)
        self.assertContains(response, "This employee already has this skill.")
        self.assertContains(response, "Proficiency details could not be saved.")

    def test_invalid_level_is_rejected_with_field_feedback(self):
        for invalid_level in ("0", "6"):
            with self.subTest(level=invalid_level):
                data = self.valid_create_data()
                data["level"] = invalid_level
                response = self.client.post(self.create_url, data)

                self.assertEqual(response.status_code, 200)
                self.assertIn("level", response.context["form"].errors)
                self.assertContains(response, 'id="id_level_error"')
                self.assertContains(response, 'aria-invalid="true"')
                self.assertFalse(
                    EmployeeSkill.objects.filter(
                        employee=self.employee,
                        skill=self.django,
                    ).exists()
                )

    def test_invalid_experience_is_rejected_with_field_feedback(self):
        data = self.valid_create_data()
        data["years_experience"] = "-0.1"
        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("years_experience", response.context["form"].errors)
        self.assertContains(response, 'id="id_years_experience_error"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertFalse(
            EmployeeSkill.objects.filter(
                employee=self.employee,
                skill=self.django,
            ).exists()
        )

    def test_valid_update_changes_only_proficiency_values(self):
        update_data = self.valid_update_data()
        update_data["skill"] = self.sql.skill_id
        response = self.client.post(self.update_url, update_data, follow=True)

        self.employee_skill.refresh_from_db()
        self.assertRedirects(response, self.detail_url)
        self.assertEqual(self.employee_skill.skill, self.python)
        self.assertEqual(self.employee_skill.level, 3)
        self.assertEqual(self.employee_skill.years_experience, Decimal("7.0"))
        self.assertContains(
            response,
            "Python proficiency for Jamie Rivera was updated.",
        )

    def test_invalid_update_preserves_values_and_field_feedback(self):
        response = self.client.post(
            self.update_url,
            {"level": "6", "years_experience": "-0.1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("level", response.context["form"].errors)
        self.assertIn("years_experience", response.context["form"].errors)
        self.assertContains(response, 'id="id_level_error"')
        self.assertContains(response, 'id="id_years_experience_error"')
        self.assertContains(
            response,
            "Please correct the highlighted fields before saving changes.",
        )
        self.employee_skill.refresh_from_db()
        self.assertEqual(self.employee_skill.level, 4)
        self.assertEqual(self.employee_skill.years_experience, Decimal("6.5"))

    def test_confirmed_removal_deletes_only_the_proficiency_relationship(self):
        confirmation = self.client.get(self.remove_url)
        self.assertEqual(confirmation.status_code, 200)
        self.assertTrue(
            EmployeeSkill.objects.filter(pk=self.employee_skill.pk).exists()
        )

        response = self.client.post(self.remove_url, follow=True)

        self.assertRedirects(response, self.detail_url)
        self.assertFalse(
            EmployeeSkill.objects.filter(pk=self.employee_skill.pk).exists()
        )
        self.assertTrue(Employee.objects.filter(pk=self.employee.pk).exists())
        self.assertTrue(Skill.objects.filter(pk=self.python.pk).exists())
        self.assertContains(
            response,
            "Python was removed from Jamie Rivera&#x27;s skill profile.",
        )

    def test_relationship_routes_reject_an_employee_mismatch(self):
        mismatched_update = reverse(
            "frontend:employee_skill_update",
            args=[
                self.other_employee.employee_id,
                self.employee_skill.employee_skill_id,
            ],
        )
        mismatched_remove = reverse(
            "frontend:employee_skill_remove",
            args=[
                self.other_employee.employee_id,
                self.employee_skill.employee_skill_id,
            ],
        )

        self.assertEqual(self.client.get(mismatched_update).status_code, 404)
        self.assertEqual(self.client.post(mismatched_remove).status_code, 404)
        self.assertTrue(
            EmployeeSkill.objects.filter(pk=self.employee_skill.pk).exists()
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
        proficiency_count = EmployeeSkill.objects.count()
        for url, data in (
            (self.create_url, self.valid_create_data()),
            (self.update_url, self.valid_update_data()),
            (self.remove_url, {}),
        ):
            with self.subTest(access="viewer", url=url):
                self.assertEqual(viewer_client.get(url).status_code, 403)
                self.assertEqual(viewer_client.post(url, data).status_code, 403)

        self.assertEqual(EmployeeSkill.objects.count(), proficiency_count)
        self.employee_skill.refresh_from_db()
        self.assertEqual(self.employee_skill.level, 4)

    def test_add_change_and_delete_permissions_are_independent(self):
        permission_matrix = (
            (self.add_only_user, (200, 403, 403)),
            (self.change_only_user, (403, 200, 403)),
            (self.delete_only_user, (403, 403, 200)),
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

    def test_csrf_enforcement_rejects_all_mutations_without_a_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr_admin)
        proficiency_count = EmployeeSkill.objects.count()

        self.assertEqual(
            csrf_client.post(self.create_url, self.valid_create_data()).status_code,
            403,
        )
        self.assertEqual(
            csrf_client.post(self.update_url, self.valid_update_data()).status_code,
            403,
        )
        self.assertEqual(csrf_client.post(self.remove_url).status_code, 403)

        self.assertEqual(EmployeeSkill.objects.count(), proficiency_count)
        self.employee_skill.refresh_from_db()
        self.assertEqual(self.employee_skill.level, 4)

    def test_rendered_csrf_tokens_allow_create_update_and_removal(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr_admin)

        create_form = csrf_client.get(self.create_url)
        create_data = self.valid_create_data(skill=self.sql)
        create_data["csrfmiddlewaretoken"] = self.proficiency_form_csrf_token(
            create_form
        )
        create_response = csrf_client.post(self.create_url, create_data)
        created = EmployeeSkill.objects.get(
            employee=self.employee,
            skill=self.sql,
        )
        self.assertRedirects(
            create_response,
            self.detail_url,
            fetch_redirect_response=False,
        )

        update_url = reverse(
            "frontend:employee_skill_update",
            args=[self.employee.employee_id, created.employee_skill_id],
        )
        update_form = csrf_client.get(update_url)
        update_data = {
            "level": "2",
            "years_experience": "1.5",
            "csrfmiddlewaretoken": self.proficiency_form_csrf_token(update_form),
        }
        update_response = csrf_client.post(update_url, update_data)
        self.assertRedirects(
            update_response,
            self.detail_url,
            fetch_redirect_response=False,
        )
        created.refresh_from_db()
        self.assertEqual(created.level, 2)
        self.assertEqual(created.years_experience, Decimal("1.5"))

        remove_url = reverse(
            "frontend:employee_skill_remove",
            args=[self.employee.employee_id, created.employee_skill_id],
        )
        remove_form = csrf_client.get(remove_url)
        remove_response = csrf_client.post(
            remove_url,
            {
                "csrfmiddlewaretoken": self.removal_form_csrf_token(
                    remove_form,
                    remove_url,
                )
            },
        )
        self.assertRedirects(
            remove_response,
            self.detail_url,
            fetch_redirect_response=False,
        )
        self.assertFalse(EmployeeSkill.objects.filter(pk=created.pk).exists())

    def test_failed_create_rolls_back_and_shows_safe_feedback(self):
        proficiency_count = EmployeeSkill.objects.count()
        original_save = EmployeeSkill.save

        def save_then_fail(instance, *args, **kwargs):
            original_save(instance, *args, **kwargs)
            raise DatabaseError("Simulated proficiency insert failure")

        with patch.object(EmployeeSkill, "save", new=save_then_fail):
            response = self.client.post(self.create_url, self.valid_create_data())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(EmployeeSkill.objects.count(), proficiency_count)
        self.assertFalse(
            EmployeeSkill.objects.filter(
                employee=self.employee,
                skill=self.django,
            ).exists()
        )
        self.assertContains(
            response,
            "We could not save this proficiency. No changes were applied. "
            "Please try again.",
        )

    def test_failed_update_rolls_back_and_shows_safe_feedback(self):
        original_save = EmployeeSkill.save

        def save_then_fail(instance, *args, **kwargs):
            original_save(instance, *args, **kwargs)
            raise DatabaseError("Simulated proficiency update failure")

        with patch.object(EmployeeSkill, "save", new=save_then_fail):
            response = self.client.post(self.update_url, self.valid_update_data())

        self.assertEqual(response.status_code, 200)
        self.employee_skill.refresh_from_db()
        self.assertEqual(self.employee_skill.level, 4)
        self.assertEqual(self.employee_skill.years_experience, Decimal("6.5"))
        self.assertContains(
            response,
            "We could not save this proficiency. No changes were applied. "
            "Please try again.",
        )

    def test_failed_removal_rolls_back_and_shows_safe_feedback(self):
        original_delete = EmployeeSkill.delete

        def delete_then_fail(instance, *args, **kwargs):
            original_delete(instance, *args, **kwargs)
            raise DatabaseError("Simulated proficiency removal failure")

        with patch.object(EmployeeSkill, "delete", new=delete_then_fail):
            response = self.client.post(self.remove_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            EmployeeSkill.objects.filter(
                employee=self.employee,
                skill=self.python,
            ).exists()
        )
        self.assertContains(
            response,
            "We could not remove this proficiency. No changes were applied. "
            "Please try again.",
        )
