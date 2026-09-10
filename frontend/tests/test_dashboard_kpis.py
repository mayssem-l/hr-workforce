import statistics
import time
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import Assignment, Employee, Leave, Project
from core.services.availability import has_approved_leave
from core.services.effective_availability import calculate_daily_available_hours
from core.services.workload import (
    calculate_current_workload,
    calculate_daily_allocated_hours,
)
from frontend.presenters.dashboard import build_dashboard_kpi_summary
from frontend.roles import VIEWER_GROUP, sync_role_permissions
from frontend.selectors.dashboard import DashboardSnapshot, get_dashboard_snapshot


class DashboardKpiTests(TestCase):
    START_DATE = date(2026, 9, 7)
    END_DATE = date(2026, 9, 11)
    EXPECTED_PAGE_QUERY_COUNT = 9
    EXPECTED_SELECTOR_QUERY_COUNT = 4
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(username="kpi-viewer")
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))

        cls.alex = cls.create_employee(
            "Alex",
            "Morgan",
            status=Employee.Status.ACTIVE,
            capacity="40.00",
        )
        cls.blair = cls.create_employee(
            "Blair",
            "Rivera",
            department="Finance",
            status=Employee.Status.INACTIVE,
            capacity="30.00",
        )
        cls.casey = cls.create_employee(
            "Casey",
            "Brooks",
            status=Employee.Status.ON_LEAVE,
            capacity="20.00",
        )

        cls.in_progress_project = cls.create_project(
            "Project Atlas",
            cls.START_DATE,
            cls.END_DATE,
            Project.Status.IN_PROGRESS,
        )
        cls.planned_project = cls.create_project(
            "Project Beacon",
            date(2026, 9, 9),
            cls.END_DATE,
            Project.Status.PLANNED,
        )
        cls.completed_project = cls.create_project(
            "Project Cedar",
            date(2026, 9, 1),
            date(2026, 9, 30),
            Project.Status.COMPLETED,
        )
        cls.create_project(
            "Project Delta",
            date(2026, 10, 1),
            date(2026, 10, 9),
            Project.Status.IN_PROGRESS,
        )

        Assignment.objects.bulk_create(
            [
                cls.assignment(
                    cls.alex,
                    cls.in_progress_project,
                    cls.START_DATE,
                    cls.END_DATE,
                    50,
                ),
                cls.assignment(
                    cls.alex,
                    cls.planned_project,
                    date(2026, 9, 9),
                    cls.END_DATE,
                    60,
                ),
                cls.assignment(
                    cls.blair,
                    cls.in_progress_project,
                    cls.START_DATE,
                    cls.END_DATE,
                    40,
                ),
                cls.assignment(
                    cls.alex,
                    cls.completed_project,
                    cls.START_DATE,
                    cls.END_DATE,
                    100,
                    status=Assignment.Status.CANCELLED,
                ),
            ]
        )
        Leave.objects.create(
            employee=cls.alex,
            start_date=date(2026, 9, 8),
            end_date=date(2026, 9, 8),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )
        Leave.objects.create(
            employee=cls.blair,
            start_date=cls.START_DATE,
            end_date=cls.END_DATE,
            type=Leave.Type.SICK,
            status=Leave.Status.PENDING,
        )

    @classmethod
    def create_employee(
        cls,
        first_name,
        last_name,
        *,
        department="Engineering",
        status,
        capacity,
    ):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department=department,
            position="Workforce Specialist",
            hire_date=date(2022, 1, 3),
            experience_years=Decimal("4.0"),
            capacity_hours_week=Decimal(capacity),
            status=status,
        )

    @classmethod
    def create_project(cls, name, start_date, end_date, status):
        return Project.objects.create(
            name=name,
            description=f"Planning context for {name}.",
            start_date=start_date,
            end_date=end_date,
            estimated_hours=Decimal("120.00"),
            status=status,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )

    @classmethod
    def assignment(
        cls,
        employee,
        project,
        start_date,
        end_date,
        allocation,
        *,
        status=Assignment.Status.ACTIVE,
    ):
        return Assignment(
            employee=employee,
            project=project,
            start_date=start_date,
            end_date=end_date,
            allocation_percentage=allocation,
            role_on_project="Contributor",
            status=status,
        )

    def setUp(self):
        self.url = reverse("frontend:landing")
        self.client.force_login(self.viewer)

    def filter_data(self, **overrides):
        data = {
            "start_date": self.START_DATE.isoformat(),
            "end_date": self.END_DATE.isoformat(),
            "department": "",
            "employee_status": "",
            "project_status": "",
        }
        data.update(overrides)
        return data

    def test_six_kpis_use_inclusive_period_and_distinct_service_meanings(self):
        response = self.client.get(self.url, self.filter_data())

        self.assertEqual(response.status_code, 200)
        summary = response.context["kpi_summary"]
        self.assertEqual(summary["headcount"]["total"], 3)
        self.assertEqual(
            {item["value"]: item["count"] for item in summary["headcount"]["by_status"]},
            {
                Employee.Status.ACTIVE: 1,
                Employee.Status.INACTIVE: 1,
                Employee.Status.ON_LEAVE: 1,
            },
        )
        self.assertEqual(summary["available_hours"], Decimal("24.00"))
        self.assertEqual(summary["allocated_hours"], Decimal("46.40"))
        self.assertEqual(summary["approved_leave_employee_count"], 1)
        self.assertEqual(summary["active_project_count"], 3)
        self.assertEqual(summary["over_capacity_employee_count"], 1)
        self.assertEqual(summary["working_day_count"], 5)

        for heading in (
            "Headcount",
            "Effective available capacity",
            "Scheduled allocation",
            "Employees with approved leave",
            "Projects active in period",
            "Over-capacity risk",
        ):
            self.assertContains(response, heading)
        self.assertContains(response, "24.00 h")
        self.assertContains(response, "46.40 h")
        self.assertContains(response, "Monday to Friday")
        self.assertNotContains(response, "<canvas")

        Leave.objects.create(
            employee=self.alex,
            start_date=date(2026, 9, 8),
            end_date=date(2026, 9, 9),
            type=Leave.Type.SICK,
            status=Leave.Status.APPROVED,
        )
        overlapping_leave_response = self.client.get(self.url, self.filter_data())
        overlapping_leave_summary = overlapping_leave_response.context["kpi_summary"]
        self.assertEqual(
            overlapping_leave_summary["approved_leave_employee_count"],
            1,
        )
        self.assertEqual(
            overlapping_leave_summary["available_hours"],
            Decimal("24.00"),
        )

    def test_workforce_and_project_filters_scope_their_respective_signals(self):
        response = self.client.get(
            self.url,
            self.filter_data(
                department="Engineering",
                employee_status=Employee.Status.ACTIVE,
                project_status=Project.Status.IN_PROGRESS,
            ),
        )

        summary = response.context["kpi_summary"]
        self.assertEqual(summary["headcount"]["total"], 1)
        self.assertEqual(summary["available_hours"], Decimal("4.00"))
        self.assertEqual(summary["allocated_hours"], Decimal("34.40"))
        self.assertEqual(summary["approved_leave_employee_count"], 1)
        self.assertEqual(summary["active_project_count"], 1)
        self.assertEqual(summary["over_capacity_employee_count"], 1)
        self.assertContains(response, "In progress")

    def test_each_project_status_filter_is_applied_after_date_overlap(self):
        expected_counts = {
            Project.Status.PLANNED: 1,
            Project.Status.IN_PROGRESS: 1,
            Project.Status.ON_HOLD: 0,
            Project.Status.COMPLETED: 1,
            Project.Status.CANCELLED: 0,
        }

        for status, expected_count in expected_counts.items():
            with self.subTest(status=status):
                response = self.client.get(
                    self.url,
                    self.filter_data(project_status=status),
                )
                self.assertEqual(
                    response.context["kpi_summary"]["active_project_count"],
                    expected_count,
                )

    def test_period_boundaries_overlap_assignments_leave_and_projects(self):
        response = self.client.get(
            self.url,
            self.filter_data(
                start_date=self.END_DATE.isoformat(),
                end_date=self.END_DATE.isoformat(),
                employee_status=Employee.Status.ACTIVE,
            ),
        )

        summary = response.context["kpi_summary"]
        self.assertEqual(summary["working_day_count"], 1)
        self.assertEqual(summary["allocated_hours"], Decimal("8.80"))
        self.assertEqual(summary["active_project_count"], 3)
        self.assertEqual(summary["over_capacity_employee_count"], 1)

        leave_boundary = Leave.objects.create(
            employee=self.alex,
            start_date=self.END_DATE,
            end_date=date(2026, 9, 14),
            type=Leave.Type.OTHER,
            status=Leave.Status.APPROVED,
        )
        boundary_response = self.client.get(
            self.url,
            self.filter_data(
                start_date=self.END_DATE.isoformat(),
                end_date=self.END_DATE.isoformat(),
                employee_status=Employee.Status.ACTIVE,
            ),
        )
        self.assertEqual(
            boundary_response.context["kpi_summary"]["approved_leave_employee_count"],
            1,
        )
        leave_boundary.delete()

    def test_weekend_period_keeps_dated_leave_separate_from_working_capacity(self):
        weekend_start = date(2026, 9, 12)
        weekend_end = date(2026, 9, 13)
        self.create_project(
            "Weekend project",
            weekend_start,
            weekend_end,
            Project.Status.PLANNED,
        )
        Leave.objects.create(
            employee=self.alex,
            start_date=weekend_start,
            end_date=weekend_end,
            type=Leave.Type.OTHER,
            status=Leave.Status.APPROVED,
        )

        response = self.client.get(
            self.url,
            self.filter_data(
                start_date=weekend_start.isoformat(),
                end_date=weekend_end.isoformat(),
            ),
        )

        summary = response.context["kpi_summary"]
        self.assertEqual(summary["working_day_count"], 0)
        self.assertEqual(summary["available_hours"], Decimal("0.00"))
        self.assertEqual(summary["allocated_hours"], Decimal("0.00"))
        self.assertEqual(summary["over_capacity_employee_count"], 0)
        self.assertEqual(summary["approved_leave_employee_count"], 1)
        self.assertEqual(summary["active_project_count"], 2)
        self.assertContains(response, "no Monday-to-Friday working days")

    def test_empty_workforce_and_empty_projects_render_clear_zero_state(self):
        Employee.objects.all().delete()
        Project.objects.all().delete()

        response = self.client.get(self.url, self.filter_data())

        summary = response.context["kpi_summary"]
        self.assertEqual(summary["headcount"]["total"], 0)
        self.assertEqual(summary["available_hours"], Decimal("0.00"))
        self.assertEqual(summary["allocated_hours"], Decimal("0.00"))
        self.assertEqual(summary["approved_leave_employee_count"], 0)
        self.assertEqual(summary["active_project_count"], 0)
        self.assertEqual(summary["over_capacity_employee_count"], 0)
        self.assertContains(response, "No employees match the workforce filters.")

    def test_presenter_delegates_each_calculated_value_to_core_services(self):
        employee = self.alex
        employee.dashboard_assignments = [object()]
        employee.dashboard_approved_leaves = [object()]
        snapshot = DashboardSnapshot(employees=(employee,), active_project_count=2)
        filters = {
            "start_date": self.START_DATE,
            "end_date": self.END_DATE,
            "department": "",
            "employee_status": "",
            "project_status": "",
        }

        with (
            patch(
                "frontend.presenters.dashboard.get_working_days",
                return_value=[self.START_DATE],
            ),
            patch(
                "frontend.presenters.dashboard.has_approved_leave",
                return_value=True,
            ) as approved_leave,
            patch(
                "frontend.presenters.dashboard.calculate_daily_available_hours",
                return_value=Decimal("3.25"),
            ) as available_hours,
            patch(
                "frontend.presenters.dashboard.calculate_daily_allocated_hours",
                return_value=Decimal("4.75"),
            ) as allocated_hours,
            patch(
                "frontend.presenters.dashboard.calculate_current_workload",
                return_value=Decimal("101"),
            ) as workload,
        ):
            summary = build_dashboard_kpi_summary(snapshot=snapshot, filters=filters)

        self.assertEqual(summary["available_hours"], Decimal("3.25"))
        self.assertEqual(summary["allocated_hours"], Decimal("4.75"))
        self.assertEqual(summary["approved_leave_employee_count"], 1)
        self.assertEqual(summary["over_capacity_employee_count"], 1)
        approved_leave.assert_called_once_with(
            employee,
            self.START_DATE,
            self.END_DATE,
            leave_records=employee.dashboard_approved_leaves,
        )
        available_hours.assert_called_once_with(
            employee,
            self.START_DATE,
            assignment_records=employee.dashboard_assignments,
            leave_records=employee.dashboard_approved_leaves,
        )
        allocated_hours.assert_called_once_with(
            employee,
            self.START_DATE,
            assignment_records=employee.dashboard_assignments,
        )
        workload.assert_called_once_with(
            employee,
            self.START_DATE,
            assignment_records=employee.dashboard_assignments,
        )

    def test_prefetched_service_inputs_match_legacy_queries_without_new_queries(self):
        filters = {
            "start_date": self.START_DATE,
            "end_date": self.END_DATE,
            "department": "Engineering",
            "employee_status": Employee.Status.ACTIVE,
            "project_status": "",
        }
        legacy_workload = calculate_current_workload(self.alex, date(2026, 9, 9))
        legacy_available = calculate_daily_available_hours(
            self.alex,
            date(2026, 9, 7),
        )
        legacy_allocated = calculate_daily_allocated_hours(
            self.alex,
            date(2026, 9, 9),
        )
        legacy_leave = has_approved_leave(
            self.alex,
            self.START_DATE,
            self.END_DATE,
        )

        with self.assertNumQueries(self.EXPECTED_SELECTOR_QUERY_COUNT):
            snapshot = get_dashboard_snapshot(filters=filters)

        employee = snapshot.employees[0]
        with self.assertNumQueries(0):
            prefetched_workload = calculate_current_workload(
                employee,
                date(2026, 9, 9),
                assignment_records=employee.dashboard_assignments,
            )
            prefetched_available = calculate_daily_available_hours(
                employee,
                date(2026, 9, 7),
                assignment_records=employee.dashboard_assignments,
                leave_records=employee.dashboard_approved_leaves,
            )
            prefetched_allocated = calculate_daily_allocated_hours(
                employee,
                date(2026, 9, 9),
                assignment_records=employee.dashboard_assignments,
            )
            prefetched_leave = has_approved_leave(
                employee,
                self.START_DATE,
                self.END_DATE,
                leave_records=employee.dashboard_approved_leaves,
            )
            prefetched_summary = build_dashboard_kpi_summary(
                snapshot=snapshot,
                filters=filters,
            )

        self.assertEqual(prefetched_workload, legacy_workload)
        self.assertEqual(prefetched_available, legacy_available)
        self.assertEqual(prefetched_allocated, legacy_allocated)
        self.assertEqual(prefetched_leave, legacy_leave)
        self.assertEqual(prefetched_summary["headcount"]["total"], 1)

    def test_populated_dashboard_query_count_is_fixed_as_related_rows_grow(self):
        with self.assertNumQueries(self.EXPECTED_PAGE_QUERY_COUNT):
            response = self.client.get(self.url, self.filter_data())
        self.assertEqual(response.status_code, 200)

        for index in range(5):
            project = self.create_project(
                f"Additional project {index}",
                self.START_DATE,
                self.END_DATE,
                Project.Status.PLANNED,
            )
            Assignment.objects.create(
                employee=self.casey,
                project=project,
                start_date=self.START_DATE,
                end_date=self.END_DATE,
                allocation_percentage=10,
                role_on_project="Advisor",
                status=Assignment.Status.CANCELLED,
            )

        with self.assertNumQueries(self.EXPECTED_PAGE_QUERY_COUNT):
            grown_response = self.client.get(self.url, self.filter_data())
        self.assertEqual(grown_response.status_code, 200)

    def test_warm_dashboard_timing_is_recorded(self):
        warmup_response = self.client.get(self.url, self.filter_data())
        self.assertEqual(warmup_response.status_code, 200)

        durations_ms = []
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as captured_queries:
                started_at = time.perf_counter()
                response = self.client.get(self.url, self.filter_data())
                durations_ms.append((time.perf_counter() - started_at) * 1000)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(captured_queries), self.EXPECTED_PAGE_QUERY_COUNT)

        p95_ms = statistics.quantiles(
            durations_ms,
            n=20,
            method="inclusive",
        )[18]
        print(
            "\nM4.2 KPI dashboard baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            "3 employees, 5 working days):\n"
            f"  queries={self.EXPECTED_PAGE_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )
