from core.models import Employee, EmployeeSkill, ProjectSkillRequirement
from itertools import combinations
from core.services.matching import calculate_employee_project_match
from decimal import Decimal

from ortools.sat.python import cp_model

from core.services.effective_availability import (
    calculate_available_hours_for_project,
)

def employee_can_cover_requirement(employee, requirement):
    """
    Retourne True si l'employé possède le skill demandé
    avec un niveau >= au niveau requis.
    """

    return EmployeeSkill.objects.filter(
        employee=employee,
        skill=requirement.skill,
        level__gte=requirement.required_level,
    ).exists()


def get_eligible_employees_for_requirement(requirement):
    """
    Retourne tous les employés actifs capables
    de couvrir un requirement donné.
    """

    employees = Employee.objects.filter(
        status=Employee.Status.ACTIVE
    )

    eligible_employees = []

    for employee in employees:
        if employee_can_cover_requirement(employee, requirement):
            eligible_employees.append(employee)

    return eligible_employees


def build_project_coverage_matrix(project):
    """
    Construit la liste des employés capables de couvrir
    chaque requirement du projet.
    """

    requirements = ProjectSkillRequirement.objects.filter(
        project=project
    ).select_related("skill")

    coverage = []

    for requirement in requirements:

        eligible_employees = get_eligible_employees_for_requirement(
            requirement
        )

        coverage.append(
            {
                "requirement": requirement,
                "skill": requirement.skill,
                "required_level": requirement.required_level,
                "required_quantity": requirement.required_quantity,
                "is_mandatory": requirement.is_mandatory,
                "eligible_employees": eligible_employees,
            }
        )

        

    return coverage
def evaluate_team_coverage(team, project):
    """
    Vérifie si une équipe couvre les requirements du projet.

    Un requirement mandatory doit respecter required_quantity.
    Un requirement optional peut ne pas être couvert sans rendre
    l'équipe invalide.
    """

    requirements = ProjectSkillRequirement.objects.filter(
        project=project
    ).select_related("skill")

    coverage_details = []
    team_is_valid = True

    for requirement in requirements:

        qualified_employees = []

        for employee in team:
            if employee_can_cover_requirement(
                employee,
                requirement,
            ):
                qualified_employees.append(employee)

        covered_quantity = len(qualified_employees)

        requirement_satisfied = (
            covered_quantity
            >= requirement.required_quantity
        )

        # Seuls les requirements mandatory peuvent
        # rendre l'équipe invalide.
        if (
            requirement.is_mandatory
            and not requirement_satisfied
        ):
            team_is_valid = False

        coverage_details.append(
            {
                "requirement": requirement,
                "skill": requirement.skill,
                "required_quantity": requirement.required_quantity,
                "covered_quantity": covered_quantity,
                "is_mandatory": requirement.is_mandatory,
                "is_satisfied": requirement_satisfied,
                "qualified_employees": qualified_employees,
            }
        )

    return {
        "is_valid": team_is_valid,
        "coverage": coverage_details,
    }

def find_minimum_valid_teams(project):
    """
    Cherche toutes les équipes réellement faisables ayant
    le nombre minimum d'employés.

    Le contexte d'optimisation est construit une seule fois,
    puis les combinaisons impossibles sont rejetées avant OR-Tools.
    """

    context = build_optimization_context(project)
    employees = context["employees"]

    for team_size in range(1, len(employees) + 1):

        valid_teams = []

        for team_tuple in combinations(
            employees,
            team_size,
        ):
            team = list(team_tuple)

            # 1. Préfiltrage rapide
            if not passes_fast_feasibility_checks(
                team,
                context,
            ):
                continue

            # 2. Couverture métier complète
            coverage_evaluation = evaluate_team_coverage(
                team,
                project,
            )

            if not coverage_evaluation["is_valid"]:
                continue

            # 3. Allocation réelle avec OR-Tools
            effort_solution = solve_team_effort_allocation(
                team,
                project,
                optimization_context=context,
            )

            if not effort_solution["is_feasible"]:
                continue

            valid_teams.append(
                {
                    "team": team,
                    "coverage": coverage_evaluation["coverage"],
                    "effort_solution": effort_solution,
                }
            )

        # La première taille qui donne au moins une équipe
        # correspond à la taille minimale faisable.
        if valid_teams:
            return valid_teams

    return []


def calculate_team_score(team, project):
    """
    Calcule le score global d'une équipe à partir
    des scores individuels du Matching V2.1.

    Le Team Score correspond à la moyenne
    des scores individuels.
    """

    member_scores = []

    for employee in team:
        match_result = calculate_employee_project_match(
            employee,
            project,
        )

        if match_result is None:
            continue

        member_scores.append(
            {
                "employee": employee,
                "skill_score": match_result["skill_score"],
                "workload_score": match_result["workload_score"],
                "leave_score": match_result["leave_score"],
                "experience_score": match_result["experience_score"],
                "final_score": match_result["final_score"],
            }
        )

    if not member_scores:
        return {
            "team_score": 0,
            "members": [],
        }

    team_score = sum(
        member["final_score"]
        for member in member_scores
    ) / len(member_scores)

    return {
        "team_score": round(team_score, 2),
        "members": member_scores,
    }

