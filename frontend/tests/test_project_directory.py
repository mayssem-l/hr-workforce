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

from core.models import Project
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)
from frontend.selectors.projects import PROJECT_PAGE_SIZE


class ProjectDirectoryTests(TestCase):
    EXPECTED_QUERY_COUNT = 6
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = cls._group_user("project-viewer", VIEWER_GROUP)
        cls.manager = cls._group_user(
            "project-manager",
            MANAGER_PLANNER_GROUP,
        )
        cls.hr_administrator = cls._group_user(
            "project-hr",
            HR_ADMINISTRATOR_GROUP,
        )
        cls.unassigned = get_user_model().objects.create_user(
            username="project-unassigned"
        )

        cls.atlas = cls._create_project(
            name="Atlas Renewal",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 11, 30),
            estimated_hours="320.00",
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.MEDIUM,
        )
        cls.beacon = cls._create_project(
            name="Beacon Launch",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 10, 15),
            estimated_hours="480.00",
            status=Project.Status.IN_PROGRESS,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.HIGH,
        )
        cls.cedar = cls._create_project(
            name="Cedar Migration",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 12, 15),
            estimated_hours="120.00",
            status=Project.Status.ON_HOLD,
            priority=Project.Priority.LOW,
            criticality=Project.Criticality.LOW,
        )

        for index in range(21):
            cls._create_project(
                name=f"Portfolio Initiative {index:02d}",
                start_date=date(2027, 1, 5),
                end_date=date(2027, 3, 31),
                estimated_hours=str(Decimal("100.00") + index),
                status=Project.Status.PLANNED,
                priority=Project.Priority.MEDIUM,
                criticality=Project.Criticality.MEDIUM,
            )

    @classmethod
    def _group_user(cls, username, group_name):
        user = get_user_model().objects.create_user(username=username)
        user.groups.add(Group.objects.get(name=group_name))
        return user

    @classmethod
    def _create_project(
        cls,
        *,
        name,
        start_date,
        end_date,
        estimated_hours,
        status,
        priority,
        criticality,
    ):
        return Project.objects.create(
            name=name,
            description=f"Planning context for {name}.",
            start_date=start_date,
            end_date=end_date,
            estimated_hours=Decimal(estimated_hours),
            status=status,
            priority=priority,
            criticality=criticality,
        )

    def setUp(self):
        self.url = reverse("frontend:project_list")
        self.client.force_login(self.viewer)

    def test_route_is_namespaced_and_resolves_to_the_project_list(self):
        self.assertEqual(self.url, "/projects/")
        match = resolve(self.url)
        self.assertEqual(match.view_name, "frontend:project_list")
        self.assertEqual(match.namespace, "frontend")

    def test_read_permission_handles_anonymous_unassigned_and_authorized_roles(self):
        anonymous_response = Client().get(self.url)
        self.assertRedirects(
            anonymous_response,
            f"{reverse('frontend:login')}?next={self.url}",
            fetch_redirect_response=False,
        )

        unassigned_client = Client()
        unassigned_client.force_login(self.unassigned)
        self.assertEqual(unassigned_client.get(self.url).status_code, 403)

        for user in (self.viewer, self.manager, self.hr_administrator):
            client = Client()
            client.force_login(user)
            with self.subTest(role=user.username):
                self.assertEqual(client.get(self.url).status_code, 200)

    def test_directory_renders_stored_project_information_and_active_navigation(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/projects/list.html")
        self.assertTemplateUsed(response, "frontend/projects/_project_row.html")
        self.assertContains(response, "<h1>Project directory</h1>", html=True)
        self.assertContains(response, "Project directory results")
        self.assertContains(response, "Atlas Renewal")
        self.assertContains(response, "Sep 1, 2026")
        self.assertContains(response, "320.00 h")
        self.assertContains(response, "High")
        self.assertContains(response, "Medium")
        self.assertContains(response, "Planned")
        self.assertContains(response, "Project #0001")
        self.assertRegex(
            response.content.decode("utf-8"),
            r'href="/projects/"\s+aria-current="page"',
        )
        self.assertNotContains(response, "Add project")

    def test_name_search_matches_all_search_terms(self):
        response = self.client.get(self.url, {"query": "Atlas Renewal"})

        self.assertContains(response, "Atlas Renewal")
        self.assertNotContains(response, "Beacon Launch")
        self.assertNotContains(response, "Cedar Migration")
        self.assertEqual(response.context["page_obj"].paginator.count, 1)

    def test_status_priority_criticality_and_date_filters_can_be_combined(self):
        attribute_response = self.client.get(
            self.url,
            {
                "status": Project.Status.PLANNED,
                "priority": Project.Priority.HIGH,
                "criticality": Project.Criticality.MEDIUM,
            },
        )
        self.assertEqual(attribute_response.context["page_obj"].paginator.count, 1)
        self.assertContains(attribute_response, "Atlas Renewal")
        self.assertNotContains(attribute_response, "Beacon Launch")

        date_response = self.client.get(
            self.url,
            {
                "starts_on_or_after": "2026-09-01",
                "ends_on_or_before": "2026-12-31",
            },
        )
        self.assertEqual(date_response.context["page_obj"].paginator.count, 2)
        self.assertContains(date_response, "Atlas Renewal")
        self.assertContains(date_response, "Cedar Migration")
        self.assertNotContains(date_response, "Beacon Launch")

    def test_sorting_uses_only_declared_options_and_defaults_safely(self):
        descending_response = self.client.get(
            self.url,
            {"sort": "estimated_hours_desc"},
        )
        descending_page = list(descending_response.context["page_obj"].object_list)
        self.assertEqual(descending_page[0], self.beacon)

        invalid_response = self.client.get(self.url, {"sort": "__unsafe_sort"})
        default_page = list(invalid_response.context["page_obj"].object_list)
        self.assertEqual(
            invalid_response.context["filter_form"].cleaned_data["sort"],
            "name",
        )
        self.assertEqual(default_page[0], self.atlas)

    def test_pagination_uses_twenty_rows_and_preserves_filter_parameters(self):
        response = self.client.get(
            self.url,
            {"status": Project.Status.PLANNED, "page": 2},
        )

        page_obj = response.context["page_obj"]
        self.assertEqual(page_obj.paginator.per_page, PROJECT_PAGE_SIZE)
        self.assertEqual(page_obj.paginator.count, 22)
        self.assertEqual(page_obj.number, 2)
        self.assertEqual(len(page_obj.object_list), 2)
        self.assertContains(response, "status=planned&amp;page=1")

        unfiltered_response = self.client.get(self.url, {"page": 2})
        unfiltered_page = unfiltered_response.context["page_obj"]
        self.assertEqual(unfiltered_page.number, 2)
        self.assertEqual(len(unfiltered_page.object_list), 4)
        self.assertContains(unfiltered_response, "Page 2 of 2")

    def test_filtered_and_unpopulated_directories_have_clear_empty_states(self):
        filtered_response = self.client.get(
            self.url,
            {"query": "No Such Project"},
        )
        self.assertContains(filtered_response, "No projects match these filters")
        self.assertContains(filtered_response, "Clear filters")
        self.assertNotContains(filtered_response, "Project directory results")

        Project.objects.all().delete()
        empty_response = self.client.get(self.url)
        self.assertContains(empty_response, "No projects yet")
        self.assertNotContains(empty_response, "Add project")

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
            "\nM3.1 project-directory baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            f"{Project.objects.count()} projects):\n"
            f"  queries={self.EXPECTED_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )
