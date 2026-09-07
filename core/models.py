from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def validate_date_range(start_date, end_date):
    if start_date and end_date and start_date > end_date:
        raise ValidationError({"end_date": "start_date must not be after end_date."})


class Employee(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        ON_LEAVE = "on_leave", "On leave"

    employee_id = models.AutoField(primary_key=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    department = models.CharField(max_length=100)
    position = models.CharField(max_length=100)
    hire_date = models.DateField()
    experience_years = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        validators=[MinValueValidator(0)],
    )
    capacity_hours_week = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    status = models.CharField(max_length=20, choices=Status.choices)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Skill(models.Model):
    skill_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=100)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return self.name


class EmployeeSkill(models.Model):
    employee_skill_id = models.AutoField(primary_key=True)
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="employee_skills",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="employee_skills",
    )
    level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Employee skill proficiency from 1 to 5.",
    )
    years_experience = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "skill"],
                name="unique_employee_skill",
            ),
            models.CheckConstraint(
                condition=models.Q(level__gte=1) & models.Q(level__lte=5),
                name="employeeskill_level_between_1_and_5",
            ),
        ]

    def __str__(self):
        return f"{self.employee} – {self.skill} (level {self.level})"


class Project(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        IN_PROGRESS = "in_progress", "In progress"
        ON_HOLD = "on_hold", "On hold"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Criticality(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    project_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=200)
    description = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField()
    estimated_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    status = models.CharField(max_length=20, choices=Status.choices)
    priority = models.CharField(max_length=20, choices=Priority.choices)
    criticality = models.CharField(max_length=20, choices=Criticality.choices)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="project_start_date_not_after_end_date",
            ),
        ]

    def clean(self):
        validate_date_range(self.start_date, self.end_date)

    def __str__(self):
        return self.name


class ProjectSkillRequirement(models.Model):
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    project_skill_requirement_id = models.AutoField(primary_key=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="skill_requirements",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="project_requirements",
    )
    required_level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Minimum skill level required, from 1 to 5.",
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        help_text="Importance of this skill requirement for later matching.",
    )
    is_mandatory = models.BooleanField(
        help_text="Hard requirement/filter. Not used in a matching score yet.",
    )
    required_quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )
    estimated_effort_hours = models.DecimalField(
    max_digits=10,
    decimal_places=2,
    validators=[MinValueValidator(0)],
    null=True,
    blank=True,
    help_text="Estimated total number of project hours associated with this skill requirement.",
    )


    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "skill"],
                name="unique_project_skill_requirement",
            ),
            models.CheckConstraint(
                condition=models.Q(required_level__gte=1)
                & models.Q(required_level__lte=5),
                name="projectskillrequirement_required_level_between_1_and_5",
            ),
            models.CheckConstraint(
                condition=models.Q(required_quantity__gte=1),
                name="projectskillrequirement_required_quantity_positive",
            ),
            models.CheckConstraint(
            condition=models.Q(estimated_effort_hours__gte=0),
            name="projectskillrequirement_effort_hours_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.project} requires {self.skill} (level {self.required_level})"


class Leave(models.Model):
    class Type(models.TextChoices):
        ANNUAL = "annual", "Annual"
        SICK = "sick", "Sick"
        UNPAID = "unpaid", "Unpaid"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    leave_id = models.AutoField(primary_key=True)
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="leaves",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    type = models.CharField(max_length=20, choices=Type.choices)
    status = models.CharField(max_length=20, choices=Status.choices)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="leave_start_date_not_after_end_date",
            ),
        ]

    def clean(self):
        validate_date_range(self.start_date, self.end_date)

    def __str__(self):
        return f"{self.employee} leave {self.start_date}–{self.end_date}"


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"
        REMOTE = "remote", "Remote"
        HALF_DAY = "half_day", "Half day"

    attendance_id = models.AutoField(primary_key=True)
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="attendances",
    )
    date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices)
    arrival_time = models.TimeField(null=True, blank=True)
    departure_time = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "date"],
                name="unique_employee_attendance_date",
            ),
        ]

    def clean(self):
        if (
            self.arrival_time
            and self.departure_time
            and self.arrival_time > self.departure_time
        ):
            raise ValidationError(
                {"departure_time": "arrival_time must not be after departure_time."}
            )

    def __str__(self):
        return f"{self.employee} attendance on {self.date}"


