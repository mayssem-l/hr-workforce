"""Derive and revalidate a reviewed staffing proposal without new math.

All business values come from the existing pipeline result or stored
records. Allocation percentages reuse the solver-returned utilization rate
(rounded only to fit the integer assignment field); roles reuse the
solver-returned skill labels; dates reuse the stored project period.
Current staffing is the reconciled baseline: assignments on OTHER
projects stay workload constraints, while target-project assignments
overlapping the project period are diffed per employee into
KEEP / UPDATE / ADD / REMOVE and their coverage into KEEP / ADD / REMOVE.
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
        existing = grouped.setdefault(employee_id, [])
        if requirement_id not in {
            getattr(item.get("requirement"), "project_skill_requirement_id", None)
            for item in existing
        }:
            existing.append(allocation)
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


def get_target_baseline(project):
    """Return current target-project assignments overlapping the period."""

    return list(
        Assignment.objects.filter(
            project=project,
            start_date__lte=project.end_date,
            end_date__gte=project.start_date,
        )
        .exclude(status=Assignment.Status.CANCELLED)
        .select_related("employee")
        .order_by("assignment_id")
    )


def _preferred_existing(existing_rows):
    order = {
        Assignment.Status.ACTIVE: 0,
        Assignment.Status.PLANNED: 1,
        Assignment.Status.COMPLETED: 2,
    }
    return sorted(
        existing_rows,
        key=lambda assignment: (
            order.get(assignment.status, 3),
            assignment.start_date,
            assignment.assignment_id,
        ),
    )[0]


def _current_coverage_ids(assignment):
    return set(
        AssignmentSkill.objects.filter(assignment=assignment).values_list(
            "project_skill_requirement_id", flat=True
        )
    )


def build_handoff_proposal(project, recommendation):
    """Diff current target staffing against the recommended team."""

    result = recommendation["result"]
    effort_solution = result.get("effort_solution", {})
    capacities = _capacity_by_employee(effort_solution)
    allocations = effort_solution.get("allocations", ())
    grouped = _allocations_by_employee(allocations)

    baseline = get_target_baseline(project)
    baseline_by_employee = {}
    for assignment in baseline:
        baseline_by_employee.setdefault(assignment.employee_id, []).append(
            assignment
        )

    recommended_ids = set()
    proposals = []
    for employee in result["team"]:
        employee_id = getattr(employee, "employee_id", None)
        if employee_id is not None:
            recommended_ids.add(employee_id)
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
        existing_rows = baseline_by_employee.get(employee_id, [])
        existing = _preferred_existing(existing_rows) if existing_rows else None
        if existing is None:
            action = "ADD"
            current_allocation = None
        else:
            proposed_role = _role_label(skill_names)
            current_coverage = _current_coverage_ids(existing)
            proposed_coverage = {
                requirement.project_skill_requirement_id
                for requirement in coverage_requirements
            }
            if (
                existing.allocation_percentage == allocation_percentage
                and existing.start_date == project.start_date
                and existing.end_date == project.end_date
                and existing.role_on_project == proposed_role
                and current_coverage == proposed_coverage
            ):
                action = "KEEP"
            else:
                action = "UPDATE"
            current_allocation = existing.allocation_percentage
        proposals.append(
            {
                "action": action,
                "employee": employee,
                "existing_assignment": existing,
                "capacity_row": capacity_row,
                "start_date": project.start_date,
                "end_date": project.end_date,
                "allocation_percentage": allocation_percentage,
                "current_allocation": current_allocation,
                "role_on_project": _role_label(skill_names),
                "status": (
                    existing.status
                    if existing is not None
                    else Assignment.Status.PLANNED
                ),
                "allocated_hours": capacity_row.get("allocated_hours"),
                "available_hours": capacity_row.get("available_hours"),
                "coverage_requirements": tuple(coverage_requirements),
                "service_allocations": tuple(employee_allocations),
            }
        )

    removals = []
    for assignment in baseline:
        if assignment.employee_id not in recommended_ids:
            removals.append(
                {
                    "action": "REMOVE",
                    "employee": assignment.employee,
                    "existing_assignment": assignment,
                    "capacity_row": {},
                    "start_date": assignment.start_date,
                    "end_date": assignment.end_date,
                    "allocation_percentage": None,
                    "current_allocation": assignment.allocation_percentage,
                    "role_on_project": assignment.role_on_project,
                    "status": assignment.status,
                    "allocated_hours": None,
                    "available_hours": None,
                    "coverage_requirements": (),
                    "service_allocations": (),
                }
            )
    return tuple(proposals + removals)


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

    adds_per_requirement = {}
    for proposal in proposals:
        if proposal["action"] not in ("ADD", "UPDATE"):
            continue
        existing_ids = set()
        existing = proposal["existing_assignment"]
        if proposal["action"] == "UPDATE" and existing is not None:
            existing_ids = _current_coverage_ids(existing)
        for requirement in proposal["coverage_requirements"]:
            if requirement.project_skill_requirement_id not in existing_ids:
                adds_per_requirement[requirement.project_skill_requirement_id] = (
                    adds_per_requirement.get(
                        requirement.project_skill_requirement_id, 0
                    )
                    + 1
                )

    removed_link_ids = set()
    cancelled_assignment_ids = set()
    for proposal in proposals:
        existing = proposal["existing_assignment"]
        if existing is None:
            continue
        if proposal["action"] == "REMOVE":
            cancelled_assignment_ids.add(existing.assignment_id)
            removed_link_ids.update(
                AssignmentSkill.objects.filter(
                    assignment=existing
                ).values_list("assignment_skill_id", flat=True)
            )
        elif proposal["action"] == "UPDATE":
            proposed_ids = {
                requirement.project_skill_requirement_id
                for requirement in proposal["coverage_requirements"]
            }
            removed_link_ids.update(
                AssignmentSkill.objects.filter(assignment=existing)
                .exclude(project_skill_requirement_id__in=proposed_ids)
                .values_list("assignment_skill_id", flat=True)
            )

    surviving_per_requirement = {}
    for link in AssignmentSkill.objects.filter(
        assignment__project=project,
        assignment__status__in=[
            Assignment.Status.PLANNED,
            Assignment.Status.ACTIVE,
        ],
    ).values("assignment_skill_id", "project_skill_requirement_id", "assignment_id"):
        if link["assignment_skill_id"] in removed_link_ids:
            continue
        if link["assignment_id"] in cancelled_assignment_ids:
            continue
        surviving_per_requirement[link["project_skill_requirement_id"]] = (
            surviving_per_requirement.get(
                link["project_skill_requirement_id"], 0
            )
            + 1
        )
    errors = []
    has_error = False
    for proposal in proposals:
        action = proposal["action"]
        if action in ("REMOVE", "KEEP"):
            errors.append({})
            continue
        row_errors = {}
        existing = proposal["existing_assignment"]
        if action == "UPDATE" and existing is not None:
            candidate = Assignment.objects.get(pk=existing.pk)
            candidate.allocation_percentage = proposal[
                "allocation_percentage"
            ]
            candidate.start_date = proposal["start_date"]
            candidate.end_date = proposal["end_date"]
            candidate.role_on_project = proposal["role_on_project"]
        else:
            candidate = Assignment(
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
        row_errors.update(_assignment_errors(candidate))

        keep_ids = set()
        if action == "UPDATE" and existing is not None:
            keep_ids = _current_coverage_ids(existing)
        coverage_errors = []
        for requirement in proposal["coverage_requirements"]:
            if requirement.project_id != project.project_id:
                coverage_errors.append(
                    "This requirement no longer belongs to the project."
                )
                continue
            if requirement.project_skill_requirement_id in keep_ids:
                continue
            required_quantity = getattr(
                requirement, "required_quantity", None
            )
            final_count = surviving_per_requirement.get(
                requirement.project_skill_requirement_id, 0
            ) + adds_per_requirement.get(
                requirement.project_skill_requirement_id, 0
            )
            if (
                isinstance(required_quantity, int)
                and final_count > required_quantity
            ):
                coverage_errors.append(
                    f"Covering {requirement.skill} would exceed the "
                    "required quantity."
                )
                continue
            link = AssignmentSkill(
                assignment=candidate,
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
                if final_count <= (required_quantity or 0):
                    messages = [
                        message
                        for message in messages
                        if "required quantity" not in message
                        and "already been reached" not in message
                    ]
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
