from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase
from django.urls import resolve, reverse

from core.models import (
    Assignment,
    Attendance,
    Employee,
    EmployeeSkill,
    Leave,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from core.services.attendance import (
    calculate_absenteeism_rate,
    calculate_late_rate,
    get_attendance_summary,
)
from core.services.availability import get_working_days, has_approved_leave
from core.services.effective_availability import (
    calculate_daily_available_hours,
    calculate_daily_capacity_hours,
)
from core.services.matching import calculate_employee_project_match
from core.services.optimization import build_optimization_context
from core.services.recommendation_preflight import get_recommendation_preflight
from core.services.workload import (
    calculate_current_workload,
    calculate_daily_allocated_hours,
)
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)


class Milestone4VerificationTests(TestCase):
    START_DATE = date(2026, 9, 7)
    END_DATE = date(2026, 9, 8)

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = cls._role_user("m4-final-viewer", VIEWER_GROUP)
        cls.manager = cls._role_user("m4-final-manager", MANAGER_PLANNER_GROUP)
        cls.hr_user = cls._role_user("m4-final-hr", HR_ADMINISTRATOR_GROUP)
        cls.unassigned = get_user_model().objects.create_user(
            username="m4-final-unassigned"
        )
        cls.dashboard_only = cls._permission_user(
            "m4-final-dashboard-only",
            "view_employee",
            "view_project",
        )
        cls.employee_only = cls._permission_user(
            "m4-final-employee-only",
            "view_employee",
        )
        cls.project_only = cls._permission_user(
            "m4-final-project-only",
            "view_project",
        )

        cls.alex = cls._employee("Alex", "Morgan", Decimal("40.00"))
        cls.casey = cls._employee("Casey", "Brooks", Decimal("20.00"))
        cls.inactive = cls._employee(
            "Blair",
            "Rivera",
            Decimal("40.00"),
            department="Finance",
            status=Employee.Status.INACTIVE,
        )

        cls.skill = Skill.objects.create(name="Planning analysis", category="Planning")
        EmployeeSkill.objects.create(
            employee=cls.alex,
            skill=cls.skill,
            level=5,
            years_experience=Decimal("5.0"),
        )
        EmployeeSkill.objects.create(
            employee=cls.casey,
            skill=cls.skill,
            level=4,
            years_experience=Decimal("3.0"),
        )

        cls.primary_project = cls._project("Project Atlas")
        cls.secondary_project = cls._project("Project Beacon")
        cls.outside_project = cls._project(
            "Project Outside",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 31),
            status=Project.Status.PLANNED,
        )
        ProjectSkillRequirement.objects.create(
            project=cls.primary_project,
            skill=cls.skill,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=Decimal("16.00"),
        )

        cls.alex_primary = Assignment.objects.create(
            employee=cls.alex,
            project=cls.primary_project,
            start_date=cls.START_DATE,
            end_date=cls.END_DATE,
            allocation_percentage=80,
            role_on_project="Lead",
            status=Assignment.Status.ACTIVE,
        )
        cls.alex_secondary = Assignment.objects.create(
            employee=cls.alex,
            project=cls.secondary_project,
            start_date=cls.START_DATE,
            end_date=cls.END_DATE,
            allocation_percentage=40,
            role_on_project="Reviewer",
            status=Assignment.Status.PLANNED,
        )
        cls.casey_assignment = Assignment.objects.create(
            employee=cls.casey,
            project=cls.primary_project,
            start_date=cls.START_DATE,
            end_date=cls.END_DATE,
            allocation_percentage=50,
            role_on_project="Analyst",
            status=Assignment.Status.ACTIVE,
        )

        cls.approved_leave = Leave.objects.create(
            employee=cls.alex,
            start_date=cls.END_DATE,
            end_date=cls.END_DATE,
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )
        Leave.objects.create(
            employee=cls.casey,
            start_date=cls.START_DATE,
            end_date=cls.START_DATE,
            type=Leave.Type.SICK,
            status=Leave.Status.PENDING,
        )
        cls.late_attendance = Attendance.objects.create(
            employee=cls.alex,
            date=cls.START_DATE,
            status=Attendance.Status.LATE,
        )
        cls.absent_attendance = Attendance.objects.create(
            employee=cls.alex,
            date=cls.END_DATE,
            status=Attendance.Status.ABSENT,
        )

    @staticmethod
    def _role_user(username, group_name):
        user = get_user_model().objects.create_user(username=username)
        user.groups.add(Group.objects.get(name=group_name))
        return user

    @staticmethod
    def _permission_user(username, *codenames):
        user = get_user_model().objects.create_user(username=username)
        user.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="core",
                codename__in=codenames,
            )
        )
        return user

    @classmethod
    def _employee(
        cls,
        first_name,
        last_name,
        capacity,
        *,
        department="Engineering",
        status=Employee.Status.ACTIVE,
    ):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department=department,
            position="Workforce analyst",
            hire_date=date(2021, 1, 4),
            experience_years=Decimal("5.0"),
            capacity_hours_week=capacity,
            status=status,
        )

    @classmethod
    def _project(
        cls,
        name,
        *,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        status=Project.Status.IN_PROGRESS,
    ):
        return Project.objects.create(
            name=name,
            description=f"Milestone 4 verification context for {name}.",
            start_date=start_date,
            end_date=end_date,
            estimated_hours=Decimal("16.00"),
            status=status,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )

    def setUp(self):
        self.client.force_login(self.viewer)

    def filters(self, **overrides):
        values = {
            "start_date": self.START_DATE.isoformat(),
            "end_date": self.END_DATE.isoformat(),
            "department": "Engineering",
            "employee_status": Employee.Status.ACTIVE,
            "project_status": Project.Status.IN_PROGRESS,
        }
        values.update(overrides)
        return values

    def profile_url(self, employee=None):
        employee = employee or self.alex
        query = "&".join(f"{key}={value}" for key, value in self.filters().items())
        return (
            reverse("frontend:employee_detail", args=[employee.employee_id])
            + f"?{query}"
        )

    def test_route_template_navigation_authentication_and_role_inventory(self):
        route_specs = (
            (
                "landing",
                (),
                "/",
                "frontend/dashboard/landing.html",
                'class="app-nav__item is-active"',
            ),
            (
                "employee_list",
                (),
                "/employees/",
                "frontend/employees/list.html",
                'class="app-nav__item is-active"',
            ),
            (
                "employee_detail",
                (self.alex.employee_id,),
                f"/employees/{self.alex.employee_id}/",
                "frontend/employees/detail.html",
                'class="app-nav__item is-active"',
            ),
            (
                "leave_list",
                (),
                "/leave/",
                "frontend/leaves/list.html",
                'class="app-nav__item is-active"',
            ),
            (
                "attendance_list",
                (),
                "/attendance/",
                "frontend/attendance/list.html",
                'class="app-nav__item is-active"',
            ),
        )

        for name, args, expected_path, template, active_area in route_specs:
            url = reverse(f"frontend:{name}", args=args)
            with self.subTest(route=name, check="route-template-navigation"):
                self.assertEqual(url, expected_path)
                self.assertEqual(resolve(url).view_name, f"frontend:{name}")
                response = self.client.get(url, self.filters())
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template)
                rendered = response.content.decode("utf-8")
                active_position = rendered.index(active_area)
                self.assertIn(
                    'aria-current="page"',
                    rendered[active_position : active_position + 500],
                )

            anonymous = Client().get(url)
            with self.subTest(route=name, role="anonymous"):
                self.assertEqual(anonymous.status_code, 302)
                self.assertTrue(anonymous.url.startswith(reverse("frontend:login")))

            for user in (self.viewer, self.manager, self.hr_user):
                role_client = Client()
                role_client.force_login(user)
                with self.subTest(route=name, role=user.username):
                    self.assertEqual(role_client.get(url, self.filters()).status_code, 200)

        self.assertEqual(
            Client().get(reverse("frontend:landing")).status_code,
            302,
        )
        for user in (self.unassigned, self.employee_only, self.project_only):
            client = Client()
            client.force_login(user)
            self.assertEqual(client.get(reverse("frontend:landing")).status_code, 403)

        dashboard_client = Client()
        dashboard_client.force_login(self.dashboard_only)
        self.assertEqual(dashboard_client.get(reverse("frontend:landing")).status_code, 200)
        self.assertEqual(
            dashboard_client.get(
                reverse("frontend:employee_detail", args=[self.alex.employee_id])
            ).status_code,
            200,
        )
        self.assertEqual(dashboard_client.get(reverse("frontend:leave_list")).status_code, 403)
        self.assertEqual(
            dashboard_client.get(reverse("frontend:attendance_list")).status_code,
            403,
        )

    def test_dashboard_values_and_evidence_reconcile_to_models_and_core_services(self):
        response = self.client.get(reverse("frontend:landing"), self.filters())
        self.assertEqual(response.status_code, 200)
        summary = response.context["kpi_summary"]
        distributions = response.context["distribution_context"]
        evidence = response.context["evidence_context"]
        employees = (self.alex, self.casey)
        working_days = get_working_days(self.START_DATE, self.END_DATE)

        expected_available = sum(
            (
                calculate_daily_available_hours(employee, working_day)
                for employee in employees
                for working_day in working_days
            ),
            Decimal("0.00"),
        )
        expected_allocated = sum(
            (
                calculate_daily_allocated_hours(employee, working_day)
                for employee in employees
                for working_day in working_days
            ),
            Decimal("0.00"),
        )
        expected_leave_employees = sum(
            has_approved_leave(employee, self.START_DATE, self.END_DATE)
            for employee in employees
        )
        expected_over_capacity = sum(
            any(
                calculate_current_workload(employee, working_day) > 100
                for working_day in working_days
            )
            for employee in employees
        )
        expected_projects = Project.objects.filter(
            start_date__lte=self.END_DATE,
            end_date__gte=self.START_DATE,
            status=Project.Status.IN_PROGRESS,
        ).count()

        self.assertEqual(summary["headcount"]["total"], len(employees))
        self.assertEqual(summary["available_hours"], expected_available)
        self.assertEqual(summary["allocated_hours"], expected_allocated)
        self.assertEqual(
            summary["approved_leave_employee_count"],
            expected_leave_employees,
        )
        self.assertEqual(summary["active_project_count"], expected_projects)
        self.assertEqual(
            summary["over_capacity_employee_count"],
            expected_over_capacity,
        )
        self.assertEqual(summary["working_day_count"], len(working_days))

        self.assertEqual(distributions["state"], "ready")
        self.assertEqual(distributions["total_employee_count"], len(employees))
        for distribution_name in ("availability", "utilization"):
            bands = distributions[distribution_name]["bands"]
            self.assertEqual(sum(band["count"] for band in bands), len(employees))
            self.assertTrue(all(band["evidence_url"] for band in bands if band["count"]))

        self.assertEqual(
            sum(row["available_hours"] for row in evidence["employee_rows"]),
            summary["available_hours"],
        )
        self.assertEqual(
            sum(row["allocated_hours"] for row in evidence["employee_rows"]),
            summary["allocated_hours"],
        )
        self.assertEqual(len(evidence["leave_rows"]), expected_leave_employees)
        self.assertEqual(len(evidence["project_rows"]), expected_projects)

        headcount_response = self.client.get(evidence["headcount"]["evidence_url"])
        self.assertEqual(
            headcount_response.context["page_obj"].paginator.count,
            summary["headcount"]["total"],
        )
        leave_response = self.client.get(evidence["leave_rows"][0]["records_url"])
        self.assertEqual(leave_response.context["page_obj"].paginator.count, 1)
        self.assertEqual(
            leave_response.context["page_obj"][0].leave_id,
            self.approved_leave.leave_id,
        )
        for anchor in (
            evidence["available_capacity_url"],
            evidence["allocated_capacity_url"],
            evidence["approved_leave_url"],
            evidence["project_url"],
            evidence["over_capacity_url"],
        ):
            self.assertTrue(anchor.startswith("#"))
            self.assertContains(response, f'id="{anchor[1:]}"')

    def test_employee_timeline_attendance_and_visual_evidence_match_services(self):
        response = self.client.get(self.profile_url())
        self.assertEqual(response.status_code, 200)
        timeline = response.context["timeline"]
        attendance = response.context["attendance_insight"]

        self.assertEqual(len(timeline["rows"]), 2)
        for row in timeline["rows"]:
            self.assertEqual(
                row["capacity_hours"],
                calculate_daily_capacity_hours(self.alex, row["date"]),
            )
            self.assertEqual(
                row["workload_percentage"],
                calculate_current_workload(self.alex, row["date"]),
            )
            self.assertEqual(
                row["allocated_hours"],
                calculate_daily_allocated_hours(self.alex, row["date"]),
            )
            self.assertEqual(
                row["available_hours"],
                calculate_daily_available_hours(self.alex, row["date"]),
            )

        expected_summary = get_attendance_summary(
            self.alex,
            self.START_DATE,
            self.END_DATE,
        )
        self.assertEqual(attendance["summary"], expected_summary)
        self.assertEqual(
            attendance["absenteeism_rate"],
            calculate_absenteeism_rate(self.alex, self.START_DATE, self.END_DATE),
        )
        self.assertEqual(
            attendance["late_rate"],
            calculate_late_rate(self.alex, self.START_DATE, self.END_DATE),
        )

        for template in (
            "frontend/employees/detail.html",
            "frontend/employees/_timeline_row.html",
            "frontend/employees/_attendance_status_row.html",
            "frontend/employees/_attendance_record_row.html",
            "frontend/components/table.html",
        ):
            self.assertTemplateUsed(response, template)

        rendered = response.content.decode("utf-8")
        self.assertIn(
            'class="employee-timeline-strip" aria-hidden="true"',
            rendered,
        )
        self.assertLess(
            rendered.index("Attendance status counts and record shares"),
            rendered.index('class="distribution-visual" aria-hidden="true"'),
        )
        self.assertIn(
            'class="attendance-timeline-strip" aria-hidden="true"',
            rendered,
        )
        self.assertContains(
            response,
            "Attendance does not affect staffing recommendations.",
        )

        attendance_query = parse_qs(
            attendance["total_query_string"],
            keep_blank_values=True,
        )
        self.assertEqual(attendance_query["employee"], [str(self.alex.employee_id)])
        attendance_response = self.client.get(
            f"{reverse('frontend:attendance_list')}?{attendance['total_query_string']}"
        )
        self.assertEqual(attendance_response.context["page_obj"].paginator.count, 2)

    def test_boundary_and_empty_states_remain_distinct_and_truthful(self):
        same_day = self.client.get(
            reverse("frontend:landing"),
            self.filters(start_date=self.END_DATE.isoformat()),
        )
        self.assertEqual(same_day.status_code, 200)
        self.assertEqual(same_day.context["kpi_summary"]["working_day_count"], 1)
        self.assertEqual(
            same_day.context["kpi_summary"]["approved_leave_employee_count"],
            1,
        )
        self.assertEqual(same_day.context["kpi_summary"]["active_project_count"], 2)

        weekend = self.client.get(
            reverse("frontend:landing"),
            self.filters(start_date="2026-09-12", end_date="2026-09-13"),
        )
        self.assertEqual(weekend.context["distribution_context"]["state"], "no_working_days")
        self.assertContains(
            weekend,
            "This period contains no Monday-to-Friday working days.",
        )

        filtered_empty = self.client.get(
            reverse("frontend:landing"),
            self.filters(department="Finance", employee_status=Employee.Status.ACTIVE),
        )
        self.assertEqual(filtered_empty.context["kpi_summary"]["headcount"]["total"], 0)
        self.assertEqual(
            filtered_empty.context["distribution_context"]["state"],
            "no_employees",
        )
        self.assertContains(filtered_empty, "No employees match the workforce filters.")

        Employee.objects.all().delete()
        Project.objects.all().delete()
        empty = self.client.get(
            reverse("frontend:landing"),
            {
                "start_date": self.START_DATE.isoformat(),
                "end_date": self.END_DATE.isoformat(),
            },
        )
        self.assertEqual(empty.context["kpi_summary"]["headcount"]["total"], 0)
        self.assertEqual(empty.context["kpi_summary"]["active_project_count"], 0)
        self.assertContains(empty, "No employee evidence matches these filters")
        self.assertContains(empty, "No approved-leave employee evidence")
        self.assertContains(empty, "No project evidence matches this period")

    def test_attendance_is_descriptive_only_and_staffing_sources_remain_isolated(self):
        def recommendation_signature():
            match = calculate_employee_project_match(self.alex, self.primary_project)
            preflight = get_recommendation_preflight(self.primary_project)
            context = build_optimization_context(self.primary_project)
            return {
                "match": {key: value for key, value in match.items() if key != "employee"},
                "preflight": (
                    preflight["can_generate_recommendations"],
                    tuple(blocker["code"] for blocker in preflight["blockers"]),
                ),
                "optimization": {
                    "employees": tuple(
                        employee.employee_id for employee in context["employees"]
                    ),
                    "requirements": tuple(
                        requirement.project_skill_requirement_id
                        for requirement in context["requirements"]
                    ),
                    "available_hours": context["available_hours"],
                    "eligible_by_requirement": context["eligible_by_requirement"],
                    "total_required_effort": context["total_required_effort"],
                },
            }

        before = recommendation_signature()
        Attendance.objects.create(
            employee=self.alex,
            date=date(2026, 9, 9),
            status=Attendance.Status.ABSENT,
        )
        after = recommendation_signature()
        self.assertEqual(before, after)

        repository_root = Path(__file__).resolve().parents[2]
        staffing_sources = (
            repository_root / "core/services/matching.py",
            repository_root / "core/services/matching_v1.py",
            repository_root / "core/services/optimization.py",
            repository_root / "core/services/recommendation_preflight.py",
            repository_root / "core/services/llm_explanations.py",
        )
        for source_path in staffing_sources:
            with self.subTest(source=source_path.name):
                source = source_path.read_text(encoding="utf-8").lower()
                self.assertNotIn("attendance", source)

        frontend_root = repository_root / "frontend"
        display_only_roots = (
            frontend_root / "views",
            frontend_root / "selectors",
            frontend_root / "templates",
            frontend_root / "static/frontend/js",
        )
        core_calculation_names = (
            "calculate_current_workload",
            "calculate_daily_allocated_hours",
            "calculate_daily_available_hours",
            "calculate_daily_capacity_hours",
            "calculate_absenteeism_rate",
            "calculate_late_rate",
            "get_attendance_summary",
            "get_working_days",
            "has_approved_leave",
        )
        for source_root in display_only_roots:
            for pattern in ("*.py", "*.html", "*.js"):
                for source_path in source_root.rglob(pattern):
                    source = source_path.read_text(encoding="utf-8")
                    with self.subTest(source=str(source_path)):
                        self.assertFalse(
                            any(f"{name}(" in source for name in core_calculation_names)
                        )
