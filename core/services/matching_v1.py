from core.models import Employee, EmployeeSkill, ProjectSkillRequirement

from core.services.workload import (
    calculate_min_available_capacity,
)

from core.services.availability import (
    calculate_leave_availability_rate,
)


PRIORITY_WEIGHTS = {
    ProjectSkillRequirement.Priority.LOW: 1,
    ProjectSkillRequirement.Priority.MEDIUM: 2,
    ProjectSkillRequirement.Priority.HIGH: 3,
}


def calculate_skill_score(employee, project):
    """
    Calcule la compatibilité technique entre un employé
    et les requirements d'un projet.

    Le score est compris entre 0 et 100.
    """

    requirements = ProjectSkillRequirement.objects.filter(
        project=project
    )

    if not requirements.exists():
        return 0

    total_weight = 0
    earned_score = 0

    for requirement in requirements:

        weight = PRIORITY_WEIGHTS[requirement.priority]

        total_weight += weight

        employee_skill = EmployeeSkill.objects.filter(
            employee=employee,
            skill=requirement.skill,
        ).first()

        # L'employé ne possède pas cette compétence
        if employee_skill is None:
            continue

        # Niveau insuffisant
        if employee_skill.level < requirement.required_level:
            continue

        # Requirement satisfait
        earned_score += 100 * weight

    if total_weight == 0:
        return 0

    return round(
        earned_score / total_weight,
        2,
    )


def employee_can_cover_requirement(employee, project):
    """
    Retourne True si l'employé satisfait au moins
    une exigence de compétence du projet.
    """

    requirements = ProjectSkillRequirement.objects.filter(
        project=project
    )

    for requirement in requirements:

        if EmployeeSkill.objects.filter(
            employee=employee,
            skill=requirement.skill,
            level__gte=requirement.required_level,
        ).exists():

            return True

    return False


def calculate_employee_project_match(employee, project):
    """
    Calcule le score global de matching entre
    un employé et un projet.
    """

    # Employé inactif -> non candidat
    if employee.status != Employee.Status.ACTIVE:
        return None

    # Il doit pouvoir couvrir au moins un requirement
    if not employee_can_cover_requirement(
        employee,
        project,
    ):
        return None

    skill_score = calculate_skill_score(
        employee,
        project,
    )

    workload_score = calculate_min_available_capacity(
        employee,
        project.start_date,
        project.end_date,
    )

    leave_score = calculate_leave_availability_rate(
        employee,
        project.start_date,
        project.end_date,
    )

    final_score = (
        skill_score * 0.60
        + workload_score * 0.25
        + leave_score * 0.15
    )

    return {
        "employee": employee,
        "skill_score": round(skill_score, 2),
        "workload_score": round(workload_score, 2),
        "leave_score": round(leave_score, 2),
        "final_score": round(final_score, 2),
    }


def rank_employees_for_project(project):
    """
    Retourne les employés éligibles classés
    du meilleur au moins bon candidat.
    """

    results = []

    employees = Employee.objects.filter(
        status=Employee.Status.ACTIVE
    )

    for employee in employees:

        result = calculate_employee_project_match(
            employee,
            project,
        )

        if result is not None:
            results.append(result)

    results.sort(
        key=lambda result: result["final_score"],
        reverse=True,
    )

    return results