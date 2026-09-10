from urllib.parse import urlencode

from django.urls import reverse

from frontend.navigation import with_planning_return


def _recommendation_navigation(project, user):
    planning_url = reverse(
        "frontend:project_planning",
        args=[project.project_id],
    )
    can_view_project = user.has_perm("core.view_project")
    can_view_requirements = can_view_project and user.has_perm(
        "core.view_projectskillrequirement"
    )
    can_view_candidates = (
        can_view_requirements
        and user.has_perm("core.view_employee")
        and user.has_perm("core.view_skill")
    )
    return {
        "planning_url": planning_url if can_view_project else None,
        "project_url": (
            reverse(
                "frontend:project_detail",
                args=[project.project_id],
            )
            if can_view_project
            else None
        ),
        "requirements_url": (
            f"{planning_url}#planning-requirements-title"
            if can_view_requirements
            else None
        ),
        "candidates_url": (
            f"{planning_url}#planning-candidates-title"
            if can_view_candidates
            else None
        ),
    }


def _employee_profile_url(employee, project, user, planning_url):
    employee_id = getattr(employee, "employee_id", None)
    if (
        not employee_id
        or not planning_url
        or not user.has_perm("core.view_employee")
    ):
        return None

    period_query = urlencode(
        {
            "start_date": project.start_date.isoformat(),
            "end_date": project.end_date.isoformat(),
        }
    )
    profile_url = (
        reverse(
            "frontend:employee_detail",
            args=[employee_id],
        )
        + f"?{period_query}"
    )
    return with_planning_return(profile_url, planning_url)


def _present_team_member(employee, project, user, planning_url):
    if employee is None:
        return {
            "employee": None,
            "label": "Employee record unavailable",
            "profile_url": None,
        }

    label = str(employee).strip() or "Employee record unavailable"
    return {
        "employee": employee,
        "label": label,
        "profile_url": _employee_profile_url(
            employee,
            project,
            user,
            planning_url,
        ),
    }


def _record_key(record, identifier_name):
    identifier = getattr(record, identifier_name, None)
    if identifier is not None:
        return ("stored", identifier)
    return ("returned-object", id(record))


def _build_capacity_evidence(
    capacities,
    project,
    user,
    planning_url,
):
    if not isinstance(capacities, (list, tuple)):
        return {
            "state": "unavailable",
            "message": (
                "Employee capacity evidence was not returned for this strategy."
            ),
            "rows": (),
        }
    if not capacities:
        return {
            "state": "empty",
            "message": (
                "No employee capacity rows were returned for this strategy."
            ),
            "rows": (),
        }

    rows = []
    for capacity in capacities:
        if not isinstance(capacity, dict):
            return {
                "state": "unavailable",
                "message": (
                    "Employee capacity evidence could not be read safely."
                ),
                "rows": (),
            }
        member = _present_team_member(
            capacity.get("employee"),
            project,
            user,
            planning_url,
        )
        rows.append(
            {
                **member,
                "available_hours": capacity.get("available_hours"),
                "allocated_hours": capacity.get("allocated_hours"),
                "utilization_rate": capacity.get("utilization_rate"),
                "service_capacity": capacity,
            }
        )
    return {
        "state": "available",
        "message": (
            "Available hours, allocated hours, and utilization are the exact "
            "per-employee values returned by the solver."
        ),
        "rows": tuple(rows),
    }


