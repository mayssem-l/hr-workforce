from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.urls import reverse

from core.models import Assignment, Employee
from core.services.matching import (
    employee_can_cover_requirement,
    rank_employees_for_project,
)
from core.services.optimization import (
    build_optimization_context,
    get_fast_feasibility_issues,
    get_requirement_capacity_evidence,
    units_to_hours,
)
from core.services.recommendation_preflight import get_recommendation_preflight
from frontend.presenters.projects import build_project_stored_planning_context


BLOCKER_ORDER = {
    "invalid_project_dates": 10,
    "mandatory_effort_must_be_positive": 20,
    "no_mandatory_requirements": 30,
    "stale_planning_inputs": 40,
    "insufficient_eligible_headcount": 50,
    "insufficient_qualified_capacity": 60,
}


def _employee_profile_url(employee, project):
    period_query = urlencode(
        {
            "start_date": project.start_date.isoformat(),
            "end_date": project.end_date.isoformat(),
        }
    )
    return (
        reverse(
            "frontend:employee_detail",
            args=[employee.employee_id],
        )
        + f"?{period_query}"
    )


def build_project_planning_foundation(project):
    """Return stored planning context without readiness or candidate assessment."""

    return build_project_stored_planning_context(project)


def _requirement_signature(requirement):
    return (
        requirement.project_skill_requirement_id,
        requirement.project_id,
        requirement.skill_id,
        requirement.required_level,
        requirement.priority,
        requirement.is_mandatory,
        requirement.required_quantity,
        requirement.estimated_effort_hours,
    )


def _blocker_sort_key(blocker):
    requirement = blocker.get("requirement")
    requirement_id = (
        requirement.project_skill_requirement_id if requirement else 0
    )
    return (BLOCKER_ORDER[blocker["code"]], requirement_id)


def _readiness_result(blockers, *, assessed_capacity=False):
    blockers = tuple(sorted(blockers, key=_blocker_sort_key))
    if blockers:
        stale = any(
            blocker["code"] == "stale_planning_inputs"
            for blocker in blockers
        )
        return {
            "is_ready": False,
            "candidate_assessment_allowed": False,
            "label": "Refresh planning inputs" if stale else "Planning review needed",
            "title": (
                "Current planning data needs to be refreshed."
                if stale
                else "Resolve these blockers before continuing."
            ),
            "message": (
                "This read-only assessment stopped because the current data no "
                "longer matches the planning context shown on the page."
                if stale
                else "The project is not ready to continue to candidate assessment."
            ),
            "tone": "warning",
            "blockers": blockers,
            "capacity_assessed": assessed_capacity,
        }

    return {
        "is_ready": True,
        "candidate_assessment_allowed": True,
        "label": "Ready for candidate assessment",
        "title": "Current planning inputs pass the readiness checks.",
        "message": (
            "Mandatory inputs, eligible headcount, and qualified capacity are "
            "sufficient to continue to candidate assessment."
        ),
        "tone": "success",
        "blockers": (),
        "capacity_assessed": assessed_capacity,
    }


def _stale_blocker():
    return {
        "code": "stale_planning_inputs",
        "message": (
            "Planning inputs changed while this page was being assessed. Refresh "
            "the page before relying on this readiness result."
        ),
    }


def _cheap_readiness_blockers(project, stored_context, preflight):
    blockers = [
        {
            "code": blocker["code"],
            "requirement": blocker.get("requirement"),
            "message": blocker["message"],
        }
        for blocker in preflight["blockers"]
    ]

    try:
        project.clean()
    except ValidationError:
        blockers.append(
            {
                "code": "invalid_project_dates",
                "message": (
                    "The project start date must be on or before the end date "
                    "before planning can continue."
                ),
            }
        )

    mandatory_requirements = [
        requirement
        for requirement in stored_context["requirements"]
        if requirement.is_mandatory
    ]
    if not mandatory_requirements:
        blockers.append(
            {
                "code": "no_mandatory_requirements",
                "message": (
                    "Add at least one mandatory skill requirement before planning "
                    "a team. Optional requirements alone do not define the work "
                    "that later optimization must cover."
                ),
            }
        )

    stored_by_id = {
        requirement.project_skill_requirement_id: requirement
        for requirement in mandatory_requirements
    }
    preflight_is_stale = any(
        blocker.get("requirement") is not None
        and (
            blocker["requirement"].project_skill_requirement_id
            not in stored_by_id
            or _requirement_signature(blocker["requirement"])
            != _requirement_signature(
                stored_by_id[
                    blocker["requirement"].project_skill_requirement_id
                ]
            )
        )
        for blocker in preflight["blockers"]
    )
    if preflight_is_stale:
        blockers.append(_stale_blocker())

    return blockers, mandatory_requirements


def _context_matches_requirements(context, mandatory_requirements):
    displayed = sorted(
        (_requirement_signature(requirement) for requirement in mandatory_requirements),
        key=lambda signature: signature[0],
    )
    assessed = sorted(
        (_requirement_signature(requirement) for requirement in context["requirements"]),
        key=lambda signature: signature[0],
    )
    return displayed == assessed


def _capacity_blockers(issues):
    headcount_requirement_ids = {
        issue["requirement"].project_skill_requirement_id
        for issue in issues
        if issue["code"] == "insufficient_eligible_headcount"
    }
    specific_capacity_issues = [
        issue
        for issue in issues
        if issue["code"] == "insufficient_qualified_capacity"
        and issue["requirement"].project_skill_requirement_id
        not in headcount_requirement_ids
    ]

    blockers = []
    for issue in issues:
        if issue["code"] == "insufficient_eligible_headcount":
            requirement = issue["requirement"]
            blockers.append(
                {
                    "code": issue["code"],
                    "requirement": requirement,
                    "message": (
                        f"{requirement.skill} needs {issue['required_count']} "
                        f"qualified active employee"
                        f"{'s' if issue['required_count'] != 1 else ''}, but "
                        f"{issue['eligible_count']} currently meet"
                        f"{'s' if issue['eligible_count'] == 1 else ''} level "
                        f"{requirement.required_level}."
                    ),
                }
            )

    for issue in specific_capacity_issues:
        requirement = issue["requirement"]
        blockers.append(
            {
                "code": issue["code"],
                "requirement": requirement,
                "message": (
                    f"{requirement.skill} needs "
                    f"{units_to_hours(issue['required_units'])} hours, but its "
                    "qualified active employees currently have "
                    f"{units_to_hours(issue['available_units'])} hours of "
                    "effective capacity across the project dates."
                ),
            }
        )

    total_issue = next(
        (
            issue
            for issue in issues
            if issue["code"] == "insufficient_total_capacity"
        ),
        None,
    )
    if total_issue and not headcount_requirement_ids and not specific_capacity_issues:
        blockers.append(
            {
                "code": "insufficient_qualified_capacity",
                "message": (
                    "Mandatory requirements need "
                    f"{units_to_hours(total_issue['required_units'])} hours in "
                    "total, but active employees qualified for at least one "
                    "mandatory requirement currently have "
                    f"{units_to_hours(total_issue['available_units'])} hours of "
                    "effective capacity across the project dates."
                ),
            }
        )

    return blockers


