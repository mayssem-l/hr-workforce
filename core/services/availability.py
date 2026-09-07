from datetime import timedelta

from core.models import Leave


def get_working_days(start_date, end_date):
    """
    Retourne la liste des jours ouvrables (lundi-vendredi)
    compris dans la période.
    """

    if start_date > end_date:
        raise ValueError("start_date must not be after end_date.")

    working_days = []
    current_date = start_date

    while current_date <= end_date:
        # Monday = 0 ... Sunday = 6
        if current_date.weekday() < 5:
            working_days.append(current_date)

        current_date += timedelta(days=1)

    return working_days


def get_approved_leaves(employee, start_date, end_date):
    """
    Retourne les congés approuvés de l'employé
    qui chevauchent la période demandée.
    """

    if start_date > end_date:
        raise ValueError("start_date must not be after end_date.")

    return Leave.objects.filter(
        employee=employee,
        status=Leave.Status.APPROVED,
        start_date__lte=end_date,
        end_date__gte=start_date,
    )


def has_approved_leave(employee, start_date, end_date):
    """
    Indique si l'employé possède au moins un congé approuvé
    qui chevauche la période.
    """

    return get_approved_leaves(
        employee,
        start_date,
        end_date,
    ).exists()


def get_leave_working_days(employee, start_date, end_date):
    """
    Retourne l'ensemble des jours ouvrables pendant lesquels
    l'employé est en congé approuvé.

    Utiliser un set évite de compter deux fois une date
    si deux congés se chevauchent accidentellement.
    """

    approved_leaves = get_approved_leaves(
        employee,
        start_date,
        end_date,
    )

    leave_days = set()

    for leave in approved_leaves:

        actual_start = max(
            start_date,
            leave.start_date,
        )

        actual_end = min(
            end_date,
            leave.end_date,
        )

        current_date = actual_start

        while current_date <= actual_end:

            if current_date.weekday() < 5:
                leave_days.add(current_date)

            current_date += timedelta(days=1)

    return sorted(leave_days)


def calculate_leave_days(employee, start_date, end_date):
    """
    Nombre de jours ouvrables de congé approuvé
    pendant la période.
    """

    return len(
        get_leave_working_days(
            employee,
            start_date,
            end_date,
        )
    )


def calculate_leave_availability_rate(employee, start_date, end_date):
    """
    Pourcentage de jours ouvrables pendant lesquels l'employé
    est disponible du point de vue des congés uniquement.

    Exemple :
    période = 20 jours ouvrables
    congé approuvé = 4 jours

    disponibilité congés = 16 / 20 = 80 %
    """

    working_days = get_working_days(
        start_date,
        end_date,
    )

    total_working_days = len(working_days)

    if total_working_days == 0:
        return 0

    leave_days = calculate_leave_days(
        employee,
        start_date,
        end_date,
    )

    available_days = total_working_days - leave_days

    return round(
        (available_days / total_working_days) * 100,
        2,
    )


def is_fully_available_from_leave(employee, start_date, end_date):
    """
    True si l'employé n'a aucun jour ouvrable
    de congé approuvé pendant la période.
    """

    return calculate_leave_days(
        employee,
        start_date,
        end_date,
    ) == 0