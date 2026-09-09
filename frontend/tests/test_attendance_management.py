import re
import statistics
import time
from datetime import date, time as clock_time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import DatabaseError, connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from core.models import Attendance, Employee
from core.services.attendance import get_attendance_records
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)
from frontend.selectors.attendance import ATTENDANCE_PAGE_SIZE


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


class AttendanceDirectoryTests(TestCase):
    EXPECTED_QUERY_COUNT = 7
    TIMING_SAMPLE_COUNT = 7

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="attendance-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.hr_user = get_user_model().objects.create_user(username="attendance-hr")
        cls.hr_user.groups.add(Group.objects.get(name=HR_ADMINISTRATOR_GROUP))
        cls.no_access_user = get_user_model().objects.create_user(
            username="attendance-no-access"
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
        cls.alex_present = Attendance.objects.create(
            employee=cls.alex,
            date=date(2026, 9, 8),
            status=Attendance.Status.PRESENT,
            arrival_time=clock_time(8, 30),
            departure_time=clock_time(17, 0),
        )
        cls.jamie_late = Attendance.objects.create(
            employee=cls.jamie,
            date=date(2026, 9, 9),
            status=Attendance.Status.LATE,
            arrival_time=clock_time(9, 20),
            departure_time=clock_time(17, 30),
        )
        for index in range(23):
            Attendance.objects.create(
                employee=cls.alex if index % 2 else cls.jamie,
                date=date(2027, 1, 1) + timedelta(days=index),
                status=Attendance.Status.REMOTE,
                arrival_time=clock_time(8, 0),
                departure_time=clock_time(16, 30),
            )

    def setUp(self):
        self.url = reverse("frontend:attendance_list")
        self.client.force_login(self.viewer)

    def test_directory_route_renders_descriptive_context_and_navigation(self):
        self.assertEqual(self.url, "/attendance/")
        self.assertEqual(resolve(self.url).view_name, "frontend:attendance_list")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/attendance/list.html")
        self.assertContains(response, "<h1>Attendance directory</h1>", html=True)
        self.assertContains(response, "Attendance directory results")
        self.assertContains(response, "Alex Morgan")
        self.assertContains(response, "Arrival 8:00 AM")
        self.assertContains(response, "Departure 4:30 PM")
        self.assertContains(
            response,
            "Operational history only; attendance does not affect staffing "
            "recommendations",
        )
        self.assertRegex(
            response.content.decode("utf-8"),
            r'href="/attendance/"\s+aria-current="page"',
        )

    def test_employee_status_and_date_filters_are_combined(self):
        response = self.client.get(
            self.url,
            {
                "employee": str(self.alex.employee_id),
                "status": Attendance.Status.PRESENT,
                "from_date": "2026-09-08",
                "to_date": "2026-09-08",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertEqual(
            [
                record.attendance_id
                for record in response.context["page_obj"].object_list
            ],
            [self.alex_present.attendance_id],
        )
        self.assertContains(response, "Sep 8, 2026")

        outside = self.client.get(
            self.url,
            {"from_date": "2026-09-10", "to_date": "2026-12-31"},
        )
        self.assertEqual(outside.context["page_obj"].paginator.count, 0)

    def test_sorting_is_allow_listed_and_deterministic(self):
        employee_response = self.client.get(self.url, {"sort": "employee"})
        names = [
            str(record.employee)
            for record in employee_response.context["page_obj"].object_list
        ]
        self.assertEqual(names, sorted(names))

        invalid_response = self.client.get(
            self.url,
            {"sort": "-employee__department"},
        )
        self.assertEqual(
            invalid_response.context["filter_form"].cleaned_data["sort"],
            "date_desc",
        )
        dates_and_ids = [
            (record.date, record.attendance_id)
            for record in invalid_response.context["page_obj"].object_list
        ]
        self.assertEqual(
            dates_and_ids,
            sorted(
                dates_and_ids,
                key=lambda item: (-item[0].toordinal(), item[1]),
            ),
        )

    def test_pagination_is_bounded_and_preserves_filter_parameters(self):
        response = self.client.get(
            self.url,
            {"status": Attendance.Status.REMOTE, "page": 2},
        )

        page_obj = response.context["page_obj"]
        self.assertEqual(page_obj.paginator.per_page, ATTENDANCE_PAGE_SIZE)
        self.assertEqual(page_obj.number, 2)
        self.assertEqual(page_obj.paginator.count, 23)
        self.assertContains(response, "status=remote&amp;page=1")

    def test_invalid_filter_period_shows_field_feedback(self):
        response = self.client.get(
            self.url,
            {"from_date": "2026-09-10", "to_date": "2026-09-01"},
        )

        self.assertIn("to_date", response.context["filter_form"].errors)
        self.assertContains(response, 'id="id_to_date_error"')
        self.assertContains(
            response,
            "The end of the filter period must be on or after its start.",
        )

    def test_filtered_and_unpopulated_empty_states_are_distinct(self):
        filtered = self.client.get(
            self.url,
            {"status": Attendance.Status.ABSENT},
        )
        self.assertContains(filtered, "No attendance records match these filters")
        self.assertContains(filtered, "Clear filters")

        Attendance.objects.all().delete()
        empty = self.client.get(self.url)
        self.assertContains(empty, "No attendance records yet")
        self.assertNotContains(empty, "Add the first attendance record")

        hr_client = Client()
        hr_client.force_login(self.hr_user)
        self.assertContains(
            hr_client.get(self.url),
            "Add the first attendance record",
        )

    def test_view_permission_boundaries_are_enforced(self):
        anonymous = Client().get(self.url)
        self.assertRedirects(
            anonymous,
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
        self.assertEqual(self.client.get(self.url).status_code, 200)
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
            "\nM3.9 attendance-directory baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            f"{Attendance.objects.count()} attendance records):\n"
            f"  queries={self.EXPECTED_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )


class AttendanceMaintenanceTests(TestCase):
    FORM_CSRF_PATTERN = re.compile(
        r'<form method="post" novalidate data-loading-form>\s*'
        r'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)">'
    )
    DELETE_CSRF_PATTERN = re.compile(
        r'<form method="post" action="[^"]+/delete/" data-loading-form>\s*'
        r'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)">'
    )

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.hr_user = get_user_model().objects.create_user(
            username="attendance-maintainer"
        )
        cls.hr_user.groups.add(Group.objects.get(name=HR_ADMINISTRATOR_GROUP))
        cls.viewer = get_user_model().objects.create_user(
            username="attendance-readonly"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.employee = create_employee(first_name="Taylor", last_name="Brooks")
        cls.other_employee = create_employee(
            first_name="Jordan",
            last_name="Lee",
            department="Operations",
        )
        cls.attendance = Attendance.objects.create(
            employee=cls.employee,
            date=date(2026, 9, 8),
            status=Attendance.Status.PRESENT,
            arrival_time=clock_time(8, 30),
            departure_time=clock_time(17, 0),
        )
        cls.other_day = Attendance.objects.create(
            employee=cls.employee,
            date=date(2026, 9, 9),
            status=Attendance.Status.REMOTE,
            arrival_time=clock_time(8, 0),
            departure_time=clock_time(16, 30),
        )
        cls.add_only_user = cls._permission_user(
            "attendance-add-only",
            "add_attendance",
        )
        cls.change_only_user = cls._permission_user(
            "attendance-change-only",
            "change_attendance",
        )
        cls.delete_only_user = cls._permission_user(
            "attendance-delete-only",
            "delete_attendance",
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
        self.create_url = reverse("frontend:attendance_create")
        self.update_url = reverse(
            "frontend:attendance_update",
            args=[self.attendance.attendance_id],
        )
        self.delete_url = reverse(
            "frontend:attendance_delete",
            args=[self.attendance.attendance_id],
        )
        self.client.force_login(self.hr_user)

    def valid_create_data(self):
        return {
            "employee": str(self.other_employee.employee_id),
            "date": "2026-09-10",
            "status": Attendance.Status.LATE,
            "arrival_time": "09:15",
            "departure_time": "17:30",
        }

    def valid_update_data(self):
        return {
            "employee": str(self.employee.employee_id),
            "date": "2026-09-08",
            "status": Attendance.Status.HALF_DAY,
            "arrival_time": "08:45",
            "departure_time": "13:00",
        }

    def csrf_token(self, response, pattern):
        match = pattern.search(response.content.decode("utf-8"))
        self.assertIsNotNone(match, "The POST form must render its own CSRF input.")
        return match.group(1)

    def test_routes_render_forms_and_safe_confirmation(self):
        self.assertEqual(self.create_url, "/attendance/new/")
        self.assertEqual(
            resolve(self.create_url).view_name,
            "frontend:attendance_create",
        )
        self.assertEqual(
            resolve(self.update_url).view_name,
            "frontend:attendance_update",
        )
        self.assertEqual(
            resolve(self.delete_url).view_name,
            "frontend:attendance_delete",
        )

        create_response = self.client.get(self.create_url)
        self.assertTemplateUsed(
            create_response,
            "frontend/attendance/create.html",
        )
        self.assertContains(create_response, "<h1>Add attendance</h1>", html=True)
        self.assertContains(create_response, "Attendance record")
        self.assertContains(create_response, "Recorded times")
        self.assertContains(create_response, 'type="time"', count=2)
        self.assertContains(
            create_response,
            "does not affect staffing recommendations",
        )
        self.csrf_token(create_response, self.FORM_CSRF_PATTERN)

        update_response = self.client.get(self.update_url)
        self.assertTemplateUsed(update_response, "frontend/attendance/edit.html")
        self.assertContains(update_response, "<h1>Edit attendance</h1>", html=True)
        self.assertContains(update_response, "Taylor Brooks")
        self.csrf_token(update_response, self.FORM_CSRF_PATTERN)

        delete_response = self.client.get(self.delete_url)
        self.assertTemplateUsed(
            delete_response,
            "frontend/attendance/confirm_delete.html",
        )
        self.assertContains(delete_response, "Delete this attendance record?")
        self.assertContains(
            delete_response,
            "Employee details, planning, and staffing recommendations will not "
            "change",
        )
        self.assertTrue(Attendance.objects.filter(pk=self.attendance.pk).exists())
        self.csrf_token(delete_response, self.DELETE_CSRF_PATTERN)

    def test_valid_create_preserves_employee_status_and_service_history(self):
        response = self.client.post(
            self.create_url,
            self.valid_create_data(),
            follow=True,
        )

        created = Attendance.objects.get(
            employee=self.other_employee,
            date=date(2026, 9, 10),
        )
        self.assertRedirects(response, reverse("frontend:attendance_list"))
        self.assertEqual(created.status, Attendance.Status.LATE)
        self.assertEqual(created.arrival_time, clock_time(9, 15))
        self.other_employee.refresh_from_db()
        self.assertEqual(self.other_employee.status, Employee.Status.ACTIVE)
        self.assertEqual(
            list(
                get_attendance_records(
                    self.other_employee,
                    date(2026, 9, 10),
                    date(2026, 9, 10),
                ).values_list("attendance_id", flat=True)
            ),
            [created.attendance_id],
        )
        self.assertContains(response, "Attendance for Jordan Lee")
        self.assertContains(response, "was added.")

    def test_valid_update_preserves_employee_status(self):
        response = self.client.post(
            self.update_url,
            self.valid_update_data(),
            follow=True,
        )

        self.attendance.refresh_from_db()
        self.employee.refresh_from_db()
        self.assertRedirects(response, reverse("frontend:attendance_list"))
        self.assertEqual(self.attendance.status, Attendance.Status.HALF_DAY)
        self.assertEqual(self.attendance.arrival_time, clock_time(8, 45))
        self.assertEqual(self.attendance.departure_time, clock_time(13, 0))
        self.assertEqual(self.employee.status, Employee.Status.ACTIVE)
        self.assertContains(response, "Attendance for Taylor Brooks")
        self.assertContains(response, "was updated.")

    def test_duplicate_employee_date_is_rejected_on_create_and_update(self):
        count_before = Attendance.objects.count()
        duplicate_create = self.valid_create_data()
        duplicate_create.update(
            {
                "employee": str(self.employee.employee_id),
                "date": "2026-09-08",
            }
        )
        create_response = self.client.post(self.create_url, duplicate_create)

        self.assertEqual(Attendance.objects.count(), count_before)
        self.assertIn("date", create_response.context["form"].errors)
        self.assertContains(create_response, 'id="id_date_error"')
        self.assertContains(
            create_response,
            "An attendance record already exists for Taylor Brooks on this date.",
        )

        update_data = self.valid_update_data()
        update_data["date"] = "2026-09-09"
        update_response = self.client.post(self.update_url, update_data)
        self.assertIn("date", update_response.context["form"].errors)
        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.date, date(2026, 9, 8))
        self.assertEqual(self.attendance.status, Attendance.Status.PRESENT)

    def test_invalid_time_order_and_choices_show_errors_without_changes(self):
        count_before = Attendance.objects.count()
        invalid_create = self.valid_create_data()
        invalid_create.update(
            {
                "status": "not-a-status",
                "arrival_time": "18:00",
                "departure_time": "08:00",
            }
        )
        create_response = self.client.post(self.create_url, invalid_create)
        self.assertEqual(Attendance.objects.count(), count_before)
        self.assertIn("status", create_response.context["form"].errors)

        invalid_update = self.valid_update_data()
        invalid_update.update(
            {"arrival_time": "14:00", "departure_time": "09:00"}
        )
        update_response = self.client.post(self.update_url, invalid_update)
        self.assertIn("departure_time", update_response.context["form"].errors)
        self.assertContains(update_response, 'id="id_departure_time_error"')
        self.assertContains(
            update_response,
            "Departure time must be at or after arrival time.",
        )
        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.arrival_time, clock_time(8, 30))
        self.assertEqual(self.attendance.departure_time, clock_time(17, 0))

    def test_directory_actions_match_write_permissions(self):
        list_url = reverse("frontend:attendance_list")
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
            (
                self.add_only_user,
                self.create_url,
                self.update_url,
                self.delete_url,
            ),
            (
                self.change_only_user,
                self.update_url,
                self.create_url,
                self.delete_url,
            ),
            (
                self.delete_only_user,
                self.delete_url,
                self.create_url,
                self.update_url,
            ),
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
        count_before = Attendance.objects.count()

        self.assertEqual(
            csrf_client.post(self.create_url, self.valid_create_data()).status_code,
            403,
        )
        self.assertEqual(
            csrf_client.post(self.update_url, self.valid_update_data()).status_code,
            403,
        )
        self.assertEqual(csrf_client.post(self.delete_url).status_code, 403)
        self.assertEqual(Attendance.objects.count(), count_before)
        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.status, Attendance.Status.PRESENT)

    def test_rendered_csrf_tokens_allow_create_update_and_delete(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr_user)

        create_data = self.valid_create_data()
        create_data["csrfmiddlewaretoken"] = self.csrf_token(
            csrf_client.get(self.create_url),
            self.FORM_CSRF_PATTERN,
        )
        self.assertRedirects(
            csrf_client.post(self.create_url, create_data),
            reverse("frontend:attendance_list"),
            fetch_redirect_response=False,
        )
        created = Attendance.objects.get(
            employee=self.other_employee,
            date=date(2026, 9, 10),
        )

        update_url = reverse(
            "frontend:attendance_update",
            args=[created.attendance_id],
        )
        update_data = self.valid_create_data()
        update_data.update(
            {
                "status": Attendance.Status.REMOTE,
                "csrfmiddlewaretoken": self.csrf_token(
                    csrf_client.get(update_url),
                    self.FORM_CSRF_PATTERN,
                ),
            }
        )
        self.assertRedirects(
            csrf_client.post(update_url, update_data),
            reverse("frontend:attendance_list"),
            fetch_redirect_response=False,
        )

        delete_url = reverse(
            "frontend:attendance_delete",
            args=[created.attendance_id],
        )
        delete_data = {
            "csrfmiddlewaretoken": self.csrf_token(
                csrf_client.get(delete_url),
                self.DELETE_CSRF_PATTERN,
            )
        }
        self.assertRedirects(
            csrf_client.post(delete_url, delete_data),
            reverse("frontend:attendance_list"),
            fetch_redirect_response=False,
        )
        self.assertFalse(Attendance.objects.filter(pk=created.pk).exists())

    def test_missing_stale_and_unsupported_requests_are_safe(self):
        missing_update = reverse("frontend:attendance_update", args=[999999])
        missing_delete = reverse("frontend:attendance_delete", args=[999999])
        self.assertEqual(self.client.get(missing_update).status_code, 404)
        self.assertEqual(self.client.get(missing_delete).status_code, 404)
        self.assertEqual(self.client.put(self.delete_url).status_code, 405)

        self.attendance.delete()
        stale = self.client.post(self.delete_url, follow=True)
        self.assertRedirects(stale, reverse("frontend:attendance_list"))
        self.assertContains(
            stale,
            "This attendance record no longer exists. No deletion was needed.",
        )

    def test_confirmed_delete_removes_only_attendance_history(self):
        response = self.client.post(self.delete_url, follow=True)

        self.assertRedirects(response, reverse("frontend:attendance_list"))
        self.assertFalse(Attendance.objects.filter(pk=self.attendance.pk).exists())
        self.assertTrue(Attendance.objects.filter(pk=self.other_day.pk).exists())
        self.assertTrue(Employee.objects.filter(pk=self.employee.pk).exists())
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.ACTIVE)
        self.assertContains(response, "Attendance for Taylor Brooks")
        self.assertContains(response, "was deleted.")

    def test_failed_create_and_update_roll_back_with_safe_feedback(self):
        original_save = Attendance.save

        def save_then_fail(instance, *args, **kwargs):
            original_save(instance, *args, **kwargs)
            raise DatabaseError("Simulated attendance save failure")

        with patch.object(Attendance, "save", new=save_then_fail):
            create_response = self.client.post(
                self.create_url,
                self.valid_create_data(),
            )
        self.assertFalse(
            Attendance.objects.filter(
                employee=self.other_employee,
                date=date(2026, 9, 10),
            ).exists()
        )
        self.assertContains(
            create_response,
            "We could not save this attendance record. No changes were applied. "
            "Please try again.",
        )

        with patch.object(Attendance, "save", new=save_then_fail):
            update_response = self.client.post(
                self.update_url,
                self.valid_update_data(),
            )
        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.status, Attendance.Status.PRESENT)
        self.assertEqual(self.attendance.arrival_time, clock_time(8, 30))
        self.assertContains(
            update_response,
            "We could not save this attendance record. No changes were applied. "
            "Please try again.",
        )

    def test_failed_delete_rolls_back_with_safe_feedback(self):
        original_delete = Attendance.delete

        def delete_then_fail(instance, *args, **kwargs):
            original_delete(instance, *args, **kwargs)
            raise DatabaseError("Simulated attendance delete failure")

        with patch.object(Attendance, "delete", new=delete_then_fail):
            response = self.client.post(self.delete_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Attendance.objects.filter(pk=self.attendance.pk).exists())
        self.assertContains(
            response,
            "We could not delete this attendance record. Nothing was deleted. "
            "Please try again.",
        )
