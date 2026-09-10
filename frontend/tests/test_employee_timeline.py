import statistics
import time
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import Assignment, Employee, Leave, Project
from frontend.presenters.employees import build_employee_timeline
from frontend.roles import VIEWER_GROUP, sync_role_permissions
from frontend.selectors.employees import get_employee_profile


class EmployeeTimelineTests(TestCase):
    AS_OF = date(2026, 9, 8)
    START = date(2026, 9, 4)
    END = date(2026, 9, 7)
    EXPECTED_QUERY_COUNT = 10
    SELECTOR_QUERY_COUNT = 4
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(username="timeline-viewer")
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.unassigned = get_user_model().objects.create_user(
            username="timeline-unassigned"
        )

        cls.employee = cls._employee("Avery", "Morgan")
        cls.empty_employee = cls._employee("Casey", "Stone")
        cls.inactive_employee = cls._employee(
            "Riley",
            "Ng",
            status=Employee.Status.INACTIVE,
        )
        cls.zero_capacity_employee = cls._employee(
            "Taylor",
            "Brooks",
            capacity=Decimal("0.00"),
        )

        alpha = cls._project("Alpha")
        legacy = cls._project("Legacy")
        beta = cls._project("Beta")
        cancelled = cls._project("Cancelled context")
        cls._assignment(
            cls.employee,
            alpha,
            cls.START,
            cls.END,
            50,
            Assignment.Status.ACTIVE,
        )
        cls._assignment(
            cls.employee,
            legacy,
            cls.START,
            cls.START,
            20,
            Assignment.Status.COMPLETED,
        )
        cls._assignment(
            cls.employee,
            beta,
            cls.END,
            cls.END,
            60,
            Assignment.Status.PLANNED,
        )
        cls._assignment(
            cls.employee,
            cancelled,
            cls.START,
            cls.END,
            30,
            Assignment.Status.CANCELLED,
        )
        cls._assignment(
            cls.inactive_employee,
            alpha,
            cls.START,
            cls.END,
            50,
            Assignment.Status.ACTIVE,
        )

        Leave.objects.create(
            employee=cls.employee,
            start_date=cls.START,
            end_date=cls.START,
            type=Leave.Type.SICK,
            status=Leave.Status.PENDING,
        )
        Leave.objects.create(
            employee=cls.employee,
            start_date=cls.END,
            end_date=cls.END,
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )
        Leave.objects.create(
            employee=cls.employee,
            start_date=date(2026, 9, 6),
            end_date=date(2026, 9, 6),
            type=Leave.Type.OTHER,
            status=Leave.Status.REJECTED,
        )

    @classmethod
    def _employee(
        cls,
        first_name,
        last_name,
        *,
        status=Employee.Status.ACTIVE,
        capacity=Decimal("40.00"),
    ):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Delivery",
            position="Consultant",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("5.0"),
            capacity_hours_week=capacity,
            status=status,
        )

    @classmethod
    def _project(cls, name):
        return Project.objects.create(
            name=name,
            description=f"{name} planning context.",
            start_date=cls.START,
            end_date=cls.END,
            estimated_hours=Decimal("80.00"),
            status=Project.Status.IN_PROGRESS,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )

    @classmethod
    def _assignment(cls, employee, project, start, end, allocation, status):
        return Assignment.objects.create(
            employee=employee,
            project=project,
            start_date=start,
            end_date=end,
            allocation_percentage=allocation,
            role_on_project="Contributor",
            status=status,
        )

    def setUp(self):
        self.client.force_login(self.viewer)
        self.url = reverse(
            "frontend:employee_detail",
            args=[self.employee.employee_id],
        )
        self.period_query = "start_date=2026-09-04&end_date=2026-09-07"

    def _get(self, employee=None, query=None):
        employee = employee or self.employee
        url = reverse("frontend:employee_detail", args=[employee.employee_id])
        return self.client.get(f"{url}?{query or self.period_query}")

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_daily_timeline_uses_inclusive_boundaries_and_core_semantics(
        self,
        _localdate,
    ):
        response = self._get()
        rows = {row["date"]: row for row in response.context["timeline"]["rows"]}

        self.assertEqual(tuple(rows), (
            date(2026, 9, 4),
            date(2026, 9, 5),
            date(2026, 9, 6),
            date(2026, 9, 7),
        ))
        friday = rows[self.START]
        self.assertEqual(friday["capacity_hours"], Decimal("8.00"))
        self.assertEqual(friday["workload_percentage"], 70)
        self.assertEqual(friday["allocated_hours"], Decimal("5.60"))
        self.assertEqual(friday["available_hours"], Decimal("2.40"))
        self.assertEqual(
            [assignment.project.name for assignment in friday["assignments"]],
            ["Legacy", "Alpha"],
        )
        self.assertEqual(friday["approved_leaves"], ())

        saturday = rows[date(2026, 9, 5)]
        self.assertEqual(saturday["state_label"], "Weekend")
        self.assertEqual(saturday["capacity_hours"], Decimal("0.00"))
        self.assertEqual(saturday["allocated_hours"], Decimal("0.00"))
        self.assertEqual(saturday["available_hours"], Decimal("0.00"))

        monday = rows[self.END]
        self.assertEqual(monday["workload_percentage"], 110)
        self.assertEqual(monday["allocated_hours"], Decimal("8.80"))
        self.assertEqual(monday["available_hours"], Decimal("0.00"))
        self.assertEqual(monday["state_label"], "Approved leave")
        self.assertEqual(monday["approved_leaves"][0].type, Leave.Type.ANNUAL)

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_non_approved_leave_and_cancelled_assignment_do_not_change_values(
        self,
        _localdate,
    ):
        response = self._get()
        friday = response.context["timeline"]["rows"][0]

        self.assertEqual(friday["workload_percentage"], 70)
        self.assertEqual(friday["available_hours"], Decimal("2.40"))
        self.assertNotContains(response, "Cancelled context")
        self.assertNotContains(response, "Sick leave")
        self.assertContains(
            response,
            "only dated approved leave reduces effective availability.",
        )

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_inactive_employee_keeps_schedule_evidence_but_has_no_availability(
        self,
        _localdate,
    ):
        response = self._get(self.inactive_employee)
        friday = response.context["timeline"]["rows"][0]

        self.assertEqual(friday["workload_percentage"], 50)
        self.assertEqual(friday["allocated_hours"], Decimal("4.00"))
        self.assertEqual(friday["available_hours"], Decimal("0.00"))
        self.assertEqual(friday["state_label"], "Inactive employee")

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_empty_and_partial_period_states_remain_explainable(self, _localdate):
        empty_response = self._get(self.empty_employee)
        self.assertContains(
            empty_response,
            "No assignments overlap this reporting period.",
        )
        self.assertContains(
            empty_response,
            "No approved leave overlaps this reporting period.",
        )

        capacity_response = self._get(self.zero_capacity_employee)
        self.assertContains(
            capacity_response,
            "Stored weekly capacity is not available.",
        )
        self.assertEqual(
            capacity_response.context["timeline"]["rows"][0]["state_label"],
            "No stored capacity",
        )

        weekend_response = self._get(
            self.empty_employee,
            "start_date=2026-09-05&end_date=2026-09-06",
        )
        self.assertContains(weekend_response, "This period contains weekends only.")
        self.assertEqual(weekend_response.context["timeline"]["working_day_count"], 0)

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_shared_period_defaults_validation_and_dashboard_continuity(
        self,
        _localdate,
    ):
        default_response = self.client.get(self.url)
        self.assertEqual(
            default_response.context["period_context"]["start_date"],
            date(2026, 9, 1),
        )
        self.assertEqual(
            default_response.context["period_context"]["end_date"],
            date(2026, 9, 30),
        )

        response = self._get()
        self.assertContains(response, "Sep 4, 2026 to Sep 7, 2026")
        self.assertEqual(
            response.context["dashboard_url"],
            "/?start_date=2026-09-04&end_date=2026-09-07"
            "&department=&employee_status=&project_status=",
        )

        invalid_response = self._get(
            query="start_date=2026-09-08&end_date=2026-09-07"
        )
        self.assertIsNone(invalid_response.context["timeline"])
        self.assertContains(
            invalid_response,
            "The end date must be on or after the start date.",
        )
        self.assertContains(invalid_response, "The reporting period needs attention")

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_timeline_has_accessible_table_and_supplemental_visual(self, _localdate):
        response = self._get()

        self.assertContains(
            response,
            "<caption>Daily workload and effective availability evidence for the selected reporting period</caption>",
            html=True,
        )
        self.assertContains(response, '<th scope="row"', count=4)
        self.assertContains(response, 'aria-hidden="true"')
        self.assertContains(
            response,
            'aria-label="Employee timeline reporting period"',
        )
        for heading in (
            "Daily capacity",
            "Scheduled workload",
            "Effective availability",
            "Assignment context",
            "Approved leave context",
        ):
            self.assertContains(response, heading)

    def test_timeline_presenter_delegates_every_workforce_value_to_services(self):
        employee = get_employee_profile(
            self.employee.employee_id,
            on_date=self.AS_OF,
            timeline_start_date=self.START,
            timeline_end_date=self.START,
        )
        with (
            patch(
                "frontend.presenters.employees.get_working_days",
                return_value=[self.START],
            ) as working_days,
            patch(
                "frontend.presenters.employees.get_current_assignments",
                return_value=[],
            ) as assignments,
            patch(
                "frontend.presenters.employees.get_approved_leaves",
                return_value=[],
            ) as approved_leaves,
            patch(
                "frontend.presenters.employees.calculate_daily_capacity_hours",
                return_value=Decimal("8.00"),
            ) as capacity,
            patch(
                "frontend.presenters.employees.calculate_current_workload",
                return_value=37,
            ) as workload,
            patch(
                "frontend.presenters.employees.calculate_daily_allocated_hours",
                return_value=Decimal("2.96"),
            ) as allocated,
            patch(
                "frontend.presenters.employees.calculate_daily_available_hours",
                return_value=Decimal("5.04"),
            ) as available,
        ):
            timeline = build_employee_timeline(
                employee,
                start_date=self.START,
                end_date=self.START,
            )

        self.assertEqual(timeline["rows"][0]["available_hours"], Decimal("5.04"))
        for service in (
            working_days,
            assignments,
            approved_leaves,
            capacity,
            workload,
            allocated,
            available,
        ):
            service.assert_called_once()
        self.assertIs(
            workload.call_args.kwargs["assignment_records"],
            employee.profile_timeline_assignments,
        )
        self.assertIs(
            available.call_args.kwargs["leave_records"],
            employee.profile_timeline_leaves,
        )

    def test_selector_loads_timeline_context_in_four_queries(self):
        with self.assertNumQueries(self.SELECTOR_QUERY_COUNT):
            employee = get_employee_profile(
                self.employee.employee_id,
                on_date=self.AS_OF,
                timeline_start_date=self.START,
                timeline_end_date=self.END,
            )
            assignment_names = [
                assignment.project.name
                for assignment in employee.profile_timeline_assignments
            ]
            leave_statuses = [
                leave.status for leave in employee.profile_timeline_leaves
            ]
            list(employee.profile_skills)

        self.assertEqual(
            assignment_names,
            ["Legacy", "Alpha", "Cancelled context", "Beta"],
        )
        self.assertEqual(
            leave_statuses,
            [Leave.Status.PENDING, Leave.Status.REJECTED, Leave.Status.APPROVED],
        )

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_permissions_missing_employee_and_read_only_request(self, _localdate):
        anonymous_response = Client().get(f"{self.url}?{self.period_query}")
        self.assertRedirects(
            anonymous_response,
            f"{reverse('frontend:login')}?next={self.url}%3F{self.period_query.replace('&', '%26')}",
            fetch_redirect_response=False,
        )
        unassigned_client = Client()
        unassigned_client.force_login(self.unassigned)
        self.assertEqual(
            unassigned_client.get(f"{self.url}?{self.period_query}").status_code,
            403,
        )
        missing_url = reverse("frontend:employee_detail", args=[999999])
        self.assertEqual(
            self.client.get(f"{missing_url}?{self.period_query}").status_code,
            404,
        )
        self.assertEqual(Assignment.objects.count(), 5)
        self.assertEqual(Leave.objects.count(), 3)

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_period_timeline_meets_fixed_query_budget_and_warm_timing(
        self,
        _localdate,
    ):
        with self.assertNumQueries(self.EXPECTED_QUERY_COUNT):
            response = self._get()
        self.assertEqual(response.status_code, 200)

        durations_ms = []
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as captured_queries:
                started_at = time.perf_counter()
                response = self._get()
                durations_ms.append((time.perf_counter() - started_at) * 1000)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(captured_queries), self.EXPECTED_QUERY_COUNT)

        p95_ms = statistics.quantiles(durations_ms, n=20, method="inclusive")[18]
        print(
            "\nM4.4 employee timeline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            "4 calendar days, 4 assignment records, 3 leave records):\n"
            f"  queries={self.EXPECTED_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )
