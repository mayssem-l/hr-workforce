from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, Attendance, Employee, Leave, Project
from frontend.roles import VIEWER_GROUP, sync_role_permissions


class DashboardEvidenceTests(TestCase):
    START_DATE = date(2026, 9, 7)
    END_DATE = date(2026, 9, 8)

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="evidence-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.dashboard_only = get_user_model().objects.create_user(
            username="evidence-dashboard-only"
        )
        cls.dashboard_only.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename="view_employee",
            ),
            Permission.objects.get(
                content_type__app_label="core",
                codename="view_project",
            ),
        )

        cls.alex = cls.create_employee(
            "Alex",
            "Morgan",
            department="Research & Design",
            status=Employee.Status.ACTIVE,
        )
        cls.casey = cls.create_employee(
            "Casey",
            "Brooks",
            department="Research & Design",
            status=Employee.Status.ACTIVE,
        )
        cls.blair = cls.create_employee(
            "Blair",
            "Rivera",
            department="Finance",
            status=Employee.Status.INACTIVE,
        )

        cls.overlapping_project = cls.create_project(
            "Project Atlas",
            date(2026, 9, 1),
            cls.END_DATE,
            Project.Status.IN_PROGRESS,
        )
        cls.create_project(
            "Project Outside",
            date(2026, 10, 1),
            date(2026, 10, 9),
            Project.Status.IN_PROGRESS,
        )
        Assignment.objects.create(
            employee=cls.alex,
            project=cls.overlapping_project,
            start_date=cls.START_DATE,
            end_date=cls.END_DATE,
            allocation_percentage=80,
            role_on_project="Lead",
            status=Assignment.Status.ACTIVE,
        )
        Assignment.objects.create(
            employee=cls.alex,
            project=cls.overlapping_project,
            start_date=cls.START_DATE,
            end_date=cls.END_DATE,
            allocation_percentage=40,
            role_on_project="Reviewer",
            status=Assignment.Status.ACTIVE,
        )
        cls.first_leave = Leave.objects.create(
            employee=cls.alex,
            start_date=cls.START_DATE,
            end_date=cls.START_DATE,
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )
        cls.second_leave = Leave.objects.create(
            employee=cls.alex,
            start_date=cls.END_DATE,
            end_date=cls.END_DATE,
            type=Leave.Type.SICK,
            status=Leave.Status.APPROVED,
        )
        Attendance.objects.create(
            employee=cls.alex,
            date=cls.START_DATE,
            status=Attendance.Status.LATE,
        )

    @classmethod
    def create_employee(cls, first_name, last_name, *, department, status):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department=department,
            position="Workforce Specialist",
            hire_date=date(2022, 1, 3),
            experience_years=Decimal("4.0"),
            capacity_hours_week=Decimal("40.00"),
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

    def setUp(self):
        self.url = reverse("frontend:landing")
        self.client.force_login(self.viewer)

    def filter_data(self, **overrides):
        data = {
            "start_date": self.START_DATE.isoformat(),
            "end_date": self.END_DATE.isoformat(),
            "department": "Research & Design",
            "employee_status": Employee.Status.ACTIVE,
            "project_status": Project.Status.IN_PROGRESS,
        }
        data.update(overrides)
        return data

    @staticmethod
    def query_values(url):
        return parse_qs(urlsplit(url).query, keep_blank_values=True)

    def get_dashboard(self, **overrides):
        return self.client.get(self.url, self.filter_data(**overrides))

    def test_every_aggregate_maps_to_exact_consistent_evidence(self):
        response = self.get_dashboard()

        self.assertEqual(response.status_code, 200)
        summary = response.context["kpi_summary"]
        distributions = response.context["distribution_context"]
        evidence = response.context["evidence_context"]

        self.assertEqual(summary["headcount"]["total"], 2)
        self.assertEqual(summary["available_hours"], Decimal("16.00"))
        self.assertEqual(summary["allocated_hours"], Decimal("19.20"))
        self.assertEqual(summary["approved_leave_employee_count"], 1)
        self.assertEqual(summary["active_project_count"], 1)
        self.assertEqual(summary["over_capacity_employee_count"], 1)

        self.assertEqual(len(evidence["employee_rows"]), 2)
        self.assertEqual(
            sum(row["available_hours"] for row in evidence["employee_rows"]),
            summary["available_hours"],
        )
        self.assertEqual(
            sum(row["allocated_hours"] for row in evidence["employee_rows"]),
            summary["allocated_hours"],
        )
        self.assertEqual(
            sum(bool(row["over_capacity_dates"]) for row in evidence["employee_rows"]),
            summary["over_capacity_employee_count"],
        )
        self.assertEqual(len(evidence["leave_rows"]), 1)
        self.assertEqual(len(evidence["leave_rows"][0]["leaves"]), 2)
        self.assertEqual(len(evidence["project_rows"]), 1)

        self.assertEqual(
            evidence["available_capacity_url"],
            "#employee-capacity-evidence",
        )
        self.assertEqual(
            evidence["allocated_capacity_url"],
            "#employee-capacity-evidence",
        )
        self.assertEqual(
            evidence["over_capacity_url"],
            "#employee-capacity-evidence",
        )
        self.assertEqual(
            evidence["approved_leave_url"],
            "#approved-leave-evidence",
        )
        self.assertEqual(evidence["project_url"], "#project-period-evidence")
        for distribution_name in ("availability", "utilization"):
            for band in distributions[distribution_name]["bands"]:
                expected = "#employee-capacity-evidence" if band["count"] else ""
                self.assertEqual(band["evidence_url"], expected)

    def test_headcount_link_uses_the_exact_directory_contract_and_result(self):
        response = self.get_dashboard()
        evidence = response.context["evidence_context"]
        headcount_url = evidence["headcount"]["evidence_url"]

        self.assertIn("Research+%26+Design", headcount_url)
        self.assertEqual(
            self.query_values(headcount_url),
            {
                "start_date": ["2026-09-07"],
                "end_date": ["2026-09-08"],
                "department": ["Research & Design"],
                "status": ["active"],
                "project_status": ["in_progress"],
                "sort": ["name"],
            },
        )
        directory_response = self.client.get(headcount_url)
        self.assertEqual(directory_response.status_code, 200)
        self.assertEqual(
            directory_response.context["page_obj"].paginator.count,
            response.context["kpi_summary"]["headcount"]["total"],
        )
        self.assertContains(
            directory_response,
            "Dashboard reporting context preserved.",
        )

    def test_employee_profile_preserves_full_dashboard_context_and_return_paths(self):
        dashboard_response = self.get_dashboard()
        employee_row = next(
            row
            for row in dashboard_response.context["evidence_context"]["employee_rows"]
            if row["employee"].employee_id == self.alex.employee_id
        )
        self.assertEqual(
            self.query_values(employee_row["profile_url"]),
            {
                "start_date": ["2026-09-07"],
                "end_date": ["2026-09-08"],
                "department": ["Research & Design"],
                "employee_status": ["active"],
                "project_status": ["in_progress"],
            },
        )

        profile_response = self.client.get(employee_row["profile_url"])
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(
            self.query_values(profile_response.context["dashboard_url"]),
            self.query_values(employee_row["profile_url"]),
        )
        workforce_values = self.query_values(profile_response.context["workforce_url"])
        self.assertEqual(workforce_values["department"], ["Research & Design"])
        self.assertEqual(workforce_values["status"], ["active"])
        self.assertEqual(workforce_values["project_status"], ["in_progress"])
        self.assertContains(profile_response, "Return to filtered workforce")
        self.assertContains(profile_response, "Return to dashboard")

        timeline = profile_response.context["timeline"]
        self.assertEqual(len(timeline["rows"]), 2)
        self.assertTrue(all(row["assignments"] for row in timeline["rows"]))
        self.assertTrue(
            all(row["workload_percentage"] == 120 for row in timeline["rows"])
        )

    def test_leave_aggregate_uses_distinct_on_page_evidence_and_exact_record_link(self):
        response = self.get_dashboard()
        leave_row = response.context["evidence_context"]["leave_rows"][0]

        self.assertEqual(
            self.query_values(leave_row["records_url"]),
            {
                "employee": [str(self.alex.employee_id)],
                "status": ["approved"],
                "from_date": ["2026-09-07"],
                "to_date": ["2026-09-08"],
                "sort": ["start_date_asc"],
            },
        )
        self.assertContains(response, "keeps multiple leave records from inflating")
        records_response = self.client.get(leave_row["records_url"])
        self.assertEqual(records_response.status_code, 200)
        self.assertEqual(records_response.context["page_obj"].paginator.count, 2)
        self.assertContains(records_response, "Reporting period preserved.")
        self.assertContains(records_response, "Return to employee profile")

    def test_project_aggregate_uses_overlap_evidence_not_directory_date_filters(self):
        response = self.get_dashboard()
        projects = response.context["evidence_context"]["project_rows"]

        self.assertEqual(
            [row["project"].project_id for row in projects],
            [self.overlapping_project.project_id],
        )
        self.assertContains(response, "Project Atlas")
        self.assertNotContains(response, "Project Outside")
        self.assertContains(
            response,
            "the project directory's start-after and end-before filters "
            "describe a different question",
        )

    def test_profile_to_attendance_uses_supported_filters_and_returns(self):
        dashboard_response = self.get_dashboard()
        profile_url = next(
            row["profile_url"]
            for row in dashboard_response.context["evidence_context"][
                "employee_rows"
            ]
            if row["employee"].employee_id == self.alex.employee_id
        )
        profile_response = self.client.get(profile_url)
        attendance_query = profile_response.context["attendance_insight"][
            "total_query_string"
        ]

        self.assertEqual(
            parse_qs(attendance_query, keep_blank_values=True),
            {
                "employee": [str(self.alex.employee_id)],
                "status": [""],
                "from_date": ["2026-09-07"],
                "to_date": ["2026-09-08"],
                "sort": ["date_asc"],
            },
        )
        attendance_response = self.client.get(
            f"{reverse('frontend:attendance_list')}?{attendance_query}"
        )
        self.assertEqual(attendance_response.context["page_obj"].paginator.count, 1)
        self.assertContains(attendance_response, "Return to employee profile")
        self.assertEqual(
            self.query_values(
                attendance_response.context["navigation_context"][
                    "employee_profile_url"
                ]
            ),
            {
                "start_date": ["2026-09-07"],
                "end_date": ["2026-09-08"],
            },
        )

    def test_stale_optional_filters_are_removed_before_evidence_urls_are_built(self):
        response = self.get_dashboard(
            department="Former & Team",
            employee_status="legacy-status",
            project_status="retired-project-status",
        )

        self.assertEqual(response.status_code, 200)
        evidence = response.context["evidence_context"]
        headcount_values = self.query_values(evidence["headcount"]["evidence_url"])
        self.assertEqual(headcount_values["department"], [""])
        self.assertEqual(headcount_values["status"], [""])
        self.assertEqual(headcount_values["project_status"], [""])
        for stale_value in (
            "Former",
            "legacy-status",
            "retired-project-status",
        ):
            self.assertNotIn(stale_value, evidence["headcount"]["evidence_url"])
            self.assertNotIn(stale_value, evidence["employee_rows"][0]["profile_url"])

    def test_zero_result_destinations_remain_clear_and_followable(self):
        response = self.get_dashboard(
            department="Finance",
            employee_status=Employee.Status.ACTIVE,
            project_status=Project.Status.CANCELLED,
        )

        summary = response.context["kpi_summary"]
        evidence = response.context["evidence_context"]
        self.assertEqual(summary["headcount"]["total"], 0)
        self.assertEqual(summary["active_project_count"], 0)
        self.assertFalse(evidence["employee_rows"])
        self.assertFalse(evidence["leave_rows"])
        self.assertFalse(evidence["project_rows"])
        self.assertContains(response, "No employee evidence matches these filters")
        self.assertContains(response, "No approved-leave employee evidence")
        self.assertContains(response, "No project evidence matches this period")

        directory_response = self.client.get(evidence["headcount"]["evidence_url"])
        self.assertEqual(directory_response.status_code, 200)
        self.assertEqual(directory_response.context["page_obj"].paginator.count, 0)
        self.assertContains(directory_response, "No employees match these filters")

    def test_leave_record_evidence_respects_the_existing_model_permission(self):
        self.client.force_login(self.dashboard_only)
        response = self.get_dashboard()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Leave evidence is restricted")
        self.assertNotContains(response, "View approved leave records")
        self.assertNotContains(response, "Annual leave")
        self.assertNotContains(response, "Sick leave")