def build_ranked_candidate_context(project, readiness):
    """Present the matching service result without changing its order or scores."""

    component_definitions = (
        {
            "label": "Skill match",
            "unit": "Score out of 100",
            "description": (
                "Fit across the project's stored skill requirements, including "
                "required level, priority, and mandatory status."
            ),
        },
        {
            "label": "Workload",
            "unit": "Percentage",
            "description": (
                "The lowest free scheduled capacity across the inclusive project "
                "period."
            ),
        },
        {
            "label": "Leave",
            "unit": "Percentage",
            "description": (
                "The share of Monday-to-Friday project days without approved "
                "dated leave."
            ),
        },
        {
            "label": "Experience",
            "unit": "Score out of 100",
            "description": (
                "Overall years of experience translated by the current matching "
                "rules."
            ),
        },
        {
            "label": "Project fit",
            "unit": "Score out of 100",
            "description": (
                "The current weighted result across the four components."
            ),
        },
    )
    base_context = {
        "period_start": project.start_date,
        "period_end": project.end_date,
        "component_definitions": component_definitions,
        "requirements_url": "#planning-requirements-title",
    }

    if not readiness["candidate_assessment_allowed"]:
        return {
            **base_context,
            "state": "blocked",
            "title": "Candidate assessment paused",
            "message": (
                "Resolve the planning-readiness blockers above before reviewing "
                "ranked employees."
            ),
            "rows": (),
            "service_results": (),
            "count": 0,
        }

    service_results = tuple(rank_employees_for_project(project))
    if not service_results:
        return {
            **base_context,
            "state": "empty",
            "title": "No eligible candidates returned",
            "message": (
                "The current matching rules did not return an active employee who "
                "meets "
                "at least one current project requirement. Refresh the workspace "
                "after reviewing employee skills and project requirements."
            ),
            "rows": (),
            "service_results": (),
            "count": 0,
        }

    rows = tuple(
        {
            "rank": rank,
            "employee": result["employee"],
            "profile_url": _employee_profile_url(
                result["employee"],
                project,
            ),
            "requirements_url": base_context["requirements_url"],
            "skill_score": result["skill_score"],
            "workload_score": result["workload_score"],
            "leave_score": result["leave_score"],
            "experience_score": result["experience_score"],
            "final_score": result["final_score"],
        }
        for rank, result in enumerate(service_results, start=1)
    )
    return {
        **base_context,
        "state": "ranked",
        "title": "Ranked eligible candidates",
        "message": (
            "These active employees meet at least one current project requirement "
            "and remain in the exact order returned by the current matching rules. "
            "This ranking does not select or recommend a team."
        ),
        "rows": rows,
        "service_results": service_results,
        "count": len(rows),
    }


def build_candidate_exclusion_context(project, readiness, candidates, workforce):
    """Explain absence from the exact service-returned candidate set."""

    base_context = {
        "requirements_url": "#planning-requirements-title",
        "rows": (),
        "count": 0,
    }
    if not readiness["candidate_assessment_allowed"]:
        return {
            **base_context,
            "state": "blocked",
            "title": "Exclusion assessment paused",
            "message": (
                "Resolve the planning-readiness blockers before reviewing why "
                "employees are absent from the candidate list."
            ),
        }

    workforce = tuple(workforce)
    candidate_ids = {
        result["employee"].employee_id
        for result in candidates["service_results"]
    }
    workforce_ids = {employee.employee_id for employee in workforce}
    if not candidate_ids.issubset(workforce_ids):
        return {
            **base_context,
            "state": "unavailable",
            "title": "Exclusion evidence unavailable",
            "message": (
                "Candidate data no longer matches the current workforce. Refresh "
                "the workspace before relying on an exclusion explanation."
            ),
        }

    requirements = tuple(project.profile_requirements)
    rows = []
    for employee in workforce:
        if employee.employee_id in candidate_ids:
            continue

        if employee.status != Employee.Status.ACTIVE:
            reason_code = "inactive_status"
            reason_label = "Not active for matching"
            reason_message = (
                f"Current employee status is {employee.get_status_display()}. "
                "The matching service considers only employees with Active status."
            )
        elif not employee_can_cover_requirement(
            employee,
            project,
            requirements=requirements,
            employee_skills=employee.planning_skills,
        ):
            reason_code = "no_qualifying_requirement"
            reason_label = "No qualifying requirement"
            reason_message = (
                "Current skill proficiency does not meet the required level for "
                "any stored project requirement."
            )
        else:
            reason_code = "eligibility_explanation_unavailable"
            reason_label = "Explanation unavailable"
            reason_message = (
                "Current status and skill evidence do not explain why this employee "
                "was absent from the matching service result. Refresh the workspace "
                "before relying on this explanation."
            )

        rows.append(
            {
                "employee": employee,
                "profile_url": _employee_profile_url(employee, project),
                "requirements_url": base_context["requirements_url"],
                "reason_code": reason_code,
                "reason_label": reason_label,
                "reason_message": reason_message,
            }
        )

    rows = tuple(rows)
    if not rows:
        return {
            **base_context,
            "state": "complete",
            "title": "No employees excluded",
            "message": (
                "Every current workforce record is present in the matching service "
                "candidate result."
            ),
        }

    return {
        **base_context,
        "state": "explained",
        "title": "Candidate exclusions explained",
        "message": (
            "These employees are absent from the exact candidate result returned by "
            "the current matching service."
        ),
        "rows": rows,
        "count": len(rows),
    }


