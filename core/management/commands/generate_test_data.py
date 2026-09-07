import random

from datetime import date, time, timedelta
from decimal import Decimal

from faker import Faker

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    Assignment,
    AssignmentSkill,
    Attendance,
    Employee,
    EmployeeSkill,
    Leave,
    Project,
    ProjectSkillRequirement,
    Skill,
)


def save_valid(instance):
    """
    Run Django model validation before saving.

    This is important because objects created directly with the ORM
    do not automatically call model.clean().
    """
    instance.full_clean()
    instance.save()
    return instance


class Command(BaseCommand):
    help = "Generate a small coherent synthetic dataset for the HR workforce platform."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing business data before generating the dataset.",
        )

        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Random seed used to make generation reproducible.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        seed = options["seed"]
        reset = options["reset"]

        random.seed(seed)
        Faker.seed(seed)

        fake = Faker("fr_FR")
        fake.seed_instance(seed)

        # ---------------------------------------------------------
        # Existing data protection
        # ---------------------------------------------------------

        business_models = [
            AssignmentSkill,
            Assignment,
            Attendance,
            Leave,
            ProjectSkillRequirement,
            Project,
            EmployeeSkill,
            Skill,
            Employee,
        ]

        data_exists = any(model.objects.exists() for model in business_models)

        if data_exists and not reset:
            raise CommandError(
                "Business data already exists. "
                "Run the command with --reset if you want to replace it."
            )

        if reset:
            self.stdout.write("Deleting existing business data...")

            # Delete in dependency order.
            AssignmentSkill.objects.all().delete()
            Assignment.objects.all().delete()
            Attendance.objects.all().delete()
            Leave.objects.all().delete()
            ProjectSkillRequirement.objects.all().delete()
            Project.objects.all().delete()
            EmployeeSkill.objects.all().delete()
            Skill.objects.all().delete()
            Employee.objects.all().delete()

        # ---------------------------------------------------------
        # 1. SKILLS
        # ---------------------------------------------------------

        self.stdout.write("Creating skills...")

        skill_definitions = [
            ("Python", "Programming"),
            ("Django", "Backend"),
            ("SQL", "Database"),
            ("React", "Frontend"),
            ("Machine Learning", "AI"),
            ("Power BI", "Data Analytics"),
            ("Git", "Development Tools"),
            ("Docker", "DevOps"),
        ]

        skills = {}

        for name, category in skill_definitions:
            skill = Skill(
                name=name,
                category=category,
            )

            save_valid(skill)

            skills[name] = skill

        # ---------------------------------------------------------
        # 2. EMPLOYEES + THEIR PROFILE DEFINITIONS
        # ---------------------------------------------------------

        self.stdout.write("Creating employees...")

        employee_profiles = [
            {
                "department": "IT",
                "position": "Backend Developer",
                "experience": Decimal("5.0"),
                "skills": {
                    "Python": (5, Decimal("4.5")),
                    "Django": (4, Decimal("4.0")),
                    "SQL": (4, Decimal("4.0")),
                    "Git": (4, Decimal("4.5")),
                    "Docker": (3, Decimal("2.5")),
                },
            },
            {
                "department": "IT",
                "position": "Backend Developer",
                "experience": Decimal("4.0"),
                "skills": {
                    "Python": (4, Decimal("3.5")),
                    "Django": (4, Decimal("3.0")),
                    "SQL": (3, Decimal("3.0")),
                    "Git": (4, Decimal("3.5")),
                    "Docker": (3, Decimal("2.0")),
                },
            },
            {
                "department": "Data",
                "position": "Data Analyst",
                "experience": Decimal("3.0"),
                "skills": {
                    "Python": (3, Decimal("2.0")),
                    "SQL": (5, Decimal("3.0")),
                    "Power BI": (5, Decimal("2.5")),
                    "Git": (3, Decimal("2.0")),
                },
            },
            {
                "department": "Data",
                "position": "Data Scientist",
                "experience": Decimal("4.0"),
                "skills": {
                    "Python": (4, Decimal("3.5")),
                    "SQL": (4, Decimal("3.0")),
                    "Machine Learning": (5, Decimal("4.0")),
                    "Git": (3, Decimal("2.0")),
                },
            },
            {
                "department": "IT",
                "position": "Frontend Developer",
                "experience": Decimal("3.0"),
                "skills": {
                    "React": (5, Decimal("3.0")),
                    "Git": (4, Decimal("2.5")),
                    "SQL": (2, Decimal("1.0")),
                },
            },
            {
                "department": "IT",
                "position": "Full Stack Developer",
                "experience": Decimal("5.0"),
                "skills": {
                    "Python": (4, Decimal("4.0")),
                    "Django": (3, Decimal("3.0")),
                    "React": (4, Decimal("3.5")),
                    "SQL": (4, Decimal("4.0")),
                    "Git": (4, Decimal("4.0")),
                },
            },
            {
                "department": "IT",
                "position": "DevOps Engineer",
                "experience": Decimal("6.0"),
                "skills": {
                    "Docker": (5, Decimal("5.0")),
                    "Git": (5, Decimal("5.0")),
                    "Python": (3, Decimal("3.0")),
                    "SQL": (2, Decimal("1.5")),
                },
            },
            {
                "department": "IT",
                "position": "Junior Backend Developer",
                "experience": Decimal("2.0"),
                "skills": {
                    "Python": (3, Decimal("2.0")),
                    "Django": (3, Decimal("1.5")),
                    "SQL": (3, Decimal("1.5")),
                    "Git": (3, Decimal("2.0")),
                },
            },
            {
                "department": "Data",
                "position": "Junior Data Analyst",
                "experience": Decimal("2.0"),
                "skills": {
                    "SQL": (4, Decimal("2.0")),
                    "Power BI": (4, Decimal("1.5")),
                    "Python": (2, Decimal("1.0")),
                },
            },
            {
                "department": "IT",
                "position": "Frontend Developer",
                "experience": Decimal("2.0"),
                "skills": {
                    "React": (4, Decimal("2.0")),
                    "Git": (3, Decimal("1.5")),
                    "SQL": (2, Decimal("1.0")),
                },
            },
        ]

        employees = []

        reference_date = date(2026, 9, 1)

        for profile in employee_profiles:
            experience = profile["experience"]

            hire_date = reference_date - timedelta(
                days=int(float(experience) * 365.25)
            )

            employee = Employee(
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                department=profile["department"],
                position=profile["position"],
                hire_date=hire_date,
                experience_years=experience,
                capacity_hours_week=Decimal("40.00"),
                status=Employee.Status.ACTIVE,
            )

            save_valid(employee)

            employees.append(employee)

        # ---------------------------------------------------------
        # 3. EMPLOYEE SKILLS
        # ---------------------------------------------------------

        self.stdout.write("Creating employee skills...")

        for employee, profile in zip(employees, employee_profiles):
            for skill_name, skill_values in profile["skills"].items():

                level, years_experience = skill_values

                employee_skill = EmployeeSkill(
                    employee=employee,
                    skill=skills[skill_name],
                    level=level,
                    years_experience=years_experience,
                )

                save_valid(employee_skill)

        # ---------------------------------------------------------
        # 4. PROJECTS
        # ---------------------------------------------------------

        self.stdout.write("Creating projects...")

        hr_project = save_valid(
            Project(
                name="HR Platform",
                description="Human resources management and workforce platform.",
                start_date=date(2026, 9, 1),
                end_date=date(2026, 10, 31),
                estimated_hours=Decimal("480.00"),
                status=Project.Status.IN_PROGRESS,
                priority=Project.Priority.HIGH,
                criticality=Project.Criticality.HIGH,
            )
        )

        analytics_project = save_valid(
            Project(
                name="Analytics Dashboard",
                description="Business intelligence and analytics dashboard.",
                start_date=date(2026, 9, 15),
                end_date=date(2026, 10, 15),
                estimated_hours=Decimal("240.00"),
                status=Project.Status.PLANNED,
                priority=Project.Priority.MEDIUM,
                criticality=Project.Criticality.MEDIUM,
            )
        )

        recruitment_project = save_valid(
            Project(
                name="Recruitment Portal",
                description="Web recruitment and candidate management portal.",
                start_date=date(2026, 10, 1),
                end_date=date(2026, 11, 15),
                estimated_hours=Decimal("320.00"),
                status=Project.Status.PLANNED,
                priority=Project.Priority.HIGH,
                criticality=Project.Criticality.MEDIUM,
            )
        )

        projects = {
            "HR Platform": hr_project,
            "Analytics Dashboard": analytics_project,
            "Recruitment Portal": recruitment_project,
        }

        # ---------------------------------------------------------
        # 5. PROJECT SKILL REQUIREMENTS
        # ---------------------------------------------------------

        self.stdout.write("Creating project skill requirements...")

        requirement_definitions = [
        # HR Platform - total mandatory effort = 480 h
        (
            hr_project,
            "Python",
            4,
            ProjectSkillRequirement.Priority.HIGH,
            True,
            2,
            Decimal("220.00"),
        ),
        (
            hr_project,
            "Django",
            3,
            ProjectSkillRequirement.Priority.HIGH,
            True,
            1,
            Decimal("160.00"),
        ),
        (
            hr_project,
            "SQL",
            3,
            ProjectSkillRequirement.Priority.MEDIUM,
            True,
            1,
            Decimal("100.00"),
        ),

        # Analytics Dashboard - total mandatory effort = 240 h
        (
            analytics_project,
            "SQL",
            4,
            ProjectSkillRequirement.Priority.HIGH,
            True,
            1,
            Decimal("120.00"),
        ),
        (
            analytics_project,
            "Power BI",
            4,
            ProjectSkillRequirement.Priority.HIGH,
            True,
            1,
            Decimal("120.00"),
        ),
        (
            analytics_project,
            "Python",
            3,
            ProjectSkillRequirement.Priority.MEDIUM,
            False,
            1,
            Decimal("0.00"),
        ),

        # Recruitment Portal - total mandatory effort = 320 h
        (
            recruitment_project,
            "React",
            4,
            ProjectSkillRequirement.Priority.HIGH,
            True,
            1,
            Decimal("180.00"),
        ),
        (
            recruitment_project,
            "Django",
            3,
            ProjectSkillRequirement.Priority.HIGH,
            True,
            1,
            Decimal("140.00"),
        ),
        (
            recruitment_project,
            "SQL",
            3,
            ProjectSkillRequirement.Priority.MEDIUM,
            False,
            1,
            Decimal("0.00"),
        ),
        ]

        requirements = {}

        for (
            project,
            skill_name,
            required_level,
            priority,
            mandatory,
            quantity,
            estimated_effort_hours,
        ) in requirement_definitions:

            requirement = ProjectSkillRequirement(
                project=project,
                skill=skills[skill_name],
                required_level=required_level,
                priority=priority,
                is_mandatory=mandatory,
                required_quantity=quantity,
                estimated_effort_hours=estimated_effort_hours,
            )

            save_valid(requirement)

            requirements[(project.name, skill_name)] = requirement

        # ---------------------------------------------------------
        # 6. ASSIGNMENTS
        for project in projects.values():
            mandatory_effort = sum(
        (
            requirement.estimated_effort_hours or Decimal("0.00")
        )
        for requirement in project.skill_requirements.filter(
            is_mandatory=True
        )
        )

        if mandatory_effort != project.estimated_hours:
            raise CommandError(
                f"Effort mismatch for {project.name}: "
                f"project estimated_hours={project.estimated_hours}, "
                f"mandatory skill effort={mandatory_effort}"
        )
        # ---------------------------------------------------------

        self.stdout.write("Creating assignments...")

        assignment_1 = save_valid(
            Assignment(
                employee=employees[0],
                project=hr_project,
                start_date=date(2026, 9, 1),
                end_date=date(2026, 10, 31),
                allocation_percentage=50,
                role_on_project="Senior Backend Developer",
                status=Assignment.Status.ACTIVE,
            )
        )

        assignment_2 = save_valid(
            Assignment(
                employee=employees[1],
                project=hr_project,
                start_date=date(2026, 9, 1),
                end_date=date(2026, 10, 31),
                allocation_percentage=40,
                role_on_project="Backend Developer",
                status=Assignment.Status.ACTIVE,
            )
        )

        assignment_3 = save_valid(
            Assignment(
                employee=employees[5],
                project=hr_project,
                start_date=date(2026, 9, 1),
                end_date=date(2026, 10, 31),
                allocation_percentage=30,
                role_on_project="Full Stack Developer",
                status=Assignment.Status.ACTIVE,
            )
        )

        assignment_4 = save_valid(
            Assignment(
                employee=employees[2],
                project=analytics_project,
                start_date=date(2026, 9, 15),
                end_date=date(2026, 10, 15),
                allocation_percentage=50,
                role_on_project="Data Analyst",
                status=Assignment.Status.PLANNED,
            )
        )

        assignment_5 = save_valid(
            Assignment(
                employee=employees[3],
                project=analytics_project,
                start_date=date(2026, 9, 15),
                end_date=date(2026, 10, 15),
                allocation_percentage=30,
                role_on_project="Data Scientist",
                status=Assignment.Status.PLANNED,
            )
        )

        assignment_6 = save_valid(
            Assignment(
                employee=employees[4],
                project=recruitment_project,
                start_date=date(2026, 10, 1),
                end_date=date(2026, 11, 15),
                allocation_percentage=50,
                role_on_project="Frontend Developer",
                status=Assignment.Status.PLANNED,
            )
        )

        assignment_7 = save_valid(
            Assignment(
                employee=employees[5],
                project=recruitment_project,
                start_date=date(2026, 10, 1),
                end_date=date(2026, 11, 15),
                allocation_percentage=40,
                role_on_project="Full Stack Developer",
                status=Assignment.Status.PLANNED,
            )
        )

        # ---------------------------------------------------------
        # 7. ASSIGNMENT SKILLS
        # ---------------------------------------------------------

        self.stdout.write("Creating assignment-skill coverage...")

        assignment_skill_definitions = [
            # HR Platform
            (assignment_1, "Python"),
            (assignment_1, "Django"),
            (assignment_2, "Python"),
            (assignment_3, "SQL"),

            # Analytics Dashboard
            (assignment_4, "SQL"),
            (assignment_4, "Power BI"),
            (assignment_5, "Python"),

            # Recruitment Portal
            (assignment_6, "React"),
            (assignment_7, "Django"),
            (assignment_7, "SQL"),
        ]

        for assignment, skill_name in assignment_skill_definitions:

            requirement = requirements[
                (assignment.project.name, skill_name)
            ]

            assignment_skill = AssignmentSkill(
                assignment=assignment,
                project_skill_requirement=requirement,
            )

            save_valid(assignment_skill)

        # ---------------------------------------------------------
        # 8. LEAVES
        # ---------------------------------------------------------

        self.stdout.write("Creating leave records...")

        leave_definitions = [
            (
                employees[7],
                date(2026, 6, 15),
                date(2026, 6, 17),
                Leave.Type.ANNUAL,
                Leave.Status.APPROVED,
            ),
            (
                employees[8],
                date(2026, 6, 22),
                date(2026, 6, 22),
                Leave.Type.SICK,
                Leave.Status.APPROVED,
            ),
            (
                employees[9],
                date(2026, 6, 25),
                date(2026, 6, 27),
                Leave.Type.ANNUAL,
                Leave.Status.PENDING,
            ),
        ]

        for (
            employee,
            start_date,
            end_date,
            leave_type,
            leave_status,
        ) in leave_definitions:

            leave = Leave(
                employee=employee,
                start_date=start_date,
                end_date=end_date,
                type=leave_type,
                status=leave_status,
            )

            save_valid(leave)

        # ---------------------------------------------------------
        # 9. ATTENDANCE HISTORY
        # ---------------------------------------------------------

        self.stdout.write("Creating attendance history...")

        attendance_start = date(2026, 8, 3)
        attendance_end = date(2026, 8, 31)

        current_date = attendance_start

        while current_date <= attendance_end:

            # Monday = 0 ... Sunday = 6
            if current_date.weekday() < 5:

                for employee in employees:

                    attendance_status = random.choices(
                        [
                            Attendance.Status.PRESENT,
                            Attendance.Status.LATE,
                            Attendance.Status.ABSENT,
                            Attendance.Status.REMOTE,
                            Attendance.Status.HALF_DAY,
                        ],
                        weights=[
                            78,
                            8,
                            5,
                            7,
                            2,
                        ],
                        k=1,
                    )[0]

                    arrival_time = None
                    departure_time = None

                    if attendance_status == Attendance.Status.PRESENT:

                        arrival_time = time(
                            8,
                            random.randint(20, 55),
                        )

                        departure_time = time(
                            17,
                            random.randint(0, 30),
                        )

                    elif attendance_status == Attendance.Status.LATE:

                        arrival_time = time(
                            9,
                            random.randint(5, 45),
                        )

                        departure_time = time(
                            17,
                            random.randint(0, 40),
                        )

                    elif attendance_status == Attendance.Status.REMOTE:

                        arrival_time = time(9, 0)
                        departure_time = time(17, 0)

                    elif attendance_status == Attendance.Status.HALF_DAY:

                        arrival_time = time(9, 0)
                        departure_time = time(13, 0)

                    elif attendance_status == Attendance.Status.ABSENT:

                        arrival_time = None
                        departure_time = None

                    attendance = Attendance(
                        employee=employee,
                        date=current_date,
                        status=attendance_status,
                        arrival_time=arrival_time,
                        departure_time=departure_time,
                    )

                    save_valid(attendance)

            current_date += timedelta(days=1)

        # ---------------------------------------------------------
        # FINAL COUNTS
        # ---------------------------------------------------------

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Dataset generated successfully."))
        self.stdout.write("")

        self.stdout.write(
            f"Employees: {Employee.objects.count()}"
        )

        self.stdout.write(
            f"Skills: {Skill.objects.count()}"
        )

        self.stdout.write(
            f"EmployeeSkill: {EmployeeSkill.objects.count()}"
        )

        self.stdout.write(
            f"Projects: {Project.objects.count()}"
        )

        self.stdout.write(
            f"ProjectSkillRequirement: "
            f"{ProjectSkillRequirement.objects.count()}"
        )

        self.stdout.write(
            f"Assignments: {Assignment.objects.count()}"
        )

        self.stdout.write(
            f"AssignmentSkill: {AssignmentSkill.objects.count()}"
        )

        self.stdout.write(
            f"Leaves: {Leave.objects.count()}"
        )

        self.stdout.write(
            f"Attendance: {Attendance.objects.count()}"
        )