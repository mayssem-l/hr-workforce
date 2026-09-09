import re
import statistics
import time
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import DatabaseError, connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from core.models import Employee, EmployeeSkill, Skill
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)
from frontend.selectors.skills import SKILL_PAGE_SIZE


class SkillDirectoryTests(TestCase):
    EXPECTED_DIRECTORY_QUERY_COUNT = 7
    EXPECTED_DETAIL_QUERY_COUNT = 5
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(username="skill-viewer")
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.unassigned = get_user_model().objects.create_user(
            username="skill-unassigned"
        )

        cls.python = Skill.objects.create(name="Python", category="Engineering")
        cls.django = Skill.objects.create(name="Django", category="Engineering")
        cls.sql = Skill.objects.create(name="SQL", category="Data")
        cls.leadership = Skill.objects.create(
            name="Leadership",
            category="Management",
        )
        for index in range(25):
            Skill.objects.create(
                name=f"Specialty {index:02d}",
                category="Specialty",
            )

        employee = Employee.objects.create(
            first_name="Avery",
            last_name="Chen",
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

    def setUp(self):
        self.list_url = reverse("frontend:skill_list")
        self.detail_url = reverse(
            "frontend:skill_detail",
            args=[self.python.skill_id],
        )
        self.client.force_login(self.viewer)

    def test_read_routes_are_namespaced_and_resolve(self):
        self.assertEqual(self.list_url, "/skills/")
        list_match = resolve(self.list_url)
        self.assertEqual(list_match.view_name, "frontend:skill_list")
        self.assertEqual(list_match.namespace, "frontend")

        self.assertEqual(self.detail_url, f"/skills/{self.python.skill_id}/")
        detail_match = resolve(self.detail_url)
        self.assertEqual(detail_match.view_name, "frontend:skill_detail")
        self.assertEqual(detail_match.kwargs["skill_id"], self.python.skill_id)

    def test_read_permission_handles_anonymous_unassigned_and_viewer_users(self):
        for url in (self.list_url, self.detail_url):
            with self.subTest(access="anonymous", url=url):
                anonymous_response = Client().get(url)
                self.assertRedirects(
                    anonymous_response,
                    f"{reverse('frontend:login')}?next={url}",
                    fetch_redirect_response=False,
                )

            unassigned_client = Client()
            unassigned_client.force_login(self.unassigned)
            self.assertEqual(unassigned_client.get(url).status_code, 403)
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_directory_renders_grouped_skills_and_workforce_navigation(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/skills/list.html")
        self.assertTemplateUsed(response, "frontend/skills/_skill_row.html")
        self.assertContains(response, "<h1>Skill directory</h1>", html=True)
        self.assertContains(response, "Capability category")
        self.assertContains(response, "Engineering skills")
        self.assertContains(response, "Python")
        self.assertContains(response, "1 employee profile")
        self.assertContains(response, self.detail_url)
        self.assertContains(response, reverse("frontend:employee_list"))
        self.assertRegex(
            response.content.decode("utf-8"),
            r'href="/skills/"\s+aria-current="page"',
        )
        self.assertRegex(
            response.content.decode("utf-8"),
            r'href="/employees/"\s+aria-current="page"',
        )
        self.assertNotContains(response, "Add skill")

        employee_directory = self.client.get(reverse("frontend:employee_list"))
        self.assertContains(employee_directory, self.list_url)
        self.assertContains(employee_directory, "Skills")

    def test_category_filter_limits_results_and_grouping(self):
        response = self.client.get(self.list_url, {"category": "Engineering"})

        self.assertEqual(response.context["page_obj"].paginator.count, 2)
        self.assertContains(response, "Django")
        self.assertContains(response, "Python")
        self.assertNotContains(response, "SQL")
        self.assertEqual(len(response.context["skill_groups"]), 1)
        self.assertEqual(
            response.context["skill_groups"][0]["category"],
            "Engineering",
        )

    def test_pagination_is_deterministic_and_preserves_the_category_filter(self):
        response = self.client.get(self.list_url, {"page": 2})

        page_obj = response.context["page_obj"]
        self.assertEqual(page_obj.paginator.per_page, SKILL_PAGE_SIZE)
        self.assertEqual(page_obj.paginator.count, 29)
        self.assertEqual(page_obj.number, 2)
        self.assertEqual(len(page_obj.object_list), 5)
        self.assertContains(response, "Page 2 of 2")

        filtered_response = self.client.get(
            self.list_url,
            {"category": "Specialty", "page": 2},
        )
        self.assertEqual(filtered_response.context["page_obj"].number, 2)
        self.assertEqual(len(filtered_response.context["page_obj"].object_list), 1)
        self.assertContains(
            filtered_response,
            "category=Specialty&amp;page=1",
        )

    def test_filtered_and_unpopulated_directories_have_clear_empty_states(self):
        filtered_response = self.client.get(
            self.list_url,
            {"category": "No such category"},
        )
        self.assertContains(filtered_response, "No skills match this category")
        self.assertContains(filtered_response, "Clear filter")
        self.assertNotContains(filtered_response, "Capability category")

        Skill.objects.all().delete()
        empty_response = self.client.get(self.list_url)
        self.assertContains(empty_response, "No skills yet")
        self.assertNotContains(empty_response, "Add the first skill")

    def test_detail_renders_core_fields_usage_and_empty_state(self):
        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/skills/detail.html")
        self.assertContains(response, "<h1>Python</h1>", html=True)
        self.assertContains(response, "Engineering")
        self.assertContains(response, "Employee profiles")
        self.assertContains(response, "1")
        self.assertNotContains(response, "Edit skill")

        unused_url = reverse(
            "frontend:skill_detail",
            args=[self.sql.skill_id],
        )
        unused_response = self.client.get(unused_url)
        self.assertContains(unused_response, "No employee profiles use this skill yet")

    def test_missing_detail_returns_not_found(self):
        missing_url = reverse("frontend:skill_detail", args=[999999])
        self.assertEqual(self.client.get(missing_url).status_code, 404)

    def test_directory_query_count_and_warm_response_time_are_recorded(self):
        with self.assertNumQueries(self.EXPECTED_DIRECTORY_QUERY_COUNT):
            response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)

        durations_ms = []
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as captured_queries:
                started_at = time.perf_counter()
                response = self.client.get(self.list_url)
                durations_ms.append((time.perf_counter() - started_at) * 1000)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                len(captured_queries),
                self.EXPECTED_DIRECTORY_QUERY_COUNT,
            )

        p95_ms = statistics.quantiles(durations_ms, n=20, method="inclusive")[18]
        print(
            "\nM2.4 skill-directory baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            f"{Skill.objects.count()} skills):\n"
            f"  queries={self.EXPECTED_DIRECTORY_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )

    def test_detail_query_count_and_warm_response_time_are_recorded(self):
        with self.assertNumQueries(self.EXPECTED_DETAIL_QUERY_COUNT):
            response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)

        durations_ms = []
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as captured_queries:
                started_at = time.perf_counter()
                response = self.client.get(self.detail_url)
                durations_ms.append((time.perf_counter() - started_at) * 1000)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(captured_queries), self.EXPECTED_DETAIL_QUERY_COUNT)

        p95_ms = statistics.quantiles(durations_ms, n=20, method="inclusive")[18]
        print(
            "\nM2.4 skill-detail baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs):\n"
            f"  queries={self.EXPECTED_DETAIL_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )


class SkillMaintenanceTests(TestCase):
    SKILL_FORM_CSRF_PATTERN = re.compile(
        r'<form method="post" novalidate data-loading-form>\s*'
        r'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)">'
    )

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.hr_admin = get_user_model().objects.create_user(username="skill-hr")
        cls.hr_admin.groups.add(Group.objects.get(name=HR_ADMINISTRATOR_GROUP))
        cls.viewer = get_user_model().objects.create_user(username="skill-readonly")
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))

        cls.add_only_user = get_user_model().objects.create_user(
            username="skill-add-only"
        )
        cls.add_only_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename="add_skill",
            )
        )
        cls.change_only_user = get_user_model().objects.create_user(
            username="skill-change-only"
        )
        cls.change_only_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename="change_skill",
            )
        )

        cls.skill = Skill.objects.create(name="Python", category="Engineering")

    def setUp(self):
        self.create_url = reverse("frontend:skill_create")
        self.update_url = reverse(
            "frontend:skill_update",
            args=[self.skill.skill_id],
        )
        self.client.force_login(self.hr_admin)

    @staticmethod
    def valid_create_data():
        return {"name": "Data Analysis", "category": "Data"}

    @staticmethod
    def valid_update_data():
        return {"name": "Python Engineering", "category": "Engineering"}

    def skill_form_csrf_token(self, response):
        match = self.SKILL_FORM_CSRF_PATTERN.search(
            response.content.decode("utf-8")
        )
        self.assertIsNotNone(
            match,
            "The skill POST form must render its own CSRF input.",
        )
        return match.group(1)

    def test_write_routes_are_namespaced_and_render_forms(self):
        self.assertEqual(self.create_url, "/skills/new/")
        self.assertEqual(resolve(self.create_url).view_name, "frontend:skill_create")
        self.assertEqual(
            self.update_url,
            f"/skills/{self.skill.skill_id}/edit/",
        )
        self.assertEqual(resolve(self.update_url).view_name, "frontend:skill_update")

        create_response = self.client.get(self.create_url)
        self.assertEqual(create_response.status_code, 200)
        self.assertTemplateUsed(create_response, "frontend/skills/create.html")
        self.assertTemplateUsed(create_response, "frontend/skills/_skill_form.html")
        self.assertContains(create_response, "<h1>Add skill</h1>", html=True)
        self.assertContains(create_response, "Capability definition")
        self.assertContains(create_response, 'for="id_name"')
        self.assertContains(create_response, 'for="id_category"')
        self.skill_form_csrf_token(create_response)

        update_response = self.client.get(self.update_url)
        self.assertEqual(update_response.status_code, 200)
        self.assertTemplateUsed(update_response, "frontend/skills/edit.html")
        self.assertContains(update_response, "<h1>Edit skill</h1>", html=True)
        self.assertContains(update_response, "Python")
        self.assertContains(update_response, "Save changes")
        self.skill_form_csrf_token(update_response)

    def test_authorized_actions_are_connected_and_hidden_from_viewers(self):
        list_url = reverse("frontend:skill_list")
        detail_url = reverse(
            "frontend:skill_detail",
            args=[self.skill.skill_id],
        )
        list_response = self.client.get(list_url)
        detail_response = self.client.get(detail_url)
        self.assertContains(list_response, self.create_url)
        self.assertContains(list_response, "Add skill")
        self.assertContains(detail_response, self.update_url)
        self.assertContains(detail_response, "Edit skill")

        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        self.assertNotContains(viewer_client.get(list_url), "Add skill")
        self.assertNotContains(viewer_client.get(detail_url), "Edit skill")

    def test_valid_create_saves_and_redirects_to_skill_detail(self):
        response = self.client.post(
            self.create_url,
            self.valid_create_data(),
            follow=True,
        )

        skill = Skill.objects.get(name="Data Analysis")
        self.assertRedirects(
            response,
            reverse("frontend:skill_detail", args=[skill.skill_id]),
        )
        self.assertEqual(skill.category, "Data")
        self.assertContains(response, "Data Analysis was added to the skill directory.")
        self.assertContains(response, "<h1>Data Analysis</h1>", html=True)

    def test_invalid_create_surfaces_field_errors_without_saving(self):
        skill_count = Skill.objects.count()
        response = self.client.post(
            self.create_url,
            {"name": "", "category": "x" * 101},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Skill.objects.count(), skill_count)
        self.assertIn("name", response.context["form"].errors)
        self.assertIn("category", response.context["form"].errors)
        self.assertContains(response, 'id="id_name_error"')
        self.assertContains(response, 'id="id_category_error"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(
            response,
            "Please correct the highlighted fields before saving the skill.",
        )

    def test_valid_update_saves_and_redirects_to_skill_detail(self):
        response = self.client.post(
            self.update_url,
            self.valid_update_data(),
            follow=True,
        )

        self.skill.refresh_from_db()
        self.assertRedirects(
            response,
            reverse("frontend:skill_detail", args=[self.skill.skill_id]),
        )
        self.assertEqual(self.skill.name, "Python Engineering")
        self.assertEqual(self.skill.category, "Engineering")
        self.assertContains(response, "Skill Python Engineering was updated.")

    def test_invalid_update_keeps_stored_skill_unchanged(self):
        response = self.client.post(
            self.update_url,
            {"name": "Attempted name", "category": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("category", response.context["form"].errors)
        self.assertContains(response, 'id="id_category_error"')
        self.assertContains(response, "Please correct the highlighted fields")
        self.skill.refresh_from_db()
        self.assertEqual(self.skill.name, "Python")
        self.assertEqual(self.skill.category, "Engineering")

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
        skill_count = Skill.objects.count()
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
        self.assertEqual(Skill.objects.count(), skill_count)
        self.skill.refresh_from_db()
        self.assertEqual(self.skill.name, "Python")

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
        self.assertFalse(Skill.objects.filter(name="Data Analysis").exists())
        self.skill.refresh_from_db()
        self.assertEqual(self.skill.name, "Python")

    def test_csrf_enforced_client_can_create_and_update_from_rendered_forms(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr_admin)

        create_form_response = csrf_client.get(self.create_url)
        create_data = self.valid_create_data()
        create_data["csrfmiddlewaretoken"] = self.skill_form_csrf_token(
            create_form_response
        )
        create_response = csrf_client.post(self.create_url, create_data)
        created_skill = Skill.objects.get(name="Data Analysis")
        self.assertRedirects(
            create_response,
            reverse("frontend:skill_detail", args=[created_skill.skill_id]),
            fetch_redirect_response=False,
        )

        update_url = reverse(
            "frontend:skill_update",
            args=[created_skill.skill_id],
        )
        update_form_response = csrf_client.get(update_url)
        update_data = {
            "name": "Analytics",
            "category": "Data and insight",
            "csrfmiddlewaretoken": self.skill_form_csrf_token(
                update_form_response
            ),
        }
        update_response = csrf_client.post(update_url, update_data)
        self.assertRedirects(
            update_response,
            reverse("frontend:skill_detail", args=[created_skill.skill_id]),
            fetch_redirect_response=False,
        )
        created_skill.refresh_from_db()
        self.assertEqual(created_skill.name, "Analytics")
        self.assertEqual(created_skill.category, "Data and insight")

    def test_failed_create_rolls_back_and_shows_safe_feedback(self):
        skill_count = Skill.objects.count()
        original_save = Skill.save

        def save_then_fail(instance, *args, **kwargs):
            original_save(instance, *args, **kwargs)
            raise DatabaseError("Simulated skill insert failure")

        with patch.object(Skill, "save", new=save_then_fail):
            response = self.client.post(self.create_url, self.valid_create_data())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Skill.objects.count(), skill_count)
        self.assertFalse(Skill.objects.filter(name="Data Analysis").exists())
        self.assertContains(
            response,
            "We could not save this skill. No changes were applied. Please try again.",
        )

    def test_failed_update_rolls_back_and_shows_safe_feedback(self):
        original_save = Skill.save

        def save_then_fail(instance, *args, **kwargs):
            original_save(instance, *args, **kwargs)
            raise DatabaseError("Simulated skill update failure")

        with patch.object(Skill, "save", new=save_then_fail):
            response = self.client.post(self.update_url, self.valid_update_data())

        self.assertEqual(response.status_code, 200)
        self.skill.refresh_from_db()
        self.assertEqual(self.skill.name, "Python")
        self.assertEqual(self.skill.category, "Engineering")
        self.assertContains(
            response,
            "We could not save this skill. No changes were applied. Please try again.",
        )