def rank_minimum_valid_teams(project):
    """
    Trouve les équipes valides de taille minimale,
    calcule leur score et les classe du meilleur
    au moins bon.

    Les équipes ayant exactement le même score
    reçoivent le même rang.
    """

    valid_teams = find_minimum_valid_teams(project)

    ranked_teams = []

    for result in valid_teams:
        scoring = calculate_team_score(
            result["team"],
            project,
        )

        ranked_teams.append(
            {
                "team": result["team"],
                "coverage": result["coverage"],
                "effort_solution": result["effort_solution"],
                "team_score": scoring["team_score"],
                "members": scoring["members"],
            }
        )

    # Meilleur score en premier
    ranked_teams.sort(
        key=lambda item: item["team_score"],
        reverse=True,
    )

    # Gestion des ex aequo
    previous_score = None
    previous_rank = 0

    for index, result in enumerate(
        ranked_teams,
        start=1,
    ):
        if result["team_score"] == previous_score:
            result["rank"] = previous_rank
        else:
            result["rank"] = index
            previous_rank = index

        previous_score = result["team_score"]

    return ranked_teams
def explain_team(result):
    """
    Construit une explication structurée d'une équipe classée.
    """

    explanations = []

    for coverage in result["coverage"]:

        employees = [
            str(employee)
            for employee in coverage["qualified_employees"]
        ]

        explanations.append(
            {
                "skill": str(coverage["skill"]),
                "mandatory": coverage["is_mandatory"],
                "required_quantity": coverage["required_quantity"],
                "covered_quantity": coverage["covered_quantity"],
                "is_satisfied": coverage["is_satisfied"],
                "covered_by": employees,
            }
        )

    return {
        "rank": result["rank"],
        "team": [
            str(employee)
            for employee in result["team"]
        ],
        "team_score": result["team_score"],
        "requirements": explanations,
    }
HOUR_SCALE = 100
UTILIZATION_SCALE = 10000


def hours_to_units(hours):
    """
    Convertit les heures en entier pour OR-Tools.

    Exemples :
    352.00 h -> 35200
    281.60 h -> 28160
    """

    return int(
        Decimal(str(hours)) * HOUR_SCALE
    )


def units_to_hours(units):
    """
    Convertit les unités OR-Tools en heures.

    Exemples :
    35200 -> 352.00 h
    28160 -> 281.60 h
    """

    return (
        Decimal(units) / Decimal(HOUR_SCALE)
    ).quantize(Decimal("0.01"))

def build_optimization_context(project):
    """
    Précalcule une seule fois les informations qui ne changent
    pas d'une combinaison d'équipe à une autre.
    """

    employees = list(
        Employee.objects.filter(
            status=Employee.Status.ACTIVE
        )
    )

    requirements = list(
        ProjectSkillRequirement.objects.filter(
            project=project,
            is_mandatory=True,
            estimated_effort_hours__gt=0,
        ).select_related("skill")
    )

    # ---------------------------------------------------------
    # Disponibilité calculée UNE SEULE FOIS par employé
    # ---------------------------------------------------------

    available_hours = {}

    for employee in employees:
        hours = calculate_available_hours_for_project(
            employee,
            project,
        )

        available_hours[employee.employee_id] = (
            hours_to_units(hours)
        )

    # ---------------------------------------------------------
    # Éligibilité calculée UNE SEULE FOIS
    # employee -> requirement
    # ---------------------------------------------------------

    eligible_by_requirement = {}

    for requirement in requirements:

        requirement_id = (
            requirement.project_skill_requirement_id
        )

        eligible_by_requirement[requirement_id] = {
            employee.employee_id
            for employee in employees
            if employee_can_cover_requirement(
                employee,
                requirement,
            )
        }

    # ---------------------------------------------------------
    # Effort obligatoire total du projet
    # ---------------------------------------------------------

    total_required_effort = sum(
        hours_to_units(
            requirement.estimated_effort_hours
        )
        for requirement in requirements
    )

    return {
        "employees": employees,
        "requirements": requirements,
        "available_hours": available_hours,
        "eligible_by_requirement": eligible_by_requirement,
        "total_required_effort": total_required_effort,
    }

def passes_fast_feasibility_checks(team, context):
    """
    Rejette rapidement les équipes manifestement impossibles
    avant de lancer OR-Tools.
    """

    team_ids = {
        employee.employee_id
        for employee in team
    }

    # ---------------------------------------------------------
    # 1. Chaque membre doit pouvoir contribuer
    #    à au moins un requirement obligatoire.
    # ---------------------------------------------------------

    for employee in team:

        can_contribute = any(
            employee.employee_id in eligible_ids
            for eligible_ids
            in context["eligible_by_requirement"].values()
        )

        if not can_contribute:
            return False

    # ---------------------------------------------------------
    # 2. Capacité totale suffisante ?
    # ---------------------------------------------------------

    total_team_capacity = sum(
        context["available_hours"][employee_id]
        for employee_id in team_ids
    )

    if (
        total_team_capacity
        < context["total_required_effort"]
    ):
        return False

    # ---------------------------------------------------------
    # 3. Vérifications requirement par requirement
    # ---------------------------------------------------------

    for requirement in context["requirements"]:

        requirement_id = (
            requirement.project_skill_requirement_id
        )

        qualified_ids = (
            team_ids
            & context["eligible_by_requirement"][
                requirement_id
            ]
        )

        # Pas assez de personnes qualifiées
        if (
            len(qualified_ids)
            < requirement.required_quantity
        ):
            return False

        # Pas assez de capacité qualifiée pour ce skill
        qualified_capacity = sum(
            context["available_hours"][employee_id]
            for employee_id in qualified_ids
        )

        required_effort = hours_to_units(
            requirement.estimated_effort_hours
        )

        if qualified_capacity < required_effort:
            return False

    return True

def solve_team_effort_allocation(team, project, optimization_context=None):
    """
    Vérifie et optimise la répartition des heures obligatoires
    du projet entre les membres d'une équipe.

    Priorités :
    1. Respecter toutes les contraintes métier.
    2. Minimiser les participations inutiles aux skills.
    3. Minimiser le taux d'utilisation maximum.
    4. Parmi ces solutions, maximiser le taux d'utilisation minimum
    afin de réduire l'écart de charge entre les membres.
    """

    # ---------------------------------------------------------
    # 1. Vérification technique de base
    # ---------------------------------------------------------

    coverage_evaluation = evaluate_team_coverage(
        team,
        project,
    )

    if not coverage_evaluation["is_valid"]:
        return {
            "is_feasible": False,
            "reason": "Mandatory skill coverage is not satisfied.",
            "allocations": [],
        }

    # ---------------------------------------------------------
    # 2. Requirements obligatoires avec effort > 0
    # ---------------------------------------------------------
    if optimization_context is None:
        requirements = list(
            ProjectSkillRequirement.objects.filter(
                project=project,
                is_mandatory=True,
                estimated_effort_hours__gt=0,
            ).select_related("skill")
        )
    else:
        requirements = optimization_context[
            "requirements"
        ]

    # ---------------------------------------------------------
    # 3. Heures réellement disponibles par employé
    # ---------------------------------------------------------

    available_hours = {}

    if optimization_context is None:

        for employee in team:
            hours = calculate_available_hours_for_project(
                employee,
                project,
            )

            available_hours[
                employee.employee_id
            ] = hours_to_units(hours)

    else:

        for employee in team:

            available_hours[
                employee.employee_id
            ] = optimization_context[
                "available_hours"
            ][employee.employee_id]


    # ---------------------------------------------------------
    # 4. Modèle OR-Tools
    # ---------------------------------------------------------

    model = cp_model.CpModel()

    hour_variables = {}
    participation_variables = {}

    # ---------------------------------------------------------
    # 5. Variables employee <-> requirement
    # ---------------------------------------------------------

    for employee in team:

        employee_capacity = available_hours[
            employee.employee_id
        ]

        for requirement in requirements:

            # if not employee_can_cover_requirement(
            #     employee,
            #     requirement,
            # ):
            #     continue
            if optimization_context is None:

                can_cover = employee_can_cover_requirement(
                    employee,
                    requirement,
                )

            else:

                requirement_id = (
                    requirement.project_skill_requirement_id
                )

                can_cover = (
                    employee.employee_id
                    in optimization_context[
                        "eligible_by_requirement"
                    ][requirement_id]
                )

            if not can_cover:
                continue

            requirement_effort = hours_to_units(
                requirement.estimated_effort_hours
            )

            maximum_hours = min(
                employee_capacity,
                requirement_effort,
            )

            key = (
                employee.employee_id,
                requirement.project_skill_requirement_id,
            )

            hours_var = model.NewIntVar(
                0,
                maximum_hours,
                (
                    f"hours_employee_{employee.employee_id}"
                    f"_requirement_"
                    f"{requirement.project_skill_requirement_id}"
                ),
            )

            participation_var = model.NewBoolVar(
                (
                    f"participates_employee_{employee.employee_id}"
                    f"_requirement_"
                    f"{requirement.project_skill_requirement_id}"
                )
            )

            hour_variables[key] = hours_var
            participation_variables[key] = participation_var

            # participation = 0 -> 0 heure
            model.Add(
                hours_var
                <= maximum_hours * participation_var
            )

            # participation = 1 -> au moins 1 heure
            model.Add(
                hours_var
                >= HOUR_SCALE * participation_var
            )
    # ---------------------------------------------------------
    # Chaque membre sélectionné dans l'équipe doit
    # réellement participer à au moins un requirement.
    # ---------------------------------------------------------

    for employee in team:

        employee_participations = [
            variable
            for (
                employee_id,
                requirement_id,
            ), variable in participation_variables.items()
            if employee_id == employee.employee_id
        ]

        # L'employé ne peut couvrir aucun requirement mandatory
        if not employee_participations:
            return {
                "is_feasible": False,
                "reason": (
                    f"{employee} cannot contribute to any "
                    f"mandatory requirement."
                ),
                "allocations": [],
            }

        # Chaque membre de l'équipe doit participer
        # à au moins un requirement.
        model.Add(
            sum(employee_participations) >= 1
        )        

    # ---------------------------------------------------------
    # 6. Capacité totale de chaque employé
    # ---------------------------------------------------------

    employee_hour_expressions = {}

    for employee in team:

        employee_variables = [
            variable
            for (
                employee_id,
                requirement_id,
            ), variable in hour_variables.items()
            if employee_id == employee.employee_id
        ]

        if employee_variables:
            used_hours = sum(employee_variables)
        else:
            used_hours = 0

        employee_hour_expressions[
            employee.employee_id
        ] = used_hours

        model.Add(
            used_hours
            <= available_hours[employee.employee_id]
        )

    # ---------------------------------------------------------
    # 7. Contraintes des requirements
    # ---------------------------------------------------------

    for requirement in requirements:

        requirement_id = (
            requirement.project_skill_requirement_id
        )

        requirement_hour_variables = [
            variable
            for (
                employee_id,
                current_requirement_id,
            ), variable in hour_variables.items()
            if current_requirement_id == requirement_id
        ]

        requirement_participation_variables = [
            variable
            for (
                employee_id,
                current_requirement_id,
            ), variable in participation_variables.items()
            if current_requirement_id == requirement_id
        ]

        if not requirement_hour_variables:
            return {
                "is_feasible": False,
                "reason": (
                    f"No qualified employee available "
                    f"for {requirement.skill}."
                ),
                "allocations": [],
            }

        required_effort = hours_to_units(
            requirement.estimated_effort_hours
        )

        # Toutes les heures du requirement doivent être réalisées.
        model.Add(
            sum(requirement_hour_variables)
            == required_effort
        )

        # Au moins required_quantity employés doivent participer.
        model.Add(
            sum(requirement_participation_variables)
            >= requirement.required_quantity
        )

    # ---------------------------------------------------------
    # 8. PRIORITÉ 1 :
    #    minimiser les participations inutiles
    # ---------------------------------------------------------

    total_participations = sum(
        participation_variables.values()
    )

    model.Minimize(
        total_participations
    )

    solver = cp_model.CpSolver()

    status = solver.Solve(model)

    if status not in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE,
    ):
        return {
            "is_feasible": False,
            "reason": (
                "The team does not have enough qualified "
                "available hours to complete the mandatory effort."
            ),
            "allocations": [],
        }

    minimum_participations = solver.Value(
        total_participations
    )

    # On fixe maintenant ce meilleur résultat.
    model.Add(
        total_participations
        == minimum_participations
    )

    # ---------------------------------------------------------
    # 9. PRIORITÉ 2 :
    #    minimiser le taux d'utilisation maximum
    # ---------------------------------------------------------

    max_utilization = model.NewIntVar(
        0,
        UTILIZATION_SCALE,
        "max_utilization",
    )

    for employee in team:

        capacity = available_hours[
            employee.employee_id
        ]

        if capacity <= 0:
            continue

        used_hours = employee_hour_expressions[
            employee.employee_id
        ]

        # used / capacity <= max_utilization
        #
        # On évite les nombres décimaux grâce
        # à UTILIZATION_SCALE.
        model.Add(
            used_hours * UTILIZATION_SCALE
            <= max_utilization * capacity
        )

    model.Minimize(
        max_utilization
    )

    status = solver.Solve(model)

    if status not in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE,
    ):
        return {
            "is_feasible": False,
            "reason": (
                "No balanced feasible allocation was found."
            ),
            "allocations": [],
        }

    # ---------------------------------------------------------
    # 10. Fixer le meilleur max_utilization trouvé
    # ---------------------------------------------------------

    best_max_utilization = solver.Value(
        max_utilization
    )

    model.Add(
        max_utilization
        == best_max_utilization
    )


    # ---------------------------------------------------------
    # 11. PRIORITÉ 3 :
    #     maximiser l'utilisation minimum
    # ---------------------------------------------------------

    min_utilization = model.NewIntVar(
        0,
        UTILIZATION_SCALE,
        "min_utilization",
    )

    for employee in team:

        capacity = available_hours[
            employee.employee_id
        ]

        if capacity <= 0:
            continue

        used_hours = employee_hour_expressions[
            employee.employee_id
        ]

        model.Add(
            used_hours * UTILIZATION_SCALE
            >= min_utilization * capacity
        )

    model.Maximize(
        min_utilization
    )

    status = solver.Solve(model)

    if status not in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE,
    ):
        return {
            "is_feasible": False,
            "reason": (
                "No allocation with optimized "
                "minimum utilization was found."
            ),
            "allocations": [],
        }

    

    # ---------------------------------------------------------
    # 12. Lire les allocations
    # ---------------------------------------------------------

    allocations = []

    for requirement in requirements:

        for employee in team:

            key = (
                employee.employee_id,
                requirement.project_skill_requirement_id,
            )

            if key not in hour_variables:
                continue

            allocated_units = solver.Value(
                hour_variables[key]
            )

            if allocated_units > 0:
                allocations.append(
                    {
                        "employee": employee,
                        "requirement": requirement,
                        "skill": requirement.skill,
                        "hours": units_to_hours(
                            allocated_units
                        ),
                    }
                )

    # ---------------------------------------------------------
    # 13. Capacités + utilisation réelle
    # ---------------------------------------------------------

    employee_capacities = []

    for employee in team:

        capacity_units = available_hours[
            employee.employee_id
        ]

        used_expression = employee_hour_expressions[
            employee.employee_id
        ]

        if isinstance(used_expression, int):
            used_units = used_expression
        else:
            used_units = solver.Value(
                used_expression
            )

        if capacity_units > 0:
            utilization_rate = round(
                (used_units / capacity_units) * 100,
                2,
            )
        else:
            utilization_rate = 0

        employee_capacities.append(
            {
                "employee": employee,
                "available_hours": units_to_hours(
                    capacity_units
                ),
                "allocated_hours": units_to_hours(
                    used_units
                ),
                "utilization_rate": utilization_rate,
            }
        )

    return {
        "is_feasible": True,
        "reason": (
            "The team can absorb all mandatory effort."
        ),
        "minimum_participations": minimum_participations,
        "allocations": allocations,
        "employee_capacities": employee_capacities,
    }

def calculate_team_metrics(team_result):
    """
    Calcule les métriques de charge et de capacité
    d'une équipe déjà validée par OR-Tools.

    Aucun nouveau calcul de disponibilité ni appel OR-Tools
    n'est effectué ici : on réutilise les résultats existants.
    """

    capacities = team_result[
        "effort_solution"
    ]["employee_capacities"]

    if not capacities:
        return None

    # ---------------------------------------------------------
    # 1. Capacité totale disponible de l'équipe
    # ---------------------------------------------------------

    total_available_hours = sum(
        item["available_hours"]
        for item in capacities
    )

    # ---------------------------------------------------------
    # 2. Heures réellement affectées au projet
    # ---------------------------------------------------------

    total_allocated_hours = sum(
        item["allocated_hours"]
        for item in capacities
    )

    # ---------------------------------------------------------
    # 3. Capacité restante après affectation
    # ---------------------------------------------------------

    remaining_capacity_hours = (
        total_available_hours
        - total_allocated_hours
    )

    # ---------------------------------------------------------
    # 4. Taux d'utilisation global de l'équipe
    # ---------------------------------------------------------

    if total_available_hours > 0:
        team_utilization_rate = round(
            float(
                total_allocated_hours
                / total_available_hours
                * 100
            ),
            2,
        )
    else:
        team_utilization_rate = 0

    # ---------------------------------------------------------
    # 5. Taux individuels
    # ---------------------------------------------------------

    utilization_rates = [
        item["utilization_rate"]
        for item in capacities
    ]

    average_utilization = round(
        sum(utilization_rates)
        / len(utilization_rates),
        2,
    )

    max_utilization = max(
        utilization_rates
    )

    min_utilization = min(
        utilization_rates
    )

    # ---------------------------------------------------------
    # 6. Écart de charge entre le membre le plus
    #    chargé et le moins chargé
    # ---------------------------------------------------------

    utilization_spread = round(
        max_utilization - min_utilization,
        2,
    )

    return {
        "team_size": len(team_result["team"]),
        "total_available_hours": total_available_hours,
        "total_allocated_hours": total_allocated_hours,
        "remaining_capacity_hours": remaining_capacity_hours,
        "team_utilization_rate": team_utilization_rate,
        "average_utilization": average_utilization,
        "max_utilization": max_utilization,
        "min_utilization": min_utilization,
        "utilization_spread": utilization_spread,
    }

def dominates(team_a, team_b):
    """
    Retourne True si team_a domine team_b.

    team_a doit être :
    - au moins aussi bonne que team_b sur tous les critères ;
    - strictement meilleure sur au moins un critère.
    """

    metrics_a = team_a["metrics"]
    metrics_b = team_b["metrics"]

    # ---------------------------------------------------------
    # A doit être au moins aussi bonne partout.
    # ---------------------------------------------------------

    at_least_as_good = (
        team_a["team_score"] >= team_b["team_score"]
        and metrics_a["remaining_capacity_hours"]
        >= metrics_b["remaining_capacity_hours"]
        and metrics_a["max_utilization"]
        <= metrics_b["max_utilization"]
        and metrics_a["utilization_spread"]
        <= metrics_b["utilization_spread"]
        and team_a["team_size"]
        <= team_b["team_size"]
    )

    if not at_least_as_good:
        return False

    # ---------------------------------------------------------
    # Et A doit être strictement meilleure
    # sur au moins un critère.
    # ---------------------------------------------------------

    strictly_better = (
        team_a["team_score"] > team_b["team_score"]
        or metrics_a["remaining_capacity_hours"]
        > metrics_b["remaining_capacity_hours"]
        or metrics_a["max_utilization"]
        < metrics_b["max_utilization"]
        or metrics_a["utilization_spread"]
        < metrics_b["utilization_spread"]
        or team_a["team_size"]
        < team_b["team_size"]
    )

    return strictly_better

def find_pareto_teams(teams):
    """
    Conserve uniquement les équipes non dominées.

    Une équipe est retirée si une autre équipe est
    au moins aussi bonne sur tous les critères et
    meilleure sur au moins un.
    """

    pareto_teams = []

    for candidate in teams:

        is_dominated = False

        for other in teams:

            if candidate is other:
                continue

            if dominates(
                other,
                candidate,
            ):
                is_dominated = True
                break

        if not is_dominated:
            pareto_teams.append(candidate)

    return pareto_teams

def select_recommended_teams(pareto_teams):
    """
    Sélectionne jusqu'à 3 recommandations distinctes
    parmi les équipes Pareto.

    Stratégies :
    1. Compact match :
       meilleure équipe de taille minimale.

    2. Balanced alternative :
       meilleure équipe avec un membre supplémentaire,
       en privilégiant une faible charge maximale.

    3. Capacity alternative :
       meilleure équipe avec deux membres supplémentaires,
       en privilégiant la réserve de capacité.

    Aucun score pondéré supplémentaire n'est utilisé.
    """

    if not pareto_teams:
        return []

    recommendations = []

    # ---------------------------------------------------------
    # Taille minimale trouvée parmi les équipes Pareto
    # ---------------------------------------------------------

    min_team_size = min(
        team["team_size"]
        for team in pareto_teams
    )

    # =========================================================
    # 1. MEILLEURE ÉQUIPE COMPACTE
    # =========================================================

    compact_candidates = [
        team
        for team in pareto_teams
        if team["team_size"] == min_team_size
    ]

    if compact_candidates:

        compact_team = max(
            compact_candidates,
            key=lambda team: (
                team["team_score"],
                -team["metrics"]["max_utilization"],
                -team["metrics"]["utilization_spread"],
            ),
        )

        recommendations.append(
            {
                "category": "compact_match",
                "label": "Best compact match",
                "reason": (
                    "Smallest feasible team with the strongest "
                    "overall matching quality."
                ),
                "result": compact_team,
            }
        )

    # =========================================================
    # 2. MEILLEURE ALTERNATIVE ÉQUILIBRÉE
    # =========================================================

    balanced_size = min_team_size + 1

    balanced_candidates = [
        team
        for team in pareto_teams
        if team["team_size"] == balanced_size
    ]

    if balanced_candidates:

        balanced_team = min(
            balanced_candidates,
            key=lambda team: (
                team["metrics"]["max_utilization"],
                team["metrics"]["utilization_spread"],
                -team["team_score"],
            ),
        )

        recommendations.append(
            {
                "category": "balanced",
                "label": "Best balanced alternative",
                "reason": (
                    "Uses one additional employee to reduce "
                    "individual workload while keeping the "
                    "allocation well balanced."
                ),
                "result": balanced_team,
            }
        )

    # =========================================================
    # 3. MEILLEURE ALTERNATIVE DE CAPACITÉ
    # =========================================================

    capacity_size = min_team_size + 2

    capacity_candidates = [
        team
        for team in pareto_teams
        if team["team_size"] == capacity_size
    ]

    if capacity_candidates:

        capacity_team = max(
            capacity_candidates,
            key=lambda team: (
                team["metrics"]["remaining_capacity_hours"],
                team["team_score"],
                -team["metrics"]["max_utilization"],
            ),
        )

        recommendations.append(
            {
                "category": "capacity",
                "label": "Best capacity alternative",
                "reason": (
                    "Provides greater remaining capacity while "
                    "limiting the team to two additional members "
                    "beyond the minimum feasible size."
                ),
                "result": capacity_team,
            }
        )

    return recommendations

def compare_recommendations(recommendations):
    """
    Compare chaque recommandation avec la précédente
    et calcule les écarts sur les principaux critères.
    """

    comparisons = []

    for index in range(1, len(recommendations)):

        previous_rec = recommendations[index - 1]
        current_rec = recommendations[index]

        previous = previous_rec["result"]
        current = current_rec["result"]

        previous_metrics = previous["metrics"]
        current_metrics = current["metrics"]

        comparisons.append(
            {
                "from_label": previous_rec["label"],
                "to_label": current_rec["label"],

                "team_size_change": (
                    current["team_size"]
                    - previous["team_size"]
                ),

                "team_score_change": round(
                    current["team_score"]
                    - previous["team_score"],
                    2,
                ),

                "remaining_capacity_change": (
                    current_metrics["remaining_capacity_hours"]
                    - previous_metrics["remaining_capacity_hours"]
                ),

                "max_utilization_change": round(
                    current_metrics["max_utilization"]
                    - previous_metrics["max_utilization"],
                    2,
                ),

                "utilization_spread_change": round(
                    current_metrics["utilization_spread"]
                    - previous_metrics["utilization_spread"],
                    2,
                ),
            }
        )

    return comparisons

# def build_recommendation_explanations(
#     recommendations,
#     comparisons,
# ):
#     """
#     Construit des explications factuelles pour les
#     recommandations sélectionnées.

#     Aucun LLM n'est utilisé ici.
#     Les explications proviennent uniquement des métriques
#     et des écarts déjà calculés.
#     """

#     explanations = []

#     # Permet de retrouver rapidement la comparaison
#     # correspondant à une recommandation.
#     comparison_by_target = {
#         comparison["to_label"]: comparison
#         for comparison in comparisons
#     }

#     for recommendation in recommendations:

#         result = recommendation["result"]
#         metrics = result["metrics"]

#         strengths = []
#         tradeoffs = []

#         # -----------------------------------------------------
#         # 1. Informations propres à la catégorie
#         # -----------------------------------------------------

#         category = recommendation["category"]

#         if category == "compact_match":

#             strengths.append(
#                 (
#                     f"Mobilise seulement "
#                     f"{result['team_size']} employés."
#                 )
#             )

#             strengths.append(
#                 (
#                     f"Matching moyen élevé : "
#                     f"{result['team_score']:.2f}."
#                 )
#             )

#             strengths.append(
#                 (
#                     f"Charge maximale : "
#                     f"{metrics['max_utilization']:.2f}%."
#                 )
#             )

#             strengths.append(
#                 (
#                     f"Écart de charge très faible : "
#                     f"{metrics['utilization_spread']:.2f} points."
#                 )
#             )

#         # -----------------------------------------------------
#         # 2. Comparaison avec la recommandation précédente
#         # -----------------------------------------------------

#         comparison = comparison_by_target.get(
#             recommendation["label"]
#         )

#         if comparison is not None:

#             # Taille d'équipe
#             size_change = comparison[
#                 "team_size_change"
#             ]

#             if size_change > 0:
#                 tradeoffs.append(
#                     (
#                         f"Mobilise {size_change} employé(s) "
#                         f"supplémentaire(s)."
#                     )
#                 )
#             elif size_change < 0:
#                 strengths.append(
#                     (
#                         f"Mobilise {abs(size_change)} employé(s) "
#                         f"de moins."
#                     )
#                 )

#             # Matching
#             score_change = comparison[
#                 "team_score_change"
#             ]

#             if score_change > 0:
#                 strengths.append(
#                     (
#                         f"Améliore le matching moyen de "
#                         f"{score_change:.2f} points."
#                     )
#                 )
#             elif score_change < 0:
#                 tradeoffs.append(
#                     (
#                         f"Réduit le matching moyen de "
#                         f"{abs(score_change):.2f} points."
#                     )
#                 )

#             # Capacité restante
#             capacity_change = comparison[
#                 "remaining_capacity_change"
#             ]

#             if capacity_change > 0:
#                 strengths.append(
#                     (
#                         f"Ajoute {capacity_change:.2f} h "
#                         f"de capacité restante."
#                     )
#                 )
#             elif capacity_change < 0:
#                 tradeoffs.append(
#                     (
#                         f"Réduit la capacité restante de "
#                         f"{abs(capacity_change):.2f} h."
#                     )
#                 )

#             # Charge maximale
#             max_util_change = comparison[
#                 "max_utilization_change"
#             ]

#             if max_util_change < 0:
#                 strengths.append(
#                     (
#                         f"Réduit la charge maximale de "
#                         f"{abs(max_util_change):.2f} points."
#                     )
#                 )
#             elif max_util_change > 0:
#                 tradeoffs.append(
#                     (
#                         f"Augmente la charge maximale de "
#                         f"{max_util_change:.2f} points."
#                     )
#                 )

#             # Équilibre de charge
#             spread_change = comparison[
#                 "utilization_spread_change"
#             ]

#             if spread_change < 0:
#                 strengths.append(
#                     (
#                         f"Améliore l'équilibre de charge de "
#                         f"{abs(spread_change):.2f} points."
#                     )
#                 )
#             elif spread_change > 0:
#                 tradeoffs.append(
#                     (
#                         f"Augmente l'écart de charge de "
#                         f"{spread_change:.2f} points."
#                     )
#                 )

#         explanations.append(
#             {
#                 "category": recommendation["category"],
#                 "label": recommendation["label"],
#                 "team": [
#                     str(employee)
#                     for employee in result["team"]
#                 ],
#                 "strengths": strengths,
#                 "tradeoffs": tradeoffs,
#             }
#         )

#     return explanations

def build_recommendation_explanations(
    recommendations,
    comparisons,
):
    """
    Construit des explications factuelles et complètes
    pour les recommandations sélectionnées.

    Aucun LLM n'est utilisé ici.
    Toutes les explications proviennent des métriques
    et des écarts déjà calculés.
    """

    explanations = []

    comparison_by_target = {
        comparison["to_label"]: comparison
        for comparison in comparisons
    }

    comparison_by_source = {
        comparison["from_label"]: comparison
        for comparison in comparisons
    }

    for recommendation in recommendations:

        result = recommendation["result"]
        metrics = result["metrics"]

        strengths = []
        tradeoffs = []

        category = recommendation["category"]
        label = recommendation["label"]

        # -----------------------------------------------------
        # 1. Informations propres à l'équipe
        # -----------------------------------------------------

        if category == "compact_match":

            strengths.append(
                f"Mobilise seulement {result['team_size']} employés."
            )

            strengths.append(
                f"Matching moyen élevé : {result['team_score']:.2f}."
            )

            strengths.append(
                (
                    f"Répartition de charge très homogène : "
                    f"écart de {metrics['utilization_spread']:.2f} points."
                )
            )

            # Comparaison avec l'alternative suivante
            next_comparison = comparison_by_source.get(label)

            if next_comparison is not None:

                capacity_change = next_comparison[
                    "remaining_capacity_change"
                ]

                if capacity_change > 0:
                    tradeoffs.append(
                        (
                            f"Dispose de {capacity_change:.2f} h "
                            f"de capacité restante en moins que "
                            f"l'alternative équilibrée."
                        )
                    )

                max_util_change = next_comparison[
                    "max_utilization_change"
                ]

                if max_util_change < 0:
                    tradeoffs.append(
                        (
                            f"Charge maximale supérieure de "
                            f"{abs(max_util_change):.2f} points "
                            f"à l'alternative équilibrée."
                        )
                    )

        # -----------------------------------------------------
        # 2. Autres recommandations :
        #    comparaison avec la recommandation précédente
        # -----------------------------------------------------

        else:

            comparison = comparison_by_target.get(label)

            if comparison is not None:

                size_change = comparison[
                    "team_size_change"
                ]

                if size_change > 0:
                    tradeoffs.append(
                        (
                            f"Mobilise {size_change} employé(s) "
                            f"supplémentaire(s)."
                        )
                    )

                score_change = comparison[
                    "team_score_change"
                ]

                if score_change > 0:
                    strengths.append(
                        (
                            f"Améliore le matching moyen de "
                            f"{score_change:.2f} points."
                        )
                    )

                elif score_change < 0:
                    tradeoffs.append(
                        (
                            f"Réduit le matching moyen de "
                            f"{abs(score_change):.2f} points."
                        )
                    )

                capacity_change = comparison[
                    "remaining_capacity_change"
                ]

                if capacity_change > 0:
                    strengths.append(
                        (
                            f"Ajoute {capacity_change:.2f} h "
                            f"de capacité restante."
                        )
                    )

                elif capacity_change < 0:
                    tradeoffs.append(
                        (
                            f"Réduit la capacité restante de "
                            f"{abs(capacity_change):.2f} h."
                        )
                    )

                max_util_change = comparison[
                    "max_utilization_change"
                ]

                if max_util_change < 0:
                    strengths.append(
                        (
                            f"Réduit la charge maximale de "
                            f"{abs(max_util_change):.2f} points."
                        )
                    )

                elif max_util_change > 0:
                    tradeoffs.append(
                        (
                            f"Augmente la charge maximale de "
                            f"{max_util_change:.2f} points."
                        )
                    )

                spread_change = comparison[
                    "utilization_spread_change"
                ]

                if spread_change < 0:
                    strengths.append(
                        (
                            f"Améliore l'équilibre de charge de "
                            f"{abs(spread_change):.2f} points."
                        )
                    )

                elif spread_change > 0:
                    tradeoffs.append(
                        (
                            f"Augmente l'écart de charge de "
                            f"{spread_change:.2f} points."
                        )
                    )

        explanations.append(
            {
                "category": category,
                "label": label,
                "team": [
                    str(employee)
                    for employee in result["team"]
                ],
                "strengths": strengths,
                "tradeoffs": tradeoffs,
            }
        )

    return explanations


def find_all_feasible_teams(project):
    """
    Teste toutes les combinaisons d'employés actifs et conserve
    uniquement les équipes réellement faisables.

    Les informations stables du projet sont précalculées une fois.
    Les équipes manifestement impossibles sont rejetées avant
    d'appeler OR-Tools.
    """

    context = build_optimization_context(project)
    employees = context["employees"]

    feasible_teams = []

    for team_size in range(
        1,
        len(employees) + 1,
    ):

        for team_tuple in combinations(
            employees,
            team_size,
        ):
            team = list(team_tuple)

            # 1. Préfiltrage rapide en mémoire
            if not passes_fast_feasibility_checks(
                team,
                context,
            ):
                continue

            # 2. Couverture métier complète
            coverage_evaluation = evaluate_team_coverage(
                team,
                project,
            )

            if not coverage_evaluation["is_valid"]:
                continue

            # 3. Faisabilité réelle des heures avec OR-Tools
            effort_solution = solve_team_effort_allocation(
                team,
                project,
                optimization_context=context,
            )

            if not effort_solution["is_feasible"]:
                continue

            # 4. Matching
            scoring = calculate_team_score(
                team,
                project,
            )

            # # 5. Conserver la solution faisable
            # feasible_teams.append(
            #     {
            #         "team": team,
            #         "team_size": len(team),
            #         "coverage": coverage_evaluation["coverage"],
            #         "effort_solution": effort_solution,
            #         "team_score": scoring["team_score"],
            #         "members": scoring["members"],
            #     }
            # )
            team_result = {
                "team": team,
                "team_size": len(team),
                "coverage": coverage_evaluation["coverage"],
                "effort_solution": effort_solution,
                "team_score": scoring["team_score"],
                "members": scoring["members"],
            }

            team_result["metrics"] = calculate_team_metrics(
                team_result
            )

            feasible_teams.append(
                team_result
            )

    return feasible_teams

