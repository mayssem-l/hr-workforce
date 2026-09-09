from core.services.matching import employee_can_cover_requirement


def build_assignment_employee_hints(project, employees):
    """Build advisory labels using the existing qualification service."""
    employees = list(employees)
    project_has_requirements = project.skill_requirements.exists()
    hints = {}

    for employee in employees:
        if project_has_requirements:
            skill_match = employee_can_cover_requirement(employee, project)
            skill_message = (
                "Matches at least one project skill"
                if skill_match
                else "No matching project skill found"
            )
        else:
            skill_message = "No project skills defined"

        hints[employee.employee_id] = {
            "skill_message": skill_message,
            "status": employee.get_status_display(),
        }

    return employees, hints
