import re
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import DatabaseError
from django.test import Client, TestCase
from django.urls import resolve, reverse

from core.models import Project
from frontend.roles import (
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)


class ProjectCreateUpdateTests(TestCase):
    PROJECT_FORM_CSRF_PATTERN = re.compile(
        r'<form method="post" novalidate data-loading-form>\s*'
        r'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)">'
    )

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.manager = get_user_model().objects.create_user(
            username="project-maintainer"
        )
        cls.manager.groups.add(Group.objects.get(name=MANAGER_PLANNER_GROUP))
        cls.viewer = get_user_model().objects.create_user(
            username="project-readonly"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))

        cls.add_only_user = get_user_model().objects.create_user(
            username="project-add-only"
        )
        cls.add_only_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename="add_project",
            )
        )
        cls.change_only_user = get_user_model().objects.create_user(
            username="project-change-only"
        )
        cls.change_only_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename="change_project",
            )
        )

        cls.project = Project.objects.create(
            name="Atlas Renewal",
            description="Modernize the workforce planning platform.",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 31),
            estimated_hours=Decimal("240.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.MEDIUM,
        )

    def setUp(self):
        self.create_url = reverse("frontend:project_create")
        self.update_url = reverse(
            "frontend:project_update",
            args=[self.project.project_id],
        )
        self.client.force_login(self.manager)

    @staticmethod
    def valid_create_data():
        return {
            "name": "Beacon Launch",
            "description": "Launch the next planning workspace.",
            "start_date": "2027-01-10",
            "end_date": "2027-05-28",
            "estimated_hours": "480.00",
            "status": Project.Status.PLANNED,
            "priority": Project.Priority.MEDIUM,
            "criticality": Project.Criticality.HIGH,
        }

    def valid_update_data(self):
        return {
            "name": "Atlas Renewal",
            "description": "Modernize planning and delivery workflows.",
            "start_date": "2026-09-15",
            "end_date": "2027-01-31",
            "estimated_hours": "360.50",
            "status": Project.Status.IN_PROGRESS,
            "priority": Project.Priority.HIGH,
            "criticality": Project.Criticality.HIGH,
        }

    def project_form_csrf_token(self, response):
        match = self.PROJECT_FORM_CSRF_PATTERN.search(
            response.content.decode("utf-8")
        )
        self.assertIsNotNone(
            match,
            "The project POST form must render its own CSRF input.",
        )
        return match.group(1)

    def test_create_and_update_routes_are_namespaced_and_render_forms(self):
        self.assertEqual(self.create_url, "/projects/new/")
        self.assertEqual(
            resolve(self.create_url).view_name,
            "frontend:project_create",
        )
        self.assertEqual(
            self.update_url,
            f"/projects/{self.project.project_id}/edit/",
        )
        update_match = resolve(self.update_url)
        self.assertEqual(update_match.view_name, "frontend:project_update")
        self.assertEqual(update_match.kwargs["project_id"], self.project.project_id)

        create_response = self.client.get(self.create_url)
        self.assertEqual(create_response.status_code, 200)
        self.assertTemplateUsed(create_response, "frontend/projects/create.html")
        self.assertTemplateUsed(
            create_response,
            "frontend/projects/_project_form.html",
        )
        self.assertContains(create_response, "<h1>Add project</h1>", html=True)
        self.assertContains(create_response, "Project definition")
        self.assertContains(create_response, "Schedule and planning")
        self.assertContains(create_response, "Project estimate (hours)")
        self.assertContains(create_response, 'type="date"', count=2)
        self.project_form_csrf_token(create_response)

        update_response = self.client.get(self.update_url)
        self.assertEqual(update_response.status_code, 200)
        self.assertTemplateUsed(update_response, "frontend/projects/edit.html")
        self.assertContains(update_response, "<h1>Edit project</h1>", html=True)
        self.assertContains(update_response, "Atlas Renewal")
        self.assertContains(update_response, "Save changes")
        self.project_form_csrf_token(update_response)

        for response in (create_response, update_response):
            self.assertRegex(
                response.content.decode("utf-8"),
                r'href="/projects/"\s+aria-current="page"',
            )

    def test_actions_are_connected_for_writers_and_hidden_from_viewers(self):
        list_url = reverse("frontend:project_list")
        detail_url = reverse(
            "frontend:project_detail",
            args=[self.project.project_id],
        )
        self.assertContains(self.client.get(list_url), self.create_url)
        self.assertContains(self.client.get(list_url), "Add project")
        self.assertContains(self.client.get(detail_url), self.update_url)
        self.assertContains(self.client.get(detail_url), "Edit project")

        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        self.assertNotContains(viewer_client.get(list_url), "Add project")
        self.assertNotContains(viewer_client.get(detail_url), "Edit project")

    def test_valid_create_saves_and_redirects_to_project_detail(self):
        response = self.client.post(
            self.create_url,
            self.valid_create_data(),
            follow=True,
        )

        project = Project.objects.get(name="Beacon Launch")
        self.assertRedirects(
            response,
            reverse("frontend:project_detail", args=[project.project_id]),
        )
        self.assertEqual(project.description, "Launch the next planning workspace.")
        self.assertEqual(project.start_date, date(2027, 1, 10))
        self.assertEqual(project.end_date, date(2027, 5, 28))
        self.assertEqual(project.estimated_hours, Decimal("480.00"))
        self.assertEqual(project.status, Project.Status.PLANNED)
        self.assertEqual(project.priority, Project.Priority.MEDIUM)
        self.assertEqual(project.criticality, Project.Criticality.HIGH)
        self.assertContains(
            response,
            "Beacon Launch was added to the project directory.",
        )
        self.assertContains(response, "<h1>Beacon Launch</h1>", html=True)

    def test_invalid_create_surfaces_field_and_model_errors_without_saving(self):
        project_count = Project.objects.count()
        response = self.client.post(
            self.create_url,
            {
                "name": "",
                "description": "",
                "start_date": "2027-06-01",
                "end_date": "2027-05-01",
                "estimated_hours": "-1.00",
                "status": "not-a-status",
                "priority": "not-a-priority",
                "criticality": "not-a-criticality",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Project.objects.count(), project_count)
        for field_name in (
            "name",
            "description",
            "end_date",
            "estimated_hours",
            "status",
            "priority",
            "criticality",
        ):
            with self.subTest(field=field_name):
                self.assertIn(field_name, response.context["form"].errors)
                self.assertContains(response, f'id="id_{field_name}_error"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(
            response,
            "Please correct the highlighted fields before saving the project.",
        )

    def test_valid_update_saves_and_redirects_to_project_detail(self):
        response = self.client.post(
            self.update_url,
            self.valid_update_data(),
            follow=True,
        )

        self.project.refresh_from_db()
        self.assertRedirects(
            response,
            reverse(
                "frontend:project_detail",
                args=[self.project.project_id],
            ),
        )
        self.assertEqual(
            self.project.description,
            "Modernize planning and delivery workflows.",
        )
        self.assertEqual(self.project.start_date, date(2026, 9, 15))
        self.assertEqual(self.project.end_date, date(2027, 1, 31))
        self.assertEqual(self.project.estimated_hours, Decimal("360.50"))
        self.assertEqual(self.project.status, Project.Status.IN_PROGRESS)
        self.assertEqual(self.project.criticality, Project.Criticality.HIGH)
        self.assertContains(response, "Project Atlas Renewal was updated.")

    def test_invalid_update_keeps_the_stored_project_unchanged(self):
        invalid_data = self.valid_update_data()
        invalid_data.update(
            {
                "description": "Attempted invalid change.",
                "start_date": "2027-03-01",
                "end_date": "2027-02-01",
                "estimated_hours": "-10.00",
            }
        )

        response = self.client.post(self.update_url, invalid_data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("end_date", response.context["form"].errors)
        self.assertIn("estimated_hours", response.context["form"].errors)
        self.assertContains(response, 'id="id_end_date_error"')
        self.assertContains(response, 'id="id_estimated_hours_error"')
        self.assertContains(
            response,
            "Please correct the highlighted fields before saving changes.",
        )
        self.project.refresh_from_db()
        self.assertEqual(
            self.project.description,
            "Modernize the workforce planning platform.",
        )
        self.assertEqual(self.project.start_date, date(2026, 9, 1))
        self.assertEqual(self.project.end_date, date(2026, 12, 31))
        self.assertEqual(self.project.estimated_hours, Decimal("240.00"))

    def test_missing_update_target_returns_not_found(self):
        missing_url = reverse("frontend:project_update", args=[999999])
        self.assertEqual(self.client.get(missing_url).status_code, 404)

    def test_anonymous_and_viewer_users_cannot_access_write_views(self):
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
        project_count = Project.objects.count()
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
        self.assertEqual(Project.objects.count(), project_count)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.PLANNED)

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
        csrf_client.force_login(self.manager)

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
        self.assertFalse(Project.objects.filter(name="Beacon Launch").exists())
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.PLANNED)

    def test_rendered_csrf_tokens_allow_create_and_update(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.manager)

        create_form_response = csrf_client.get(self.create_url)
        create_data = self.valid_create_data()
        create_data["csrfmiddlewaretoken"] = self.project_form_csrf_token(
            create_form_response
        )
        create_response = csrf_client.post(self.create_url, create_data)
        created_project = Project.objects.get(name="Beacon Launch")
        self.assertRedirects(
            create_response,
            reverse(
                "frontend:project_detail",
                args=[created_project.project_id],
            ),
            fetch_redirect_response=False,
        )

        update_url = reverse(
            "frontend:project_update",
            args=[created_project.project_id],
        )
        update_form_response = csrf_client.get(update_url)
        update_data = self.valid_create_data()
        update_data.update(
            {
                "name": "Beacon Delivery",
                "status": Project.Status.IN_PROGRESS,
                "csrfmiddlewaretoken": self.project_form_csrf_token(
                    update_form_response
                ),
            }
        )
        update_response = csrf_client.post(update_url, update_data)
        self.assertRedirects(
            update_response,
            reverse(
                "frontend:project_detail",
                args=[created_project.project_id],
            ),
            fetch_redirect_response=False,
        )
        created_project.refresh_from_db()
        self.assertEqual(created_project.name, "Beacon Delivery")
        self.assertEqual(created_project.status, Project.Status.IN_PROGRESS)

    def test_failed_create_rolls_back_and_shows_safe_feedback(self):
        project_count = Project.objects.count()
        original_save = Project.save

        def save_then_fail(instance, *args, **kwargs):
            original_save(instance, *args, **kwargs)
            raise DatabaseError("Simulated project insert failure")

        with patch.object(Project, "save", new=save_then_fail):
            response = self.client.post(self.create_url, self.valid_create_data())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Project.objects.count(), project_count)
        self.assertFalse(Project.objects.filter(name="Beacon Launch").exists())
        self.assertContains(
            response,
            "We could not save this project. No changes were applied. "
            "Please try again.",
        )

    def test_failed_update_rolls_back_and_shows_safe_feedback(self):
        original_save = Project.save

        def save_then_fail(instance, *args, **kwargs):
            original_save(instance, *args, **kwargs)
            raise DatabaseError("Simulated project update failure")

        with patch.object(Project, "save", new=save_then_fail):
            response = self.client.post(self.update_url, self.valid_update_data())

        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(
            self.project.description,
            "Modernize the workforce planning platform.",
        )
        self.assertEqual(self.project.start_date, date(2026, 9, 1))
        self.assertEqual(self.project.estimated_hours, Decimal("240.00"))
        self.assertEqual(self.project.status, Project.Status.PLANNED)
        self.assertContains(
            response,
            "We could not save this project. No changes were applied. "
            "Please try again.",
        )
