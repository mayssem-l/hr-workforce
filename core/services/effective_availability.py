from datetime import timedelta
from decimal import Decimal

from core.models import Employee, Leave
from core.services.workload import calculate_current_workload


def calculate_daily_capacity_hours(employee, on_date):
    """Return stored weekday capacity before workload or leave adjustments."""

    if on_date.weekday() >= 5:
        return Decimal("0.00")
    return employee.capacity_hours_week / Decimal("5")


def is_on_approved_leave(employee, on_date, leave_records=None):
    """
    Retourne True si l'employé est en congé approuvé
    à cette date.
    """

    if leave_records is not None:
        return any(
            leave.employee_id == employee.employee_id
            and leave.status == Leave.Status.APPROVED
            and leave.start_date <= on_date <= leave.end_date
            for leave in leave_records
        )

    return Leave.objects.filter(
        employee=employee,
        status=Leave.Status.APPROVED,
        start_date__lte=on_date,
        end_date__gte=on_date,
    ).exists()


def calculate_daily_available_hours(
    employee,
    on_date,
    exclude_project=None,
    assignment_records=None,
    leave_records=None,
):
    """
    Calcule le nombre d'heures réellement disponibles
    pour un employé sur une journée donnée. Les listes préchargées
    conservent les mêmes règles sans requêtes répétées.
    """

    # Week-end
    if on_date.weekday() >= 5:
        return Decimal("0.00")

    # Employé inactif
    if employee.status == Employee.Status.INACTIVE:
        return Decimal("0.00")

    # Congé approuvé
    if is_on_approved_leave(
        employee,
        on_date,
        leave_records=leave_records,
    ):
        return Decimal("0.00")

    # Capacité quotidienne théorique.
    # Exemple : 40 h / semaine -> 8 h / jour.
    daily_capacity = calculate_daily_capacity_hours(employee, on_date)

    workload = calculate_current_workload(
        employee,
        on_date,
        exclude_project=exclude_project,
        assignment_records=assignment_records,
    )

    workload = Decimal(str(workload))

    available_percentage = max(
        Decimal("0"),
        Decimal("100") - workload,
    )

    available_hours = (
        daily_capacity
        * available_percentage
        / Decimal("100")
    )

    return available_hours.quantize(
        Decimal("0.01")
    )


def calculate_available_hours_for_project(
    employee,
    project,
    assignment_records=None,
    leave_records=None,
):
    """
    Calcule toutes les heures que l'employé peut
    réellement fournir pendant la durée du projet.

    Les affectations au projet lui-même sont exclues.
    """

    current_date = project.start_date
    total_available_hours = Decimal("0.00")

    while current_date <= project.end_date:

        total_available_hours += (
            calculate_daily_available_hours(
                employee,
                current_date,
                exclude_project=project,
                assignment_records=assignment_records,
                leave_records=leave_records,
            )
        )

        current_date += timedelta(days=1)

    return total_available_hours.quantize(
        Decimal("0.01")
    )
