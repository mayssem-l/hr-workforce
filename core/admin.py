from django.contrib import admin

from .models import (
    Assignment,
    Attendance,
    Employee,
    EmployeeSkill,
    Leave,
    Project,
    ProjectSkillRequirement,
    Skill,
    AssignmentSkill,

)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "employee_id",
        "first_name",
        "last_name",
        "department",
        "position",
        "hire_date",
        "capacity_hours_week",
        "status",
    )
    list_filter = ("status", "department")
    search_fields = ("first_name", "last_name", "department", "position")


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("skill_id", "name", "category")
    list_filter = ("category",)
    search_fields = ("name", "category")


@admin.register(EmployeeSkill)
class EmployeeSkillAdmin(admin.ModelAdmin):
    list_display = (
        "employee_skill_id",
        "employee",
        "skill",
        "level",
        "years_experience",
    )
    list_filter = ("level", "skill")
    search_fields = (
        "employee__first_name",
        "employee__last_name",
        "skill__name",
    )


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "project_id",
        "name",
        "start_date",
        "end_date",
        "estimated_hours",
        "status",
        "priority",
        "criticality",
    )
    list_filter = ("status", "priority", "criticality")
    search_fields = ("name", "description")


@admin.register(ProjectSkillRequirement)
class ProjectSkillRequirementAdmin(admin.ModelAdmin):
    list_display = (
        "project_skill_requirement_id",
        "project",
        "skill",
        "required_level",
        "priority",
        "is_mandatory",
        "required_quantity",
        "estimated_effort_hours",
    )
    list_filter = ("is_mandatory", "priority", "required_level")
    search_fields = ("project__name", "skill__name")


@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = (
        "leave_id",
        "employee",
        "start_date",
        "end_date",
        "type",
        "status",
    )
    list_filter = ("type", "status")
    search_fields = ("employee__first_name", "employee__last_name")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = (
        "attendance_id",
        "employee",
        "date",
        "status",
        "arrival_time",
        "departure_time",
    )
    list_filter = ("status",)
    search_fields = ("employee__first_name", "employee__last_name")


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "assignment_id",
        "employee",
        "project",
        "start_date",
        "end_date",
        "allocation_percentage",
        "role_on_project",
        "status",
    )
    list_filter = ("status",)
    search_fields = (
        "employee__first_name",
        "employee__last_name",
        "project__name",
        "role_on_project",
    )
@admin.register(AssignmentSkill)
class AssignmentSkillAdmin(admin.ModelAdmin):
    list_display = (
        "assignment_skill_id",
        "assignment",
        "project_skill_requirement",
    )

    list_filter = (
        "project_skill_requirement__skill",
        "project_skill_requirement__project",
    )

    search_fields = (
        "assignment__employee__first_name",
        "assignment__employee__last_name",
        "assignment__project__name",
        "project_skill_requirement__skill__name",
    )
