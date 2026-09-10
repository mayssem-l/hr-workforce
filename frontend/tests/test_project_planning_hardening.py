import inspect
import statistics
import time
from datetime import date
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

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
from core.services.effective_availability import (
    calculate_available_hours_for_project,
)
from core.services.matching import rank_employees_for_project
from core.services.optimization import build_optimization_context, units_to_hours
from frontend.presenters.planning import (
    build_candidate_exclusion_context,
    build_project_planning_workspace,
    build_requirement_evidence_context,
)
from frontend.roles import (
    HR_ADMINISTRATOR_GROUP,
    VIEWER_GROUP,
    sync_role_permissions,
)
from frontend.selectors.planning import get_candidate_exclusion_workforce
from frontend.selectors.projects import get_project_profile


class _PlanningMarkupAudit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.references = []
        self.headings = []
        self.tables = []
        self._table_stack = []
        self.positive_tabindex = []
        self.inline_handlers = []
        self.anchors_without_href = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.ids.append(element_id)
        for attribute in ("aria-labelledby", "aria-describedby"):
            if attributes.get(attribute):
                self.references.extend(attributes[attribute].split())
        if len(tag) == 2 and tag.startswith("h") and tag[1].isdigit():
            self.headings.append(int(tag[1]))
        if tag == "table":
            table = {"caption_count": 0, "header_scopes": []}
            self.tables.append(table)
            self._table_stack.append(table)
        elif tag == "caption" and self._table_stack:
            self._table_stack[-1]["caption_count"] += 1
        elif tag == "th" and self._table_stack:
            self._table_stack[-1]["header_scopes"].append(
                attributes.get("scope")
            )
        if tag == "a" and not attributes.get("href"):
            self.anchors_without_href.append(attributes)
        tabindex = attributes.get("tabindex")
        if tabindex and tabindex.lstrip("-").isdigit() and int(tabindex) > 0:
            self.positive_tabindex.append((tag, tabindex))
        self.inline_handlers.extend(
            attribute
            for attribute in attributes
            if attribute.startswith("on")
        )

    def handle_endtag(self, tag):
        if tag == "table" and self._table_stack:
            self._table_stack.pop()


class _PlanningBaselineMixin:
    TIMING_SAMPLE_COUNT = 7
    AUTHENTICATED_SHELL_QUERY_COUNT = 4

    def _service_workspace(self):
        project = get_project_profile(self.project.project_id)
        workspace = build_project_planning_workspace(project)
        workforce = ()
        if workspace["readiness"]["candidate_assessment_allowed"]:
            workforce = get_candidate_exclusion_workforce()
        workspace["candidate_exclusions"] = build_candidate_exclusion_context(
            project,
            workspace["readiness"],
            workspace["candidates"],
            workforce,
        )
        return workspace

    def _measure_baseline(self, label, expected_service_queries, expected_page_queries):
        self.assertEqual(
            expected_page_queries - expected_service_queries,
            self.AUTHENTICATED_SHELL_QUERY_COUNT,
        )
        warm_service = self._service_workspace()
        self.assertEqual(warm_service["project"], self.project)
        warm_response = self.client.get(self.url)
        self.assertEqual(warm_response.status_code, 200)

        service_durations = []
        response_durations = []
        response_sizes = []
        for _ in range(self.TIMING_SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as service_queries:
                started_at = time.perf_counter()
                workspace = self._service_workspace()
                service_durations.append((time.perf_counter() - started_at) * 1000)
            self.assertEqual(len(service_queries), expected_service_queries)
            self.assertEqual(workspace["project"], self.project)

            with CaptureQueriesContext(connection) as page_queries:
                started_at = time.perf_counter()
                response = self.client.get(self.url)
                response_durations.append((time.perf_counter() - started_at) * 1000)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(page_queries), expected_page_queries)
            response_sizes.append(len(response.content))

        service_p95 = statistics.quantiles(
            service_durations,
            n=20,
            method="inclusive",
        )[18]
        response_p95 = statistics.quantiles(
            response_durations,
            n=20,
            method="inclusive",
        )[18]
        print(
            f"\nM5.7 {label} final warm baseline "
            f"({self.TIMING_SAMPLE_COUNT} samples):\n"
            f"  service_queries={expected_service_queries}, "
            f"service_median={statistics.median(service_durations):.3f} ms, "
            f"service_p95={service_p95:.3f} ms\n"
            f"  page_queries={expected_page_queries} "
            f"({self.AUTHENTICATED_SHELL_QUERY_COUNT} shell + "
            f"{expected_service_queries} planning), "
            f"response_median={statistics.median(response_durations):.3f} ms, "
            f"response_p95={response_p95:.3f} ms, "
            f"response={max(response_sizes)} bytes"
        )


