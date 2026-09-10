from django.db.models import Count, Q

from core.models import Attendance


def get_attendance_records(
    employee,
    start_date,
    end_date,
    attendance_records=None,
):
    """
    Retourne les enregistrements Attendance de l'employé
    compris dans la période demandée.
    """

    if start_date > end_date:
        raise ValueError("start_date must not be after end_date.")

    if attendance_records is not None:
        return [
            record
            for record in attendance_records
            if record.employee_id == employee.employee_id
            and start_date <= record.date <= end_date
        ]

    return Attendance.objects.filter(
        employee=employee,
        date__gte=start_date,
        date__lte=end_date,
    )


def get_attendance_summary(
    employee,
    start_date,
    end_date,
    attendance_records=None,
):
    """
    Retourne un résumé de l'historique Attendance
    de l'employé pendant la période.
    """

    records = get_attendance_records(
        employee,
        start_date,
        end_date,
        attendance_records=attendance_records,
    )

    if attendance_records is not None:
        total_days = len(records)
        return {
            "total_days": total_days,
            "present_days": sum(
                record.status == Attendance.Status.PRESENT for record in records
            ),
            "absent_days": sum(
                record.status == Attendance.Status.ABSENT for record in records
            ),
            "late_days": sum(
                record.status == Attendance.Status.LATE for record in records
            ),
            "remote_days": sum(
                record.status == Attendance.Status.REMOTE for record in records
            ),
            "half_days": sum(
                record.status == Attendance.Status.HALF_DAY for record in records
            ),
            "non_absent_days": sum(
                record.status != Attendance.Status.ABSENT for record in records
            ),
        }

    summary = records.aggregate(
        total_days=Count("attendance_id"),

        present_days=Count(
            "attendance_id",
            filter=Q(status=Attendance.Status.PRESENT),
        ),

        absent_days=Count(
            "attendance_id",
            filter=Q(status=Attendance.Status.ABSENT),
        ),

        late_days=Count(
            "attendance_id",
            filter=Q(status=Attendance.Status.LATE),
        ),

        remote_days=Count(
            "attendance_id",
            filter=Q(status=Attendance.Status.REMOTE),
        ),

        half_days=Count(
            "attendance_id",
            filter=Q(status=Attendance.Status.HALF_DAY),
        ),

        non_absent_days=Count(
            "attendance_id",
            filter=~Q(status=Attendance.Status.ABSENT),
        ),
    )

    return summary


def calculate_absenteeism_rate(
    employee,
    start_date,
    end_date,
    attendance_records=None,
):
    """
    Taux d'absentéisme :

    nombre de jours absents
    ----------------------- x 100
    nombre total de jours Attendance enregistrés
    """

    summary = get_attendance_summary(
        employee,
        start_date,
        end_date,
        attendance_records=attendance_records,
    )

    total_days = summary["total_days"]
    absent_days = summary["absent_days"]

    if total_days == 0:
        return 0

    return round(
        (absent_days / total_days) * 100,
        2,
    )


def calculate_late_rate(
    employee,
    start_date,
    end_date,
    attendance_records=None,
):
    """
    Taux de retard parmi les jours où l'employé
    n'était pas absent.

    nombre de jours en retard
    ------------------------- x 100
    nombre de jours travaillés
    """

    summary = get_attendance_summary(
        employee,
        start_date,
        end_date,
        attendance_records=attendance_records,
    )

    late_days = summary["late_days"]
    worked_days = summary["non_absent_days"]

    if worked_days == 0:
        return 0

    return round(
        (late_days / worked_days) * 100,
        2,
    )
