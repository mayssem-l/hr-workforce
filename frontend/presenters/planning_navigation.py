from urllib.parse import urlencode

from django.urls import reverse

from frontend.navigation import with_planning_return


def _action(label, url, *, kind="secondary"):
    return {"label": label, "url": url, "kind": kind}


def _planning_url(project):
    return reverse("frontend:project_planning", args=[project.project_id])


def _returned_url(route_name, planning_url, *, args=(), query=None):
    url = reverse(route_name, args=args)
    if query:
        url = f"{url}?{urlencode(query)}"
    return with_planning_return(url, planning_url)


def _employee_profile_url(employee, project, planning_url, *, anchor=""):
    url = _returned_url(
        "frontend:employee_detail",
        planning_url,
        args=[employee.employee_id],
        query={
            "start_date": project.start_date.isoformat(),
            "end_date": project.end_date.isoformat(),
        },
    )
    return f"{url}{anchor}"


def _leave_evidence_url(project, planning_url, *, employee=None):
    query = {
        "status": "approved",
        "from_date": project.start_date.isoformat(),
        "to_date": project.end_date.isoformat(),
    }
    if employee is not None:
        query["employee"] = employee.employee_id
    return _returned_url(
        "frontend:leave_list",
        planning_url,
        query=query,
    )


def _requirement_actions(project, row, user, planning_url):
    requirement = row["requirement"]
    actions = [
        _action(
            "Review employee skill evidence",
            "#planning-candidate-exclusions-title",
        )
    ]
    if user.has_perm("core.change_projectskillrequirement"):
        actions.insert(
            0,
            _action(
                "Edit requirement",
                _returned_url(
                    "frontend:project_requirement_update",
                    planning_url,
                    args=[
                        project.project_id,
                        requirement.project_skill_requirement_id,
                    ],
                ),
                kind="primary",
            ),
        )

    needs_assignment_work = row["coverage_state"]["code"] in {
        "partial_coverage",
        "no_current_coverage",
    }
    if needs_assignment_work and user.has_perm("core.add_assignment"):
        actions.append(
            _action(
                "Add project assignment",
                _returned_url(
                    "frontend:project_assignment_create",
                    planning_url,
                    args=[project.project_id],
                ),
                kind="primary",
            )
        )

    if (
        row["capacity_state"]["code"] == "insufficient_qualified_capacity"
        and user.has_perm("core.view_leave")
    ):
        actions.append(
            _action(
                "Review approved leave",
                _leave_evidence_url(project, planning_url),
            )
        )

    return tuple(actions)


def _readiness_actions(project, blocker, user, planning_url):
    code = blocker["code"]
    requirement = blocker.get("requirement")
    actions = []
    if code == "invalid_project_dates":
        if user.has_perm("core.change_project"):
            actions.append(
                _action(
                    "Edit project schedule",
                    _returned_url(
                        "frontend:project_update",
                        planning_url,
                        args=[project.project_id],
                    ),
                    kind="primary",
                )
            )
    elif code == "mandatory_effort_must_be_positive" and requirement:
        if user.has_perm("core.change_projectskillrequirement"):
            actions.append(
                _action(
                    "Enter requirement effort",
                    _returned_url(
                        "frontend:project_requirement_update",
                        planning_url,
                        args=[
                            project.project_id,
                            requirement.project_skill_requirement_id,
                        ],
                    ),
                    kind="primary",
                )
            )
        actions.append(
            _action(
                "Review requirement evidence",
                f"#requirement-evidence-{requirement.project_skill_requirement_id}",
            )
        )
    elif code == "no_mandatory_requirements":
        if user.has_perm("core.add_projectskillrequirement"):
            actions.append(
                _action(
                    "Add mandatory requirement",
                    _returned_url(
                        "frontend:project_requirement_create",
                        planning_url,
                        args=[project.project_id],
                    ),
                    kind="primary",
                )
            )
        actions.append(
            _action("Review stored requirements", "#planning-requirements-title")
        )
    elif code in {
        "insufficient_eligible_headcount",
        "insufficient_qualified_capacity",
    }:
        if requirement:
            actions.append(
                _action(
                    "Review requirement evidence",
                    f"#requirement-evidence-{requirement.project_skill_requirement_id}",
                )
            )
        else:
            actions.append(
                _action(
                    "Review requirement evidence",
                    "#planning-requirement-evidence-title",
                )
            )
        if code == "insufficient_qualified_capacity" and user.has_perm(
            "core.view_leave"
        ):
            actions.append(
                _action(
                    "Review approved leave",
                    _leave_evidence_url(project, planning_url),
                )
            )
    elif code == "stale_planning_inputs":
        actions.append(
            _action(
                "Refresh planning workspace",
                planning_url,
                kind="primary",
            )
        )
    return tuple(actions)