def _build_allocation_matrix(allocations, capacity_evidence):
    if not isinstance(allocations, (list, tuple)):
        return {
            "state": "unavailable",
            "message": "The solver did not return readable allocation rows.",
            "columns": (),
            "rows": (),
            "column_keys": frozenset(),
        }
    if not allocations:
        return {
            "state": "empty",
            "message": (
                "The solver returned no positive employee-to-requirement "
                "allocation rows for this strategy."
            ),
            "columns": (),
            "rows": (),
            "column_keys": frozenset(),
        }
    if capacity_evidence["state"] != "available":
        return {
            "state": "unavailable",
            "message": (
                "An allocation matrix cannot be aligned without the solver's "
                "employee-capacity rows."
            ),
            "columns": (),
            "rows": (),
            "column_keys": frozenset(),
        }

    columns = []
    columns_by_key = {}
    readable_allocations = []
    for allocation in allocations:
        if not isinstance(allocation, dict):
            return {
                "state": "unavailable",
                "message": "The solver returned an unreadable allocation row.",
                "columns": (),
                "rows": (),
                "column_keys": frozenset(),
            }
        requirement = allocation.get("requirement")
        requirement_key = _record_key(
            requirement,
            "project_skill_requirement_id",
        )
        if requirement_key not in columns_by_key:
            skill = allocation.get("skill")
            requirement_is_available = getattr(requirement, "pk", None) is not None
            skill_label = (
                str(skill).strip()
                if skill is not None and str(skill).strip()
                else "Requirement record unavailable"
            )
            if not requirement_is_available and skill_label != (
                "Requirement record unavailable"
            ):
                skill_label = f"{skill_label} — requirement record unavailable"
            column = {
                "key": requirement_key,
                "requirement": requirement,
                "skill": skill,
                "label": skill_label,
                "required_level": getattr(requirement, "required_level", None),
                "required_effort_hours": getattr(
                    requirement,
                    "estimated_effort_hours",
                    None,
                ),
                "service_first_allocation": allocation,
            }
            columns_by_key[requirement_key] = column
            columns.append(column)
        readable_allocations.append(allocation)

    allocations_by_pair = {}
    for allocation in readable_allocations:
        employee_key = _record_key(
            allocation.get("employee"),
            "employee_id",
        )
        requirement_key = _record_key(
            allocation.get("requirement"),
            "project_skill_requirement_id",
        )
        allocations_by_pair.setdefault(
            (employee_key, requirement_key),
            allocation,
        )

    rows = []
    for capacity_row in capacity_evidence["rows"]:
        employee_key = _record_key(
            capacity_row["employee"],
            "employee_id",
        )
        cells = []
        for column in columns:
            allocation = allocations_by_pair.get((employee_key, column["key"]))
            cells.append(
                {
                    "allocation": allocation,
                    "has_returned_allocation": allocation is not None,
                    "hours": (
                        allocation.get("hours")
                        if allocation is not None
                        else None
                    ),
                }
            )
        rows.append(
            {
                **capacity_row,
                "cells": tuple(cells),
            }
        )

    return {
        "state": "available",
        "message": (
            "Each populated cell is one employee-to-requirement hour value "
            "returned by OR-Tools. A dash means no allocation row was returned; "
            "it is not a frontend-calculated zero."
        ),
        "columns": tuple(columns),
        "rows": tuple(rows),
        "column_keys": frozenset(columns_by_key),
    }


