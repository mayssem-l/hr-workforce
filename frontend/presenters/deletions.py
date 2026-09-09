def build_employee_deletion_impact(employee):
    skills = [
        {
            "name": employee_skill.skill.name,
            "level": employee_skill.level,
        }
        for employee_skill in employee.deletion_employee_skills
    ]
    has_related_information = bool(
        skills
        or employee.assignment_count
        or employee.leave_count
        or employee.attendance_count
    )
    return {
        "kind": "employee",
        "skills": skills,
        "assignment_count": employee.assignment_count,
        "leave_count": employee.leave_count,
        "attendance_count": employee.attendance_count,
        "has_related_information": has_related_information,
        "badge_label": (
            "Related information" if has_related_information else "Profile only"
        ),
        "summary": (
            "Deleting this employee will also remove their skills, project "
            "assignments, leave history, and attendance history shown below."
            if has_related_information
            else "This employee has no related information. Only the employee "
            "profile will be deleted."
        ),
        "retained_message": (
            "Projects and skill definitions will not be deleted."
        ),
    }


def build_skill_deletion_impact(skill):
    employees = [
        {
            "name": str(employee_skill.employee),
            "level": employee_skill.level,
        }
        for employee_skill in skill.deletion_employee_skills
    ]
    has_related_information = bool(employees or skill.project_requirement_count)
    return {
        "kind": "skill",
        "employees": employees,
        "project_requirement_count": skill.project_requirement_count,
        "has_related_information": has_related_information,
        "badge_label": "In active use" if has_related_information else "Skill only",
        "summary": (
            "Deleting this skill will remove it from the employee profiles shown "
            "below and from the project requirements that use it."
            if has_related_information
            else "This skill is not used by any employee profile or project "
            "requirement. Only the skill will be deleted."
        ),
        "retained_message": (
            "Employee profiles and projects will not be deleted."
        ),
    }


def build_project_deletion_impact(project):
    requirements = [
        {
            "is_mandatory": requirement.is_mandatory,
            "level": requirement.required_level,
            "name": requirement.skill.name,
            "quantity": requirement.required_quantity,
        }
        for requirement in project.deletion_requirements
    ]
    assignments = [
        {
            "employee": str(assignment.employee),
            "role": assignment.role_on_project,
            "status": assignment.get_status_display(),
        }
        for assignment in project.deletion_assignments
    ]
    has_related_information = bool(
        requirements or assignments or project.deletion_coverage_count
    )
    return {
        "kind": "project",
        "requirements": requirements,
        "assignments": assignments,
        "coverage_count": project.deletion_coverage_count,
        "has_related_information": has_related_information,
        "badge_label": (
            "Planning records included"
            if has_related_information
            else "Project only"
        ),
        "summary": (
            "Deleting this project will also remove its skill requirements, "
            "employee assignments, and requirement coverage shown below."
            if has_related_information
            else "This project has no skill requirements, employee assignments, "
            "or requirement coverage. Only the project will be deleted."
        ),
        "retained_message": (
            "Employee profiles, skill definitions, leave records, and attendance "
            "history will not be deleted."
        ),
    }


def build_assignment_deletion_impact(assignment):
    coverage = [
        {
            "level": link.project_skill_requirement.required_level,
            "name": link.project_skill_requirement.skill.name,
        }
        for link in assignment.deletion_coverage
    ]
    has_related_information = bool(coverage)
    return {
        "kind": "assignment",
        "coverage": coverage,
        "coverage_count": len(coverage),
        "has_related_information": has_related_information,
        "badge_label": (
            "Coverage included" if has_related_information else "Assignment only"
        ),
        "summary": (
            "Deleting this assignment will also remove its requirement coverage "
            "shown below."
            if has_related_information
            else "This assignment has no requirement coverage. Only the "
            "assignment will be deleted."
        ),
        "retained_message": (
            "The employee profile, project, project requirements, and skill "
            "definitions will not be deleted."
        ),
    }
