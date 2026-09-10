import hashlib
import json

from core.models import (
    Assignment,
    Employee,
    EmployeeSkill,
    Leave,
    Project,
    ProjectSkillRequirement,
)


def _serialized_signature(payload):
    serialized = json.dumps(
        payload,
        default=str,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def get_recommendation_input_snapshot(project_id):
    """Return a stable digest and current IDs for recommendation inputs."""

    project = Project.objects.values_list(
        "project_id",
        "name",
        "start_date",
        "end_date",
        "estimated_hours",
        "status",
        "priority",
        "criticality",
    ).get(project_id=project_id)
    start_date = project[2]
    end_date = project[3]

    requirements = tuple(
        ProjectSkillRequirement.objects.filter(project_id=project_id)
        .select_related("skill")
        .order_by("project_skill_requirement_id")
        .values_list(
            "project_skill_requirement_id",
            "project_id",
            "skill_id",
            "skill__name",
            "skill__category",
            "required_level",
            "priority",
            "is_mandatory",
            "required_quantity",
            "estimated_effort_hours",
        )
    )
    requirement_ids = frozenset(row[0] for row in requirements)
    requirement_skill_ids = frozenset(row[2] for row in requirements)

    employees = tuple(
        Employee.objects.filter(status=Employee.Status.ACTIVE)
        .order_by("employee_id")
        .values_list(
            "employee_id",
            "first_name",
            "last_name",
            "experience_years",
            "capacity_hours_week",
            "status",
        )
    )
    employee_ids = frozenset(row[0] for row in employees)

    employee_skills = tuple(
        EmployeeSkill.objects.filter(
            employee_id__in=employee_ids,
            skill_id__in=requirement_skill_ids,
        )
        .order_by("employee_skill_id")
        .values_list(
            "employee_skill_id",
            "employee_id",
            "skill_id",
            "level",
        )
    )
    assignments = tuple(
        Assignment.objects.filter(
            employee_id__in=employee_ids,
            start_date__lte=end_date,
            end_date__gte=start_date,
        )
        .exclude(status=Assignment.Status.CANCELLED)
        .order_by("assignment_id")
        .values_list(
            "assignment_id",
            "employee_id",
            "project_id",
            "start_date",
            "end_date",
            "allocation_percentage",
            "status",
        )
    )
    approved_leaves = tuple(
        Leave.objects.filter(
            employee_id__in=employee_ids,
            status=Leave.Status.APPROVED,
            start_date__lte=end_date,
            end_date__gte=start_date,
        )
        .order_by("leave_id")
        .values_list(
            "leave_id",
            "employee_id",
            "start_date",
            "end_date",
            "status",
        )
    )

    payload = (
        project,
        requirements,
        employees,
        employee_skills,
        assignments,
        approved_leaves,
    )
    return {
        "signature": _serialized_signature(payload),
        "project_id": project_id,
        "requirement_ids": requirement_ids,
        "employee_ids": employee_ids,
    }


def recommendation_references_are_current(pipeline_result, snapshot):
    """Confirm returned ORM references belong to the current input snapshot."""

    try:
        recommendations = pipeline_result["recommendations"]
        if not isinstance(recommendations, (list, tuple)):
            return False

        for recommendation in recommendations:
            result = recommendation["result"]
            for employee in result["team"]:
                if employee.employee_id not in snapshot["employee_ids"]:
                    return False

            effort_solution = result.get("effort_solution", {})
            for capacity in effort_solution.get("employee_capacities", ()):
                if capacity["employee"].employee_id not in snapshot["employee_ids"]:
                    return False
            for allocation in effort_solution.get("allocations", ()):
                if allocation["employee"].employee_id not in snapshot["employee_ids"]:
                    return False
                if (
                    allocation["requirement"].project_skill_requirement_id
                    not in snapshot["requirement_ids"]
                ):
                    return False

            for coverage in result.get("coverage", ()):
                if (
                    coverage["requirement"].project_skill_requirement_id
                    not in snapshot["requirement_ids"]
                ):
                    return False
                for employee in coverage.get("qualified_employees", ()):
                    if employee.employee_id not in snapshot["employee_ids"]:
                        return False
    except (AttributeError, KeyError, TypeError):
        return False
    return True


def recommendation_pipeline_result_is_complete(pipeline_result):
    """Validate the existing pipeline envelope before presenting any evidence."""

    if not isinstance(pipeline_result, dict):
        return False
    sequence_fields = (
        "feasible_teams",
        "pareto_teams",
        "recommendations",
        "comparisons",
        "explanations",
    )
    if any(
        not isinstance(pipeline_result.get(field), (list, tuple))
        for field in sequence_fields
    ):
        return False

    recommendations = pipeline_result["recommendations"]
    explanations = pipeline_result["explanations"]
    if len(recommendations) > 3 or len(explanations) != len(recommendations):
        return False
    if recommendations and not pipeline_result["pareto_teams"]:
        return False
    if pipeline_result["pareto_teams"] and not pipeline_result["feasible_teams"]:
        return False

    try:
        for recommendation, explanation in zip(
            recommendations,
            explanations,
            strict=True,
        ):
            if recommendation["category"] != explanation["category"]:
                return False
            if recommendation["label"] != explanation["label"]:
                return False
            if not isinstance(recommendation["result"], dict):
                return False
            if not isinstance(explanation["team"], (list, tuple)):
                return False
            if not isinstance(explanation["strengths"], (list, tuple)):
                return False
            if not isinstance(explanation["tradeoffs"], (list, tuple)):
                return False
    except (KeyError, TypeError):
        return False
    return "elapsed_seconds" in pipeline_result
