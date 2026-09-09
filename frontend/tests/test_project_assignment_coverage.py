import re
import statistics
import time
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import NON_FIELD_ERRORS
from django.db import DatabaseError, connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from core.models import (
    Assignment,
    AssignmentSkill,
    Employee,
    EmployeeSkill,
    Project,
    ProjectSkillRequirement,
    Skill,
)
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    MANAGER_PLANNER_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)


class ProjectAssignmentCoverageTests(TestCase):
    EXPECTED_COVERAGE_QUERY_COUNT = 13
    TIMING_SAMPLE_COUNT = 25
    COVERAGE_FORM_CSRF_PATTERN = re.compile(
        r'<form method="post" novalidate data-loading-form>\s*'
        r'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)">'
    )

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.hr_admin = cls._group_user("coverage-hr", HR_ADMINISTRATOR_GROUP)
        cls.manager = cls._group_user(
            "coverage-manager",
            MANAGER_PLANNER_GROUP,
        )
        cls.viewer = cls._group_user("coverage-viewer", VIEWER_GROUP)
        cls.add_only_user = cls._permission_user(
            "coverage-add-only",
            "add_assignmentskill",
        )
        cls.delete_only_user = cls._permission_user(
            "coverage-delete-only",
            "delete_assignmentskill",
        )

        cls.project = cls._create_project("Atlas Renewal")
        cls.other_project = cls._create_project("Beacon Expansion")

        cls.python = Skill.objects.create(name="Python", category="Engineering")
        cls.django = Skill.objects.create(name="Django", category="Engineering")
        cls.react = Skill.objects.create(name="React", category="Engineering")
        cls.sql = Skill.objects.create(name="SQL", category="Data")
        cls.devops = Skill.objects.create(name="DevOps", category="Operations")

        cls.python_requirement = cls._create_requirement(
            cls.project,
            cls.python,
            required_level=4,
            required_quantity=2,
        )
        cls.django_requirement = cls._create_requirement(
            cls.project,
            cls.django,
            required_level=4,
            required_quantity=2,
        )
        cls.react_requirement = cls._create_requirement(
            cls.project,
            cls.react,
            required_level=3,
            required_quantity=1,
        )
        cls.sql_requirement = cls._create_requirement(
            cls.project,
            cls.sql,
            required_level=4,
            required_quantity=1,
        )
        cls.devops_requirement = cls._create_requirement(
            cls.project,
            cls.devops,
            required_level=4,
            required_quantity=1,
        )
        cls.other_requirement = cls._create_requirement(
            cls.other_project,
            cls.python,
            required_level=3,
            required_quantity=1,
        )

        cls.employee = cls._create_employee("Jamie", "Rivera")
        EmployeeSkill.objects.create(
            employee=cls.employee,
            skill=cls.python,
            level=5,
            years_experience=Decimal("6.0"),
        )
        EmployeeSkill.objects.create(
            employee=cls.employee,
            skill=cls.django,
            level=4,
            years_experience=Decimal("4.0"),
        )
        EmployeeSkill.objects.create(
            employee=cls.employee,
            skill=cls.sql,
            level=2,
            years_experience=Decimal("2.0"),
        )
        EmployeeSkill.objects.create(
            employee=cls.employee,
            skill=cls.devops,
            level=5,
            years_experience=Decimal("5.0"),
        )
        cls.assignment = cls._create_assignment(
            cls.project,
            cls.employee,
            role="Platform lead",
        )
        cls.coverage = AssignmentSkill.objects.create(
            assignment=cls.assignment,
            project_skill_requirement=cls.python_requirement,
        )

        cls.other_employee = cls._create_employee("Morgan", "Lee")
        EmployeeSkill.objects.create(
            employee=cls.other_employee,
            skill=cls.devops,
            level=5,
            years_experience=Decimal("5.0"),
        )
        cls.capacity_assignment = cls._create_assignment(
            cls.project,
            cls.other_employee,
            role="Operations lead",
            status=Assignment.Status.ACTIVE,
        )
        cls.capacity_coverage = AssignmentSkill.objects.create(
            assignment=cls.capacity_assignment,
            project_skill_requirement=cls.devops_requirement,
        )

        cls.other_assignment = cls._create_assignment(
            cls.other_project,
            cls.employee,
            role="Advisor",
        )
        cls.other_coverage = AssignmentSkill.objects.create(
            assignment=cls.other_assignment,
            project_skill_requirement=cls.other_requirement,
        )

    @classmethod
    def _group_user(cls, username, group_name):
        user = get_user_model().objects.create_user(username=username)
        user.groups.add(Group.objects.get(name=group_name))
        return user

    @classmethod
    def _permission_user(cls, username, codename):
        user = get_user_model().objects.create_user(username=username)
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename=codename,
            )
        )
        return user

    @staticmethod
    def _create_project(name):
        return Project.objects.create(
            name=name,
            description=f"Plan {name}.",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 12, 15),
            estimated_hours=Decimal("400.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )

    @staticmethod
    def _create_requirement(
        project,
        skill,
        *,
        required_level,
        required_quantity,
    ):
        return ProjectSkillRequirement.objects.create(
            project=project,
            skill=skill,
            required_level=required_level,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=required_quantity,
            estimated_effort_hours=Decimal("80.00"),
        )

    @staticmethod
    def _create_employee(first_name, last_name):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Engineering",
            position="Platform Engineer",
            hire_date=date(2019, 4, 15),
            experience_years=Decimal("7.0"),
            capacity_hours_week=Decimal("40.00"),
            status=Employee.Status.ACTIVE,
        )

    @staticmethod
    def _create_assignment(project, employee, *, role, status=None):
        return Assignment.objects.create(
            employee=employee,
            project=project,
            start_date=project.start_date,
            end_date=project.end_date,
            allocation_percentage=40,
            role_on_project=role,
            status=status or Assignment.Status.PLANNED,
        )

    def setUp(self):
        self.detail_url = reverse(
            "frontend:project_detail",
            args=[self.project.project_id],
        )
        self.coverage_url = reverse(
            "frontend:project_assignment_coverage",
            args=[self.project.project_id, self.assignment.assignment_id],
        )
        self.create_url = reverse(
            "frontend:project_assignment_coverage_create",
            args=[self.project.project_id, self.assignment.assignment_id],
        )
        self.remove_url = reverse(
            "frontend:project_assignment_coverage_remove",
            args=[
                self.project.project_id,
                self.assignment.assignment_id,
                self.coverage.assignment_skill_id,
            ],
        )
        self.client.force_login(self.hr_admin)

    def coverage_form_csrf_token(self, response):
        match = self.COVERAGE_FORM_CSRF_PATTERN.search(
            response.content.decode("utf-8")
        )
        self.assertIsNotNone(
            match,
            "The coverage POST form must render its own CSRF input.",
        )
        return match.group(1)

    def removal_form_csrf_token(self, response, action_url):
        pattern = re.compile(
            rf'<form method="post" action="{re.escape(action_url)}" '
            rf'data-loading-form>\s*'
            rf'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)">'
        )
        match = pattern.search(response.content.decode("utf-8"))
        self.assertIsNotNone(
            match,
            "The coverage removal form must render its own CSRF input.",
        )
        return match.group(1)

    def test_routes_are_assignment_scoped_namespaced_and_render(self):
        self.assertEqual(
            self.coverage_url,
            f"/projects/{self.project.project_id}/assignments/"
            f"{self.assignment.assignment_id}/coverage/",
        )
        self.assertEqual(
            resolve(self.coverage_url).view_name,
            "frontend:project_assignment_coverage",
        )
        self.assertEqual(
            resolve(self.create_url).view_name,
            "frontend:project_assignment_coverage_create",
        )
        self.assertEqual(
            resolve(self.remove_url).view_name,
            "frontend:project_assignment_coverage_remove",
        )

        response = self.client.get(self.coverage_url)
        self.assertTemplateUsed(
            response,
            "frontend/projects/assignments/coverage/detail.html",
        )
        self.assertContains(response, "<h1>Requirement coverage</h1>", html=True)
        self.assertContains(response, "Jamie Rivera")
        self.assertContains(response, "Atlas Renewal")
        self.assertContains(response, "Python")

        create_response = self.client.get(self.create_url)
        self.assertTemplateUsed(
            create_response,
            "frontend/projects/assignments/coverage/create.html",
        )
        self.coverage_form_csrf_token(create_response)

        remove_response = self.client.get(self.remove_url)
        self.assertTemplateUsed(
            remove_response,
            "frontend/projects/assignments/coverage/confirm_remove.html",
        )
        self.assertContains(remove_response, "Remove this coverage link?")
        self.removal_form_csrf_token(remove_response, self.remove_url)

    def test_project_detail_links_to_assignment_coverage_for_readers(self):
        response = self.client.get(self.detail_url)
        self.assertContains(response, self.coverage_url)
        self.assertContains(response, "Review coverage")

        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        viewer_response = viewer_client.get(self.detail_url)
        self.assertContains(viewer_response, self.coverage_url)
        self.assertContains(viewer_response, "Review coverage")

    def test_coverage_profile_explains_covered_available_and_unavailable(self):
        response = self.client.get(self.coverage_url)

        self.assertContains(response, "Covered")
        self.assertContains(
            response,
            "Jamie Rivera is already linked to this requirement.",
        )
        self.assertContains(response, "Available")
        self.assertContains(
            response,
            "Jamie Rivera meets this requirement&#x27;s current coverage rules.",
        )
        self.assertContains(response, "Unavailable", count=3)
        self.assertContains(response, "does not possess the skill React")
        self.assertContains(response, "but level 4 is required")
        self.assertContains(
            response,
            "The required quantity for DevOps has already been reached.",
        )

    def test_add_form_choices_are_project_scoped_and_exclude_existing_links(self):
        response = self.client.get(self.create_url)
        queryset = response.context["form"].fields[
            "project_skill_requirement"
        ].queryset
        requirement_ids = set(
            queryset.values_list("project_skill_requirement_id", flat=True)
        )

        self.assertNotIn(
            self.python_requirement.project_skill_requirement_id,
            requirement_ids,
        )
        self.assertIn(
            self.django_requirement.project_skill_requirement_id,
            requirement_ids,
        )
        self.assertIn(
            self.react_requirement.project_skill_requirement_id,
            requirement_ids,
        )
        self.assertNotIn(
            self.other_requirement.project_skill_requirement_id,
            requirement_ids,
        )
        self.assertContains(
            response,
            "Django — Level 4 · 2 needed · Mandatory",
        )
        self.assertNotContains(response, "Beacon Expansion")

    def test_valid_coverage_is_added_and_reported(self):
        response = self.client.post(
            self.create_url,
            {
                "project_skill_requirement": (
                    self.django_requirement.project_skill_requirement_id
                )
            },
            follow=True,
        )

        self.assertRedirects(response, self.coverage_url)
        self.assertTrue(
            AssignmentSkill.objects.filter(
                assignment=self.assignment,
                project_skill_requirement=self.django_requirement,
            ).exists()
        )
        self.assertContains(
            response,
            "Django coverage was added for Jamie Rivera.",
        )

    def test_wrong_project_requirement_is_rejected_by_scoped_choice(self):
        coverage_count = AssignmentSkill.objects.count()
        response = self.client.post(
            self.create_url,
            {
                "project_skill_requirement": (
                    self.other_requirement.project_skill_requirement_id
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(AssignmentSkill.objects.count(), coverage_count)
        self.assertIn(
            "project_skill_requirement",
            response.context["form"].errors,
        )
        self.assertContains(response, "Select a valid choice")
        self.assertContains(response, 'id="id_project_skill_requirement_error"')

    def test_missing_and_insufficient_employee_skills_use_model_feedback(self):
        cases = (
            (self.react_requirement, "does not possess the skill React"),
            (self.sql_requirement, "but level 4 is required"),
        )
        for requirement, expected_message in cases:
            with self.subTest(skill=requirement.skill.name):
                response = self.client.post(
                    self.create_url,
                    {
                        "project_skill_requirement": (
                            requirement.project_skill_requirement_id
                        )
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(
                    "project_skill_requirement",
                    response.context["form"].errors,
                )
                self.assertContains(response, expected_message)
                self.assertFalse(
                    AssignmentSkill.objects.filter(
                        assignment=self.assignment,
                        project_skill_requirement=requirement,
                    ).exists()
                )

    def test_required_quantity_limit_uses_assignment_skill_validation(self):
        response = self.client.post(
            self.create_url,
            {
                "project_skill_requirement": (
                    self.devops_requirement.project_skill_requirement_id
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "project_skill_requirement",
            response.context["form"].errors,
        )
        self.assertContains(
            response,
            "The required quantity for DevOps has already been reached.",
        )
        self.assertFalse(
            AssignmentSkill.objects.filter(
                assignment=self.assignment,
                project_skill_requirement=self.devops_requirement,
            ).exists()
        )

    def test_duplicate_coverage_is_prevented_with_clear_feedback(self):
        coverage_count = AssignmentSkill.objects.count()
        response = self.client.post(
            self.create_url,
            {
                "project_skill_requirement": (
                    self.python_requirement.project_skill_requirement_id
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(AssignmentSkill.objects.count(), coverage_count)
        self.assertIn(NON_FIELD_ERRORS, response.context["form"].errors)
        self.assertContains(
            response,
            "This assignment already covers this project requirement.",
        )

    def test_removal_requires_confirmation_and_preserves_parent_records(self):
        response = self.client.get(self.remove_url)
        self.assertTrue(
            AssignmentSkill.objects.filter(pk=self.coverage.pk).exists()
        )
        self.assertContains(response, "Python · Level 4")
        self.assertContains(
            response,
            "The assignment, project requirement, employee skill, and project "
            "will remain unchanged.",
        )

        response = self.client.post(self.remove_url, follow=True)
        self.assertRedirects(response, self.coverage_url)
        self.assertFalse(
            AssignmentSkill.objects.filter(pk=self.coverage.pk).exists()
        )
        self.assertTrue(Assignment.objects.filter(pk=self.assignment.pk).exists())
        self.assertTrue(
            ProjectSkillRequirement.objects.filter(
                pk=self.python_requirement.pk
            ).exists()
        )
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
        self.assertTrue(EmployeeSkill.objects.filter(
            employee=self.employee,
            skill=self.python,
        ).exists())
        self.assertContains(
            response,
            "Python coverage was removed for Jamie Rivera.",
        )

    def test_stale_and_mismatched_assignment_context_returns_not_found(self):
        mismatched_coverage_url = reverse(
            "frontend:project_assignment_coverage",
            args=[self.project.project_id, self.other_assignment.assignment_id],
        )
        mismatched_create_url = reverse(
            "frontend:project_assignment_coverage_create",
            args=[self.project.project_id, self.other_assignment.assignment_id],
        )
        mismatched_remove_url = reverse(
            "frontend:project_assignment_coverage_remove",
            args=[
                self.project.project_id,
                self.assignment.assignment_id,
                self.other_coverage.assignment_skill_id,
            ],
        )
        stale_urls = (
            reverse(
                "frontend:project_assignment_coverage",
                args=[self.project.project_id, 999999],
            ),
            reverse(
                "frontend:project_assignment_coverage_create",
                args=[self.project.project_id, 999999],
            ),
            reverse(
                "frontend:project_assignment_coverage_remove",
                args=[self.project.project_id, self.assignment.assignment_id, 999999],
            ),
        )
        for url in (
            mismatched_coverage_url,
            mismatched_create_url,
            mismatched_remove_url,
            *stale_urls,
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

        for url in (mismatched_create_url, mismatched_remove_url, *stale_urls[1:]):
            with self.subTest(method="post", url=url):
                self.assertEqual(self.client.post(url).status_code, 404)

        self.assertTrue(
            AssignmentSkill.objects.filter(pk=self.other_coverage.pk).exists()
        )

    def test_anonymous_and_viewer_users_cannot_mutate_coverage(self):
        for url in (self.create_url, self.remove_url):
            with self.subTest(access="anonymous", url=url):
                response = Client().get(url)
                self.assertRedirects(
                    response,
                    f"{reverse('frontend:login')}?next={url}",
                    fetch_redirect_response=False,
                )

        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        self.assertEqual(viewer_client.get(self.coverage_url).status_code, 200)
        self.assertEqual(viewer_client.get(self.create_url).status_code, 403)
        self.assertEqual(viewer_client.get(self.remove_url).status_code, 403)
        self.assertEqual(
            viewer_client.post(
                self.create_url,
                {
                    "project_skill_requirement": (
                        self.django_requirement.project_skill_requirement_id
                    )
                },
            ).status_code,
            403,
        )
        self.assertEqual(viewer_client.post(self.remove_url).status_code, 403)
        self.assertTrue(
            AssignmentSkill.objects.filter(pk=self.coverage.pk).exists()
        )

    def test_add_and_delete_permissions_are_enforced_independently(self):
        add_client = Client()
        add_client.force_login(self.add_only_user)
        self.assertEqual(add_client.get(self.create_url).status_code, 200)
        self.assertEqual(add_client.get(self.remove_url).status_code, 403)

        delete_client = Client()
        delete_client.force_login(self.delete_only_user)
        self.assertEqual(delete_client.get(self.create_url).status_code, 403)
        self.assertEqual(delete_client.get(self.remove_url).status_code, 200)

    def test_manager_can_add_but_cannot_remove_coverage(self):
        manager_client = Client()
        manager_client.force_login(self.manager)

        detail_response = manager_client.get(self.coverage_url)
        self.assertContains(detail_response, self.create_url)
        self.assertNotContains(detail_response, self.remove_url)
        self.assertEqual(manager_client.get(self.create_url).status_code, 200)
        self.assertEqual(manager_client.get(self.remove_url).status_code, 403)

    def test_csrf_enforcement_rejects_add_and_remove_without_tokens(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr_admin)
        coverage_count = AssignmentSkill.objects.count()

        self.assertEqual(
            csrf_client.post(
                self.create_url,
                {
                    "project_skill_requirement": (
                        self.django_requirement.project_skill_requirement_id
                    )
                },
            ).status_code,
            403,
        )
        self.assertEqual(csrf_client.post(self.remove_url).status_code, 403)
        self.assertEqual(AssignmentSkill.objects.count(), coverage_count)
        self.assertTrue(
            AssignmentSkill.objects.filter(pk=self.coverage.pk).exists()
        )

    def test_rendered_csrf_tokens_allow_add_and_remove(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr_admin)

        add_form = csrf_client.get(self.create_url)
        add_response = csrf_client.post(
            self.create_url,
            {
                "project_skill_requirement": (
                    self.django_requirement.project_skill_requirement_id
                ),
                "csrfmiddlewaretoken": self.coverage_form_csrf_token(add_form),
            },
        )
        self.assertRedirects(
            add_response,
            self.coverage_url,
            fetch_redirect_response=False,
        )

        remove_form = csrf_client.get(self.remove_url)
        remove_response = csrf_client.post(
            self.remove_url,
            {
                "csrfmiddlewaretoken": self.removal_form_csrf_token(
                    remove_form,
                    self.remove_url,
                )
            },
        )
        self.assertRedirects(
            remove_response,
            self.coverage_url,
            fetch_redirect_response=False,
        )
        self.assertFalse(
            AssignmentSkill.objects.filter(pk=self.coverage.pk).exists()
        )

    def test_failed_add_and_remove_roll_back_with_feedback(self):
        original_save = AssignmentSkill.save
        original_delete = AssignmentSkill.delete

        def save_then_fail(instance, *args, **kwargs):
            original_save(instance, *args, **kwargs)
            raise DatabaseError("Simulated coverage save failure")

        def delete_then_fail(instance, *args, **kwargs):
            original_delete(instance, *args, **kwargs)
            raise DatabaseError("Simulated coverage delete failure")

        with patch.object(AssignmentSkill, "save", new=save_then_fail):
            create_response = self.client.post(
                self.create_url,
                {
                    "project_skill_requirement": (
                        self.django_requirement.project_skill_requirement_id
                    )
                },
            )
        self.assertEqual(create_response.status_code, 200)
        self.assertFalse(
            AssignmentSkill.objects.filter(
                assignment=self.assignment,
                project_skill_requirement=self.django_requirement,
            ).exists()
        )
        self.assertContains(
            create_response,
            "We could not add this requirement coverage. No changes were "
            "applied. Please try again.",
        )

        with patch.object(AssignmentSkill, "delete", new=delete_then_fail):
            remove_response = self.client.post(self.remove_url)
        self.assertEqual(remove_response.status_code, 200)
        self.assertTrue(
            AssignmentSkill.objects.filter(pk=self.coverage.pk).exists()
        )
        self.assertContains(
            remove_response,
            "We could not remove this requirement coverage. No changes were "
            "applied. Please try again.",
        )

    def test_remove_rejects_unsupported_methods_without_mutation(self):
        response = self.client.put(self.remove_url)

        self.assertEqual(response.status_code, 405)
        self.assertTrue(
            AssignmentSkill.objects.filter(pk=self.coverage.pk).exists()
        )

    def test_empty_project_has_clear_coverage_and_add_states(self):
        empty_project = self._create_project("Empty Project")
        empty_assignment = self._create_assignment(
            empty_project,
            self.employee,
            role="Advisor",
        )
        coverage_url = reverse(
            "frontend:project_assignment_coverage",
            args=[empty_project.project_id, empty_assignment.assignment_id],
        )
        create_url = reverse(
            "frontend:project_assignment_coverage_create",
            args=[empty_project.project_id, empty_assignment.assignment_id],
        )

        detail_response = self.client.get(coverage_url)
        self.assertContains(detail_response, "No project requirements defined")
        self.assertNotContains(detail_response, create_url)

        create_response = self.client.get(create_url)
        self.assertContains(create_response, "No unlinked requirements")
        self.assertNotContains(
            create_response,
            '<button class="btn btn-primary" type="submit"',
        )

    def test_populated_coverage_page_matches_recorded_query_budget(self):
        with self.assertNumQueries(self.EXPECTED_COVERAGE_QUERY_COUNT):
            response = self.client.get(self.coverage_url)

        self.assertEqual(response.status_code, 200)

    def test_warm_coverage_response_time_is_recorded(self):
        warmup_response = self.client.get(self.coverage_url)
        self.assertEqual(warmup_response.status_code, 200)

        durations_ms = []
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as captured_queries:
                started_at = time.perf_counter()
                response = self.client.get(self.coverage_url)
                durations_ms.append((time.perf_counter() - started_at) * 1000)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                len(captured_queries),
                self.EXPECTED_COVERAGE_QUERY_COUNT,
            )

        p95_ms = statistics.quantiles(
            durations_ms,
            n=20,
            method="inclusive",
        )[18]
        print(
            "\nM3.6 assignment-coverage baseline "
            f"({self.TIMING_SAMPLE_COUNT} warm Django test-client GETs, "
            "5 requirements, 1 existing link):\n"
            f"  queries={self.EXPECTED_COVERAGE_QUERY_COUNT}, "
            f"median={statistics.median(durations_ms):.3f} ms, "
            f"p95={p95_ms:.3f} ms, "
            f"min={min(durations_ms):.3f} ms, "
            f"max={max(durations_ms):.3f} ms"
        )