class Assignment(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    assignment_id = models.AutoField(primary_key=True)
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    allocation_percentage = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage of the employee's working capacity allocated to this project (0–100).",
    )
    role_on_project = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="assignment_start_date_not_after_end_date",
            ),
            models.CheckConstraint(
                condition=models.Q(allocation_percentage__gte=0)
                & models.Q(allocation_percentage__lte=100),
                name="assignment_allocation_percentage_between_0_and_100",
            ),
        ]

    # def clean(self):
    #     validate_date_range(self.start_date, self.end_date)
    def clean(self):
        super().clean()

        validate_date_range(self.start_date, self.end_date)

        if not self.employee_id or not self.project_id:
            return

        requirements = ProjectSkillRequirement.objects.filter(
            project=self.project
        )

        # Si le projet a des exigences de compétences
        if requirements.exists():

            employee_skills = EmployeeSkill.objects.filter(
                employee=self.employee
            )

            qualifies_for_at_least_one = False

            for requirement in requirements:
                employee_skill = employee_skills.filter(
                    skill=requirement.skill,
                    level__gte=requirement.required_level,
                ).exists()

                if employee_skill:
                    qualifies_for_at_least_one = True
                    break

            if not qualifies_for_at_least_one:
                raise ValidationError(
                    {
                        "employee":
                        "This employee does not satisfy any of the skill "
                        "requirements for this project."
                    }
                )
        # Vérifier qu'il n'existe pas déjà un assignment chevauchant
        # pour le même employé et le même projet
        overlapping_assignments = Assignment.objects.filter(
            employee=self.employee,
            project=self.project,
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        )

        # Important quand on modifie un assignment existant
        if self.pk:
            overlapping_assignments = overlapping_assignments.exclude(pk=self.pk)

        if overlapping_assignments.exists():
            raise ValidationError(
                {
                    "project":
                    "This employee already has an overlapping assignment "
                    "for this project."
                }
            )
        # Vérifier que la charge totale de l'employé
        # ne dépasse pas 100 % pendant la période de l'assignment.

        other_assignments = Assignment.objects.filter(
            employee=self.employee,
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        ).exclude(status=Assignment.Status.CANCELLED)

        # Lorsqu'on modifie un assignment existant,
        # ne pas le compter lui-même.
        if self.pk:
            other_assignments = other_assignments.exclude(pk=self.pk)

        # Les allocations peuvent changer à chaque début d'un assignment.
        # On vérifie donc tous les points temporels pertinents.
        dates_to_check = {self.start_date}

        for assignment in other_assignments:
            if self.start_date <= assignment.start_date <= self.end_date:
                dates_to_check.add(assignment.start_date)

        for check_date in dates_to_check:

            existing_allocation = sum(
                assignment.allocation_percentage
                for assignment in other_assignments
                if assignment.start_date <= check_date <= assignment.end_date
            )

            total_allocation = existing_allocation + self.allocation_percentage

            if total_allocation > 100:
                raise ValidationError(
                    {
                        "allocation_percentage":
                        f"This assignment would increase the employee's total "
                        f"allocation to {total_allocation}% on {check_date}. "
                        f"Maximum allowed workload is 100%."
                    }
                )

        approved_leaves = Leave.objects.filter(
            employee=self.employee,
            status=Leave.Status.APPROVED,
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        )

        if approved_leaves.exists():
            raise ValidationError(
                {
                    "employee":
                    "This employee has an approved leave that overlaps "
                    "with the assignment period."
                }
            )
    def __str__(self):
        return f"{self.employee} on {self.project} ({self.allocation_percentage}%)"
class AssignmentSkill(models.Model):
    assignment_skill_id = models.AutoField(primary_key=True)

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="covered_skill_requirements",
    )

    project_skill_requirement = models.ForeignKey(
        ProjectSkillRequirement,
        on_delete=models.CASCADE,
        related_name="assignment_skills",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "project_skill_requirement"],
                name="unique_assignment_skill_requirement",
            ),
        ]

    def clean(self):
        super().clean()

        assignment = self.assignment
        requirement = self.project_skill_requirement

        # 1. The requirement must belong to the same project
        if requirement.project_id != assignment.project_id:
            raise ValidationError(
                {
                    "project_skill_requirement":
                    "This skill requirement does not belong to the assignment's project."
                }
            )

        # 2. Employee must possess the skill
        employee_skill = EmployeeSkill.objects.filter(
            employee=assignment.employee,
            skill=requirement.skill,
        ).first()

        if employee_skill is None:
            raise ValidationError(
                {
                    "project_skill_requirement":
                    f"{assignment.employee} does not possess the skill "
                    f"{requirement.skill}."
                }
            )

        # 3. Employee's level must satisfy the required level
        if employee_skill.level < requirement.required_level:
            raise ValidationError(
                {
                    "project_skill_requirement":
                    f"{assignment.employee} has level {employee_skill.level} "
                    f"in {requirement.skill}, but level "
                    f"{requirement.required_level} is required."
                }
            )

        # 4. Do not exceed the required quantity
        existing_assignments = AssignmentSkill.objects.filter(
            project_skill_requirement=requirement,
            assignment__status__in=[
                Assignment.Status.PLANNED,
                Assignment.Status.ACTIVE,
            ],
        )

        # Important when editing an existing AssignmentSkill
        if self.pk:
            existing_assignments = existing_assignments.exclude(pk=self.pk)

        if existing_assignments.count() >= requirement.required_quantity:
            raise ValidationError(
                {
                    "project_skill_requirement":
                    f"The required quantity for {requirement.skill} "
                    f"has already been reached."
                }
            )

    def __str__(self):
        return (
            f"{self.assignment.employee} covers "
            f"{self.project_skill_requirement.skill} "
            f"for {self.assignment.project}"
        )