def _current_coverage_by_requirement(assignments):
    current_statuses = {
        Assignment.Status.PLANNED,
        Assignment.Status.ACTIVE,
    }
    coverage_by_requirement = {}
    for assignment in assignments:
        if assignment.status not in current_statuses:
            continue
        for coverage in assignment.profile_coverage:
            requirement_id = coverage.project_skill_requirement_id
            coverage_by_requirement.setdefault(requirement_id, []).append(
                assignment
            )

    for requirement_id, covering_assignments in coverage_by_requirement.items():
        coverage_by_requirement[requirement_id] = sorted(
            covering_assignments,
            key=lambda assignment: (
                assignment.employee.last_name,
                assignment.employee.first_name,
                assignment.start_date,
                assignment.assignment_id,
            ),
        )
    return coverage_by_requirement


def _requirement_coverage_state(covered_quantity, required_quantity):
    remaining_quantity = max(required_quantity - covered_quantity, 0)
    if remaining_quantity == 0:
        return {
            "code": "coverage_quantity_met",
            "label": "Current coverage quantity met",
            "message": (
                "Current planned or active assignment coverage reaches the stored "
                "quantity. This does not establish future team feasibility."
            ),
            "tone": "success",
            "remaining_quantity": 0,
        }
    if covered_quantity:
        return {
            "code": "partial_coverage",
            "label": "Current coverage is partial",
            "message": (
                f"{remaining_quantity} more current assignment coverage "
                f"record{' is' if remaining_quantity == 1 else 's are'} needed "
                "to reach the stored quantity."
            ),
            "tone": "warning",
            "remaining_quantity": remaining_quantity,
        }
    return {
        "code": "no_current_coverage",
        "label": "No current assignment coverage",
        "message": (
            "No planned or active assignment currently carries this requirement."
        ),
        "tone": "warning",
        "remaining_quantity": remaining_quantity,
    }


