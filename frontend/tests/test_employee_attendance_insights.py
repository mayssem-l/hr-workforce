import statistics
import time
from datetime import date, time as clock_time
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import parse_qs

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import (
    Attendance,
    Employee,
    EmployeeSkill,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from core.services.attendance import (
    calculate_absenteeism_rate,
    calculate_late_rate,
    get_attendance_records,
    get_attendance_summary,
)
from core.services.matching import calculate_employee_project_match
from frontend.presenters.employees import build_employee_attendance_insight
from frontend.roles import VIEWER_GROUP, sync_role_permissions
from frontend.selectors.employees import get_employee_profile


class EmployeeAttendanceInsightTests(TestCase):
    AS_OF = date(2026, 9, 8)
    START = date(2026, 9, 1)
    END = date(2026, 9, 5)
    EXPECTED_QUERY_COUNT = 10
    SELECTOR_QUERY_COUNT = 5
    TIMING_SAMPLE_COUNT = 25

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="attendance-insight-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))

        cls.employee_only_user = get_user_model().objects.create_user(
            username="employee-only-viewer"
        )
        cls.employee_only_user.user_permissions.add(
            Permission.objects.get(codename="view_employee")
        )
        cls.attendance_only_user = get_user_model().objects.create_user(
            username="attendance-only-viewer"
        )
        cls.attendance_only_user.user_permissions.add(
            Permission.objects.get(codename="view_attendance")
        )

        cls.employee = cls._employee("Jordan", "Blake")
        cls.empty_employee = cls._employee("Sam", "Parker")
        cls.all_absent_employee = cls._employee("Drew", "Quinn")

        cls.records = (
            Attendance.objects.create(
                employee=cls.employee,
                date=date(2026, 9, 1),
                status=Attendance.Status.PRESENT,
                arrival_time=clock_time(8, 30),
                departure_time=clock_time(17, 0),
            ),
            Attendance.objects.create(
                employee=cls.employee,
                date=date(2026, 9, 2),
                status=Attendance.Status.ABSENT,
            ),
            Attendance.objects.create(
                employee=cls.employee,
                date=date(2026, 9, 3),
                status=Attendance.Status.LATE,
                arrival_time=clock_time(9, 15),
            ),
            Attendance.objects.create(
                employee=cls.employee,
                date=date(2026, 9, 4),
                status=Attendance.Status.REMOTE,
            ),
            Attendance.objects.create(
                employee=cls.employee,
                date=date(2026, 9, 5),
                status=Attendance.Status.HALF_DAY,
                departure_time=clock_time(12, 30),
            ),
        )
        Attendance.objects.create(
            employee=cls.employee,
            date=date(2026, 8, 31),
            status=Attendance.Status.ABSENT,
        )
        Attendance.objects.create(
            employee=cls.employee,
            date=date(2026, 9, 6),
            status=Attendance.Status.LATE,
        )
        Attendance.objects.create(
            employee=cls.all_absent_employee,
            date=date(2026, 9, 1),
            status=Attendance.Status.ABSENT,
        )

    @classmethod
    def _employee(cls, first_name, last_name):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Operations",
            position="Coordinator",
            hire_date=date(2021, 2, 1),
            experience_years=Decimal("4.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )

    def setUp(self):
        self.client.force_login(self.viewer)
        self.url = reverse(
            "frontend:employee_detail",
            args=[self.employee.employee_id],
        )
        self.query = "start_date=2026-09-01&end_date=2026-09-05"

    def _get(self, employee=None, query=None, client=None):
        employee = employee or self.employee
        client = client or self.client
        url = reverse("frontend:employee_detail", args=[employee.employee_id])
        return client.get(f"{url}?{query or self.query}")

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_summary_uses_every_stored_status_and_existing_rate_definitions(
        self,
        _localdate,
    ):
        response = self._get()
        insight = response.context["attendance_insight"]

        self.assertEqual(insight["summary"], {
            "total_days": 5,
            "present_days": 1,
            "absent_days": 1,
            "late_days": 1,
            "remote_days": 1,
            "half_days": 1,
            "non_absent_days": 4,
        })
        self.assertEqual(insight["absenteeism_rate"], 20.0)
        self.assertEqual(insight["late_rate"], 25.0)
        self.assertContains(response, "1 absent record out of 5 total")
        self.assertContains(response, "1 late record out of 4 non-absent")
        for label in ("Present", "Absent", "Late", "Remote", "Half day"):
            self.assertContains(response, label)

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_date_boundaries_and_partial_period_use_record_denominators(
        self,
        _localdate,
    ):
        response = self._get(
            query="start_date=2026-09-02&end_date=2026-09-04"
        )
        insight = response.context["attendance_insight"]

        self.assertEqual(insight["summary"]["total_days"], 3)
        self.assertEqual(insight["absenteeism_rate"], 33.33)
        self.assertEqual(insight["late_rate"], 50.0)
        self.assertEqual(
            [record.date for record in insight["records"]],
            [date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4)],
        )
        self.assertContains(response, "Attendance coverage is record-based.")
        self.assertContains(response, "Dates without records are not treated as")

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_status_only_records_do_not_invent_times_or_observations(
        self,
        _localdate,
    ):
        attendance_count = Attendance.objects.count()
        response = self._get()

        self.assertContains(response, "Times not recorded")
        self.assertContains(response, "Departure not recorded")
        self.assertContains(response, "Arrival not recorded")
        self.assertContains(
            response,
            "Chronological evidence includes recorded dates only; it does not fill gaps or infer employee status.",
        )
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.ACTIVE)
        self.assertEqual(Attendance.objects.count(), attendance_count)

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_empty_and_zero_denominator_states_are_not_presented_as_rates(
        self,
        _localdate,
    ):
        empty_response = self._get(self.empty_employee)
        self.assertContains(
            empty_response,
            "No attendance records overlap this reporting period",
        )
        self.assertContains(empty_response, "No attendance records in the denominator")
        self.assertContains(
            empty_response,
            "No non-absent attendance records in the denominator",
        )
        self.assertContains(empty_response, "Not available", count=2)

        absent_response = self._get(self.all_absent_employee)
        insight = absent_response.context["attendance_insight"]
        self.assertEqual(insight["absenteeism_rate"], 100.0)
        self.assertFalse(insight["late_has_denominator"])
        self.assertContains(absent_response, "100.0%")
        self.assertContains(
            absent_response,
            "No non-absent attendance records in the denominator",
        )

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_status_table_and_supplemental_chart_use_identical_rows(
        self,
        _localdate,
    ):
        response = self._get()

        self.assertContains(
            response,
            "<caption>Attendance status counts and record shares for the selected reporting period</caption>",
            html=True,
        )
        self.assertContains(
            response,
            "<caption>Chronological recorded attendance evidence for the selected reporting period</caption>",
            html=True,
        )
        self.assertContains(response, 'class="distribution-visual" aria-hidden="true"')
        self.assertContains(response, 'class="attendance-timeline-strip" aria-hidden="true"')
        for status_row in response.context["attendance_insight"]["status_rows"]:
            self.assertContains(
                response,
                f'data-attendance-status="{status_row["status"]}"',
                count=2,
            )
            self.assertContains(
                response,
                f'data-count="{status_row["count"]}" data-share="{status_row["share_serialized"]}"',
            )
            self.assertContains(
                response,
                f'--distribution-share: {status_row["share_serialized"]}%;',
            )

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_summary_links_open_exact_filtered_attendance_evidence(self, _localdate):
        response = self._get()
        insight = response.context["attendance_insight"]
        absent_row = next(
            row
            for row in insight["status_rows"]
            if row["status"] == Attendance.Status.ABSENT
        )
        query = parse_qs(absent_row["evidence_query_string"])

        self.assertEqual(query, {
            "employee": [str(self.employee.employee_id)],
            "status": [Attendance.Status.ABSENT],
            "from_date": ["2026-09-01"],
            "to_date": ["2026-09-05"],
            "sort": ["date_asc"],
        })
        evidence_response = self.client.get(
            reverse("frontend:attendance_list"),
            query,
        )
        self.assertEqual(evidence_response.context["page_obj"].paginator.count, 1)
        self.assertEqual(
            evidence_response.context["page_obj"].object_list[0].attendance_id,
            self.records[1].attendance_id,
        )

    def test_presenter_delegates_summary_rates_and_records_to_core_services(self):
        employee = get_employee_profile(
            self.employee.employee_id,
            on_date=self.AS_OF,
            timeline_start_date=self.START,
            timeline_end_date=self.END,
            include_attendance=True,
        )
        summary_value = {
            "total_days": 1,
            "present_days": 1,
            "absent_days": 0,
            "late_days": 0,
            "remote_days": 0,
            "half_days": 0,
            "non_absent_days": 1,
        }
        with (
            patch(
                "frontend.presenters.employees.get_attendance_records",
                return_value=[employee.profile_attendance_records[0]],
            ) as records,
            patch(
                "frontend.presenters.employees.get_attendance_summary",
                return_value=summary_value,
            ) as summary,
            patch(
                "frontend.presenters.employees.calculate_absenteeism_rate",
                return_value=Decimal("0.00"),
            ) as absenteeism,
            patch(
                "frontend.presenters.employees.calculate_late_rate",
                return_value=Decimal("0.00"),
            ) as late,
        ):
            insight = build_employee_attendance_insight(
                employee,
                start_date=self.START,
                end_date=self.END,
            )

        self.assertEqual(insight["summary"], summary_value)
        for service in (records, summary, absenteeism, late):
            service.assert_called_once()
            self.assertIs(
                service.call_args.kwargs["attendance_records"],
                employee.profile_attendance_records,
            )

    def test_prefetched_attendance_service_paths_match_query_backed_results(self):
        legacy_summary = get_attendance_summary(self.employee, self.START, self.END)
        legacy_absenteeism = calculate_absenteeism_rate(
            self.employee,
            self.START,
            self.END,
        )
        legacy_late = calculate_late_rate(self.employee, self.START, self.END)
        records = list(get_attendance_records(self.employee, self.START, self.END))

        with self.assertNumQueries(0):
            prefetched_summary = get_attendance_summary(
                self.employee,
                self.START,
                self.END,
                attendance_records=records,
            )
            prefetched_absenteeism = calculate_absenteeism_rate(
                self.employee,
                self.START,
                self.END,
                attendance_records=records,
            )
            prefetched_late = calculate_late_rate(
                self.employee,
                self.START,
                self.END,
                attendance_records=records,
            )

        self.assertEqual(prefetched_summary, legacy_summary)
        self.assertEqual(prefetched_absenteeism, legacy_absenteeism)
        self.assertEqual(prefetched_late, legacy_late)

    def test_selector_loads_attendance_with_permission_flag_in_one_fixed_query(self):
        with self.assertNumQueries(self.SELECTOR_QUERY_COUNT):
            employee = get_employee_profile(
                self.employee.employee_id,
                on_date=self.AS_OF,
                timeline_start_date=self.START,
                timeline_end_date=self.END,
                include_attendance=True,
            )
            record_dates = [
                record.date for record in employee.profile_attendance_records
            ]
            list(employee.profile_skills)

        self.assertEqual(record_dates, [record.date for record in self.records])

        with self.assertNumQueries(self.SELECTOR_QUERY_COUNT - 1):
            restricted_employee = get_employee_profile(
                self.employee.employee_id,
                on_date=self.AS_OF,
                timeline_start_date=self.START,
                timeline_end_date=self.END,
                include_attendance=False,
            )
            self.assertEqual(restricted_employee.profile_attendance_records, [])

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_attendance_visibility_requires_its_own_read_permission(self, _localdate):
        employee_client = Client()
        employee_client.force_login(self.employee_only_user)
        employee_response = self._get(client=employee_client)
        self.assertEqual(employee_response.status_code, 200)
        self.assertIsNone(employee_response.context["attendance_insight"])
        self.assertNotContains(employee_response, "Attendance summary and recorded trend")
        self.assertNotContains(employee_response, "Recorded as absent")

        attendance_client = Client()
        attendance_client.force_login(self.attendance_only_user)
        self.assertEqual(self._get(client=attendance_client).status_code, 403)

    def test_attendance_records_do_not_change_recommendation_inputs(self):
        employee = self.empty_employee
        skill = Skill.objects.create(name="M4.5 isolation", category="Operations")
        EmployeeSkill.objects.create(
            employee=employee,
            skill=skill,
            level=4,
            years_experience=Decimal("4.0"),
        )
        project = Project.objects.create(
            name="Attendance isolation project",
            description="Recommendation input regression.",
            start_date=date(2026, 10, 5),
            end_date=date(2026, 10, 9),
            estimated_hours=Decimal("20.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )
        ProjectSkillRequirement.objects.create(
            project=project,
            skill=skill,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=Decimal("20.00"),
        )
        before = calculate_employee_project_match(employee, project)
        Attendance.objects.create(
            employee=employee,
            date=date(2026, 10, 5),
            status=Attendance.Status.ABSENT,
        )
        after = calculate_employee_project_match(employee, project)

        self.assertEqual(
            {key: value for key, value in before.items() if key != "employee"},
            {key: value for key, value in after.items() if key != "employee"},
        )

    @patch("frontend.views.employees.timezone.localdate", return_value=AS_OF)
    def test_populated_attendance_insight_has_fixed_queries_and_warm_timing(
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
            "\nM4.5 attendance insight "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            "5 period records across every attendance status):\n"
            f"  queries={self.EXPECTED_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )
