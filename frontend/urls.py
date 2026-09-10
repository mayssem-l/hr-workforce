from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from frontend.views.attendance import (
    attendance_create,
    attendance_delete,
    attendance_list,
    attendance_update,
)
from frontend.views.assignments import (
    project_assignment_create,
    project_assignment_update,
)
from frontend.views.coverage import (
    project_assignment_coverage,
    project_assignment_coverage_create,
    project_assignment_coverage_remove,
)
from frontend.views.deletions import (
    assignment_delete,
    employee_delete,
    project_delete,
    skill_delete,
)
from frontend.views.employees import (
    employee_create,
    employee_detail,
    employee_list,
    employee_update,
)
from frontend.views.landing import landing
from frontend.views.planning import project_planning
from frontend.views.recommendations import project_recommendation_generate
from frontend.views.leaves import (
    leave_create,
    leave_delete,
    leave_list,
    leave_update,
)
from frontend.views.proficiencies import (
    employee_skill_create,
    employee_skill_remove,
    employee_skill_update,
)
from frontend.views.projects import (
    project_create,
    project_detail,
    project_list,
    project_update,
)
from frontend.views.requirements import (
    project_requirement_create,
    project_requirement_remove,
    project_requirement_update,
)
from frontend.views.skills import (
    skill_create,
    skill_detail,
    skill_list,
    skill_update,
)


app_name = "frontend"

urlpatterns = [
    path(
        "login/",
        LoginView.as_view(
            template_name="frontend/auth/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("projects/", project_list, name="project_list"),
    path("projects/new/", project_create, name="project_create"),
    path(
        "projects/<int:project_id>/edit/",
        project_update,
        name="project_update",
    ),
    path(
        "projects/<int:project_id>/delete/",
        project_delete,
        name="project_delete",
    ),
    path(
        "projects/<int:project_id>/requirements/add/",
        project_requirement_create,
        name="project_requirement_create",
    ),
    path(
        "projects/<int:project_id>/requirements/<int:requirement_id>/edit/",
        project_requirement_update,
        name="project_requirement_update",
    ),
    path(
        "projects/<int:project_id>/requirements/<int:requirement_id>/remove/",
        project_requirement_remove,
        name="project_requirement_remove",
    ),
    path(
        "projects/<int:project_id>/assignments/add/",
        project_assignment_create,
        name="project_assignment_create",
    ),
    path(
        "projects/<int:project_id>/assignments/<int:assignment_id>/edit/",
        project_assignment_update,
        name="project_assignment_update",
    ),
    path(
        "projects/<int:project_id>/assignments/<int:assignment_id>/delete/",
        assignment_delete,
        name="project_assignment_delete",
    ),
    path(
        "projects/<int:project_id>/assignments/<int:assignment_id>/coverage/",
        project_assignment_coverage,
        name="project_assignment_coverage",
    ),
    path(
        "projects/<int:project_id>/assignments/<int:assignment_id>/coverage/add/",
        project_assignment_coverage_create,
        name="project_assignment_coverage_create",
    ),
    path(
        "projects/<int:project_id>/assignments/<int:assignment_id>/coverage/"
        "<int:coverage_id>/remove/",
        project_assignment_coverage_remove,
        name="project_assignment_coverage_remove",
    ),
    path(
        "projects/<int:project_id>/planning/",
        project_planning,
        name="project_planning",
    ),
    path(
        "projects/<int:project_id>/recommendations/generate/",
        project_recommendation_generate,
        name="project_recommendation_generate",
    ),
    path("projects/<int:project_id>/", project_detail, name="project_detail"),
    path("employees/", employee_list, name="employee_list"),
    path("employees/new/", employee_create, name="employee_create"),
    path(
        "employees/<int:employee_id>/edit/",
        employee_update,
        name="employee_update",
    ),
    path(
        "employees/<int:employee_id>/delete/",
        employee_delete,
        name="employee_delete",
    ),
    path(
        "employees/<int:employee_id>/skills/add/",
        employee_skill_create,
        name="employee_skill_create",
    ),
    path(
        "employees/<int:employee_id>/skills/<int:employee_skill_id>/edit/",
        employee_skill_update,
        name="employee_skill_update",
    ),
    path(
        "employees/<int:employee_id>/skills/<int:employee_skill_id>/remove/",
        employee_skill_remove,
        name="employee_skill_remove",
    ),
    path(
        "employees/<int:employee_id>/",
        employee_detail,
        name="employee_detail",
    ),
    path("skills/", skill_list, name="skill_list"),
    path("skills/new/", skill_create, name="skill_create"),
    path("skills/<int:skill_id>/edit/", skill_update, name="skill_update"),
    path("skills/<int:skill_id>/delete/", skill_delete, name="skill_delete"),
    path("skills/<int:skill_id>/", skill_detail, name="skill_detail"),
    path("leave/", leave_list, name="leave_list"),
    path("leave/new/", leave_create, name="leave_create"),
    path("leave/<int:leave_id>/edit/", leave_update, name="leave_update"),
    path("leave/<int:leave_id>/delete/", leave_delete, name="leave_delete"),
    path("attendance/", attendance_list, name="attendance_list"),
    path("attendance/new/", attendance_create, name="attendance_create"),
    path(
        "attendance/<int:attendance_id>/edit/",
        attendance_update,
        name="attendance_update",
    ),
    path(
        "attendance/<int:attendance_id>/delete/",
        attendance_delete,
        name="attendance_delete",
    ),
    path("", landing, name="landing"),
]