def _requirement_assessment_state(requirement, evidence):
    qualified_count = evidence["qualified_count"]
    capacity_hours = units_to_hours(evidence["qualified_capacity_units"])
    if qualified_count == 0:
        qualification = {
            "code": "no_qualified_employees",
            "label": "No qualified active employees",
            "message": (
                "No active employee currently meets this requirement's skill and "
                "proficiency level."
            ),
            "tone": "warning",
        }
    elif not evidence["has_sufficient_headcount"]:
        qualification = {
            "code": "insufficient_qualified_headcount",
            "label": "Qualified headcount below quantity",
            "message": (
                f"{qualified_count} active employee"
                f"{' meets' if qualified_count == 1 else 's meet'} the level, "
                f"below the stored quantity of {requirement.required_quantity}."
            ),
            "tone": "warning",
        }
    else:
        qualification = {
            "code": "qualified_headcount_available",
            "label": "Qualified headcount reaches quantity",
            "message": (
                f"{qualified_count} active employee"
                f"{' meets' if qualified_count == 1 else 's meet'} the stored "
                "skill level."
            ),
            "tone": "success",
        }

    if evidence["required_units"] is None:
        capacity = {
            "code": "missing_effort",
            "label": "Capacity comparison unavailable",
            "message": (
                "No positive effort is stored, so available qualified hours cannot "
                "be compared with an effort target."
            ),
            "tone": "warning",
        }
    elif not evidence["has_sufficient_capacity"]:
        effort = units_to_hours(evidence["required_units"])
        capacity = {
            "code": "insufficient_qualified_capacity",
            "label": "Qualified capacity below effort",
            "message": (
                f"Qualified active employees have {capacity_hours:.2f} available "
                f"hours across the project dates, below the entered {effort:.2f} "
                "hours."
            ),
            "tone": "warning",
        }
    else:
        effort = units_to_hours(evidence["required_units"])
        capacity = {
            "code": "qualified_capacity_available",
            "label": "Qualified capacity reaches effort",
            "message": (
                f"Qualified active employees have {capacity_hours:.2f} available "
                f"hours across the project dates for {effort:.2f} entered hours."
            ),
            "tone": "success",
        }
    return qualification, capacity


def build_requirement_evidence_context(
    project,
    stored_context,
    assessment_context,
):
    """Shape requirement evidence from stored relations and service context."""

    requirements = tuple(stored_context["requirements"])
    if not requirements:
        return {
            "state": "empty",
            "title": "No requirement evidence available",
            "message": (
                "Add stored project requirements before reviewing qualification, "
                "coverage, or qualified capacity evidence."
            ),
            "rows": (),
            "count": 0,
            "period_start": project.start_date,
            "period_end": project.end_date,
        }

    coverage_by_requirement = _current_coverage_by_requirement(
        stored_context["assignments"]
    )
    assessment_available = assessment_context is not None
    employees = (
        sorted(
            assessment_context["employees"],
            key=lambda employee: (
                employee.last_name,
                employee.first_name,
                employee.employee_id,
            ),
        )
        if assessment_available
        else ()
    )

    rows = []
    for requirement in requirements:
        requirement_id = requirement.project_skill_requirement_id
        covering_assignments = coverage_by_requirement.get(requirement_id, ())
        coverage_rows = tuple(
            {
                "assignment": assignment,
                "employee": assignment.employee,
                "profile_url": _employee_profile_url(
                    assignment.employee,
                    project,
                ),
                "role": assignment.role_on_project,
                "assignment_status": assignment.status,
                "assignment_status_label": assignment.get_status_display(),
            }
            for assignment in covering_assignments
        )
        coverage_state = _requirement_coverage_state(
            len(coverage_rows),
            requirement.required_quantity,
        )

        qualified_rows = []
        qualified_capacity = None
        qualification_state = {
            "code": "assessment_paused",
            "label": "Qualification assessment paused",
            "message": (
                "Current planning inputs did not reach a consistent capacity "
                "assessment, so qualified employees and available hours are not "
                "shown."
            ),
            "tone": "warning",
        }
        capacity_state = {
            "code": "assessment_paused",
            "label": "Capacity assessment paused",
            "message": (
                "Resolve the planning-readiness blockers before comparing qualified "
                "capacity with entered effort."
            ),
            "tone": "warning",
        }
        if requirement.estimated_effort_hours is None or (
            requirement.estimated_effort_hours <= 0
        ):
            capacity_state = {
                "code": "missing_effort",
                "label": "Capacity comparison unavailable",
                "message": (
                    "No positive effort is stored, so available qualified hours "
                    "cannot be compared with an effort target."
                ),
                "tone": "warning",
            }
        if assessment_available:
            evidence = get_requirement_capacity_evidence(
                requirement,
                employees,
                assessment_context["available_hours"],
            )
            for employee in evidence["qualified_employees"]:
                employee_skill = next(
                    skill
                    for skill in employee.optimization_skills
                    if skill.skill_id == requirement.skill_id
                )
                available_hours = units_to_hours(
                    assessment_context["available_hours"][employee.employee_id]
                )
                qualified_rows.append(
                    {
                        "employee": employee,
                        "profile_url": _employee_profile_url(employee, project),
                        "level": employee_skill.level,
                        "available_hours": available_hours,
                    }
                )
            qualified_capacity = units_to_hours(
                evidence["qualified_capacity_units"]
            )
            qualification_state, capacity_state = _requirement_assessment_state(
                requirement,
                evidence,
            )

        rows.append(
            {
                "requirement": requirement,
                "anchor_id": f"requirement-evidence-{requirement_id}",
                "covered_quantity": len(coverage_rows),
                "remaining_quantity": coverage_state["remaining_quantity"],
                "coverage_rows": coverage_rows,
                "coverage_state": coverage_state,
                "assessment_available": assessment_available,
                "qualified_rows": tuple(qualified_rows),
                "qualified_count": len(qualified_rows),
                "qualified_capacity": qualified_capacity,
                "qualification_state": qualification_state,
                "capacity_state": capacity_state,
            }
        )

    return {
        "state": "assessed" if assessment_available else "paused",
        "title": (
            "Current requirement evidence"
            if assessment_available
            else "Requirement evidence partly available"
        ),
        "message": (
            "Qualification and capacity use the same current service context as "
            "planning readiness. Current assignment coverage is stored evidence, "
            "not proof that a future team is feasible."
            if assessment_available
            else "Stored requirements and current assignment coverage remain "
            "visible. Qualification and capacity evidence is paused until planning "
            "inputs support a consistent assessment."
        ),
        "rows": tuple(rows),
        "count": len(rows),
        "period_start": project.start_date,
        "period_end": project.end_date,
    }