def _build_coverage_evidence(
    coverage_items,
    matrix,
    project,
    user,
    planning_url,
    requirements_url,
):
    if not isinstance(coverage_items, (list, tuple)):
        return {
            "state": "unavailable",
            "message": "Requirement coverage evidence was not returned.",
            "rows": (),
        }
    if not coverage_items:
        return {
            "state": "empty",
            "message": (
                "No mandatory or optional requirement coverage rows were "
                "returned for this strategy."
            ),
            "rows": (),
        }

    rows = []
    for coverage in coverage_items:
        if not isinstance(coverage, dict):
            return {
                "state": "unavailable",
                "message": "Requirement coverage evidence could not be read safely.",
                "rows": (),
            }
        requirement = coverage.get("requirement")
        skill = coverage.get("skill")
        requirement_is_available = getattr(requirement, "pk", None) is not None
        skill_label = (
            str(skill).strip()
            if skill is not None and str(skill).strip()
            else "Requirement record unavailable"
        )
        if not requirement_is_available and skill_label != (
            "Requirement record unavailable"
        ):
            skill_label = f"{skill_label} — requirement record unavailable"
        is_mandatory = coverage.get("is_mandatory") is True
        is_satisfied = coverage.get("is_satisfied") is True
        qualified_members = tuple(
            _present_team_member(
                employee,
                project,
                user,
                planning_url,
            )
            for employee in coverage.get("qualified_employees", ())
        )
        requirement_key = _record_key(
            requirement,
            "project_skill_requirement_id",
        )
        has_matrix_column = requirement_key in matrix["column_keys"]
        if is_mandatory:
            outcome_label = (
                "Mandatory coverage met"
                if is_satisfied
                else "Mandatory coverage not met"
            )
            outcome_message = (
                "The returned coverage result satisfies this mandatory "
                "headcount requirement."
                if is_satisfied
                else "The returned coverage result does not satisfy this "
                "mandatory headcount requirement."
            )
        else:
            outcome_label = (
                "Optional coverage met"
                if is_satisfied
                else "Optional coverage not met"
            )
            outcome_message = (
                "This optional requirement is covered, but optional coverage "
                "does not determine whole-team feasibility."
                if is_satisfied
                else "This optional requirement is not covered and does not "
                "determine whole-team feasibility."
            )

        rows.append(
            {
                "requirement": requirement,
                "skill": skill,
                "label": skill_label,
                "required_level": getattr(requirement, "required_level", None),
                "required_effort_hours": getattr(
                    requirement,
                    "estimated_effort_hours",
                    None,
                ),
                "required_quantity": coverage.get("required_quantity"),
                "covered_quantity": coverage.get("covered_quantity"),
                "is_mandatory": is_mandatory,
                "requirement_type_label": (
                    "Mandatory" if is_mandatory else "Optional"
                ),
                "is_satisfied": is_satisfied,
                "outcome_label": outcome_label,
                "outcome_message": outcome_message,
                "qualified_members": qualified_members,
                "has_matrix_column": has_matrix_column,
                "requirements_url": (
                    requirements_url if requirement_is_available else None
                ),
                "service_coverage": coverage,
            }
        )
    return {
        "state": "available",
        "message": (
            "Coverage is the backend's requirement-level qualification and "
            "headcount result. It is separate from whole-team effort feasibility."
        ),
        "rows": tuple(rows),
    }


def build_recommendation_allocation_evidence(
    result,
    project,
    user,
    navigation,
):
    """Shape existing solver and coverage evidence without deriving values."""

    effort_solution = result.get("effort_solution")
    if not isinstance(effort_solution, dict):
        return {
            "solver": {
                "state": "unavailable",
                "reason": "Solver evidence was not returned for this strategy.",
                "service_solution": effort_solution,
            },
            "matrix": _build_allocation_matrix(None, {"state": "unavailable"}),
            "capacity": _build_capacity_evidence(
                None,
                project,
                user,
                navigation["planning_url"],
            ),
            "coverage": _build_coverage_evidence(
                result.get("coverage"),
                {"column_keys": frozenset()},
                project,
                user,
                navigation["planning_url"],
                navigation["requirements_url"],
            ),
        }

    solver_is_feasible = effort_solution.get("is_feasible")
    solver = {
        "state": (
            "feasible"
            if solver_is_feasible is True
            else "not_feasible"
            if solver_is_feasible is False
            else "unavailable"
        ),
        "reason": (
            effort_solution.get("reason")
            or "A solver outcome explanation was not returned."
        ),
        "service_solution": effort_solution,
    }
    capacity = _build_capacity_evidence(
        effort_solution.get("employee_capacities"),
        project,
        user,
        navigation["planning_url"],
    )
    matrix = _build_allocation_matrix(
        effort_solution.get("allocations"),
        capacity,
    )
    coverage = _build_coverage_evidence(
        result.get("coverage"),
        matrix,
        project,
        user,
        navigation["planning_url"],
        navigation["requirements_url"],
    )
    return {
        "solver": solver,
        "matrix": matrix,
        "capacity": capacity,
        "coverage": coverage,
    }


def build_recommendation_strategy_cards(project, recommendations, user):
    """Present selected strategies without changing their order or metrics."""

    navigation = _recommendation_navigation(project, user)
    cards = []
    for recommendation in recommendations:
        result = recommendation["result"]
        metrics = result["metrics"]
        cards.append(
            {
                "category": recommendation["category"],
                "label": recommendation["label"],
                "reason": recommendation["reason"],
                "members": tuple(
                    _present_team_member(
                        employee,
                        project,
                        user,
                        navigation["planning_url"],
                    )
                    for employee in result["team"]
                ),
                "team_score": result["team_score"],
                "team_size": result["team_size"],
                "total_available_hours": metrics["total_available_hours"],
                "total_allocated_hours": metrics["total_allocated_hours"],
                "remaining_capacity_hours": metrics[
                    "remaining_capacity_hours"
                ],
                "max_utilization": metrics["max_utilization"],
                "utilization_spread": metrics["utilization_spread"],
                "service_recommendation": recommendation,
                "service_result": result,
                "service_metrics": metrics,
                "allocation_evidence": build_recommendation_allocation_evidence(
                    result,
                    project,
                    user,
                    navigation,
                ),
            }
        )
    return {
        "cards": tuple(cards),
        "navigation": navigation,
    }


