from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from core.models import Employee, Project
from frontend.permissions import (
    read_model_permission_required,
    write_model_permission_required,
)
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    MANAGER_PLANNER_GROUP,
    ROLE_PERMISSION_MAP,
    VIEWER_GROUP,
    sync_role_permissions,
)


@read_model_permission_required(Employee)
def employee_read_probe(request):
    return HttpResponse("Read allowed")


@write_model_permission_required(Project, action="change")
def project_write_probe(request):
    return HttpResponse("Write allowed")


@write_model_permission_required(Employee, action="delete")
def employee_delete_probe(request):
    return HttpResponse("Delete allowed")


class RolePermissionMappingTests(TestCase):
    def test_sync_creates_groups_with_the_exact_declared_permissions(self):
        output = StringIO()

        call_command("sync_frontend_roles", stdout=output)

        self.assertIn("Synchronized 3 frontend roles.", output.getvalue())

        for group_name, expected_permissions in ROLE_PERMISSION_MAP.items():
            with self.subTest(group=group_name):
                group = Group.objects.get(name=group_name)
                actual_permissions = {
                    f"{app_label}.{codename}"
                    for app_label, codename in group.permissions.values_list(
                        "content_type__app_label",
                        "codename",
                    )
                }
                self.assertEqual(actual_permissions, expected_permissions)


class PermissionGuardTests(TestCase):
    def setUp(self):
        sync_role_permissions()
        self.request_factory = RequestFactory()

    def _user_in_group(self, username, group_name):
        user = get_user_model().objects.create_user(username=username)
        user.groups.add(Group.objects.get(name=group_name))
        return user

    def test_anonymous_read_is_redirected_to_login(self):
        request = self.request_factory.get("/permission-probe/")
        request.user = AnonymousUser()

        response = employee_read_probe(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            "/login/?next=/permission-probe/",
        )

    def test_authenticated_user_without_permission_is_forbidden(self):
        request = self.request_factory.get("/permission-probe/")
        request.user = get_user_model().objects.create_user(username="unassigned")

        with self.assertRaises(PermissionDenied):
            employee_read_probe(request)

    def test_viewer_can_read_but_cannot_write(self):
        viewer = self._user_in_group("viewer", VIEWER_GROUP)

        read_request = self.request_factory.get("/permission-probe/")
        read_request.user = viewer
        self.assertEqual(employee_read_probe(read_request).status_code, 200)

        write_request = self.request_factory.post("/permission-probe/")
        write_request.user = viewer
        with self.assertRaises(PermissionDenied):
            project_write_probe(write_request)

    def test_manager_planner_can_change_planning_records(self):
        manager = self._user_in_group("manager", MANAGER_PLANNER_GROUP)
        request = self.request_factory.post("/permission-probe/")
        request.user = manager

        self.assertEqual(project_write_probe(request).status_code, 200)

    def test_hr_administrator_can_delete_hr_records(self):
        administrator = self._user_in_group("hr-admin", HR_ADMINISTRATOR_GROUP)
        request = self.request_factory.post("/permission-probe/")
        request.user = administrator

        self.assertEqual(employee_delete_probe(request).status_code, 200)