class ProjectPlanningPopulatedHardeningTests(_PlanningBaselineMixin, TestCase):
    EXPECTED_SERVICE_QUERY_COUNT = 17
    EXPECTED_PAGE_QUERY_COUNT = 21

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = cls._role_user("m5-hardening-viewer", VIEWER_GROUP)
        cls.hr_user = cls._role_user("m5-hardening-hr", HR_ADMINISTRATOR_GROUP)

        cls.python = Skill.objects.create(name="Python", category="Engineering")
        cls.design = Skill.objects.create(
            name="Service design",
            category="Design",
        )
        cls.unused = Skill.objects.create(name="Rust", category="Engineering")
        cls.project = cls._project("M5 hardening project")
        cls.python_requirement = cls._requirement(
            cls.project,
            cls.python,
            quantity=2,
            effort="40.00",
        )
        cls.design_requirement = cls._requirement(
            cls.project,
            cls.design,
            quantity=1,
            effort="8.00",
            mandatory=False,
        )

        cls.alex = cls._employee("Alex", "Able")
        cls.blair = cls._employee("Blair", "Baker")
        cls.casey = cls._employee("Casey", "Clark")
        cls.inactive = cls._employee(
            "Inactive",
            "Dover",
            status=Employee.Status.INACTIVE,
        )
        cls.unqualified = cls._employee("Unqualified", "Evans")
        for employee, skill, level in (
            (cls.alex, cls.python, 4),
            (cls.blair, cls.python, 3),
            (cls.casey, cls.design, 3),
            (cls.inactive, cls.python, 5),
        ):
            EmployeeSkill.objects.create(
                employee=employee,
                skill=skill,
                level=level,
                years_experience=Decimal("4.0"),
            )

        cls.target_assignment = Assignment.objects.create(
            employee=cls.alex,
            project=cls.project,
            start_date=cls.project.start_date,
            end_date=cls.project.end_date,
            allocation_percentage=25,
            role_on_project="Python lead",
            status=Assignment.Status.ACTIVE,
        )
        AssignmentSkill.objects.create(
            assignment=cls.target_assignment,
            project_skill_requirement=cls.python_requirement,
        )

        cls.other_project = cls._project("Boundary project")
        cls.other_requirement = cls._requirement(
            cls.other_project,
            cls.unused,
            quantity=1,
            effort="8.00",
        )
        cls.other_assignment = Assignment.objects.create(
            employee=cls.blair,
            project=cls.other_project,
            start_date=cls.project.start_date,
            end_date=cls.project.end_date,
            allocation_percentage=50,
            role_on_project="Competing delivery",
            status=Assignment.Status.ACTIVE,
        )
        cls.approved_leave = Leave.objects.create(
            employee=cls.alex,
            start_date=date(2026, 9, 9),
            end_date=date(2026, 9, 9),
            type=Leave.Type.ANNUAL,
            status=Leave.Status.APPROVED,
        )

        cls.no_requirements_project = cls._project("No requirements project")
        cls.no_eligible_project = cls._project("No eligible employees project")
        cls._requirement(
            cls.no_eligible_project,
            cls.unused,
            quantity=1,
            effort="8.00",
        )
        cls.capacity_project = cls._project("Capacity boundary project")
        cls.capacity_requirement = cls._requirement(
            cls.capacity_project,
            cls.python,
            quantity=2,
            effort="80.00",
        )
        cls.capacity_unstaffed_requirement = cls._requirement(
            cls.capacity_project,
            cls.unused,
            quantity=1,
            effort="8.00",
        )

    @staticmethod
    def _role_user(username, role):
        user = get_user_model().objects.create_user(username=username)
        user.groups.add(Group.objects.get(name=role))
        return user

    @staticmethod
    def _project(name):
        return Project.objects.create(
            name=name,
            description="M5.7 planning boundary and accessibility evidence.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            estimated_hours=Decimal("48.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )

    @staticmethod
    def _requirement(
        project,
        skill,
        *,
        quantity,
        effort,
        mandatory=True,
    ):
        return ProjectSkillRequirement.objects.create(
            project=project,
            skill=skill,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=mandatory,
            required_quantity=quantity,
            estimated_effort_hours=Decimal(effort) if effort is not None else None,
        )

    @staticmethod
    def _employee(first_name, last_name, *, status=Employee.Status.ACTIVE):
        return Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            department="Engineering",
            position="Engineer",
            hire_date=date(2020, 1, 6),
            experience_years=Decimal("6.0"),
            capacity_hours_week=Decimal("40.00"),
            status=status,
        )

    def setUp(self):
        self.client.force_login(self.viewer)
        self.url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )

    def test_populated_final_query_service_and_response_baseline(self):
        self._measure_baseline(
            "populated workspace (2 requirements, 5 employees, 1 coverage link)",
            self.EXPECTED_SERVICE_QUERY_COUNT,
            self.EXPECTED_PAGE_QUERY_COUNT,
        )

    def test_project_requirement_assignment_and_service_boundaries(self):
        selected = get_project_profile(self.project.project_id)
        self.assertEqual(
            [row.pk for row in selected.profile_requirements],
            [self.python_requirement.pk, self.design_requirement.pk],
        )
        self.assertEqual(
            [row.pk for row in selected.profile_assignments],
            [self.target_assignment.pk],
        )
        self.assertNotIn(self.other_requirement, selected.profile_requirements)
        self.assertNotIn(self.other_assignment, selected.profile_assignments)

        workspace = self._service_workspace()
        expected_candidates = rank_employees_for_project(self.project)
        self.assertEqual(
            [row["employee"].pk for row in workspace["candidates"]["rows"]],
            [row["employee"].pk for row in expected_candidates],
        )
        self.assertNotIn(
            self.inactive.pk,
            [row["employee"].pk for row in workspace["candidates"]["rows"]],
        )
        exclusion_by_employee = {
            row["employee"].pk: row["reason_code"]
            for row in workspace["candidate_exclusions"]["rows"]
        }
        self.assertEqual(exclusion_by_employee[self.inactive.pk], "inactive_status")
        self.assertEqual(
            exclusion_by_employee[self.unqualified.pk],
            "no_qualifying_requirement",
        )

        optimization_context = build_optimization_context(self.project)
        for employee in (self.alex, self.blair):
            scalar_hours = calculate_available_hours_for_project(
                employee,
                self.project,
            )
            self.assertEqual(
                units_to_hours(
                    optimization_context["available_hours"][employee.pk]
                ),
                scalar_hours,
            )
        self.assertEqual(
            calculate_available_hours_for_project(self.alex, self.project),
            Decimal("32.00"),
        )
        self.assertEqual(
            calculate_available_hours_for_project(self.blair, self.project),
            Decimal("20.00"),
        )

    def test_empty_missing_effort_headcount_and_capacity_states(self):
        empty = self.client.get(
            reverse(
                "frontend:project_planning",
                args=[self.no_requirements_project.pk],
            )
        )
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.context["workspace"]["requirement_count"], 0)
        self.assertEqual(
            [
                blocker["code"]
                for blocker in empty.context["workspace"]["readiness"]["blockers"]
            ],
            ["no_mandatory_requirements"],
        )

        no_eligible = self.client.get(
            reverse(
                "frontend:project_planning",
                args=[self.no_eligible_project.pk],
            )
        )
        self.assertEqual(no_eligible.status_code, 200)
        self.assertEqual(
            [
                blocker["code"]
                for blocker in no_eligible.context["workspace"]["readiness"][
                    "blockers"
                ]
            ],
            ["insufficient_eligible_headcount"],
        )
        self.assertEqual(
            no_eligible.context["workspace"]["candidates"]["state"],
            "blocked",
        )

        capacity_url = reverse(
            "frontend:project_planning",
            args=[self.capacity_project.pk],
        )
        blocker_snapshots = []
        for _ in range(3):
            capacity = self.client.get(capacity_url)
            self.assertEqual(capacity.status_code, 200)
            blocker_snapshots.append(
                tuple(
                    (blocker["code"], getattr(blocker.get("requirement"), "pk", 0))
                    for blocker in capacity.context["workspace"]["readiness"][
                        "blockers"
                    ]
                )
            )
        self.assertEqual(
            blocker_snapshots[0],
            (
                (
                    "insufficient_eligible_headcount",
                    self.capacity_unstaffed_requirement.pk,
                ),
                (
                    "insufficient_qualified_capacity",
                    self.capacity_requirement.pk,
                ),
            ),
        )
        self.assertEqual(blocker_snapshots[1:], [blocker_snapshots[0]] * 2)

        self.python_requirement.estimated_effort_hours = None
        self.python_requirement.save(update_fields=["estimated_effort_hours"])
        missing = self.client.get(self.url)
        self.assertEqual(missing.status_code, 200)
        self.assertIn(
            "mandatory_effort_must_be_positive",
            [
                blocker["code"]
                for blocker in missing.context["workspace"]["readiness"]["blockers"]
            ],
        )
        self.assertEqual(
            missing.context["workspace"]["requirement_evidence"]["state"],
            "paused",
        )
        self.assertContains(missing, "Not entered")

    def test_stale_deleted_and_cross_project_targets_remain_safe(self):
        missing_planning_url = reverse(
            "frontend:project_planning",
            args=[999999],
        )
        self.assertEqual(self.client.get(missing_planning_url).status_code, 404)

        hr_client = Client()
        hr_client.force_login(self.hr_user)
        cross_requirement_url = reverse(
            "frontend:project_requirement_update",
            args=[self.project.pk, self.other_requirement.pk],
        )
        cross_assignment_url = reverse(
            "frontend:project_assignment_update",
            args=[self.project.pk, self.other_assignment.pk],
        )
        self.assertEqual(hr_client.get(cross_requirement_url).status_code, 404)
        self.assertEqual(hr_client.get(cross_assignment_url).status_code, 404)

        stale_project = self._project("Deleted planning target")
        stale_project_id = stale_project.pk
        stale_project.delete()
        self.assertEqual(
            self.client.get(
                reverse("frontend:project_planning", args=[stale_project_id])
            ).status_code,
            404,
        )

        stale_requirement = self._requirement(
            self.project,
            self.unused,
            quantity=1,
            effort="8.00",
        )
        stale_requirement_id = stale_requirement.pk
        stale_requirement.delete()
        self.assertEqual(
            hr_client.get(
                reverse(
                    "frontend:project_requirement_update",
                    args=[self.project.pk, stale_requirement_id],
                )
            ).status_code,
            404,
        )

        stale_assignment = Assignment.objects.create(
            employee=self.casey,
            project=self.project,
            start_date=self.project.start_date,
            end_date=self.project.end_date,
            allocation_percentage=10,
            role_on_project="Deleted assignment",
            status=Assignment.Status.PLANNED,
        )
        stale_assignment_id = stale_assignment.pk
        stale_assignment.delete()
        self.assertEqual(
            hr_client.get(
                reverse(
                    "frontend:project_assignment_update",
                    args=[self.project.pk, stale_assignment_id],
                )
            ).status_code,
            404,
        )

    def test_keyboard_focus_semantics_and_responsive_evidence(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        audit = _PlanningMarkupAudit()
        audit.feed(html)

        self.assertIn('<html lang="en">', html)
        self.assertLess(html.index('class="skip-link"'), html.index("<main"))
        self.assertIn('class="skip-link" href="#main-content"', html)
        self.assertIn(
            '<main class="app-main" id="main-content" tabindex="-1">',
            html,
        )
        self.assertEqual(len(audit.ids), len(set(audit.ids)))
        self.assertFalse(set(audit.references) - set(audit.ids))
        self.assertTrue(audit.headings)
        self.assertEqual(audit.headings[0], 1)
        self.assertEqual(audit.headings.count(1), 1)
        self.assertTrue(
            all(
                current <= previous + 1
                for previous, current in zip(
                    audit.headings,
                    audit.headings[1:],
                )
            )
        )
        self.assertTrue(audit.tables)
        self.assertTrue(
            all(table["caption_count"] == 1 for table in audit.tables)
        )
        self.assertTrue(
            all(
                scope in {"col", "row"}
                for table in audit.tables
                for scope in table["header_scopes"]
            )
        )
        self.assertTrue(
            all(
                "col" in table["header_scopes"]
                and "row" in table["header_scopes"]
                for table in audit.tables
            )
        )
        self.assertFalse(audit.positive_tabindex)
        self.assertFalse(audit.inline_handlers)
        self.assertFalse(audit.anchors_without_href)
        self.assertEqual(html.count('class="table-responsive"'), len(audit.tables))
        self.assertIn('role="status"', html)
        self.assertIn("Ready for candidate assessment", html)
        self.assertIn("Current coverage", html)
        self.assertIn("Qualified active employees", html)
        self.assertNotIn("<canvas", html)
        self.assertNotIn("<svg", html)

        frontend_root = Path(__file__).resolve().parents[1]
        theme = (frontend_root / "static/frontend/css/theme.css").read_text(
            encoding="utf-8"
        )
        bootstrap = (
            frontend_root / "static/frontend/vendor/bootstrap-5.3.8.min.css"
        ).read_text(encoding="utf-8")
        self.assertIn(":focus-visible", theme)
        self.assertIn("outline: 3px solid var(--wf-focus) !important;", theme)
        self.assertIn(".skip-link:focus", theme)
        self.assertIn("@media (prefers-reduced-motion: reduce)", theme)
        self.assertIn(".table-responsive{overflow-x:auto", bootstrap)
        self.assertIn("@media (max-width: 991.98px)", theme)
        self.assertIn(".requirement-evidence-states", theme)

    def test_planning_source_uses_only_approved_orchestration_boundaries(self):
        frontend_root = Path(__file__).resolve().parents[1]
        python_sources = (
            frontend_root / "views/planning.py",
            frontend_root / "presenters/planning.py",
            frontend_root / "presenters/planning_navigation.py",
            frontend_root / "selectors/planning.py",
        )
        template_sources = tuple(
            (frontend_root / "templates/frontend/planning").glob("*.html")
        )
        python_source = "\n".join(
            source.read_text(encoding="utf-8").lower()
            for source in python_sources
        )
        all_source = python_source + "\n" + "\n".join(
            source.read_text(encoding="utf-8").lower()
            for source in template_sources
        )
        for forbidden_call in (
            "calculate_employee_project_match(",
            "calculate_skill_score(",
            "calculate_min_available_capacity(",
            "calculate_leave_availability_rate(",
            "calculate_available_hours_for_project(",
            "find_all_feasible_teams(",
            "solve_team_effort_allocation(",
            "select_recommended_teams(",
            "build_recommendation_explanations(",
            "attendance.objects",
            "from core.models import attendance",
            "gemini",
            "ortools",
        ):
            with self.subTest(forbidden_call=forbidden_call):
                self.assertNotIn(forbidden_call, all_source)
        self.assertEqual(python_source.count("rank_employees_for_project("), 1)
        self.assertEqual(python_source.count("build_optimization_context("), 1)
        self.assertEqual(
            inspect.getsource(build_requirement_evidence_context)
            .lower()
            .count("get_requirement_capacity_evidence("),
            1,
        )
        app_js = (frontend_root / "static/frontend/js/app.js").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("planning", app_js.lower())


class ProjectPlanningIncompleteBaselineTests(_PlanningBaselineMixin, TestCase):
    EXPECTED_SERVICE_QUERY_COUNT = 4
    EXPECTED_PAGE_QUERY_COUNT = 8

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="m5-incomplete-baseline-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        skill = Skill.objects.create(name="Data analysis", category="Data")
        cls.project = Project.objects.create(
            name="Incomplete M5 workspace",
            description="Missing mandatory effort stops downstream assessment.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11),
            estimated_hours=Decimal("40.00"),
            status=Project.Status.PLANNED,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )
        ProjectSkillRequirement.objects.create(
            project=cls.project,
            skill=skill,
            required_level=3,
            priority=ProjectSkillRequirement.Priority.HIGH,
            is_mandatory=True,
            required_quantity=1,
            estimated_effort_hours=None,
        )

    def setUp(self):
        self.client.force_login(self.viewer)
        self.url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )

    def test_incomplete_final_query_service_and_response_baseline(self):
        self._measure_baseline(
            "incomplete workspace (missing mandatory effort)",
            self.EXPECTED_SERVICE_QUERY_COUNT,
            self.EXPECTED_PAGE_QUERY_COUNT,
        )
        workspace = self.client.get(self.url).context["workspace"]
        self.assertEqual(workspace["candidates"]["state"], "blocked")
        self.assertEqual(workspace["candidate_exclusions"]["state"], "blocked")
        self.assertEqual(workspace["requirement_evidence"]["state"], "paused")


