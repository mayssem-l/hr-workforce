import re
import statistics
import time
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import DatabaseError, connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone

from core.models import Employee, Leave
from core.services.availability import get_approved_leaves
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)
from frontend.selectors.leaves import LEAVE_PAGE_SIZE


def create_employee(*, first_name, last_name, department="Engineering"):
    return Employee.objects.create(
        first_name=first_name,
        last_name=last_name,
        department=department,
        position="Specialist",
        hire_date=date(2020, 1, 6),
        experience_years=Decimal("6.0"),
        capacity_hours_week=Decimal("40.00"),
        status=Employee.Status.ACTIVE,
    )


class LeaveDirectoryTests(TestCase):
    EXPECTED_QUERY_COUNT = 7
    TIMING_SAMPLE_COUNT = 7

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(username="leave-viewer")
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.hr_user = get_user_model().objects.create_user(username="leave-hr")
        cls.hr_user.groups.add(Group.objects.get(name=HR_ADMINISTRATOR_GROUP))
        cls.no_access_user = get_user_model().objects.create_user(
            username="leave-no-access"
        )

        cls.alex = create_employee(
            first_name="Alex",
            last_name="Morgan",
            department="Engineering",
        )
        cls.jamie = create_employee(
            first_name="Jamie",
            last_name="Rivera",
            department="Finance",
        )
        cls.alex_annual = Leave.objects.create(
            employee=cls.alex,
            start_date=date(2026, 10, 12),
            end_date=date(2026, 10, 16),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )
        cls.jamie_sick = Leave.objects.create(
            employee=cls.jamie,
            start_date=date(2026, 11, 2),
            end_date=date(2026, 11, 4),
            type=Leave.Type.SICK,
            status=Leave.Status.PENDING,
        )

        for index in range(23):
            start = date(2027, 1, 1) + timedelta(days=index * 2)
            Leave.objects.create(
                employee=cls.alex if index % 2 else cls.jamie,
                start_date=start,
                end_date=start + timedelta(days=1),
                type=Leave.Type.OTHER,
                status=Leave.Status.CANCELLED,
            )

    def setUp(self):
        self.url = reverse("frontend:leave_list")
        self.client.force_login(self.viewer)

    def test_directory_route_renders_leave_context_and_workforce_navigation(self):
        self.assertEqual(self.url, "/leave/")
        self.assertEqual(resolve(self.url).view_name, "frontend:leave_list")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/leaves/list.html")
        self.assertContains(response, "<h1>Leave directory</h1>", html=True)
        self.assertContains(response, "Leave directory results")
        self.assertContains(response, "Alex Morgan")
        self.assertContains(response, "Annual")
        self.assertContains(response, "Approved")
        self.assertContains(
            response,
            "Approved dated leave informs availability; employment status "
            "remains separate",
        )
        self.assertRegex(
            response.content.decode("utf-8"),
            r'href="/leave/"\s+aria-current="page"',
        )

    def test_employee_type_status_and_overlap_filters_are_combined(self):
        response = self.client.get(
            self.url,
            {
                "employee": str(self.alex.employee_id),
                "leave_type": Leave.Type.ANNUAL,
                "status": Leave.Status.APPROVED,
                "from_date": "2026-10-14",
                "to_date": "2026-10-14",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertContains(response, "Alex Morgan")
        self.assertContains(response, "Oct 12, 2026&ndash;Oct 16, 2026")
        self.assertEqual(
            [leave.employee_id for leave in response.context["page_obj"].object_list],
            [self.alex.employee_id],
        )

        outside_response = self.client.get(
            self.url,
            {"from_date": "2026-10-17", "to_date": "2026-11-01"},
        )
        self.assertEqual(outside_response.context["page_obj"].paginator.count, 0)

    def test_sorting_is_allow_listed_and_deterministic(self):
        employee_response = self.client.get(self.url, {"sort": "employee"})
        names = [
            str(leave.employee)
            for leave in employee_response.context["page_obj"].object_list
        ]
        self.assertEqual(names, sorted(names))

        invalid_response = self.client.get(
            self.url,
            {"sort": "-employee__department"},
        )
        self.assertEqual(
            invalid_response.context["filter_form"].cleaned_data["sort"],
            "start_date_desc",
        )
        dates_and_ids = [
            (leave.start_date, leave.leave_id)
            for leave in invalid_response.context["page_obj"].object_list
        ]
        self.assertEqual(
            dates_and_ids,
            sorted(dates_and_ids, key=lambda item: (-item[0].toordinal(), item[1])),
        )

    def test_pagination_is_bounded_and_preserves_filter_parameters(self):
        response = self.client.get(
            self.url,
            {"status": Leave.Status.CANCELLED, "page": 2},
        )

        self.assertEqual(response.status_code, 200)
        page_obj = response.context["page_obj"]
        self.assertEqual(page_obj.paginator.per_page, LEAVE_PAGE_SIZE)
        self.assertEqual(page_obj.number, 2)
        self.assertEqual(page_obj.paginator.count, 23)
        self.assertContains(response, "status=cancelled&amp;page=1")

    def test_invalid_filter_period_shows_field_feedback(self):
        response = self.client.get(
            self.url,
            {"from_date": "2026-12-01", "to_date": "2026-11-01"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("to_date", response.context["filter_form"].errors)
        self.assertContains(response, 'id="id_to_date_error"')
        self.assertContains(
            response,
            "The end of the filter period must be on or after its start.",
        )

    def test_filtered_and_unpopulated_empty_states_are_distinct(self):
        filtered = self.client.get(self.url, {"status": Leave.Status.REJECTED})
        self.assertContains(filtered, "No leave records match these filters")
        self.assertContains(filtered, "Clear filters")

        Leave.objects.all().delete()
        empty = self.client.get(self.url)
        self.assertContains(empty, "No leave records yet")
        self.assertNotContains(empty, "Add the first leave record")

        hr_client = Client()
        hr_client.force_login(self.hr_user)
        self.assertContains(hr_client.get(self.url), "Add the first leave record")

    def test_view_permission_boundaries_are_enforced(self):
        anonymous_response = Client().get(self.url)
        self.assertRedirects(
            anonymous_response,
            f"{reverse('frontend:login')}?next={self.url}",
            fetch_redirect_response=False,
        )

        no_access_client = Client()
        no_access_client.force_login(self.no_access_user)
        self.assertEqual(no_access_client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_populated_directory_query_count_matches_recorded_budget(self):
        with self.assertNumQueries(self.EXPECTED_QUERY_COUNT):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

    def test_warm_directory_response_time_is_recorded(self):
        warmup_response = self.client.get(self.url)
        self.assertEqual(warmup_response.status_code, 200)

        durations_ms = []
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as captured_queries:
                started_at = time.perf_counter()
                response = self.client.get(self.url)
                durations_ms.append((time.perf_counter() - started_at) * 1000)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(captured_queries), self.EXPECTED_QUERY_COUNT)

        p95_ms = statistics.quantiles(durations_ms, n=20, method="inclusive")[18]
        print(
            "\nM3.8 leave-directory baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            f"{Leave.objects.count()} leave records):\n"
            f"  queries={self.EXPECTED_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )


class LeaveMaintenanceTests(TestCase):
    LEAVE_FORM_CSRF_PATTERN = re.compile(
        r'<form method="post" novalidate data-loading-form>\s*'
        r'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)">'
    )
    DELETE_FORM_CSRF_PATTERN = re.compile(
        r'<form method="post" action="[^"]+/delete/" data-loading-form>\s*'
        r'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)">'
    )

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.hr_user = get_user_model().objects.create_user(
            username="leave-maintainer"
        )
        cls.hr_user.groups.add(Group.objects.get(name=HR_ADMINISTRATOR_GROUP))
        cls.viewer = get_user_model().objects.create_user(
            username="leave-readonly"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.employee = create_employee(first_name="Taylor", last_name="Brooks")
        cls.other_employee = create_employee(
            first_name="Jordan",
            last_name="Lee",
            department="Operations",
        )
        cls.leave = Leave.objects.create(
            employee=cls.employee,
            start_date=date(2026, 12, 7),
            end_date=date(2026, 12, 11),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.PENDING,
        )

        cls.add_only_user = cls._permission_user("leave-add-only", "add_leave")
        cls.change_only_user = cls._permission_user(
            "leave-change-only", "change_leave"
        )
        cls.delete_only_user = cls._permission_user(
            "leave-delete-only", "delete_leave"
        )

    @staticmethod
    def _permission_user(username, codename):
        user = get_user_model().objects.create_user(username=username)
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename=codename,
            )
        )
        return user

    def setUp(self):
        self.create_url = reverse("frontend:leave_create")
        self.update_url = reverse(
            "frontend:leave_update",
            args=[self.leave.leave_id],
        )
        self.delete_url = reverse(
            "frontend:leave_delete",
            args=[self.leave.leave_id],
        )
        self.client.force_login(self.hr_user)

    def valid_create_data(self):
        return {
            "employee": str(self.other_employee.employee_id),
            "type": Leave.Type.SICK,
            "start_date": "2027-01-11",
            "end_date": "2027-01-13",
            "status": Leave.Status.APPROVED,
        }

    def valid_update_data(self):
        return {
            "employee": str(self.employee.employee_id),
            "type": Leave.Type.UNPAID,
            "start_date": "2026-12-14",
            "end_date": "2026-12-18",
            "status": Leave.Status.APPROVED,
        }

    def csrf_token(self, response, pattern):
        match = pattern.search(response.content.decode("utf-8"))
        self.assertIsNotNone(match, "The POST form must render its own CSRF input.")
        return match.group(1)

    def test_routes_render_forms_and_safe_confirmation(self):
        self.assertEqual(self.create_url, "/leave/new/")
        self.assertEqual(resolve(self.create_url).view_name, "frontend:leave_create")
        self.assertEqual(resolve(self.update_url).view_name, "frontend:leave_update")
        self.assertEqual(resolve(self.delete_url).view_name, "frontend:leave_delete")

        create_response = self.client.get(self.create_url)
        self.assertTemplateUsed(create_response, "frontend/leaves/create.html")
        self.assertContains(create_response, "<h1>Add leave</h1>", html=True)
        self.assertContains(create_response, "Leave record")
        self.assertContains(create_response, "Schedule and approval")
        self.assertContains(create_response, 'type="date"', count=2)
        self.assertContains(create_response, "Employment status is managed separately")
        self.csrf_token(create_response, self.LEAVE_FORM_CSRF_PATTERN)

        update_response = self.client.get(self.update_url)
        self.assertTemplateUsed(update_response, "frontend/leaves/edit.html")
        self.assertContains(update_response, "<h1>Edit leave</h1>", html=True)
        self.assertContains(update_response, "Taylor Brooks")
        self.csrf_token(update_response, self.LEAVE_FORM_CSRF_PATTERN)

        delete_response = self.client.get(self.delete_url)
        self.assertTemplateUsed(delete_response, "frontend/leaves/confirm_delete.html")
        self.assertContains(delete_response, "Delete this leave record?")
        self.assertContains(delete_response, "The employee profile and employment status will not change")
        self.assertTrue(Leave.objects.filter(pk=self.leave.pk).exists())
        self.csrf_token(delete_response, self.DELETE_FORM_CSRF_PATTERN)

    def test_valid_create_preserves_employee_status_and_updates_approved_context(self):
        today = timezone.localdate()
        data = self.valid_create_data()
        data.update(
            {
                "start_date": (today + timedelta(days=20)).isoformat(),
                "end_date": (today + timedelta(days=24)).isoformat(),
            }
        )

        response = self.client.post(self.create_url, data, follow=True)

        created = Leave.objects.get(
            employee=self.other_employee,
            type=Leave.Type.SICK,
            status=Leave.Status.APPROVED,
        )
        self.assertRedirects(response, reverse("frontend:leave_list"))
        self.assertContains(response, "Sick leave for Jordan Lee was added.")
        self.other_employee.refresh_from_db()
        self.assertEqual(self.other_employee.status, Employee.Status.ACTIVE)
        self.assertEqual(
            list(
                get_approved_leaves(self.other_employee, today, date.max).values_list(
                    "leave_id", flat=True
                )
            ),
            [created.leave_id],
        )

        profile_response = self.client.get(
            reverse(
                "frontend:employee_detail",
                args=[self.other_employee.employee_id],
            )
        )
        self.assertContains(profile_response, "Upcoming approved leave")
        self.assertContains(profile_response, "Sick leave")

    def test_valid_update_preserves_employee_status(self):
        response = self.client.post(self.update_url, self.valid_update_data(), follow=True)

        self.leave.refresh_from_db()
        self.employee.refresh_from_db()
        self.assertRedirects(response, reverse("frontend:leave_list"))
        self.assertEqual(self.leave.type, Leave.Type.UNPAID)
        self.assertEqual(self.leave.start_date, date(2026, 12, 14))
        self.assertEqual(self.leave.end_date, date(2026, 12, 18))
        self.assertEqual(self.leave.status, Leave.Status.APPROVED)
        self.assertEqual(self.employee.status, Employee.Status.ACTIVE)
        self.assertContains(response, "Unpaid leave for Taylor Brooks was updated.")

    def test_invalid_create_and_update_show_field_errors_without_database_changes(self):
        count_before = Leave.objects.count()
        invalid_create = self.valid_create_data()
        invalid_create.update(
            {
                "type": "not-a-type",
                "start_date": "2027-02-10",
                "end_date": "2027-02-01",
                "status": "not-a-status",
            }
        )
        create_response = self.client.post(self.create_url, invalid_create)

        self.assertEqual(Leave.objects.count(), count_before)
        for field_name in ("type", "end_date", "status"):
            self.assertIn(field_name, create_response.context["form"].errors)
            self.assertContains(create_response, f'id="id_{field_name}_error"')
        self.assertContains(
            create_response,
            "Please correct the highlighted fields before saving the leave record.",
        )

        invalid_update = self.valid_update_data()
        invalid_update.update(
            {"start_date": "2027-03-10", "end_date": "2027-03-01"}
        )
        update_response = self.client.post(self.update_url, invalid_update)

        self.assertIn("end_date", update_response.context["form"].errors)
        self.assertContains(update_response, 'id="id_end_date_error"')
        self.leave.refresh_from_db()
        self.assertEqual(self.leave.start_date, date(2026, 12, 7))
        self.assertEqual(self.leave.end_date, date(2026, 12, 11))
        self.assertEqual(self.leave.status, Leave.Status.PENDING)

    def test_directory_actions_match_independent_write_permissions(self):
        list_url = reverse("frontend:leave_list")
        hr_response = self.client.get(list_url)
        self.assertContains(hr_response, self.create_url)
        self.assertContains(hr_response, self.update_url)
        self.assertContains(hr_response, self.delete_url)

        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        viewer_response = viewer_client.get(list_url)
        self.assertNotContains(viewer_response, self.create_url)
        self.assertNotContains(viewer_response, self.update_url)
        self.assertNotContains(viewer_response, self.delete_url)

    def test_write_permissions_are_enforced_independently(self):
        cases = (
            (self.add_only_user, self.create_url, self.update_url, self.delete_url),
            (self.change_only_user, self.update_url, self.create_url, self.delete_url),
            (self.delete_only_user, self.delete_url, self.create_url, self.update_url),
        )
        for user, allowed_url, *forbidden_urls in cases:
            client = Client()
            client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(client.get(allowed_url).status_code, 200)
                for forbidden_url in forbidden_urls:
                    self.assertEqual(client.get(forbidden_url).status_code, 403)

        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        for url in (self.create_url, self.update_url, self.delete_url):
            self.assertEqual(viewer_client.get(url).status_code, 403)

    def test_anonymous_write_requests_redirect_to_login(self):
        for url in (self.create_url, self.update_url, self.delete_url):
            response = Client().get(url)
            self.assertRedirects(
                response,
                f"{reverse('frontend:login')}?next={url}",
                fetch_redirect_response=False,
            )

    def test_csrf_enforcement_rejects_all_mutations_without_tokens(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr_user)
        leave_count = Leave.objects.count()

        self.assertEqual(
            csrf_client.post(self.create_url, self.valid_create_data()).status_code,
            403,
        )
        self.assertEqual(
            csrf_client.post(self.update_url, self.valid_update_data()).status_code,
            403,
        )
        self.assertEqual(csrf_client.post(self.delete_url).status_code, 403)
        self.assertEqual(Leave.objects.count(), leave_count)
        self.leave.refresh_from_db()
        self.assertEqual(self.leave.status, Leave.Status.PENDING)

    def test_rendered_csrf_tokens_allow_create_update_and_delete(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr_user)

        create_data = self.valid_create_data()
        create_data["csrfmiddlewaretoken"] = self.csrf_token(
            csrf_client.get(self.create_url), self.LEAVE_FORM_CSRF_PATTERN
        )
        create_response = csrf_client.post(self.create_url, create_data)
        self.assertRedirects(
            create_response,
            reverse("frontend:leave_list"),
            fetch_redirect_response=False,
        )
        created = Leave.objects.get(employee=self.other_employee, type=Leave.Type.SICK)

        update_url = reverse("frontend:leave_update", args=[created.leave_id])
        update_data = self.valid_create_data()
        update_data.update(
            {
                "type": Leave.Type.OTHER,
                "csrfmiddlewaretoken": self.csrf_token(
                    csrf_client.get(update_url), self.LEAVE_FORM_CSRF_PATTERN
                ),
            }
        )
        self.assertRedirects(
            csrf_client.post(update_url, update_data),
            reverse("frontend:leave_list"),
            fetch_redirect_response=False,
        )

        delete_url = reverse("frontend:leave_delete", args=[created.leave_id])
        delete_data = {
            "csrfmiddlewaretoken": self.csrf_token(
                csrf_client.get(delete_url), self.DELETE_FORM_CSRF_PATTERN
            )
        }
        self.assertRedirects(
            csrf_client.post(delete_url, delete_data),
            reverse("frontend:leave_list"),
            fetch_redirect_response=False,
        )
        self.assertFalse(Leave.objects.filter(pk=created.pk).exists())

    def test_missing_and_stale_records_are_handled_safely(self):
        missing_update = reverse("frontend:leave_update", args=[999999])
        missing_delete = reverse("frontend:leave_delete", args=[999999])
        self.assertEqual(self.client.get(missing_update).status_code, 404)
        self.assertEqual(self.client.get(missing_delete).status_code, 404)

        self.leave.delete()
        stale_response = self.client.post(self.delete_url, follow=True)
        self.assertRedirects(stale_response, reverse("frontend:leave_list"))
        self.assertContains(
            stale_response,
            "This leave record no longer exists. No deletion was needed.",
        )

    def test_confirmed_delete_removes_only_the_leave_record(self):
        response = self.client.post(self.delete_url, follow=True)

        self.assertRedirects(response, reverse("frontend:leave_list"))
        self.assertFalse(Leave.objects.filter(pk=self.leave.pk).exists())
        self.assertTrue(Employee.objects.filter(pk=self.employee.pk).exists())
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.ACTIVE)
        self.assertContains(response, "Annual leave for Taylor Brooks was deleted.")

    def test_failed_create_and_update_roll_back_and_show_safe_feedback(self):
        original_save = Leave.save

        def save_then_fail(instance, *args, **kwargs):
            original_save(instance, *args, **kwargs)
            raise DatabaseError("Simulated leave save failure")

        with patch.object(Leave, "save", new=save_then_fail):
            create_response = self.client.post(self.create_url, self.valid_create_data())
        self.assertFalse(
            Leave.objects.filter(employee=self.other_employee, type=Leave.Type.SICK).exists()
        )
        self.assertContains(
            create_response,
            "We could not save this leave record. No changes were applied. Please try again.",
        )

        with patch.object(Leave, "save", new=save_then_fail):
            update_response = self.client.post(self.update_url, self.valid_update_data())
        self.leave.refresh_from_db()
        self.assertEqual(self.leave.type, Leave.Type.ANNUAL)
        self.assertEqual(self.leave.status, Leave.Status.PENDING)
        self.assertContains(
            update_response,
            "We could not save this leave record. No changes were applied. Please try again.",
        )

    def test_failed_delete_rolls_back_and_shows_safe_feedback(self):
        original_delete = Leave.delete

        def delete_then_fail(instance, *args, **kwargs):
            original_delete(instance, *args, **kwargs)
            raise DatabaseError("Simulated leave delete failure")

        with patch.object(Leave, "delete", new=delete_then_fail):
            response = self.client.post(self.delete_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Leave.objects.filter(pk=self.leave.pk).exists())
        self.assertContains(
            response,
            "We could not delete this leave record. Nothing was deleted. Please try again.",
        )
