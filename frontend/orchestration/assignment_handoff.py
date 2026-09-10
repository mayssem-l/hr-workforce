"""Derive and revalidate a reviewed staffing proposal without new math.

All business values come from the existing pipeline result or stored
records. Allocation percentages reuse the solver-returned utilization rate
(rounded only to fit the integer assignment field); roles reuse the
solver-returned skill labels; dates reuse the stored project period.
Validation reuses the existing Assignment and AssignmentSkill model rules.
"""

from django.core.exceptions import ValidationError

from core.models import Assignment, AssignmentSkill


def _capacity_by_employee(effort_solution):
    capacities = {}
    if not isinstance(effort_solution, dict):
        return capacities
    rows = effort_solution.get("employee_capacities", ())
    if not isinstance(rows, (list, tuple)):
        return capacities
    for row in rows:
        if not isinstance(row, dict):
            continue
        employee = row.get("employee")
        employee_id = getattr(employee, "employee_id", None)
        if employee_id is not None and employee_id not in capacities:
            capacities[employee_id] = row
    return capacities


def _allocations_by_employee(allocations):
    grouped = {}
    if not isinstance(allocations, (list, tuple)):
        return grouped
    for allocation in allocations:
        if not isinstance(allocation, dict):
            continue
        employee = allocation.get("employee")
        requirement = allocation.get("requirement")
        employee_id = getattr(employee, "employee_id", None)
        requirement_id = getattr(
            requirement, "project_skill_requirement_id", None
        )
        if employee_id is None or requirement_id is None:
            continue
        key = (employee_id, requirement_id)
        if key not in grouped:
            grouped.setdefault(employee_id, []).append(allocation)
            grouped[f"pair:{key[0]}:{key[1]}"] = allocation
    return grouped


def _allocation_percentage(capacity_row):
    utilization = (capacity_row or {}).get("utilization_rate")
    if isinstance(utilization, bool) or not isinstance(
        utilization, (int, float)
    ):
        return None
    return min(100, max(0, int(round(utilization))))


def _role_label(skill_names):
    names = [name for name in skill_names if name]
    if not names:
        return "Team member"
    seen = []
    for name in names:
        if name not in seen:
            seen.append(name)
    role = ", ".join(seen)
    if len(role) > 100:
        role = role[:97] + "..."
    return role


def build_handoff_proposal(project, recommendation):
    """Shape unsaved assignments plus coverage pairs from service values."""

    result = recommendation["result"]
    effort_solution = result.get("effort_solution", {})
    capacities = _capacity_by_employee(effort_solution)
    allocations = effort_solution.get("allocations", ())
    grouped = _allocations_by_employee(allocations)

    proposals = []
    for employee in result["team"]:
        employee_id = getattr(employee, "employee_id", None)
        capacity_row = capacities.get(employee_id, {})
        employee_allocations = grouped.get(employee_id, [])
        skill_names = []
        coverage_requirements = []
        seen_requirements = set()
        for allocation in employee_allocations:
            requirement = allocation.get("requirement")
            requirement_id = getattr(
                requirement, "project_skill_requirement_id", None
            )
            skill = allocation.get("skill")
            skill_label = str(skill).strip() if skill is not None else ""
            if skill_label and skill_label not in skill_names:
                skill_names.append(skill_label)
            if (
                requirement_id is not None
                and requirement_id not in seen_requirements
            ):
                seen_requirements.add(requirement_id)
                coverage_requirements.append(requirement)
        allocation_percentage = _allocation_percentage(capacity_row)
        proposals.append(
            {
                "employee": employee,
                "capacity_row": capacity_row,
                "start_date": project.start_date,
                "end_date": project.end_date,
                "allocation_percentage": allocation_percentage,
                "role_on_project": _role_label(skill_names),
                "status": Assignment.Status.PLANNED,
                "allocated_hours": capacity_row.get("allocated_hours"),
                "available_hours": capacity_row.get("available_hours"),
                "coverage_requirements": tuple(coverage_requirements),
                "service_allocations": tuple(employee_allocations),
            }
        )
    return tuple(proposals)


def _assignment_errors(assignment):
    try:
        assignment.full_clean()
    except ValidationError as exc:
        return dict(exc.message_dict)
    except Exception:
        return {"__all__": ["This proposal could not be validated."]}
    return {}


def validate_handoff_proposal(project, proposals):
    """Run existing model validation without saving any record."""

    errors = []
    has_error = False
    proposed_per_requirement = {}
    for proposal in proposals:
        for requirement in proposal["coverage_requirements"]:
            requirement_id = requirement.project_skill_requirement_id
            proposed_per_requirement[requirement_id] = (
                proposed_per_requirement.get(requirement_id, 0) + 1
            )

    existing_counts = {}
    if proposed_per_requirement:
        for requirement_id in proposed_per_requirement:
            existing_counts[requirement_id] = AssignmentSkill.objects.filter(
                project_skill_requirement_id=requirement_id,
                assignment__status__in=[
                    Assignment.Status.PLANNED,
                    Assignment.Status.ACTIVE,
                ],
            ).count()

    for proposal in proposals:
        row_errors = {}
        assignment = Assignment(
            project=project,
            employee=proposal["employee"],
            start_date=proposal["start_date"],
            end_date=proposal["end_date"],
            allocation_percentage=(
                proposal["allocation_percentage"]
                if proposal["allocation_percentage"] is not None
                else 0
            ),
            role_on_project=proposal["role_on_project"],
            status=proposal["status"],
        )
        if proposal["allocation_percentage"] is None:
            row_errors["allocation_percentage"] = [
                "Solver utilization was not returned for this member."
            ]
        row_errors.update(_assignment_errors(assignment))

        coverage_errors = []
        for requirement in proposal["coverage_requirements"]:
            if requirement.project_id != project.project_id:
                coverage_errors.append(
                    "This requirement no longer belongs to the project."
                )
                continue
            required_quantity = getattr(
                requirement, "required_quantity", None
            )
            existing = existing_counts.get(
                requirement.project_skill_requirement_id, 0
            )
            proposed = proposed_per_requirement.get(
                requirement.project_skill_requirement_id, 0
            )
            if (
                isinstance(required_quantity, int)
                and existing + proposed > required_quantity
            ):
                coverage_errors.append(
                    f"Covering {requirement.skill} would exceed the "
                    "required quantity."
                )
                continue
            link = AssignmentSkill(
                assignment=assignment,
                project_skill_requirement=requirement,
            )
            try:
                link.full_clean(
                    exclude=["assignment"],
                    validate_unique=False,
                )
                link.validate_unique()
            except ValidationError as exc:
                messages = []
                for field_errors in exc.message_dict.values():
                    messages.extend(field_errors)
                coverage_errors.extend(messages)
            except Exception:
                coverage_errors.append(
                    "This coverage could not be validated."
                )
        if coverage_errors:
            row_errors["coverage"] = coverage_errors
        errors.append(row_errors)
        if row_errors:
            has_error = True
    return {"rows": tuple(errors), "has_error": has_error}