class ProjectPlanningLargeBaselineTests(_PlanningBaselineMixin, TestCase):
    EXPECTED_SERVICE_QUERY_COUNT = 17
    EXPECTED_PAGE_QUERY_COUNT = 21
    EMPLOYEE_COUNT = 60
    REQUIREMENT_COUNT = 12
    ASSIGNMENT_COUNT = 24

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(
            username="m5-large-baseline-viewer"
        )
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))
        cls.project = Project.objects.create(
            name="Large realistic M5 workspace",
            description="A scaled planning workspace used to verify fixed query cost.",
            start_date=date(2026, 9, 7),
            end_date=date(2026, 10, 2),
            estimated_hours=Decimal("960.00"),
            status=Project.Status.IN_PROGRESS,
            priority=Project.Priority.HIGH,
            criticality=Project.Criticality.HIGH,
        )
        skills = [
            Skill.objects.create(
                name=f"Planning skill {index:02d}",
                category=f"Discipline {index % 4}",
            )
            for index in range(cls.REQUIREMENT_COUNT)
        ]
        requirements = [
            ProjectSkillRequirement.objects.create(
                project=cls.project,
                skill=skill,
                required_level=3,
                priority=ProjectSkillRequirement.Priority.HIGH,
                is_mandatory=True,
                required_quantity=2,
                estimated_effort_hours=Decimal("80.00"),
            )
            for skill in skills
        ]
        employees = [
            Employee(
                first_name=f"Employee {index:02d}",
                last_name=f"Planner {index:02d}",
                department=f"Department {index % 5}",
                position="Planning specialist",
                hire_date=date(2019, 1, 7),
                experience_years=Decimal(str(3 + (index % 8))),
                capacity_hours_week=Decimal("40.00"),
                status=(
                    Employee.Status.INACTIVE
                    if index >= 54
                    else Employee.Status.ACTIVE
                ),
            )
            for index in range(cls.EMPLOYEE_COUNT)
        ]
        Employee.objects.bulk_create(employees)
        EmployeeSkill.objects.bulk_create(
            [
                EmployeeSkill(
                    employee=employees[index],
                    skill=skills[index // 4],
                    level=3 + (index % 3),
                    years_experience=Decimal("4.0"),
                )
                for index in range(48)
            ]
        )

        target_assignments = []
        for requirement_index, requirement in enumerate(requirements):
            for offset in range(2):
                employee = employees[(requirement_index * 4) + offset]
                target_assignments.append(
                    Assignment(
                        employee=employee,
                        project=cls.project,
                        start_date=cls.project.start_date,
                        end_date=cls.project.end_date,
                        allocation_percentage=25,
                        role_on_project=f"Coverage {requirement_index:02d}",
                        status=(
                            Assignment.Status.ACTIVE
                            if offset == 0
                            else Assignment.Status.PLANNED
                        ),
                    )
                )
        Assignment.objects.bulk_create(target_assignments)
        AssignmentSkill.objects.bulk_create(
            [
                AssignmentSkill(
                    assignment=assignment,
                    project_skill_requirement=requirements[index // 2],
                )
                for index, assignment in enumerate(target_assignments)
            ]
        )

        competing_project = Project.objects.create(
            name="Large fixture competing delivery",
            description="Overlapping work used by existing availability services.",
            start_date=cls.project.start_date,
            end_date=cls.project.end_date,
            estimated_hours=Decimal("400.00"),
            status=Project.Status.IN_PROGRESS,
            priority=Project.Priority.MEDIUM,
            criticality=Project.Criticality.MEDIUM,
        )
        Assignment.objects.bulk_create(
            [
                Assignment(
                    employee=employees[index],
                    project=competing_project,
                    start_date=cls.project.start_date,
                    end_date=cls.project.end_date,
                    allocation_percentage=40,
                    role_on_project="Existing workload",
                    status=Assignment.Status.ACTIVE,
                )
                for index in range(0, 48, 4)
            ]
        )
        Leave.objects.bulk_create(
            [
                Leave(
                    employee=employees[index],
                    start_date=date(2026, 9, 16),
                    end_date=date(2026, 9, 16),
                    type=Leave.Type.ANNUAL,
                    status=Leave.Status.APPROVED,
                )
                for index in range(1, 48, 8)
            ]
        )

    def setUp(self):
        self.client.force_login(self.viewer)
        self.url = reverse(
            "frontend:project_planning",
            args=[self.project.project_id],
        )

    @staticmethod
    def _ordering_snapshot(workspace):
        return (
            tuple(
                (blocker["code"], getattr(blocker.get("requirement"), "pk", 0))
                for blocker in workspace["readiness"]["blockers"]
            ),
            tuple(
                row["employee"].pk for row in workspace["candidates"]["rows"]
            ),
            tuple(
                (row["employee"].pk, row["reason_code"])
                for row in workspace["candidate_exclusions"]["rows"]
            ),
            tuple(requirement.pk for requirement in workspace["requirements"]),
            tuple(
                (
                    row["requirement"].pk,
                    tuple(item["employee"].pk for item in row["qualified_rows"]),
                    tuple(item["assignment"].pk for item in row["coverage_rows"]),
                    row["qualification_state"]["code"],
                    row["capacity_state"]["code"],
                    row["coverage_state"]["code"],
                )
                for row in workspace["requirement_evidence"]["rows"]
            ),
            tuple(assignment.pk for assignment in workspace["assignments"]),
        )

    def test_large_workspace_has_fixed_queries_and_deterministic_ordering(self):
        self._measure_baseline(
            "large workspace (60 employees, 12 requirements, 24 coverage links)",
            self.EXPECTED_SERVICE_QUERY_COUNT,
            self.EXPECTED_PAGE_QUERY_COUNT,
        )
        snapshots = []
        for _ in range(5):
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            workspace = response.context["workspace"]
            self.assertTrue(workspace["readiness"]["is_ready"])
            self.assertEqual(workspace["requirement_count"], self.REQUIREMENT_COUNT)
            self.assertEqual(workspace["assignment_count"], self.ASSIGNMENT_COUNT)
            self.assertEqual(workspace["candidates"]["count"], 48)
            self.assertEqual(workspace["candidate_exclusions"]["count"], 12)
            snapshots.append(self._ordering_snapshot(workspace))
        self.assertTrue(all(snapshot == snapshots[0] for snapshot in snapshots[1:]))
