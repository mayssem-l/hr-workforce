import re
from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import resolve, reverse

from core.models import (
    Assignment,
    AssignmentSkill,
    Attendance,
    Employee,
    EmployeeSkill,
    Leave,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)


class Milestone3RouteAndSecurityVerificationTests(TestCase):
    CONTENT_FORM_CSRF = re.compile(
        r'<form method="post" novalidate data-loading-form>\s*'
        r'<input type="hidden" name="csrfmiddlewaretoken" value="[^"]+">'
    )

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.hr_user = cls._role_user("m3-hr", HR_ADMINISTRATOR_GROUP)
        cls.manager = cls._role_user("m3-manager", MANAGER_PLANNER_GROUP)
        cls.viewer = cls._role_user("m3-viewer", VIEWER_GROUP)

        cls.employee = Employee.objects.create(
            first_name="Avery",
            last_name="Stone",
            department="Engineering",
            position="Engineer",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("6.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )
        cls.skill = Skill.objects.create(name="Python", category="Engineering")
        EmployeeSkill.objects.create(
            employee=cls.employee,
            skill=cls.skill,
            level=5,
            years_experience=Decimal("5.0"),
        )
        cls.project = Project.objects.create(
            name="M3 Verification",
            description="Verify the completed project management workflows.",
            start_date=date(2027, 1, 4),
            end_date=date(2027, 3, 31),
            estimated_hours=Decimal("160.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.MEDIUM,
        )
        cls.requirement = ProjectSkillRequirement.objects.create(
            project=cls.project,
            skill=cls.skill,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=Decimal("80.00"),
        )
        cls.assignment = Assignment.objects.create(
            employee=cls.employee,
            project=cls.project,
            start_date=date(2027, 1, 4),
            end_date=date(2027, 3, 31),
            allocation_percentage=50,
            role_on_project="Engineer",
            status=Assignment.Status.PLANNED,
        )
        cls.coverage = AssignmentSkill.objects.create(
            assignment=cls.assignment,
            project_skill_requirement=cls.requirement,
        )
        cls.leave = Leave.objects.create(
            employee=cls.employee,
            start_date=date(2027, 4, 5),
            end_date=date(2027, 4, 9),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.PENDING,
        )
        cls.attendance = Attendance.objects.create(
            employee=cls.employee,
            date=date(2026, 9, 8),
            status=Attendance.Status.PRESENT,
            arrival_time=time(8, 30),
            departure_time=time(17, 0),
        )

        project_id = cls.project.project_id
        requirement_id = cls.requirement.project_skill_requirement_id
        assignment_id = cls.assignment.assignment_id
        coverage_id = cls.coverage.assignment_skill_id
        cls.route_specs = (
            ("project_list", (), "/projects/", "frontend/projects/list.html", "project"),
            ("project_create", (), "/projects/new/", "frontend/projects/create.html", "project"),
            ("project_detail", (project_id,), f"/projects/{project_id}/", "frontend/projects/detail.html", "project"),
            ("project_update", (project_id,), f"/projects/{project_id}/edit/", "frontend/projects/edit.html", "project"),
            ("project_delete", (project_id,), f"/projects/{project_id}/delete/", "frontend/projects/confirm_delete.html", "project"),
            ("project_requirement_create", (project_id,), f"/projects/{project_id}/requirements/add/", "frontend/projects/requirements/create.html", "project"),
            ("project_requirement_update", (project_id, requirement_id), f"/projects/{project_id}/requirements/{requirement_id}/edit/", "frontend/projects/requirements/edit.html", "project"),
            ("project_requirement_remove", (project_id, requirement_id), f"/projects/{project_id}/requirements/{requirement_id}/remove/", "frontend/projects/requirements/confirm_remove.html", "project"),
            ("project_assignment_create", (project_id,), f"/projects/{project_id}/assignments/add/", "frontend/projects/assignments/create.html", "project"),
            ("project_assignment_update", (project_id, assignment_id), f"/projects/{project_id}/assignments/{assignment_id}/edit/", "frontend/projects/assignments/edit.html", "project"),
            ("project_assignment_delete", (project_id, assignment_id), f"/projects/{project_id}/assignments/{assignment_id}/delete/", "frontend/projects/assignments/confirm_delete.html", "project"),
            ("project_assignment_coverage", (project_id, assignment_id), f"/projects/{project_id}/assignments/{assignment_id}/coverage/", "frontend/projects/assignments/coverage/detail.html", "project"),
            ("project_assignment_coverage_create", (project_id, assignment_id), f"/projects/{project_id}/assignments/{assignment_id}/coverage/add/", "frontend/projects/assignments/coverage/create.html", "project"),
            ("project_assignment_coverage_remove", (project_id, assignment_id, coverage_id), f"/projects/{project_id}/assignments/{assignment_id}/coverage/{coverage_id}/remove/", "frontend/projects/assignments/coverage/confirm_remove.html", "project"),
            ("leave_list", (), "/leave/", "frontend/leaves/list.html", "workforce"),
            ("leave_create", (), "/leave/new/", "frontend/leaves/create.html", "workforce"),
            ("leave_update", (cls.leave.leave_id,), f"/leave/{cls.leave.leave_id}/edit/", "frontend/leaves/edit.html", "workforce"),
            ("leave_delete", (cls.leave.leave_id,), f"/leave/{cls.leave.leave_id}/delete/", "frontend/leaves/confirm_delete.html", "workforce"),
            ("attendance_list", (), "/attendance/", "frontend/attendance/list.html", "workforce"),
            ("attendance_create", (), "/attendance/new/", "frontend/attendance/create.html", "workforce"),
            ("attendance_update", (cls.attendance.attendance_id,), f"/attendance/{cls.attendance.attendance_id}/edit/", "frontend/attendance/edit.html", "workforce"),
            ("attendance_delete", (cls.attendance.attendance_id,), f"/attendance/{cls.attendance.attendance_id}/delete/", "frontend/attendance/confirm_delete.html", "workforce"),
        )

    @staticmethod
    def _role_user(username, group_name):
        user = get_user_model().objects.create_user(username=username)
        user.groups.add(Group.objects.get(name=group_name))
        return user

    @classmethod
    def _url(cls, name, args):
        return reverse(f"frontend:{name}", args=args)

    def test_every_milestone3_route_resolves_and_renders_its_template(self):
        self.client.force_login(self.hr_user)

        for name, args, expected_path, template_name, area in self.route_specs:
            url = self._url(name, args)
            with self.subTest(route=name):
                self.assertEqual(url, expected_path)
                self.assertEqual(resolve(url).view_name, f"frontend:{name}")
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template_name)
                navigation_path = "/projects/" if area == "project" else "/employees/"
                self.assertRegex(
                    response.content.decode("utf-8"),
                    rf'href="{re.escape(navigation_path)}"\s+aria-current="page"',
                )

    def test_anonymous_and_role_boundaries_cover_every_milestone3_route(self):
        anonymous_client = Client()
        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        manager_client = Client()
        manager_client.force_login(self.manager)

        read_routes = {
            "project_list",
            "project_detail",
            "project_assignment_coverage",
            "leave_list",
            "attendance_list",
        }
        manager_write_routes = {
            "project_create",
            "project_update",
            "project_requirement_create",
            "project_requirement_update",
            "project_assignment_create",
            "project_assignment_update",
            "project_assignment_coverage_create",
        }

        for name, args, _path, _template, _area in self.route_specs:
            url = self._url(name, args)
            with self.subTest(route=name, role="anonymous"):
                response = anonymous_client.get(url)
                self.assertRedirects(
                    response,
                    f"{reverse('frontend:login')}?next={url}",
                    fetch_redirect_response=False,
                )
            with self.subTest(route=name, role="viewer"):
                expected_status = 200 if name in read_routes else 403
                self.assertEqual(viewer_client.get(url).status_code, expected_status)
            with self.subTest(route=name, role="manager"):
                expected_status = 200 if name in read_routes | manager_write_routes else 403
                self.assertEqual(manager_client.get(url).status_code, expected_status)

    def test_every_milestone3_post_form_renders_a_csrf_token(self):
        self.client.force_login(self.hr_user)
        content_form_routes = {
            "project_create",
            "project_update",
            "project_requirement_create",
            "project_requirement_update",
            "project_assignment_create",
            "project_assignment_update",
            "project_assignment_coverage_create",
            "leave_create",
            "leave_update",
            "attendance_create",
            "attendance_update",
        }
        confirmation_routes = {
            "project_delete",
            "project_requirement_remove",
            "project_assignment_delete",
            "project_assignment_coverage_remove",
            "leave_delete",
            "attendance_delete",
        }

        for name, args, _path, _template, _area in self.route_specs:
            if name not in content_form_routes | confirmation_routes:
                continue
            url = self._url(name, args)
            response = self.client.get(url)
            rendered = response.content.decode("utf-8")
            with self.subTest(route=name):
                if name in content_form_routes:
                    self.assertRegex(rendered, self.CONTENT_FORM_CSRF)
                else:
                    confirmation_pattern = re.compile(
                        rf'<form method="post" action="{re.escape(url)}" '
                        r'data-loading-form>\s*'
                        r'<input type="hidden" name="csrfmiddlewaretoken" '
                        r'value="[^"]+">'
                    )
                    self.assertRegex(rendered, confirmation_pattern)