def build_project_planning_workspace(project):
    """Add current, read-only readiness evidence to the stored workspace."""

    stored_context = build_project_planning_foundation(project)

    # This service intentionally runs first. Its blockers stop all downstream
    # workforce-capacity assessment.
    preflight = get_recommendation_preflight(project)
    blockers, mandatory_requirements = _cheap_readiness_blockers(
        project,
        stored_context,
        preflight,
    )
    requirement_assessment_context = None
    if blockers:
        readiness = _readiness_result(blockers)
    else:
        optimization_context = build_optimization_context(project)
        if not _context_matches_requirements(
            optimization_context,
            mandatory_requirements,
        ):
            readiness = _readiness_result([_stale_blocker()])
        else:
            requirement_assessment_context = optimization_context
            contributing_ids = set().union(
                *optimization_context["eligible_by_requirement"].values()
            )
            contributing_employees = [
                employee
                for employee in optimization_context["employees"]
                if employee.employee_id in contributing_ids
            ]
            issues = get_fast_feasibility_issues(
                contributing_employees,
                optimization_context,
            )
            readiness = _readiness_result(
                _capacity_blockers(issues),
                assessed_capacity=True,
            )

    estimates_match = (
        project.estimated_hours == stored_context["mandatory_effort_hours"]
    )
    workspace = {
        **stored_context,
        "readiness": readiness,
        "estimates_match": estimates_match,
        "estimate_message": (
            "The project estimate matches the entered mandatory skill effort."
            if estimates_match
            else "The project estimate and entered mandatory skill effort differ. "
            "They remain separate stored values; review both before later "
            "optimization."
        ),
    }
    workspace["candidates"] = build_ranked_candidate_context(
        project,
        readiness,
    )
    workspace["requirement_evidence"] = build_requirement_evidence_context(
        project,
        stored_context,
        requirement_assessment_context,
    )
    return workspace