def build_recommendation_decision_evidence(
    recommendations,
    comparisons,
    explanations,
    manager_summaries=None,
):
    """Align existing deterministic evidence without deriving new claims."""

    explanations_are_readable = isinstance(explanations, (list, tuple))
    explanations_by_key = {}
    if explanations_are_readable:
        for explanation in explanations:
            if isinstance(explanation, dict):
                explanations_by_key.setdefault(
                    (
                        explanation.get("category"),
                        explanation.get("label"),
                    ),
                    explanation,
                )

    if isinstance(manager_summaries, dict):
        enrichment_state = manager_summaries.get("state", "unavailable")
        enrichment_message = manager_summaries.get(
            "message",
            "Optional Gemini summaries are unavailable.",
        )
        summary_items = manager_summaries.get("items", ())
    else:
        enrichment_state = "disabled"
        enrichment_message = (
            "Optional Gemini summaries are off. The deterministic strengths, "
            "trade-offs, and comparisons remain complete."
        )
        summary_items = ()
    summaries_by_key = {
        (item.get("category"), item.get("label")): item
        for item in summary_items
        if isinstance(item, dict)
    }

    strategy_items = []
    teams_by_label = {}
    has_unavailable_explanation = not explanations_are_readable
    for recommendation in recommendations:
        explanation = explanations_by_key.get(
            (
                recommendation.get("category"),
                recommendation.get("label"),
            )
        )
        explanation_is_readable = (
            isinstance(explanation, dict)
            and isinstance(explanation.get("team"), (list, tuple))
            and isinstance(explanation.get("strengths"), (list, tuple))
            and isinstance(explanation.get("tradeoffs"), (list, tuple))
        )
        if explanation_is_readable:
            team = explanation["team"]
            strengths = explanation["strengths"]
            tradeoffs = explanation["tradeoffs"]
            teams_by_label.setdefault(explanation["label"], team)
        else:
            has_unavailable_explanation = True
            team = ()
            strengths = ()
            tradeoffs = ()
        strategy_items.append(
            {
                "state": (
                    "available" if explanation_is_readable else "unavailable"
                ),
                "category": recommendation.get("category"),
                "label": recommendation.get("label"),
                "team": team,
                "strengths": strengths,
                "tradeoffs": tradeoffs,
                "service_recommendation": recommendation,
                "service_explanation": explanation,
                "manager_summary": summaries_by_key.get(
                    (
                        recommendation.get("category"),
                        recommendation.get("label"),
                    ),
                    {
                        "state": (
                            "disabled"
                            if enrichment_state == "disabled"
                            else "unavailable"
                        ),
                        "summary": None,
                    },
                ),
            }
        )

    if strategy_items:
        strategy_state = (
            "unavailable" if has_unavailable_explanation else "available"
        )
    else:
        strategy_state = "empty"

    comparison_items = []
    comparisons_are_readable = isinstance(comparisons, (list, tuple))
    if comparisons_are_readable:
        required_comparison_fields = {
            "from_label",
            "to_label",
            "team_size_change",
            "team_score_change",
            "remaining_capacity_change",
            "max_utilization_change",
            "utilization_spread_change",
        }
        for comparison in comparisons:
            if not isinstance(comparison, dict) or not (
                required_comparison_fields <= comparison.keys()
            ):
                comparisons_are_readable = False
                comparison_items = []
                break
            comparison_items.append(
                {
                    "from_label": comparison["from_label"],
                    "to_label": comparison["to_label"],
                    "from_team": teams_by_label.get(
                        comparison["from_label"],
                        (),
                    ),
                    "to_team": teams_by_label.get(
                        comparison["to_label"],
                        (),
                    ),
                    "team_size_change": comparison["team_size_change"],
                    "team_score_change": comparison["team_score_change"],
                    "remaining_capacity_change": comparison[
                        "remaining_capacity_change"
                    ],
                    "max_utilization_change": comparison[
                        "max_utilization_change"
                    ],
                    "utilization_spread_change": comparison[
                        "utilization_spread_change"
                    ],
                    "service_comparison": comparison,
                }
            )

    comparison_state = (
        "unavailable"
        if not comparisons_are_readable
        else "available"
        if comparison_items
        else "empty"
    )
    return {
        "enrichment": {
            "state": enrichment_state,
            "message": enrichment_message,
        },
        "strategies": {
            "state": strategy_state,
            "items": tuple(strategy_items),
            "service_explanations": explanations,
        },
        "comparisons": {
            "state": comparison_state,
            "items": tuple(comparison_items),
            "service_comparisons": comparisons,
        },
    }


def build_recommendation_generation_context(project, readiness, form):
    is_available = readiness["candidate_assessment_allowed"]
    return {
        "state": "available" if is_available else "blocked",
        "title": (
            "Generate feasible team options"
            if is_available
            else "Recommendation generation is not available"
        ),
        "message": (
            "Start the existing feasibility and recommendation pipeline only "
            "when you are ready to wait for the current project assessment."
            if is_available
            else "Resolve the planning-readiness blockers before starting the "
            "recommendation pipeline."
        ),
        "action_url": reverse(
            "frontend:project_recommendation_generate",
            args=[project.project_id],
        ),
        "form": form if is_available else None,
    }


def build_recommendation_result_foundation(
    project,
    pipeline_result,
    user,
    manager_summaries=None,
):
    recommendation_count = len(pipeline_result["recommendations"])
    if recommendation_count:
        state = "completed"
        label = "Run completed"
        title = "Recommendation generation completed."
        message = (
            f"The existing pipeline returned {recommendation_count} selected "
            f"strateg{'y' if recommendation_count == 1 else 'ies'}. Review "
            "the team-level evidence for each selected strategy below."
        )
    else:
        state = "empty"
        label = "No strategy returned"
        title = "No recommendation strategy was returned."
        message = (
            "The pipeline completed without a selected strategy. This initial "
            "result does not infer which planning condition prevented one."
        )

    strategies = build_recommendation_strategy_cards(
        project,
        pipeline_result["recommendations"],
        user,
    )
    decision_evidence = build_recommendation_decision_evidence(
        pipeline_result["recommendations"],
        pipeline_result["comparisons"],
        pipeline_result["explanations"],
        manager_summaries,
    )
    return {
        "state": state,
        "tone": "success" if recommendation_count else "warning",
        "label": label,
        "title": title,
        "message": message,
        "recommendation_count": recommendation_count,
        "elapsed_seconds": pipeline_result["elapsed_seconds"],
        "pipeline_result": pipeline_result,
        "strategies": strategies,
        "decision_evidence": decision_evidence,
    }


def build_recommendation_error_foundation(state):
    states = {
        "invalid": {
            "label": "Request expired",
            "title": "This recommendation request is no longer valid.",
            "message": (
                "Return to the planning workspace to start a new request. No "
                "recommendation pipeline was started."
            ),
        },
        "duplicate": {
            "label": "Request already submitted",
            "title": "This recommendation request was already submitted.",
            "message": (
                "A second pipeline run was not started. Return to the planning "
                "workspace when you need a new assessment."
            ),
        },
        "error": {
            "label": "Run not completed",
            "title": "Recommendation generation could not be completed.",
            "message": (
                "No recommendation result was saved and no staffing record was "
                "changed. Return to the planning workspace and try again."
            ),
        },
    }
    selected = states[state]
    return {
        "state": state,
        "tone": "warning",
        "recommendation_count": None,
        "elapsed_seconds": None,
        "pipeline_result": None,
        "strategies": {"cards": (), "navigation": {}},
        "decision_evidence": {
            "enrichment": {
                "state": "disabled",
                "message": "Optional Gemini summaries are off.",
            },
            "strategies": {"state": "empty", "items": ()},
            "comparisons": {"state": "empty", "items": ()},
        },
        **selected,
    }