def add_planning_repair_navigation(workspace, user):
    """Attach permission-aware links without changing planning assessments."""

    project = workspace["project"]
    planning_url = _planning_url(project)
    can_change_workforce = any(
        user.has_perm(permission)
        for permission in (
            "core.change_employee",
            "core.add_employeeskill",
            "core.change_employeeskill",
        )
    )
    has_planning_write = any(
        user.has_perm(permission)
        for permission in (
            "core.change_project",
            "core.add_projectskillrequirement",
            "core.change_projectskillrequirement",
            "core.add_assignment",
            "core.change_assignment",
            "core.add_assignmentskill",
        )
    )

    workspace["repair"] = {
        "planning_url": planning_url,
        "project_edit_url": (
            _returned_url(
                "frontend:project_update",
                planning_url,
                args=[project.project_id],
            )
            if user.has_perm("core.change_project")
            else None
        ),
        "requirement_create_url": (
            _returned_url(
                "frontend:project_requirement_create",
                planning_url,
                args=[project.project_id],
            )
            if user.has_perm("core.add_projectskillrequirement")
            else None
        ),
        "assignment_create_url": (
            _returned_url(
                "frontend:project_assignment_create",
                planning_url,
                args=[project.project_id],
            )
            if user.has_perm("core.add_assignment")
            else None
        ),
        "leave_url": (
            _leave_evidence_url(project, planning_url)
            if user.has_perm("core.view_leave")
            else None
        ),
        "leave_restricted": not user.has_perm("core.view_leave"),
        "is_read_only": not (has_planning_write or can_change_workforce),
    }

    candidate_state = workspace["candidates"]["state"]
    candidate_actions = []
    if candidate_state == "blocked":
        candidate_actions.append(
            _action("Review planning readiness", "#planning-readiness-title")
        )
    elif candidate_state == "empty":
        candidate_actions.extend(
            (
                _action(
                    "Review employee skill evidence",
                    "#planning-candidate-exclusions-title",
                ),
                _action(
                    "Review project requirements",
                    "#planning-requirements-title",
                ),
            )
        )
    workspace["candidates"]["repair_actions"] = tuple(candidate_actions)

    exclusion_state = workspace["candidate_exclusions"]["state"]
    exclusion_actions = []
    if exclusion_state == "blocked":
        exclusion_actions.append(
            _action("Review planning readiness", "#planning-readiness-title")
        )
    elif exclusion_state == "unavailable":
        exclusion_actions.append(
            _action("Refresh planning workspace", planning_url, kind="primary")
        )
    workspace["candidate_exclusions"]["repair_actions"] = tuple(
        exclusion_actions
    )

    for blocker in workspace["readiness"]["blockers"]:
        blocker["repair_actions"] = _readiness_actions(
            project,
            blocker,
            user,
            planning_url,
        )
        blocker["repair_note"] = (
            "Approved dated leave can affect this capacity result, but your "
            "access does not include leave records."
            if blocker["code"] == "insufficient_qualified_capacity"
            and not user.has_perm("core.view_leave")
            else ""
        )

    for row in workspace["candidates"]["rows"]:
        row["profile_url"] = _employee_profile_url(
            row["employee"],
            project,
            planning_url,
        )

    for row in workspace["candidate_exclusions"]["rows"]:
        employee = row["employee"]
        row["profile_url"] = _employee_profile_url(
            employee,
            project,
            planning_url,
        )
        row["repair_action"] = None
        if row["reason_code"] == "inactive_status" and user.has_perm(
            "core.change_employee"
        ):
            row["repair_action"] = _action(
                "Update employee status",
                _returned_url(
                    "frontend:employee_update",
                    planning_url,
                    args=[employee.employee_id],
                ),
                kind="primary",
            )
        elif row["reason_code"] == "no_qualifying_requirement" and (
            user.has_perm("core.add_employeeskill")
            or user.has_perm("core.change_employeeskill")
        ):
            row["repair_action"] = _action(
                "Manage employee skills",
                _employee_profile_url(
                    employee,
                    project,
                    planning_url,
                    anchor="#skills-title",
                ),
                kind="primary",
            )

    for requirement in workspace["requirements"]:
        requirement.repair_edit_url = (
            _returned_url(
                "frontend:project_requirement_update",
                planning_url,
                args=[
                    project.project_id,
                    requirement.project_skill_requirement_id,
                ],
            )
            if user.has_perm("core.change_projectskillrequirement")
            else None
        )

    for row in workspace["requirement_evidence"]["rows"]:
        row["repair_actions"] = _requirement_actions(
            project,
            row,
            user,
            planning_url,
        )
        row["leave_restricted"] = (
            row["capacity_state"]["code"] == "insufficient_qualified_capacity"
            and not user.has_perm("core.view_leave")
        )
        for qualified in row["qualified_rows"]:
            qualified["profile_url"] = _employee_profile_url(
                qualified["employee"],
                project,
                planning_url,
            )
        for coverage in row["coverage_rows"]:
            assignment = coverage["assignment"]
            coverage["profile_url"] = _employee_profile_url(
                coverage["employee"],
                project,
                planning_url,
            )
            coverage["coverage_url"] = _returned_url(
                "frontend:project_assignment_coverage",
                planning_url,
                args=[project.project_id, assignment.assignment_id],
            )

    for assignment in workspace["assignments"]:
        assignment.repair_edit_url = (
            _returned_url(
                "frontend:project_assignment_update",
                planning_url,
                args=[project.project_id, assignment.assignment_id],
            )
            if user.has_perm("core.change_assignment")
            else None
        )
        assignment.repair_coverage_url = _returned_url(
            "frontend:project_assignment_coverage",
            planning_url,
            args=[project.project_id, assignment.assignment_id],
        )

    workspace["requirement_evidence"]["repair_actions"] = (
        (
            _action(
                "Add skill requirement",
                workspace["repair"]["requirement_create_url"],
                kind="primary",
            ),
        )
        if workspace["requirement_evidence"]["state"] == "empty"
        and workspace["repair"]["requirement_create_url"]
        else ()
    )

    return workspace
