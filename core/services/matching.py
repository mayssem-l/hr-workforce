from django.db.models import Prefetch

from core.models import (
    Assignment,
    Employee,
    EmployeeSkill,
    Leave,
    ProjectSkillRequirement,
)

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
MANDATORY_MULTIPLIER = 1.5
EXPERIENCE_CAP_YEARS = 10


def calculate_skill_score(
    employee,
    project,
    *,
    requirements=None,
    employee_skills=None,
):
    """
    Calcule le score technique Employee <-> Project.

    Le score tient compte de :
    - la présence de la compétence ;
    - employee level vs required level ;
    - la priorité du requirement ;
    - is_mandatory.

    Retourne un score entre 0 et 100.
    """

    if requirements is None:
        requirements = ProjectSkillRequirement.objects.filter(
            project=project
        )

    if not requirements:
        return 0

    total_weight = 0
    earned_score = 0

    for requirement in requirements:

        # -----------------------------
        # 1. Poids selon la priorité
        # -----------------------------

        weight = PRIORITY_WEIGHTS[
            requirement.priority
        ]

        # -----------------------------
        # 2. Bonus de poids si mandatory
        # -----------------------------

        if requirement.is_mandatory:
            weight *= MANDATORY_MULTIPLIER

        total_weight += weight

        # -----------------------------
        # 3. Chercher le skill employé
        # -----------------------------

        if employee_skills is None:
            employee_skill = EmployeeSkill.objects.filter(
                employee=employee,
                skill=requirement.skill,
            ).first()
        else:
            employee_skill = next(
                (
                    skill
                    for skill in employee_skills
                    if skill.skill_id == requirement.skill_id
                ),
                None,
            )

        # Skill absent
        if employee_skill is None:
            continue

        # Niveau insuffisant
        if employee_skill.level < requirement.required_level:
            continue

        # -----------------------------
        # 4. Score lié au niveau
        # -----------------------------

        level_difference = (
            employee_skill.level
            - requirement.required_level
        )

        # Exactement le niveau demandé -> 90
        # +1 niveau                    -> 95
        # +2 niveaux ou plus           -> 100
        requirement_score = min(
            100,
            90 + (level_difference * 5),
        )

        earned_score += (
            requirement_score * weight
        )

    if total_weight == 0:
        return 0

    return round(
        earned_score / total_weight,
        2,
    )


def employee_can_cover_requirement(
    employee,
    project,
    *,
    requirements=None,
    employee_skills=None,
):
    """
    Retourne True si l'employé satisfait au moins
    une exigence de compétence du projet.
    """

    if requirements is None:
        requirements = ProjectSkillRequirement.objects.filter(
            project=project
        )

    for requirement in requirements:

        if employee_skills is None:
            is_qualified = EmployeeSkill.objects.filter(
                employee=employee,
                skill=requirement.skill,
                level__gte=requirement.required_level,
            ).exists()
        else:
            is_qualified = any(
                skill.skill_id == requirement.skill_id
                and skill.level >= requirement.required_level
                for skill in employee_skills
            )

        if is_qualified:

            return True

    return False

def calculate_experience_score(employee):
    """
    Convertit les années d'expérience globale de l'employé
    en un score entre 0 et 100.

    0 an  -> 0
    2 ans -> 20
    5 ans -> 50
    8 ans -> 80
    10 ans ou plus -> 100
    """

    experience = float(employee.experience_years)

    score = (
        experience / EXPERIENCE_CAP_YEARS
    ) * 100

    return round(
        min(score, 100),
        2,
    )

def calculate_employee_project_match(
    employee,
    project,
    *,
    requirements=None,
    employee_skills=None,
    assignment_records=None,
    leave_records=None,
):
    """
    Calcule le score global de matching entre
    un employé et un projet.
    """
    experience_score = calculate_experience_score(
    employee
)
    # Employé inactif -> non candidat
    if employee.status != Employee.Status.ACTIVE:
        return None

    # Il doit pouvoir couvrir au moins un requirement
    if not employee_can_cover_requirement(
        employee,
        project,
        requirements=requirements,
        employee_skills=employee_skills,
    ):
        return None

    skill_score = calculate_skill_score(
        employee,
        project,
        requirements=requirements,
        employee_skills=employee_skills,
    )

    workload_score = calculate_min_available_capacity(
        employee,
        project.start_date,
        project.end_date,
        assignment_records=assignment_records,
    )

    leave_score = calculate_leave_availability_rate(
        employee,
        project.start_date,
        project.end_date,
        leave_records=leave_records,
    )

    final_score = (
    skill_score * 0.55
    + workload_score * 0.20
    + leave_score * 0.15
    + experience_score * 0.10
)

    # final_score = (
    #     skill_score * 0.60
    #     + workload_score * 0.25
    #     + leave_score * 0.15
    # )

    return {
        "employee": employee,
        "skill_score": round(skill_score, 2),
        "workload_score": round(workload_score, 2),
        "leave_score": round(leave_score, 2),
        "final_score": round(final_score, 2),
        "experience_score": round(experience_score, 2),
    }




def rank_employees_for_project(project):
    """
    Retourne les employés éligibles classés
    du meilleur au moins bon candidat.
    """

    requirements = list(
        ProjectSkillRequirement.objects.filter(project=project)
    )
    employee_skills = EmployeeSkill.objects.only(
        "employee_skill_id",
        "employee_id",
        "skill_id",
        "level",
    )
    assignments = (
        Assignment.objects.filter(
            start_date__lte=project.end_date,
            end_date__gte=project.start_date,
        )
        .exclude(status=Assignment.Status.CANCELLED)
        .only(
            "assignment_id",
            "employee_id",
            "start_date",
            "end_date",
            "allocation_percentage",
            "status",
        )
    )
    approved_leaves = Leave.objects.filter(
        status=Leave.Status.APPROVED,
        start_date__lte=project.end_date,
        end_date__gte=project.start_date,
    ).only(
        "leave_id",
        "employee_id",
        "start_date",
        "end_date",
        "status",
    )
    employees = Employee.objects.filter(
        status=Employee.Status.ACTIVE
    ).prefetch_related(
        Prefetch(
            "employee_skills",
            queryset=employee_skills,
            to_attr="matching_skills",
        ),
        Prefetch(
            "assignments",
            queryset=assignments,
            to_attr="matching_assignments",
        ),
        Prefetch(
            "leaves",
            queryset=approved_leaves,
            to_attr="matching_leaves",
        ),
    )

    results = []

    for employee in employees:

        result = calculate_employee_project_match(
            employee,
            project,
            requirements=requirements,
            employee_skills=employee.matching_skills,
            assignment_records=employee.matching_assignments,
            leave_records=employee.matching_leaves,
        )

        if result is not None:
            results.append(result)

    results.sort(
        key=lambda result: result["final_score"],
        reverse=True,
    )

    return results
