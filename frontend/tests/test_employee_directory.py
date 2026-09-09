import statistics
import time
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from core.models import Employee
from frontend.roles import VIEWER_GROUP, sync_role_permissions
from frontend.selectors.employees import EMPLOYEE_PAGE_SIZE


class EmployeeDirectoryTests(TestCase):
    EXPECTED_QUERY_COUNT = 7
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(username="directory-viewer")
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.unassigned = get_user_model().objects.create_user(
            username="directory-unassigned"
        )

        cls.alex_morgan = cls._create_employee(
            first_name="Alex",
            last_name="Morgan",
            department="Engineering",
            position="Platform Engineer",
            status=Employee.Status.ACTIVE,
            capacity="80.00",
            experience="7.5",
            hire_date=date(2018, 4, 16),
        )
        cls.alex_rivers = cls._create_employee(
            first_name="Alex",
            last_name="Rivers",
            department="Sales",
            position="Account Manager",
            status=Employee.Status.INACTIVE,
            capacity="32.00",
            experience="4.0",
            hire_date=date(2021, 8, 9),
        )
        cls.sam_morgan = cls._create_employee(
            first_name="Sam",
            last_name="Morgan",
            department="Engineering",
            position="Product Designer",
            status=Employee.Status.ON_LEAVE,
            capacity="24.00",
            experience="5.0",
            hire_date=date(2019, 11, 4),
        )

        for index in range(21):
            cls._create_employee(
                first_name=f"Employee{index:02d}",
                last_name=f"Person{index:02d}",
                department="Operations" if index % 2 else "Finance",
                position="Workforce Specialist",
                status=Employee.Status.ACTIVE,
                capacity=str(Decimal("36.00") + index),
                experience="3.0",
                hire_date=date(2022, 1, 3),
            )

    @classmethod
    def _create_employee(
        cls,
        *,
        first_name,
        last_name,
        department,
        position,
        status,
        capacity,
        experience,
        hire_date,
    ):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department=department,
            position=position,
            hire_date=hire_date,
            experience_years=Decimal(experience),
            capacity_hours_week=Decimal(capacity),
            status=status,
        )

    def setUp(self):
        self.url = reverse("frontend:employee_list")
        self.client.force_login(self.viewer)

    def test_route_is_namespaced_and_resolves_to_the_employee_list(self):
        self.assertEqual(self.url, "/employees/")
        match = resolve(self.url)
        self.assertEqual(match.view_name, "frontend:employee_list")
        self.assertEqual(match.namespace, "frontend")

    def test_read_permission_handles_anonymous_unassigned_and_viewer_users(self):
        anonymous_response = Client().get(self.url)
        self.assertRedirects(
            anonymous_response,
            f"{reverse('frontend:login')}?next={self.url}",
            fetch_redirect_response=False,
        )

        unassigned_client = Client()
        unassigned_client.force_login(self.unassigned)
        self.assertEqual(unassigned_client.get(self.url).status_code, 403)

        viewer_response = self.client.get(self.url)
        self.assertEqual(viewer_response.status_code, 200)

    def test_directory_renders_the_desktop_table_and_active_navigation(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/employees/list.html")
        self.assertTemplateUsed(response, "frontend/employees/_employee_row.html")
        self.assertContains(response, "<h1>Employee directory</h1>", html=True)
        self.assertContains(response, "Employee directory results")
        self.assertContains(response, "Alex Morgan")
        self.assertContains(response, "80.00 h")
        self.assertContains(response, "Active")
        self.assertContains(
            response,
            reverse(
                "frontend:employee_detail",
                args=[self.alex_morgan.employee_id],
            ),
        )
        self.assertContains(response, "View profile for Alex Morgan")
        self.assertRegex(
            response.content.decode("utf-8"),
            r'href="/employees/"\s+aria-current="page"',
        )
        self.assertNotContains(response, "Add employee")

    def test_name_search_matches_all_name_terms(self):
        response = self.client.get(self.url, {"query": "Alex Morgan"})

        self.assertContains(response, "Alex Morgan")
        self.assertNotContains(response, "Alex Rivers")
        self.assertNotContains(response, "Sam Morgan")
        self.assertEqual(response.context["page_obj"].paginator.count, 1)

    def test_status_and_department_filters_can_be_combined(self):
        response = self.client.get(
            self.url,
            {"status": Employee.Status.INACTIVE, "department": "Sales"},
        )

        self.assertContains(response, "Alex Rivers")
        self.assertNotContains(response, "Alex Morgan")
        self.assertEqual(response.context["page_obj"].paginator.count, 1)

    def test_sorting_uses_only_declared_options_and_defaults_safely(self):
        descending_response = self.client.get(self.url, {"sort": "name_desc"})
        descending_page = list(descending_response.context["page_obj"].object_list)
        self.assertEqual(descending_page[0], self.alex_rivers)

        invalid_response = self.client.get(self.url, {"sort": "__unsafe_sort"})
        default_page = list(invalid_response.context["page_obj"].object_list)
        self.assertEqual(
            invalid_response.context["filter_form"].cleaned_data["sort"],
            "name",
        )
        self.assertEqual(default_page[0], self.alex_morgan)

    def test_pagination_uses_twenty_rows_and_preserves_filter_parameters(self):
        response = self.client.get(
            self.url,
            {"status": Employee.Status.ACTIVE, "page": 2},
        )

        page_obj = response.context["page_obj"]
        self.assertEqual(page_obj.paginator.per_page, EMPLOYEE_PAGE_SIZE)
        self.assertEqual(page_obj.paginator.count, 22)
        self.assertEqual(page_obj.number, 2)
        self.assertEqual(len(page_obj.object_list), 2)
        self.assertContains(response, "status=active&amp;page=1")

        unfiltered_response = self.client.get(self.url, {"page": 2})
        unfiltered_page = unfiltered_response.context["page_obj"]
        self.assertEqual(unfiltered_page.number, 2)
        self.assertEqual(len(unfiltered_page.object_list), 4)
        self.assertContains(unfiltered_response, "Page 2 of 2")

    def test_filtered_and_unpopulated_directories_have_clear_empty_states(self):
        filtered_response = self.client.get(self.url, {"query": "No Such Person"})
        self.assertContains(filtered_response, "No employees match these filters")
        self.assertContains(filtered_response, "Clear filters")
        self.assertNotContains(filtered_response, "Employee directory results")

        Employee.objects.all().delete()
        empty_response = self.client.get(self.url)
        self.assertContains(empty_response, "No employees yet")
        self.assertNotContains(empty_response, "Add employee")

    def test_populated_directory_query_count_matches_the_recorded_budget(self):
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

        p95_ms = statistics.quantiles(
            durations_ms,
            n=20,
            method="inclusive",
        )[18]
        print(
            "\nM2.1 employee-directory baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            f"{Employee.objects.count()} employees):\n"
            f"  queries={self.EXPECTED_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )
