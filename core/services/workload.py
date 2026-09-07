from decimal import Decimal

from django.db.models import Sum

from core.models import Assignment
from datetime import timedelta

def calculate_current_workload(
    employee,
    on_date,
    exclude_project=None,
    ):
    """
    Calcule la charge totale de l'employé à une date donnée.

    exclude_project permet d'ignorer un projet précis,
    notamment lorsqu'on calcule la capacité disponible
    pour optimiser ce même projet.
    """

    assignments = Assignment.objects.filter(
        employee=employee,
        start_date__lte=on_date,
        end_date__gte=on_date,
    ).exclude(
        status=Assignment.Status.CANCELLED
    )

    if exclude_project is not None:
        assignments = assignments.exclude(
            project=exclude_project
        )

    total = assignments.aggregate(
        total=Sum("allocation_percentage")
    )["total"]

    return total or 0


def calculate_available_capacity(employee, on_date):
    """
    Calculate the remaining percentage of working capacity
    for an employee on a specific date.
    """

    workload = calculate_current_workload(employee, on_date)

    return max(0, 100 - workload)


def calculate_workload_hours(employee, on_date):
    """
    Convert the workload percentage into weekly hours.
    """

    workload = calculate_current_workload(employee, on_date)

    return (
        Decimal(str(workload))
        / Decimal("100")
        * employee.capacity_hours_week
    )


def calculate_available_hours(employee, on_date):
    """
    Calculate remaining weekly working hours.
    """

    available_percentage = calculate_available_capacity(
        employee,
        on_date,
    )

    return (
        Decimal(str(available_percentage))
        / Decimal("100")
        * employee.capacity_hours_week
    )
# ============================================================
# CALCULS SUR UNE PERIODE
# ============================================================


def calculate_max_workload(employee, start_date, end_date):
    """
    Retourne la charge maximale atteinte par l'employé
    pendant toute la période.
    """

    if start_date > end_date:
        raise ValueError("start_date must not be after end_date.")

    current_date = start_date
    max_workload = 0

    while current_date <= end_date:

        workload = calculate_current_workload(
            employee,
            current_date,
        )

        max_workload = max(
            max_workload,
            workload,
        )

        current_date += timedelta(days=1)

    return max_workload


def calculate_average_workload(employee, start_date, end_date):
    """
    Retourne la charge moyenne de l'employé
    pendant toute la période.
    """

    if start_date > end_date:
        raise ValueError("start_date must not be after end_date.")

    current_date = start_date

    workloads = []

    while current_date <= end_date:

        workload = calculate_current_workload(
            employee,
            current_date,
        )

        workloads.append(workload)

        current_date += timedelta(days=1)

    if not workloads:
        return 0

    return round(
        sum(workloads) / len(workloads),
        2,
    )


def calculate_min_available_capacity(employee, start_date, end_date):
    """
    Retourne la capacité minimale disponible pendant la période.

    Exemple :
    si la charge maximale atteint 80 %,
    la capacité minimale disponible est 20 %.
    """

    max_workload = calculate_max_workload(
        employee,
        start_date,
        end_date,
    )

    return max(
        0,
        100 - max_workload,
    )