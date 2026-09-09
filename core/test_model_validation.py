from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import (
    Assignment,
    AssignmentSkill,
    Employee,
    EmployeeSkill,
    Leave,
    Project,
    ProjectSkillRequirement,
    Skill,
)


class StaffingModelValidationTests(TestCase):
    def setUp(self):
        self.python = Skill.objects.create(name="Python", category="Engineering")
        self.react = Skill.objects.create(name="React", category="Engineering")

        self.project = self._create_project("Primary project")
        self.other_project = self._create_project("Other project")

        self.python_requirement = self._create_requirement(
            self.project,
            self.python,
            required_level=3,
        )
        self.react_requirement = self._create_requirement(
            self.project,
            self.react,
            required_level=4,
        )
        self.other_requirement = self._create_requirement(
            self.other_project,
            self.python,
            required_level=3,
        )

        self.employee = self._create_employee("Ada", "Qualified")
        EmployeeSkill.objects.create(
            employee=self.employee,
            skill=self.python,
            level=4,
            years_experience=Decimal("4.0"),
        )

    def _create_employee(self, first_name, last_name):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Engineering",
            position="Developer",
            hire_date=date(2020, 1, 1),
            experience_years=Decimal("5.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )

    def _create_project(self, name):
        return Project.objects.create(
            name=name,
            description="Validation test project.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 18),
            estimated_hours=Decimal("80.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )

    def _create_requirement(self, project, skill, required_level):
        return ProjectSkillRequirement.objects.create(
            project=project,
            skill=skill,
            required_level=required_level,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=Decimal("40.00"),
        )

    def _assignment(
        self,
        employee=None,
        project=None,
        allocation_percentage=50,
        start_date=date(2026, 9, 7),
        end_date=date(2026, 9, 18),
        status=Assignment.Status.PLANNED,
    ):
        return Assignment(
            employee=employee or self.employee,
            project=project or self.project,
            start_date=start_date,
            end_date=end_date,
            allocation_percentage=allocation_percentage,
            role_on_project="Developer",
            status=status,
        )

    def assert_field_validation_error(self, instance, field, message_fragment):
        with self.assertRaises(ValidationError) as raised:
            instance.full_clean()

        self.assertIn(field, raised.exception.message_dict)
        self.assertTrue(
            any(
                message_fragment in message
                for message in raised.exception.message_dict[field]
            ),
            raised.exception.message_dict,
        )

    def test_assignment_rejects_employee_without_a_qualifying_skill(self):
        unqualified_employee = self._create_employee("Uma", "Unqualified")

        self.assert_field_validation_error(
            self._assignment(employee=unqualified_employee),
            "employee",
            "does not satisfy any of the skill requirements",
        )

    def test_assignment_rejects_overlap_for_same_employee_and_project(self):
        self._assignment(
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
        ).save()

        self.assert_field_validation_error(
            self._assignment(
                start_date=date(2026, 9, 11),
                end_date=date(2026, 9, 18),
            ),
            "project",
            "already has an overlapping assignment",
        )

    def test_assignment_rejects_total_allocation_above_one_hundred_percent(self):
        self._assignment(
            project=self.other_project,
            allocation_percentage=60,
        ).save()

        self.assert_field_validation_error(
            self._assignment(allocation_percentage=50),
            "allocation_percentage",
            "total allocation to 110%",
        )

    def test_assignment_rejects_approved_leave_overlap(self):
        Leave.objects.create(
            employee=self.employee,
            start_date=date(2026, 9, 10),
            end_date=date(2026, 9, 11),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )

        self.assert_field_validation_error(
            self._assignment(),
            "employee",
            "approved leave that overlaps",
        )

    def test_frontend_facing_model_text_uses_expected_unicode(self):
        employee_skill = EmployeeSkill.objects.get(
            employee=self.employee,
            skill=self.python,
        )
        leave = Leave(
            employee=self.employee,
            start_date=date(2026, 9, 10),
            end_date=date(2026, 9, 11),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )

        self.assertEqual(
            str(employee_skill),
            "Ada Qualified – Python (level 4)",
        )
        self.assertEqual(
            str(leave),
            "Ada Qualified leave 2026-09-10–2026-09-11",
        )
        self.assertIn(
            "(0–100)",
            Assignment._meta.get_field("allocation_percentage").help_text,
        )

    def test_assignment_skill_rejects_requirement_from_another_project(self):
        assignment = self._assignment()
        assignment.save()

        self.assert_field_validation_error(
            AssignmentSkill(
                assignment=assignment,
                project_skill_requirement=self.other_requirement,
            ),
            "project_skill_requirement",
            "does not belong to the assignment's project",
        )

    def test_assignment_skill_rejects_a_skill_the_employee_does_not_have(self):
        assignment = self._assignment()
        assignment.save()

        self.assert_field_validation_error(
            AssignmentSkill(
                assignment=assignment,
                project_skill_requirement=self.react_requirement,
            ),
            "project_skill_requirement",
            "does not possess the skill",
        )

    def test_assignment_skill_rejects_an_insufficient_skill_level(self):
        EmployeeSkill.objects.create(
            employee=self.employee,
            skill=self.react,
            level=3,
            years_experience=Decimal("3.0"),
        )
        assignment = self._assignment()
        assignment.save()

        self.assert_field_validation_error(
            AssignmentSkill(
                assignment=assignment,
                project_skill_requirement=self.react_requirement,
            ),
            "project_skill_requirement",
            "but level 4 is required",
        )

    def test_assignment_skill_rejects_coverage_above_required_quantity(self):
        first_assignment = self._assignment()
        first_assignment.save()
        AssignmentSkill.objects.create(
            assignment=first_assignment,
            project_skill_requirement=self.python_requirement,
        )

        second_employee = self._create_employee("Bea", "Qualified")
        EmployeeSkill.objects.create(
            employee=second_employee,
            skill=self.python,
            level=4,
            years_experience=Decimal("4.0"),
        )
        second_assignment = self._assignment(employee=second_employee)
        second_assignment.save()

        self.assert_field_validation_error(
            AssignmentSkill(
                assignment=second_assignment,
                project_skill_requirement=self.python_requirement,
            ),
            "project_skill_requirement",
            "required quantity for Python has already been reached",
        )
