import re
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import DatabaseError
from django.test import Client, TestCase
from django.urls import resolve, reverse

from core.models import Employee
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)


class EmployeeCreateUpdateTests(TestCase):
    EMPLOYEE_FORM_CSRF_PATTERN = re.compile(
        r'<form method="post" novalidate data-loading-form>\s*'
        r'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)">'
    )

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()

        cls.hr_admin = get_user_model().objects.create_user(username="employee-hr")
        cls.hr_admin.groups.add(Group.objects.get(name=HR_ADMINISTRATOR_GROUP))
        cls.viewer = get_user_model().objects.create_user(username="employee-viewer")
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))

        cls.add_only_user = get_user_model().objects.create_user(
            username="employee-add-only"
        )
        cls.add_only_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename="add_employee",
            )
        )
        cls.change_only_user = get_user_model().objects.create_user(
            username="employee-change-only"
        )
        cls.change_only_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename="change_employee",
            )
        )

        cls.employee = Employee.objects.create(
            first_name="Jamie",
            last_name="Rivera",
            department="Engineering",
            position="Platform Engineer",
            hire_date=date(2019, 4, 15),
            experience_years=Decimal("7.5"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )

    def setUp(self):
        self.create_url = reverse("frontend:employee_create")
        self.update_url = reverse(
            "frontend:employee_update",
            args=[self.employee.employee_id],
        )
        self.client.force_login(self.hr_admin)

    @staticmethod
    def valid_create_data():
        return {
            "first_name": "Avery",
            "last_name": "Chen",
            "department": "Product",
            "position": "Product Manager",
            "hire_date": "2024-02-12",
            "experience_years": "6.5",
            "capacity_hours_week": "37.50",
            "status": Employee.Status.ACTIVE,
        }

    def valid_update_data(self):
        return {
            "first_name": "Jamie",
            "last_name": "Rivera",
            "department": "Platform Engineering",
            "position": "Senior Platform Engineer",
            "hire_date": "2019-04-15",
            "experience_years": "8.0",
            "capacity_hours_week": "36.00",
            "status": Employee.Status.ON_LEAVE,
        }

    def employee_form_csrf_token(self, response):
        match = self.EMPLOYEE_FORM_CSRF_PATTERN.search(
            response.content.decode("utf-8")
        )
        self.assertIsNotNone(
            match,
            "The employee POST form must render its own CSRF input.",
        )
        return match.group(1)

    def test_create_and_update_routes_are_namespaced_and_render_forms(self):
        create_match = resolve(self.create_url)
        update_match = resolve(self.update_url)
        self.assertEqual(self.create_url, "/employees/new/")
        self.assertEqual(create_match.view_name, "frontend:employee_create")
        self.assertEqual(
            self.update_url,
            f"/employees/{self.employee.employee_id}/edit/",
        )
        self.assertEqual(update_match.view_name, "frontend:employee_update")
        self.assertEqual(
            update_match.kwargs["employee_id"],
            self.employee.employee_id,
        )

        create_response = self.client.get(self.create_url)
        self.assertEqual(create_response.status_code, 200)
        self.assertTemplateUsed(create_response, "frontend/employees/create.html")
        self.assertTemplateUsed(
            create_response,
            "frontend/employees/_employee_form.html",
        )
        self.assertContains(create_response, "<h1>Add employee</h1>", html=True)
        self.assertContains(create_response, "Weekly capacity (hours)")
        self.assertContains(create_response, 'type="date"')
        self.assertContains(create_response, "Monday-to-Friday")
        self.assertRegex(
            create_response.content.decode("utf-8"),
            r'href="/employees/"\s+aria-current="page"',
        )

        update_response = self.client.get(self.update_url)
        self.assertEqual(update_response.status_code, 200)
        self.assertTemplateUsed(update_response, "frontend/employees/edit.html")
        self.assertContains(update_response, "<h1>Edit employee</h1>", html=True)
        self.assertContains(update_response, "Jamie Rivera")
        self.assertContains(update_response, "Platform Engineer")
        self.assertContains(update_response, "Save changes")
        self.assertRegex(
            update_response.content.decode("utf-8"),
            r'href="/employees/"\s+aria-current="page"',
        )

    def test_authorized_actions_are_connected_from_directory_and_detail(self):
        directory_response = self.client.get(reverse("frontend:employee_list"))
        detail_response = self.client.get(
            reverse(
                "frontend:employee_detail",
                args=[self.employee.employee_id],
            )
        )

        self.assertContains(directory_response, self.create_url)
        self.assertContains(directory_response, "Add employee")
        self.assertContains(detail_response, self.update_url)
        self.assertContains(detail_response, "Edit employee")

        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        self.assertNotContains(
            viewer_client.get(reverse("frontend:employee_list")),
            "Add employee",
        )
        self.assertNotContains(
            viewer_client.get(
                reverse(
                    "frontend:employee_detail",
                    args=[self.employee.employee_id],
                )
            ),
            "Edit employee",
        )

    def test_valid_create_saves_and_redirects_to_the_employee_profile(self):
        response = self.client.post(
            self.create_url,
            self.valid_create_data(),
            follow=True,
        )

        employee = Employee.objects.get(first_name="Avery", last_name="Chen")
        self.assertRedirects(
            response,
            reverse("frontend:employee_detail", args=[employee.employee_id]),
        )
        self.assertEqual(employee.department, "Product")
        self.assertEqual(employee.position, "Product Manager")
        self.assertEqual(employee.experience_years, Decimal("6.5"))
        self.assertEqual(employee.capacity_hours_week, Decimal("37.50"))
        self.assertEqual(employee.status, Employee.Status.ACTIVE)
        self.assertContains(response, "Avery Chen was added to the workforce.")
        self.assertContains(response, "<h1>Avery Chen</h1>", html=True)

    def test_invalid_create_surfaces_field_errors_without_saving(self):
        invalid_data = self.valid_create_data()
        invalid_data.update(
            {
                "first_name": "",
                "hire_date": "not-a-date",
                "experience_years": "-1.0",
                "capacity_hours_week": "-0.01",
                "status": "not-a-status",
            }
        )
        employee_count = Employee.objects.count()

        response = self.client.post(self.create_url, invalid_data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Employee.objects.count(), employee_count)
        for field_name in (
            "first_name",
            "hire_date",
            "experience_years",
            "capacity_hours_week",
            "status",
        ):
            with self.subTest(field=field_name):
                self.assertIn(field_name, response.context["form"].errors)
                self.assertContains(response, f'id="id_{field_name}_error"')
        self.assertContains(
            response,
            "Please correct the highlighted fields before saving the employee.",
        )
        self.assertContains(response, 'aria-invalid="true"')

    def test_valid_update_saves_and_redirects_to_the_employee_profile(self):
        response = self.client.post(
            self.update_url,
            self.valid_update_data(),
            follow=True,
        )

        self.employee.refresh_from_db()
        self.assertRedirects(
            response,
            reverse(
                "frontend:employee_detail",
                args=[self.employee.employee_id],
            ),
        )
        self.assertEqual(self.employee.department, "Platform Engineering")
        self.assertEqual(self.employee.position, "Senior Platform Engineer")
        self.assertEqual(self.employee.experience_years, Decimal("8.0"))
        self.assertEqual(self.employee.capacity_hours_week, Decimal("36.00"))
        self.assertEqual(self.employee.status, Employee.Status.ON_LEAVE)
        self.assertContains(
            response,
            "Employee profile for Jamie Rivera was updated.",
        )

    def test_invalid_update_keeps_the_stored_employee_unchanged(self):
        invalid_data = self.valid_update_data()
        invalid_data.update(
            {
                "first_name": "Changed in invalid submission",
                "capacity_hours_week": "-2.00",
            }
        )

        response = self.client.post(self.update_url, invalid_data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("capacity_hours_week", response.context["form"].errors)
        self.assertContains(response, 'id="id_capacity_hours_week_error"')
        self.assertContains(
            response,
            "Please correct the highlighted fields before saving changes.",
        )
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.first_name, "Jamie")
        self.assertEqual(self.employee.department, "Engineering")
        self.assertEqual(self.employee.capacity_hours_week, Decimal("40.00"))

    def test_anonymous_and_viewer_users_cannot_access_write_views(self):
        anonymous_client = Client()
        for url in (self.create_url, self.update_url):
            with self.subTest(access="anonymous", url=url):
                response = anonymous_client.get(url)
                self.assertRedirects(
                    response,
                    f"{reverse('frontend:login')}?next={url}",
                    fetch_redirect_response=False,
                )

        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        employee_count = Employee.objects.count()
        self.assertEqual(viewer_client.get(self.create_url).status_code, 403)
        self.assertEqual(viewer_client.get(self.update_url).status_code, 403)
        self.assertEqual(
            viewer_client.post(self.create_url, self.valid_create_data()).status_code,
            403,
        )
        self.assertEqual(
            viewer_client.post(self.update_url, self.valid_update_data()).status_code,
            403,
        )
        self.assertEqual(Employee.objects.count(), employee_count)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.department, "Engineering")

    def test_add_and_change_permissions_are_enforced_independently(self):
        add_client = Client()
        add_client.force_login(self.add_only_user)
        self.assertEqual(add_client.get(self.create_url).status_code, 200)
        self.assertEqual(add_client.get(self.update_url).status_code, 403)

        change_client = Client()
        change_client.force_login(self.change_only_user)
        self.assertEqual(change_client.get(self.create_url).status_code, 403)
        self.assertEqual(change_client.get(self.update_url).status_code, 200)

    def test_csrf_enforcement_rejects_create_and_update_without_a_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr_admin)

        create_response = csrf_client.post(
            self.create_url,
            self.valid_create_data(),
        )
        update_response = csrf_client.post(
            self.update_url,
            self.valid_update_data(),
        )

        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(update_response.status_code, 403)
        self.assertFalse(Employee.objects.filter(first_name="Avery").exists())
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.department, "Engineering")

    def test_csrf_enforced_client_can_create_and_update_from_rendered_forms(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr_admin)

        create_form_response = csrf_client.get(self.create_url)
        create_data = self.valid_create_data()
        create_data["csrfmiddlewaretoken"] = self.employee_form_csrf_token(
            create_form_response
        )
        create_response = csrf_client.post(self.create_url, create_data)

        created_employee = Employee.objects.get(
            first_name="Avery",
            last_name="Chen",
        )
        self.assertRedirects(
            create_response,
            reverse(
                "frontend:employee_detail",
                args=[created_employee.employee_id],
            ),
            fetch_redirect_response=False,
        )

        update_url = reverse(
            "frontend:employee_update",
            args=[created_employee.employee_id],
        )
        update_form_response = csrf_client.get(update_url)
        update_data = self.valid_create_data()
        update_data.update(
            {
                "position": "Senior Product Manager",
                "capacity_hours_week": "35.00",
                "csrfmiddlewaretoken": self.employee_form_csrf_token(
                    update_form_response
                ),
            }
        )
        update_response = csrf_client.post(update_url, update_data)

        self.assertRedirects(
            update_response,
            reverse(
                "frontend:employee_detail",
                args=[created_employee.employee_id],
            ),
            fetch_redirect_response=False,
        )
        created_employee.refresh_from_db()
        self.assertEqual(created_employee.position, "Senior Product Manager")
        self.assertEqual(created_employee.capacity_hours_week, Decimal("35.00"))

    def test_failed_create_rolls_back_the_insert_and_shows_safe_feedback(self):
        employee_count = Employee.objects.count()
        original_save = Employee.save

        def save_then_fail(instance, *args, **kwargs):
            original_save(instance, *args, **kwargs)
            raise DatabaseError("Simulated employee insert failure")

        with patch.object(Employee, "save", new=save_then_fail):
            response = self.client.post(self.create_url, self.valid_create_data())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Employee.objects.count(), employee_count)
        self.assertFalse(Employee.objects.filter(first_name="Avery").exists())
        self.assertContains(
            response,
            "We could not save this employee. No changes were applied. "
            "Please try again.",
        )

    def test_failed_update_rolls_back_changes_and_shows_safe_feedback(self):
        original_save = Employee.save

        def save_then_fail(instance, *args, **kwargs):
            original_save(instance, *args, **kwargs)
            raise DatabaseError("Simulated employee update failure")

        with patch.object(Employee, "save", new=save_then_fail):
            response = self.client.post(self.update_url, self.valid_update_data())

        self.assertEqual(response.status_code, 200)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.department, "Engineering")
        self.assertEqual(self.employee.position, "Platform Engineer")
        self.assertEqual(self.employee.capacity_hours_week, Decimal("40.00"))
        self.assertContains(
            response,
            "We could not save this employee. No changes were applied. "
            "Please try again.",
        )
