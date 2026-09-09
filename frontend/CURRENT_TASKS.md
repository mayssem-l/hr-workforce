# Current Tasks

Last updated: 2026-09-09

## Active milestone

**Milestone 4 — Workforce dashboard and employee insights**

Status: In progress. Milestone 3 is approved and complete. Task M4.1 is complete and awaiting approval; Milestone 4 application work is limited to the approved read-only dashboard filter foundation.

Goal: let managers move from a filtered workforce overview to the employees, assignments, projects, and dated leave that explain capacity, workload, availability, utilization, and descriptive attendance signals.

Implementation constraints: keep the interface server-rendered inside the Django monolith; preserve the existing workforce-planning visual identity and responsive shell; keep all user-visible text in natural, manager-friendly English; enforce the approved Django model-permission policy; reuse existing `core` workload, leave, effective-availability, and attendance services instead of duplicating calculations in selectors, templates, or browser code; keep the current Monday-to-Friday capacity assumption explicit; present every chart with an accessible table or text equivalent; preserve filter context across drill-down links; keep attendance descriptive and separate from staffing recommendations; and measure page-specific queries above the four-query authenticated-shell baseline.

## Current focus

Task M4.2 — Workforce KPI summary. Not started; awaiting approval after M4.1 review.

## Milestone 4 task breakdown

### M4.1 Dashboard date-range and filter foundation

- [x] Replace the foundation-only dashboard content with a read-only Milestone 4 dashboard frame while preserving the existing route, shell, visual identity, and responsive behavior.
- [x] Add one server-validated, inclusive reporting-period control with documented default behavior and clear start/end date errors; use the configured Django date context and retain the existing Monday-to-Friday service assumptions without inventing a holiday calendar.
- [x] Add department, employee status, and project status filters from existing stored values, with stable choices, safe handling of stale or invalid query parameters, and a clear applied-filter summary.
- [x] Preserve the complete validated filter state in dashboard GET links and provide an obvious reset action; do not calculate or render Milestone 4 KPIs yet.
- [x] Require the existing view permissions for every model represented by the dashboard filter contract and test routing, templates, navigation, valid/invalid ranges, filter persistence, empty choice sets, permission boundaries, query count, and warm response time.

Scope boundary: M4.1 establishes the shared read-only dashboard and filter contract only. It adds no KPI calculations, charts, timelines, attendance summaries, writes, model changes, or recommendation behavior.

Completion evidence:

- Created files: `frontend/forms/dashboard.py`, `frontend/presenters/dashboard.py`, and `frontend/tests/test_dashboard_filters.py`.
- Modified files: `frontend/views/landing.py`, `frontend/templates/frontend/dashboard/landing.html`, `frontend/static/frontend/css/theme.css`, `frontend/tests/test_landing.py`, `frontend/tests/test_foundation_verification.py`, and `frontend/CURRENT_TASKS.md`.
- Dashboard-frame result: the existing `/` route, authenticated shell, Dashboard navigation state, workforce-planning visual identity, and responsive behavior are preserved while the foundation placeholder is replaced by a read-only workforce-overview frame. It contains reporting context only; no KPI, chart, timeline, attendance summary, calculation, or write workflow was added.
- Reporting-period result: the configured Django local date selects the current calendar month by default. Both boundary dates are explicitly inclusive, same-day ranges are allowed, missing and malformed dates receive field-level English errors, and an end date before the start date suppresses reporting context until corrected. The existing Monday-to-Friday assumption and absence of a holiday calendar are stated without changing any service rule.
- Filter result: department choices come from distinct stored employee departments in stable order, while employee and project statuses reuse their model-defined choices. Valid filters remain selected and receive a manager-readable summary; stale department or status values safely normalize to the corresponding all-records choice, including when the department dataset is empty.
- Link-state result: the Apply action uses GET, Reset returns to the documented default period, and the current-view link serializes all five validated parameters in stable order: start date, end date, department, employee status, and project status.
- Permission and method result: the dashboard requires both `core.view_employee` and `core.view_project`; anonymous users redirect to login, users holding neither or only one permission receive 403, canonical viewer roles retain access, and non-GET requests receive 405. Existing CSRF-protected shell POST behavior remains unchanged.
- Query and timing result: the page uses five fixed queries for a role-based user: the four-query authenticated shell plus one distinct department-choice query. The final focused 25-request warm run recorded a 6.901 ms median and 7.856 ms p95; the final complete-suite run recorded a 6.891 ms median and 8.075 ms p95.
- Commands run:
  - `python manage.py test frontend.tests.test_dashboard_filters --verbosity 1`
  - focused 20-test dashboard, landing, and foundation verification command
  - `python manage.py test frontend --verbosity 1`
  - `python manage.py test --verbosity 1`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py check`
  - edited-file trailing-whitespace scan
  - `git diff --check`
- Result: all 12 focused M4.1 tests passed in 0.386 s; all 20 combined dashboard/landing/foundation tests passed in 0.731 s; all 283 frontend tests passed in 13.199 s; and the final complete 297-test project suite passed in 14.055 s. Django system checks and migration drift checks pass, and whitespace checks report no errors.
- Lessons result: no reusable lesson beyond the existing filter allow-list, authenticated-shell query-baseline, accessibility, and service-boundary guidance was discovered, so `LESSONS_LEARNED.md` was not changed.

### M4.2 Workforce KPI summary

- [ ] Define and test the reporting-period meaning of each planned KPI before rendering it: headcount by employee status, available capacity, allocated capacity, employees on approved dated leave, active projects, and over-capacity risk.
- [ ] Build optimized selectors for stored aggregates and thin presenters that call existing workload, leave, and effective-availability services for calculated values; do not recreate service formulas in frontend code.
- [ ] Render accessible KPI cards with units, reporting-period context, manager-friendly definitions, clear zero/empty states, and explicit weekday/date-based assumptions.
- [ ] Keep employment status separate from dated approved leave and distinguish scheduled allocation from effective availability wherever both appear.
- [ ] Test boundary dates, overlapping assignments and leave, inactive employees, weekends, project statuses, over-capacity cases, empty datasets, permission scopes, service delegation, fixed query behavior, and warm timing.

Scope boundary: M4.2 adds the six summary signals only. It does not add charts, employee timelines, attendance trends, recommendation inputs, or new calculation rules.

### M4.3 Capacity and utilization distributions

- [ ] Add filtered workforce capacity and utilization distributions using the M4.1 reporting period and the same service-backed values established in M4.2.
- [ ] Define stable, manager-readable distribution bands and centralize presentation shaping outside templates without changing the meaning of workload, capacity, or availability.
- [ ] Render an accessible data table or text equivalent as the primary evidence for every visualization, with charts remaining supplemental and using the existing visual system.
- [ ] Provide useful all-zero, no-employee, and incomplete-context states without presenting missing data as zero capacity.
- [ ] Test band boundaries, exact table/chart agreement, filtered results, empty states, accessibility semantics, permission boundaries, deterministic serialization, query count, and warm timing.

Scope boundary: M4.3 visualizes the existing filtered workforce measures only. It does not add employee timelines, attendance trends, staffing scores, or browser-side business calculations.

### M4.4 Employee workload and availability timeline

- [ ] Extend the existing employee profile with a reporting-period workload and effective-availability timeline driven by the shared M4.1 date contract.
- [ ] Use existing workload and effective-availability services for each displayed value, preserving assignment status/date, inactive employee, weekend, approved-leave, and daily-capacity semantics.
- [ ] Show readable daily or period-bucket evidence with assignment and approved-leave context, an accessible table equivalent, and explicit Monday-to-Friday assumptions.
- [ ] Preserve the selected reporting period when moving between dashboard evidence and an employee profile, with clear empty and partial-data states.
- [ ] Test service delegation, date boundaries, weekends, overlapping work, approved versus non-approved leave, inactive status, missing employees, permissions, accessibility, query behavior, and warm timing.

Scope boundary: M4.4 adds read-only employee insight. It does not edit assignments or leave, create a shared calendar, alter availability formulas, or run recommendations.

### M4.5 Descriptive attendance summaries and trends

- [ ] Add reporting-period attendance summaries using the existing attendance service outputs for total, present, absent, late, remote, and half-day records plus the existing absenteeism and late-rate definitions.
- [ ] Present attendance as descriptive operational history with clear record-count denominators, date context, and accessible trend evidence; never label it as a staffing score or recommendation factor.
- [ ] Link attendance summaries to the filtered attendance records that explain them while preserving employee and date context where supported.
- [ ] Handle no records, partial time coverage, and status-only records without inventing missing observations or changing employee status.
- [ ] Test service delegation, date boundaries, every attendance status, zero-denominator behavior, filtered links, empty states, permissions, table/chart agreement, query count, and warm timing; retain a regression proving recommendation inputs are unchanged.

Scope boundary: M4.5 is read-only and descriptive. It does not change attendance calculations, attendance CRUD, employee availability, matching, optimization, or recommendation selection.

### M4.6 Aggregate evidence and drill-down continuity

- [ ] Connect every dashboard KPI and distribution to the filtered employee, project, assignment, leave, or on-page evidence that explains the aggregate.
- [ ] Define an explicit mapping from each aggregate to its evidence destination and preserve only query parameters that the destination understands.
- [ ] Provide manager-friendly context when an aggregate is broader than an existing directory filter, using an on-page evidence table instead of a misleading link.
- [ ] Preserve reporting-period and applicable department/status context through dashboard-to-profile and profile-to-directory navigation, with clear return paths.
- [ ] Test every aggregate/evidence mapping, URL encoding, stale parameters, zero-result destinations, permission boundaries, and consistency between displayed totals and linked records.

Scope boundary: M4.6 integrates existing Milestone 4 views and evidence. It adds no new KPI, visualization, calculation, write workflow, or recommendation behavior.

### M4.7 Query, accessibility, and boundary hardening

- [ ] Profile dashboard, distribution, employee-timeline, and attendance-summary queries against the authenticated-shell baseline and remove avoidable N+1 work without bypassing existing services.
- [ ] Verify realistic populated, large-range, boundary-date, weekend, empty, and filtered-empty cases; keep any reporting range guard manager-friendly and consistent across views if measurement proves one necessary.
- [ ] Verify keyboard navigation, heading structure, focus behavior, status text, chart alternatives, table captions, and color-independent interpretation across Milestone 4 pages.
- [ ] Confirm filters and calculations remain deterministic across pagination and repeated warm requests, and record the final query and response-time baselines.
- [ ] Run focused regression suites for Milestones 2 and 3 to prove the dashboard work did not change CRUD, validation, permissions, CSRF, deletion, leave, attendance, matching, or recommendation contracts.

Scope boundary: M4.7 hardens and measures implemented Milestone 4 behavior. It introduces no product feature unless a measured defect requires a narrowly scoped correction.

### M4.8 Milestone 4 verification

- [ ] Verify every Milestone 4 route, template, navigation state, filter contract, drill-down, authentication rule, role boundary, and model permission.
- [ ] Verify KPI, distribution, employee-timeline, and attendance-summary values against existing models and service outputs for populated, boundary, and empty scenarios.
- [ ] Verify every visualization has an equivalent readable table or text representation and every aggregate reaches accurate filtered evidence.
- [ ] Confirm attendance remains descriptive and absent from staffing recommendation inputs, and confirm no frontend calculation duplicates a `core` service rule.
- [ ] Run the complete project test suite, `python manage.py check`, migration-drift, whitespace, and `git diff --check`; record final query/performance baselines and reusable lessons.
- [ ] Close Milestone 4 only when every exit criterion passes, leaving Milestone 5 unstarted pending explicit approval.

Scope boundary: M4.8 is verification and finalization only. It adds no new feature unless a real defect is found, and any correction must remain narrowly within Milestone 4.

## Milestone 4 exit criteria

- [ ] Managers can apply one consistent reporting period plus department, employee-status, and project-status filters across the workforce dashboard.
- [ ] Dashboard KPIs show headcount, available capacity, allocated capacity, approved dated leave, active projects, and over-capacity risk with clear service-backed meanings.
- [ ] Capacity and utilization distributions have accessible evidence equivalents and remain consistent with the filtered KPI values.
- [ ] Employee profiles provide service-backed workload and effective-availability timelines with assignment, weekday, status, and approved-leave context.
- [ ] Attendance summaries and trends use existing attendance services, remain descriptive, and do not affect matching or recommendations.
- [ ] Every aggregate links to accurate filtered records or on-page evidence that explains it, without passing unsupported or misleading filters.
- [ ] Read views enforce the approved permissions, handle boundary and empty states, avoid avoidable N+1 queries, and have recorded warm performance baselines.
- [ ] The complete test suite and Django checks pass, Milestone 4 contains no duplicated core calculation, and Milestone 5 remains unstarted until explicit approval.

## Completed Milestone 3 task breakdown

### M3.1 Project directory

- [x] Add the namespaced project-list route and connect the Projects navigation entry without adding write or detail behavior.
- [x] Build an optimized project-directory selector with name search; status, priority, criticality, and relevant date filters; allow-listed sorting; deterministic ordering; and pagination.
- [x] Render the desktop-first project table with stored planning fields, status/priority presentation, result context, preserved filter parameters, and distinct filtered/unpopulated empty states.
- [x] Require `core.view_project` and verify anonymous, forbidden, viewer, manager/planner, and HR Administrator access.
- [x] Add route, rendering, filter, sorting, pagination, query-count, and warm response-time tests.

Scope boundary: M3.1 is read-only. It will not add project detail, create, update, requirements, assignments, or deletion; those remain in later tasks.

Completion evidence:

- Created files: `frontend/forms/projects.py`, `frontend/selectors/projects.py`, `frontend/views/projects.py`, `frontend/templates/frontend/projects/list.html`, `frontend/templates/frontend/projects/_project_row.html`, and `frontend/tests/test_project_directory.py`.
- Modified files: `frontend/urls.py`, `frontend/templates/frontend/components/navigation.html`, `frontend/static/frontend/css/theme.css`, and this task file.
- Routing and navigation result: `frontend:project_list` resolves to `/projects/`. The existing Projects primary-navigation item is now an active, keyboard-accessible link on the directory page; Workforce, Planning, and Recommendations behavior is otherwise unchanged.
- Selector result: the directory selects only the eight stored display fields and performs no related-record query. It searches all terms in project names; filters only valid project status, priority, and criticality values; supports start-on/after and end-on/before date boundaries; and accepts only seven declared sort options, each with deterministic primary-key tie-breaking.
- Interface result: the desktop-first directory uses the established page header, filter card, table, status badge, pagination, empty-state, and responsive theme patterns. It shows project name, schedule, estimated hours, priority, criticality, and status. Filtered and unpopulated states are distinct, and no create, update, delete, detail, requirement, assignment, leave, or attendance action is present.
- Permission result: the route requires `core.view_project`. Anonymous users redirect to login, authenticated users without that permission receive 403, and Viewer, Manager / Planner, and HR Administrator roles render the directory successfully.
- Query result: a populated authorized request with 24 projects uses 6 queries: the 4-query authenticated role-based shell plus one paginator count and one limited project-page query. Rendering causes no per-project query.
- Response-time baseline: 25 warm Django test-client GETs using in-memory SQLite with 24 projects recorded median 12.331 ms, p95 13.713 ms, minimum 11.907 ms, and maximum 43.401 ms. The measurement includes Django request handling and template rendering but excludes browser/network latency and static-file transfer.
- Commands run:
  - `python manage.py test frontend.tests.test_project_directory --verbosity 2`
  - `python manage.py test frontend.tests --verbosity 2`
  - `python manage.py test --verbosity 2`
  - `python manage.py check`
  - `git diff --check`
- Result: all 10 focused project-directory tests passed in 0.663 s; all 125 frontend tests passed in 8.305 s; the complete 139-test project suite passed in 9.235 s; Django reported no system-check issues; and `git diff --check` passed with only the known LF-to-CRLF working-copy warnings for `core/services/optimization.py`, `hr_workforce/settings.py`, and `hr_workforce/urls.py`.
- Architecture result: M3.1 stayed inside the server-rendered Django monolith and reused the existing Project model and shared presentation components. It added no model, migration, `core` business-logic change, calculation, JavaScript business rule, write flow, project detail, project requirement, assignment, leave, attendance, or deletion behavior. At the M3.1 handoff, M3.2 had not started.
- Follow-up lesson: none. Existing fixed-query directory, allow-listed sorting, service-ownership, and authenticated-shell baseline rules cover this work.

### M3.2 Project detail and planning context

- [x] Add the namespaced project-detail route and link project entries from the directory.
- [x] Build fixed-query selectors/presenters for the project's stored profile, skill requirements, assignments, and assignment coverage context.
- [x] Show the project estimate alongside total mandatory requirement effort and clearly flag incomplete or mismatched planning inputs using existing preflight/service results.
- [x] Present requirements, assigned employees, allocation/date/status context, and useful section-specific empty states without recalculating domain values in templates or JavaScript.
- [x] Require `core.view_project` plus the applicable related-model view permissions and add missing-target, rendering, service-delegation, query-count, and timing tests.

Scope boundary: M3.2 remains read-only and will not add any maintenance form or mutation.

Completion evidence:

- Created files: `frontend/presenters/projects.py`, `frontend/templates/frontend/projects/detail.html`, `frontend/templates/frontend/projects/_requirement_row.html`, `frontend/templates/frontend/projects/_assignment_row.html`, and `frontend/tests/test_project_detail.py`.
- Modified files: `frontend/permissions.py`, `frontend/selectors/projects.py`, `frontend/views/projects.py`, `frontend/urls.py`, `frontend/templates/frontend/projects/_project_row.html`, `frontend/templates/frontend/components/navigation.html`, `frontend/static/frontend/css/theme.css`, and this task file.
- Routing and navigation result: `frontend:project_detail` resolves to `/projects/<project_id>/`; each directory project name links to its detail page, breadcrumbs return to the directory, and Projects remains the active primary-navigation area.
- Selector and presenter result: one project, its ordered skill requirements, assignments with employee context, and each assignment's requirement coverage are loaded in four fixed queries. The presenter shapes stored data for display and delegates recommendation readiness blockers to `core.services.recommendation_preflight.get_recommendation_preflight`.
- Planning-context result: the page compares the stored project estimate with total mandatory requirement effort, distinguishes aligned estimates, mismatches, incomplete mandatory effort, and projects without mandatory requirements, and displays the existing preflight message when mandatory effort is missing or non-positive.
- Interface result: the read-only detail page shows project status, schedule, priority, criticality, estimates, requirements, assigned employees, roles, assignment dates, allocations, statuses, and covered requirements. Requirement and assignment sections each have a specific empty state, and no create, update, delete, or maintenance action is present.
- Permission result: the route requires view permissions for `Project`, `ProjectSkillRequirement`, `Assignment`, and `AssignmentSkill`. Anonymous users redirect to login, users with no permission or only `core.view_project` receive 403, approved role-based viewers render the page, and missing projects return 404.
- Query result: a populated viewer request with three requirements, two assignments, and two coverage links uses 9 queries: the 4-query authenticated shell, the 4-query fixed project-profile selector, and one existing recommendation-preflight query. Related rendering causes no N+1 queries.
- Response-time baseline: 25 warm Django test-client GETs using in-memory SQLite with three requirements, two assignments, and two coverage links recorded median 10.635 ms, p95 12.215 ms, minimum 9.535 ms, and maximum 12.645 ms in the complete-suite run. The measurement includes Django request handling and template rendering but excludes browser/network latency and static-file transfer.
- Commands run:
  - `python manage.py test frontend.tests.test_project_detail frontend.tests.test_project_directory --verbosity 2`
  - `python manage.py test frontend.tests --verbosity 2`
  - `python manage.py test --verbosity 2`
  - `python manage.py check`
  - `git diff --check`
- Result: all 19 focused project tests passed in 1.324 s; all 134 frontend tests passed in 11.378 s; the complete 148-test project suite passed in 12.129 s; Django reported no system-check issues; and `git diff --check` passed with only the known LF-to-CRLF working-copy warnings for `core/services/optimization.py`, `hr_workforce/settings.py`, and `hr_workforce/urls.py`.
- Architecture result: M3.2 stays inside the server-rendered Django monolith, changes no model or migration, preserves validated backend behavior, and introduces no write workflow, JavaScript business rule, matching/optimization change, or M3.3 work.
- Follow-up lesson: none. Existing service-ownership, fixed-query detail-page, role-permission, and authenticated-shell baseline lessons already cover this implementation.

### M3.3 Project create and update flows

- [x] Add a `Project` `ModelForm` that preserves existing field-level and model validation for dates, estimates, statuses, priority, and criticality.
- [x] Add namespaced create/update routes, templates, breadcrumbs, natural directory/detail actions, cancel paths, and success/error feedback.
- [x] Enforce `core.add_project` and `core.change_project` independently while keeping viewer access read-only.
- [x] Use CSRF-protected POST forms and transaction-safe saves; surface field-specific validation and keep stored data unchanged after invalid or failed writes.
- [x] Test valid/invalid create and update, missing targets, anonymous/forbidden access, independent permissions, rendered CSRF tokens, tokenless rejection, and rollback behavior.

Scope boundary: M3.3 edits only the Project record. Requirement, assignment, and deletion workflows remain deferred.

Completion evidence:

- Created files: `frontend/templates/frontend/projects/create.html`, `frontend/templates/frontend/projects/edit.html`, `frontend/templates/frontend/projects/_project_form.html`, and `frontend/tests/test_project_forms.py`.
- Modified files: `frontend/forms/projects.py`, `frontend/views/projects.py`, `frontend/urls.py`, `frontend/templates/frontend/projects/list.html`, `frontend/templates/frontend/projects/detail.html`, `frontend/templates/frontend/components/navigation.html`, `frontend/static/frontend/css/theme.css`, and this task file.
- Form result: `ProjectForm` exposes only name, description, start date, end date, estimated hours, status, priority, and criticality. It uses accessible date, number, text, textarea, and select controls and continues through Django's `ModelForm` and existing `Project` validation pipeline without duplicating model rules.
- Routing and interface result: `frontend:project_create` resolves to `/projects/new/` and `frontend:project_update` resolves to `/projects/<project_id>/edit/`. Authorized users receive natural Add project and Edit project actions from the directory and detail pages, with breadcrumbs, detail/directory cancel paths, field-specific errors, loading labels, and success/error messages in the existing project design.
- Permission result: create requires `core.add_project` and update requires `core.change_project` independently. Anonymous users redirect to login, viewers receive 403 for GET and POST attempts, and write actions stay hidden from read-only users.
- Save-safety result: valid creates and updates run inside `transaction.atomic()` and redirect to project detail with success feedback. Invalid submissions and simulated database failures render actionable feedback while leaving stored Project data unchanged; missing update targets return 404.
- CSRF result: the isolated project form includes its own `{% csrf_token %}`, with the token explicitly forwarded by both parent templates. Enforced-CSRF tests prove create and update reject tokenless POSTs with 403 and accept tokens extracted from the rendered browser forms.
- Validation result: tests cover required text, reversed dates, negative estimates, and invalid status, priority, and criticality values. Errors remain attached to their corresponding fields and no invalid submission is saved.
- Commands run:
  - `python manage.py test frontend.tests.test_project_forms frontend.tests.test_project_detail frontend.tests.test_project_directory --verbosity 2`
  - `python manage.py test frontend.tests --verbosity 2`
  - `python manage.py test --verbosity 2`
  - `python manage.py check`
  - `git diff --check`
- Result: all 32 focused project tests passed in 1.270 s, including all 13 M3.3 tests; all 147 frontend tests passed in 8.604 s; the complete 161-test project suite passed in 9.770 s; Django reported no system-check issues; the edited-file trailing-whitespace scan was clean; and `git diff --check` passed with only the known LF-to-CRLF working-copy warnings for `core/services/optimization.py`, `hr_workforce/settings.py`, and `hr_workforce/urls.py`.
- Architecture result: M3.3 changes only server-rendered Project maintenance. It adds no model, migration, ProjectSkillRequirement or Assignment mutation, delete flow, JavaScript business rule, or core business-logic change. M3.4 remains unstarted.
- Follow-up lesson: none. Existing lessons already require ModelForms to retain model validation, atomic writes with clear feedback, independent model permissions, and a CSRF token inside every isolated POST-form include.

### M3.4 Project skill requirement management

- [x] Add a project-centered workflow to create and update skill requirements and to remove a requirement through explicit confirmation.
- [x] Expose skill, required level, priority, mandatory status, required quantity, and estimated effort while preserving `ProjectSkillRequirement` validation and uniqueness semantics.
- [x] Reuse recommendation preflight feedback so mandatory requirements with missing or non-positive effort are explained before recommendation work, without duplicating the rule in frontend code.
- [x] Enforce `core.add_projectskillrequirement`, `core.change_projectskillrequirement`, and `core.delete_projectskillrequirement` independently; keep every mutation POST/CSRF protected and transaction safe.
- [x] Test valid changes, duplicate requirements, invalid levels/quantities/effort, confirmed removal, stale or mismatched project relationships, forbidden actions, rendered/tokenless CSRF behavior, feedback, and rollback.

Scope boundary: M3.4 manages requirement definitions only. It will not create assignments or assignment-skill coverage.

Completion evidence:

- Created files: `frontend/forms/requirements.py`, `frontend/selectors/requirements.py`, `frontend/views/requirements.py`, `frontend/templates/frontend/projects/requirements/create.html`, `frontend/templates/frontend/projects/requirements/edit.html`, `frontend/templates/frontend/projects/requirements/_form.html`, `frontend/templates/frontend/projects/requirements/confirm_remove.html`, and `frontend/tests/test_project_requirements.py`.
- Modified files: `frontend/urls.py`, `frontend/views/projects.py`, `frontend/templates/frontend/projects/detail.html`, `frontend/templates/frontend/projects/_requirement_row.html`, `frontend/templates/frontend/components/navigation.html`, `frontend/templates/frontend/components/table.html`, this task file, and `frontend/LESSONS_LEARNED.md`.
- Workflow result: namespaced, project-scoped add, edit, and remove routes are connected naturally from the project detail page. Forms expose skill, required proficiency, people needed, effort, priority, and mandatory status, while confirmation explains the project, skill, current requirement, linked-assignment count, and removal consequences in planning language.
- Validation result: the `ProjectSkillRequirement` `ModelForm` retains existing model validators and the project/skill uniqueness constraint. Duplicate skills receive a clear form-level message; invalid levels, zero quantity, and negative effort receive field-specific feedback; stale requirements, missing projects, and requirements routed through the wrong project return 404 without mutation.
- Preflight result: blank or zero mandatory effort remains saveable exactly as the existing model permits. The workflow delegates recommendation eligibility to `get_recommendation_preflight`, displays its blocker messages on relevant forms and after redirect to project detail, and introduces no duplicate frontend recommendation rule.
- Permission result: add, change, and delete permissions are enforced independently. Viewers receive 403 and see no maintenance actions; Managers / Planners can add and edit but not remove under the approved role map; HR Administrators can perform all three actions.
- Save and removal safety result: create, update, and confirmed removal run inside `transaction.atomic()`. Removal uses POST only after an explicit confirmation and removes any linked assignment coverage through the existing relationship behavior while preserving the Project, Skill, and Assignment. Simulated database failures restore both requirements and coverage and show safe feedback.
- CSRF result: both maintenance form parents explicitly pass `csrf_token` into the isolated POST-form include, and the confirmation parent does the same for the shared confirmation component. Enforced-CSRF tests prove all three mutations reject tokenless POSTs and accept tokens extracted from their rendered forms.
- Defect found and corrected: the first focused run showed the permission-aware row actions were missing because `perms` was dropped across two `{% include ... only %}` boundaries. The shared table now accepts and forwards `perms`, the project detail page supplies it, and role-specific rendering tests protect the final output. The reusable rule is recorded in `LESSONS_LEARNED.md`.
- Commands run:
  - `python manage.py test frontend.tests.test_project_requirements frontend.tests.test_project_detail frontend.tests.test_project_forms frontend.tests.test_project_directory --verbosity 2`
  - `python manage.py test frontend.tests --verbosity 2`
  - `python manage.py test --verbosity 2`
  - `python manage.py check`
  - `git diff --check`
- Result: after correcting the isolated-include context defect, all 48 focused project tests passed in 1.776 s, including all 16 new M3.4 tests; all 163 frontend tests passed in 9.404 s; the complete 177-test project suite passed in 10.325 s; Django reported no system-check issues; the edited-file trailing-whitespace scan was clean; and `git diff --check` passed with only the known LF-to-CRLF working-copy warnings for `core/services/optimization.py`, `hr_workforce/settings.py`, and `hr_workforce/urls.py`.
- Architecture result: M3.4 changes only ProjectSkillRequirement maintenance and the existing assignment-coverage links affected by confirmed requirement removal. It adds no model, migration, assignment create/update workflow, matching/optimization change, or core business-logic change. M3.5 remains unstarted.

### M3.5 Assignment create and update flows

- [x] Add project-centered assignment create/update routes and the assignment maintenance context needed for later skill-coverage work.
- [x] Build an `Assignment` `ModelForm` for employee, project dates, allocation, project role, and status; provide eligibility hints from existing services/selectors without replacing server-side validation.
- [x] Preserve and clearly surface existing validation for valid assignment date ranges, employee qualification, same-project date overlap, total allocation above 100%, and approved-leave conflicts.
- [x] Enforce `core.add_assignment` and `core.change_assignment` independently; use CSRF-protected POST forms, transaction-safe saves, and clear success/error feedback.
- [x] Test valid/invalid create and update, stale/mismatched project context, anonymous/forbidden access, independent permissions, CSRF behavior, field-specific errors, and rollback.

Scope boundary: M3.5 manages the Assignment record only. Assignment-skill links and deletion are deferred to M3.6 and M3.7.

Completion evidence:

- Created files: `frontend/forms/assignments.py`, `frontend/presenters/assignments.py`, `frontend/selectors/assignments.py`, `frontend/views/assignments.py`, `frontend/templates/frontend/projects/assignments/create.html`, `frontend/templates/frontend/projects/assignments/edit.html`, `frontend/templates/frontend/projects/assignments/_form.html`, and `frontend/tests/test_project_assignments.py`.
- Modified files: `frontend/urls.py`, `frontend/views/projects.py`, `frontend/templates/frontend/projects/detail.html`, `frontend/templates/frontend/projects/_assignment_row.html`, `frontend/templates/frontend/components/navigation.html`, and this task file.
- Workflow result: namespaced, project-scoped add and edit routes are connected from the project detail page. The create form defaults its dates to the project schedule, and both forms expose employee, start/end dates, allocation, project role, and planning status in the existing project interface.
- Selector and guidance result: the employee selector loads only the stored employee context needed for its labels. It delegates skill-match guidance to `core.services.matching.employee_can_cover_requirement` and explicitly describes those labels as advisory; final eligibility remains owned by Assignment model validation.
- Validation result: the `Assignment` `ModelForm` preserves and surfaces the existing rules for reversed dates, employees without a qualifying project skill, overlapping assignments on the same project, combined allocation above 100%, and approved-leave conflicts. Errors remain attached to the relevant employee, project, date, allocation, role, or status field, including visible feedback for the hidden project field.
- Permission result: create requires `core.add_assignment` and edit requires `core.change_assignment` independently. Anonymous users redirect to login, viewers receive 403 for GET and POST attempts, and project-detail actions render only when the corresponding permission is present.
- Save-safety result: valid creates and updates run inside `transaction.atomic()` and redirect to project detail with success feedback. Invalid submissions and simulated database failures render clear feedback while leaving assignment data unchanged; missing projects, stale assignments, and assignments routed through the wrong project return 404 without mutation.
- CSRF result: both parent templates explicitly pass `csrf_token` into the isolated assignment form include. Enforced-CSRF tests prove create and update reject tokenless POSTs with 403 and accept tokens extracted from the rendered forms.
- Defects found and corrected during verification: the initial focused run exposed two form-rendering issues. The custom employee choice field did not inherit `Meta.help_texts`, so its advisory guidance was absent, and create-form dates were assigned after Django built its initial-value dictionary, so the project schedule defaults were blank. The field now declares its help text directly and the form writes date defaults into `self.initial`; no backend validation or business rule changed.
- Commands run:
  - `python manage.py test frontend.tests.test_project_assignments --verbosity 2`
  - `python manage.py test frontend.tests.test_project_assignments frontend.tests.test_project_detail frontend.tests.test_project_requirements frontend.tests.test_project_forms frontend.tests.test_project_directory --verbosity 2`
  - `python manage.py test frontend.tests --verbosity 2`
  - `python manage.py test --verbosity 2`
  - `python manage.py check`
  - `git diff --check`
- Result: after correcting the two rendering issues, all 17 focused M3.5 tests passed in 0.533 s; all 65 focused Milestone 3 project tests passed in 2.249 s; all 180 frontend tests passed in 9.741 s; the complete 194-test project suite passed in 11.131 s; Django reported no system-check issues; the edited-file trailing-whitespace scan was clean; and `git diff --check` passed with only the known LF-to-CRLF working-copy warnings for `core/services/optimization.py`, `hr_workforce/settings.py`, and `hr_workforce/urls.py`.
- Architecture result: M3.5 changes only server-rendered Assignment create/update maintenance and project-detail actions. It adds no model, migration, assignment-skill mutation, assignment deletion, JavaScript business rule, or core business-logic change. M3.6 remains unstarted.
- Follow-up lesson: none. Existing lessons already cover retaining model validation, delegating matching decisions to core services, independent permissions, atomic writes, and explicit CSRF forwarding through isolated form includes.

### M3.6 Assignment-skill coverage management

- [x] Add an assignment-centered workflow to show which project requirements an assignment covers and to add or remove coverage links.
- [x] Restrict choices to requirements from the assignment's project and preserve `AssignmentSkill` validation for employee skill ownership, proficiency level, project consistency, and required quantity.
- [x] Prevent duplicate coverage and explain unavailable or already-covered requirements in natural planning language.
- [x] Block requirement quantity reductions below current planned/active coverage, identify the covering employees, and require explicit coverage removal before the lower quantity can be saved.
- [x] Enforce `core.add_assignmentskill` and `core.delete_assignmentskill` independently; keep removal explicitly confirmed, POST-only, CSRF protected, and transaction safe.
- [x] Test valid coverage, wrong-project requirements, missing/insufficient employee skills, quantity limits, duplicates, confirmed removal, mismatched/stale context, forbidden actions, CSRF behavior, feedback, and rollback.

Scope boundary: M3.6 changes only AssignmentSkill relationships and does not alter matching or recommendation logic.

Completion evidence:

- Created files: `frontend/forms/coverage.py`, `frontend/presenters/coverage.py`, `frontend/views/coverage.py`, `frontend/templates/frontend/projects/assignments/coverage/detail.html`, `frontend/templates/frontend/projects/assignments/coverage/_coverage_row.html`, `frontend/templates/frontend/projects/assignments/coverage/create.html`, `frontend/templates/frontend/projects/assignments/coverage/_form.html`, `frontend/templates/frontend/projects/assignments/coverage/confirm_remove.html`, and `frontend/tests/test_project_assignment_coverage.py`.
- Modified files: `frontend/selectors/assignments.py`, `frontend/urls.py`, `frontend/templates/frontend/projects/_assignment_row.html`, this task file, and `frontend/LESSONS_LEARNED.md`.
- Workflow result: every project assignment now links to an assignment-centered requirement-coverage page. It shows each project requirement as covered, currently available, or unavailable with natural-language evidence from the existing `AssignmentSkill.clean()` rules. Authorized users can open a separately scoped add form, and authorized removers receive an explicit confirmation that identifies the employee, assignment, project, and requirement and explains which parent records remain.
- Validation result: the add form keeps the server-owned assignment field, restricts selectable requirements to the routed assignment's project, omits existing links from the initial picker, preserves the `AssignmentSkill` uniqueness constraint, and delegates employee skill ownership, proficiency level, same-project consistency, and active/planned required-quantity enforcement to the existing model validation. Wrong-project, missing-skill, insufficient-level, full-quantity, and duplicate submissions all return field or form feedback without mutation.
- Permission result: the read-only coverage page requires view access to the project and related planning models. Adding requires only `core.add_assignmentskill`; removing requires only `core.delete_assignmentskill`. Viewers can inspect evidence but cannot mutate it, Managers / Planners can add but not remove under the approved role map, and HR Administrators can do both.
- Save and removal safety result: add and confirmed removal execute inside `transaction.atomic()`. Removal occurs only on the confirmed POST path, preserves the Assignment, ProjectSkillRequirement, EmployeeSkill, Project, and Employee records, rejects unsupported methods, and leaves data unchanged with safe feedback after simulated database failures.
- CSRF result: the add-form parent and confirmation parent explicitly pass `csrf_token` into their isolated POST-form includes. Enforced-CSRF tests prove both mutations reject tokenless POSTs and accept tokens extracted from the rendered forms.
- Performance result: the populated coverage page baseline uses 13 total queries for five requirements and one existing link, including the four-query authenticated shell and the existing model-rule checks. Across 25 warm Django test-client GETs in the complete-suite run, median response time was 8.964 ms and p95 was 9.391 ms.
- Commands run:
  - `python manage.py test frontend.tests.test_project_assignment_coverage --verbosity 1`
  - `python manage.py test frontend.tests.test_project_assignment_coverage frontend.tests.test_project_assignments frontend.tests.test_project_requirements frontend.tests.test_project_detail frontend.tests.test_project_forms frontend.tests.test_project_directory --verbosity 1`
  - `python manage.py test frontend.tests --verbosity 1`
  - `python manage.py test --verbosity 1`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py check`
  - `git diff --check`
- Result: all 21 focused M3.6 tests passed in 0.658 s; all 86 focused Milestone 3 project tests passed in 2.896 s; all 201 frontend tests passed in 10.289 s; and the complete 215-test project suite passed in 11.268 s. No migrations were detected, Django reported no system-check issues, and `git diff --check` passed with only the known LF-to-CRLF working-copy warnings for `core/services/optimization.py`, `hr_workforce/settings.py`, and `hr_workforce/urls.py`.
- Architecture result: M3.6 adds only server-rendered AssignmentSkill relationship inspection, addition, and removal. It adds no model, migration, assignment/project deletion, matching, optimization, recommendation, JavaScript business rule, or core business-logic change. M3.7 remains unstarted.
- Reusable lesson: a scoped `ModelChoiceField` can reject a forged relationship before Django builds the model instance while still allowing `Model.clean()` to run. The coverage form retains the valid field error and avoids calling relationship-dependent model validation on that incomplete request-local instance; the general rule is recorded in `LESSONS_LEARNED.md`.

Coverage-consistency correction evidence:

- Modified files: `core/models.py`, `frontend/tests/test_project_requirements.py`, and this task file.
- Validation result: `ProjectSkillRequirement.clean()` now compares an edited `required_quantity` with the requirement's existing planned/active coverage, matching the statuses counted by the existing `AssignmentSkill` quantity rule. A quantity equal to current coverage remains valid. A lower quantity adds a field-level error to **People needed**, explains how many employees must be removed first, and lists the employees currently covering the requirement. It never deletes or selects a coverage link automatically.
- Workflow result: after an authorized user explicitly removes enough coverage through the existing confirmed M3.6 removal workflow, the requirement edit can save the lower quantity normally. Rejected edits leave both the stored requirement quantity and every coverage link unchanged.
- Regression coverage: four HTTP-layer tests prove equality is allowed, a lower value is rejected, confirmed manual coverage removal enables the later reduction, and the rejected form shows natural guidance plus employee names while preserving the database value.
- Commands run:
  - `python manage.py test frontend.tests.test_project_requirements frontend.tests.test_project_assignment_coverage --verbosity 2`
  - `python manage.py test frontend.tests.test_project_assignment_coverage frontend.tests.test_project_assignments frontend.tests.test_project_requirements frontend.tests.test_project_detail frontend.tests.test_project_forms frontend.tests.test_project_directory --verbosity 1`
  - `python manage.py test frontend.tests --verbosity 1`
  - `python manage.py test --verbosity 1`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py check`
  - edited-file trailing-whitespace scan
  - `git diff --check`
- Result: all 41 focused requirement/coverage tests passed in 1.319 s; all 90 focused Milestone 3 project tests passed in 2.972 s; all 205 frontend tests passed in 10.484 s; and the complete 219-test project suite passed in 11.560 s. No migration, recommendation, OR-Tools, permission, CSRF, layout, styling, or M3.7 change was introduced.

### M3.7 Safe project and assignment deletion

- [x] Add safe, POST-only deletion workflows for Project and Assignment records with explicit confirmation and the corresponding delete permissions.
- [x] Present affected requirements, assignments, coverage, and other consequences with named business context and understandable counts before confirmation.
- [x] Preserve existing Django relationships and deletion behavior; make retained top-level information clear without exposing framework terminology.
- [x] Handle missing/stale targets and database failures with clear feedback while keeping deletes CSRF protected and transactional.
- [x] Test permitted/forbidden deletion, business-impact rendering, GET non-deletion, unsupported methods, CSRF enforcement, stale targets, rollback, actual related-data outcomes, and retained records.

Scope boundary: M3.7 adds no archive feature and changes no model relationship or cascade rule.

Completion evidence:

- Created files: `frontend/templates/frontend/projects/confirm_delete.html`, `frontend/templates/frontend/projects/assignments/confirm_delete.html`, and `frontend/tests/test_project_assignment_deletion.py`.
- Modified files: `frontend/selectors/deletions.py`, `frontend/presenters/deletions.py`, `frontend/views/deletions.py`, `frontend/urls.py`, `frontend/views/projects.py`, `frontend/templates/frontend/components/cascade_impact.html`, `frontend/templates/frontend/projects/detail.html`, `frontend/templates/frontend/projects/_assignment_row.html`, and this task file.
- Workflow result: permitted users can open explicit project and project-scoped assignment deletion confirmations from the project detail page. GET renders impact only, unsupported methods return 405, and deletion occurs only after the confirmation form's POST.
- Business-impact result: project confirmation names the affected skill requirements and assigned employees, shows understandable requirement, assignment, and coverage counts, and states that employee profiles, skill definitions, leave, and attendance remain. Assignment confirmation names the employee, project role, schedule, and covered requirements and states that the employee, project, requirements, and skills remain. Empty targets clearly explain when only the project or assignment itself will be removed, and no framework terminology is exposed.
- Relationship result: confirmed project deletion preserves the existing Django relationship behavior by removing the project, its requirements, assignments, and all coverage linked through either branch while retaining unrelated projects and every employee, skill, proficiency, leave, and attendance record. Confirmed assignment deletion removes only that assignment and its coverage while retaining its project, employee, requirements, skills, other assignments, and other coverage.
- Permission result: project deletion requires `core.delete_project` and assignment deletion requires `core.delete_assignment` independently. Anonymous users redirect to login; Viewers and Managers / Planners receive 403 under the approved role map; HR Administrators can perform both; and the project detail page renders only the deletion actions allowed to the signed-in user.
- Failure-safety result: both deletes run inside `transaction.atomic()`. Missing project and assignment GETs return 404; stale or mismatched confirmed POSTs return to a safe surviving page with an informational message; and simulated database failures roll back the target plus all dependent planning information before rendering clear feedback.
- CSRF result: both confirmation templates explicitly pass `csrf_token` into the isolated shared confirmation component. Enforced-CSRF tests prove tokenless project and assignment POSTs return 403 and tokens extracted from the rendered confirmation forms allow the intended deletes.
- Query result: the project deletion selector loads the project, named requirements, named assignments, and exact coverage count in four fixed queries; the assignment deletion selector loads the assignment context and named coverage in two fixed queries. Existing project-detail query and timing baselines remain unchanged.
- Commands run:
  - `python manage.py test frontend.tests.test_project_detail frontend.tests.test_safe_deletion --verbosity 1`
  - `python manage.py test frontend.tests.test_project_assignment_deletion --verbosity 2`
  - `python manage.py test frontend.tests.test_project_assignment_deletion frontend.tests.test_safe_deletion frontend.tests.test_project_detail frontend.tests.test_project_assignments frontend.tests.test_project_requirements frontend.tests.test_project_assignment_coverage frontend.tests.test_project_forms frontend.tests.test_project_directory --verbosity 1`
  - `python manage.py test frontend.tests --verbosity 1`
  - `python manage.py test --verbosity 1`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py check`
  - edited-file trailing-whitespace scan
  - `git diff --check`
- Result: the 24 pre-existing project-detail and deletion regressions passed in 0.808 s; all 18 focused M3.7 tests passed in 0.359 s; all 123 related project/deletion regression tests passed in 3.679 s; all 223 frontend tests passed in 10.976 s; and the complete 237-test project suite passed in 11.833 s. No model, migration, relationship, archive, recommendation, optimization, assignment-coverage validation, leave, attendance, or M3.8 change was introduced.
- Lessons result: no new reusable lesson was discovered; the existing deletion-graph, business-language, permission, transaction, and isolated-include CSRF lessons covered the work, so `LESSONS_LEARNED.md` was not changed.

### M3.8 Leave management

- [x] Add a permission-protected leave directory with employee, type, status, and date filters; allow-listed sorting; deterministic pagination; and useful empty states.
- [x] Add leave create/update forms and safe confirmed deletion using the existing `Leave` model and its date/status validation.
- [x] Keep employment status distinct from dated leave and reuse existing leave/availability services wherever calculated context is shown.
- [x] Enforce `core.view_leave`, `core.add_leave`, `core.change_leave`, and `core.delete_leave`; provide field-specific validation and success/error feedback; and protect every mutation with CSRF and appropriate transactions.
- [x] Test directory behavior, valid/invalid maintenance, approved/upcoming context, permission boundaries, CSRF, missing/stale records, deletion, rollback, query count, and warm response time.

Scope boundary: M3.8 manages dated leave entries only and will not infer or rewrite employee status.

Completion evidence:

- Created files: `frontend/forms/leaves.py`, `frontend/selectors/leaves.py`, `frontend/views/leaves.py`, `frontend/templates/frontend/leaves/list.html`, `frontend/templates/frontend/leaves/_leave_row.html`, `frontend/templates/frontend/leaves/_leave_form.html`, `frontend/templates/frontend/leaves/create.html`, `frontend/templates/frontend/leaves/edit.html`, `frontend/templates/frontend/leaves/confirm_delete.html`, and `frontend/tests/test_leave_management.py`.
- Modified files: `frontend/urls.py`, `frontend/templates/frontend/components/navigation.html`, `frontend/templates/frontend/components/workforce_tabs.html`, and this task file.
- Directory result: the namespaced `/leave/` directory is available from a Leave tab in Workforce and displays employee, leave type, date period, stored approval status, and permission-aware actions. Employee, type, status, and inclusive overlap-period filters combine correctly; invalid filter periods receive field feedback; six allow-listed sort modes have stable `leave_id` tie-breakers; pagination is fixed at 20 records; query parameters survive paging; and filtered-empty and unpopulated states are distinct.
- Maintenance result: HR Administrators can add, edit, and explicitly confirm deletion of dated leave through `LeaveForm`, which uses the existing `Leave` model validation pipeline and its stored type/status choices. Valid operations show clear success messages, invalid dates or choices render field-specific errors without changing stored data, GET never deletes, and a confirmed delete removes only the selected leave record.
- Availability result: the directory and forms state that employment status is separate from dated leave and that only approved leave informs dated availability. Create, update, and delete tests prove employee status remains unchanged, while an approved future leave is returned by the existing `get_approved_leaves` service and appears in the existing employee-profile upcoming-leave context.
- Permission result: the directory requires `core.view_leave`; add, edit, and delete endpoints independently require `core.add_leave`, `core.change_leave`, and `core.delete_leave`. Anonymous users redirect to login, users without the required permission receive 403, Viewers remain read-only, HR Administrators receive operational maintenance actions, and direct single-permission tests prove the write boundaries remain independent.
- Failure-safety result: create, update, and delete mutations run inside `transaction.atomic()`. Missing update/delete GETs return 404, stale confirmed delete POSTs return safely to the directory with an informational message, and simulated database failures roll back inserts, updates, and deletes before clear non-technical feedback is rendered.
- CSRF result: create/edit templates explicitly pass `csrf_token` into the isolated leave form, and delete confirmation explicitly passes it through the shared confirmation component. Enforced-CSRF tests prove all three tokenless mutations return 403 and tokens extracted from every rendered form allow the intended operations.
- Query and timing result: the populated leave directory uses seven fixed queries: the four-query authenticated shell plus one employee-choice query, one paginator count, and one joined page-row query. Seven warm Django test-client requests over 25 leave records recorded a 13.792 ms median and 37.327 ms p95 in the final complete-suite run, with no per-row query growth.
- Commands run:
  - `python manage.py test frontend.tests.test_leave_management --verbosity 2`
  - `python manage.py test frontend.tests.test_leave_management --verbosity 1`
  - `python manage.py test frontend.tests --verbosity 1`
  - `python manage.py test --verbosity 1`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py check`
  - edited-file trailing-whitespace scan
  - `git diff --check`
- Result: all 22 focused M3.8 tests passed in 0.683 s; all 245 frontend tests passed in 11.554 s; and the final complete 259-test project suite passed in 12.744 s. The final focused leave-directory timing run recorded seven queries, a 13.544 ms median, and a 28.395 ms p95. No model, migration, recommendation, optimization, assignment, assignment-skill coverage, attendance, employee-status, or M3.9 change was introduced.
- Lessons result: no new reusable lesson was discovered. The existing lessons on model-form validation, employee-status/dated-leave separation, fixed-cost directories, transactional failure handling, permission-aware isolated includes, and CSRF forwarding covered this work, so `LESSONS_LEARNED.md` was not changed.

### M3.9 Attendance management

- [x] Add a permission-protected attendance directory with employee, status, and date filters; allow-listed sorting; deterministic pagination; and useful empty states.
- [x] Add attendance create/update forms and safe confirmed deletion while preserving existing employee/date uniqueness and arrival/departure ordering validation.
- [x] Present attendance as descriptive operational history and do not imply that it changes matching or recommendation scores.
- [x] Enforce `core.view_attendance`, `core.add_attendance`, `core.change_attendance`, and `core.delete_attendance`; provide field-specific validation and success/error feedback; and protect every mutation with CSRF and appropriate transactions.
- [x] Test directory behavior, valid/invalid maintenance, duplicate employee/date prevention, invalid arrival/departure order, permission boundaries, CSRF, missing/stale records, deletion, rollback, query count, and warm response time.

Scope boundary: M3.9 does not change attendance calculations, employee availability, matching, or recommendations.

Completion evidence:

- Created files: `frontend/forms/attendance.py`, `frontend/selectors/attendance.py`, `frontend/views/attendance.py`, `frontend/templates/frontend/attendance/list.html`, `frontend/templates/frontend/attendance/_attendance_row.html`, `frontend/templates/frontend/attendance/_attendance_form.html`, `frontend/templates/frontend/attendance/create.html`, `frontend/templates/frontend/attendance/edit.html`, `frontend/templates/frontend/attendance/confirm_delete.html`, and `frontend/tests/test_attendance_management.py`.
- Modified files: `frontend/urls.py`, `frontend/templates/frontend/components/navigation.html`, `frontend/templates/frontend/components/workforce_tabs.html`, `frontend/LESSONS_LEARNED.md`, and this task file.
- Directory result: the namespaced `/attendance/` directory is available from an Attendance tab in Workforce and shows employee, date, stored status, optional arrival/departure times, and permission-aware actions. Employee, status, inclusive from/to date filters, five allow-listed sort modes with stable `attendance_id` tie-breakers, 20-record pagination with preserved parameters, filter-period validation, and distinct filtered/unpopulated empty states are implemented.
- Maintenance result: HR Administrators can add, edit, and explicitly confirm deletion of attendance through `AttendanceForm`. The existing model validation pipeline remains authoritative for stored status choices and arrival/departure ordering, while the form presents the time-order error naturally on the departure field. Duplicate employee/date submissions are rejected on the date field with manager-friendly wording before the database constraint is reached, and confirmed deletion removes only the selected attendance history.
- Descriptive-scope result: every attendance screen states that attendance is descriptive operational history and does not affect staffing recommendations. Create, update, and delete tests prove employee status remains unchanged, and a valid new record is returned by the existing `get_attendance_records` service. No matching, recommendation, optimization, availability, attendance calculation, model, or migration code changed.
- Permission result: the directory requires `core.view_attendance`; add, edit, and delete endpoints independently require `core.add_attendance`, `core.change_attendance`, and `core.delete_attendance`. Anonymous users redirect to login, users without the required permission receive 403, Viewers remain read-only, HR Administrators receive operational maintenance actions, and direct single-permission tests prove each write boundary independently.
- Failure-safety result: create, update, and delete mutations run inside `transaction.atomic()`. Missing update/delete GETs return 404, unsupported delete methods return 405, stale confirmed delete POSTs return safely to the directory with an informational message, and simulated database failures roll back inserts, updates, and deletes before clear feedback is rendered.
- CSRF result: create/edit templates explicitly pass `csrf_token` into the isolated attendance form, and delete confirmation explicitly passes it through the shared confirmation component. Enforced-CSRF tests prove all three tokenless mutations return 403 and tokens extracted from every rendered form allow the intended operations.
- Query and timing result: the populated attendance directory uses seven fixed queries: the four-query authenticated shell plus one employee-choice query, one paginator count, and one joined page-row query. Seven warm Django test-client requests over 25 attendance records recorded a 13.586 ms median and 14.247 ms p95 in the final complete-suite run, with no per-row query growth.
- Commands run:
  - `python manage.py test frontend.tests.test_attendance_management --verbosity 2`
  - `python manage.py test frontend.tests.test_attendance_management --verbosity 1`
  - `python manage.py test frontend.tests --verbosity 1`
  - `python manage.py test --verbosity 1`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py check`
  - edited-file trailing-whitespace scan
  - `git diff --check`
- Result: all 23 focused M3.9 tests passed in 0.670 s; all 268 frontend tests passed in 11.789 s; and the final complete 282-test project suite passed in 12.930 s. The final focused attendance-directory timing run recorded seven queries, a 12.915 ms median, and a 13.426 ms p95. No model, migration, attendance-calculation, availability, matching, recommendation, optimization, employee-status, or M3.10 change was introduced.
- Lessons result: `LESSONS_LEARNED.md` now records the reusable rule that manager-friendly validation wording should be translated at the `ModelForm` boundary while the model remains the authoritative validator and the field association is preserved.

### M3.10 Milestone 3 verification

- [x] Verify every Milestone 3 route, template, navigation state, authentication rule, role boundary, and model permission.
- [x] Verify important populated, empty, filtered-empty, success, validation, forbidden, stale, confirmation, failure, and rollback states across projects, requirements, assignments, coverage, leave, and attendance.
- [x] Verify CSRF protection for every Milestone 3 POST form and run the critical desktop workflows end to end through Django's HTTP layer.
- [x] Record list/detail query counts and warm response times relative to the authenticated-shell baseline; remove any avoidable N+1 query found during verification.
- [x] Run the complete project test suite, `python manage.py check`, and `git diff --check`; update reusable lessons only when a durable discovery was made.
- [x] Close Milestone 3 only when every exit criterion passes, leaving Milestone 4 unstarted pending explicit approval.

Completion evidence:

- Created file: `frontend/tests/test_milestone3_verification.py`.
- Modified files: `frontend/templates/frontend/components/navigation.html`, `frontend/CURRENT_TASKS.md`, and `frontend/LESSONS_LEARNED.md`.
- Route/template result: a consolidated verification test resolves and opens all 22 Milestone 3 project, requirement, assignment, assignment-coverage, leave, and attendance routes as an HR Administrator; every route returns 200, uses its intended namespaced template, and marks Projects or Workforce as the active primary navigation area.
- Authentication/authorization result: the same complete route inventory proves anonymous requests redirect to login. Viewers can open the five read workflows and receive 403 from every write route. Managers / Planners can open the read workflows plus the seven approved project-planning add/change routes while receiving 403 from project/assignment/coverage deletion and all leave/attendance mutations. HR Administrators can open every route. Existing model-specific permission regressions additionally prove direct permissions are enforced independently.
- State and workflow result: 171 aggregate Milestone 3 tests cover populated, empty, filtered-empty, success, invalid, forbidden, missing, stale, confirmation, unsupported-method, database-failure, and rollback states through Django's HTTP layer. They preserve validation for project and leave dates, requirement levels/quantity/effort and coverage consistency, assignment qualification/overlap/allocation/approved leave, assignment-skill project/qualification/quantity/uniqueness, attendance employee/date uniqueness, and attendance time ordering.
- CSRF result: the consolidated route audit finds an explicit hidden CSRF input in all 17 Milestone 3 mutation forms. Existing enforced-CSRF HTTP tests prove tokenless create, update, remove, and delete POSTs return 403, while tokens extracted from the rendered forms permit the intended mutations.
- Service-boundary result: project readiness and calculated profile context continue to delegate to existing `core` services. A direct source audit found no Attendance reference in matching, recommendation, optimization, Pareto, or team-metric services. Leave remains date-based, attendance remains descriptive, and HTTP tests prove neither workflow silently changes employee status.
- Query/performance result: no avoidable N+1 query was found. Against the four-query authenticated-shell baseline, the final complete-suite run recorded project directory at 6 queries and 13.015 ms warm median, project profile at 9 queries and 8.028 ms, assignment coverage at 13 queries and 9.493 ms, leave directory at 7 queries and 15.057 ms, and attendance directory at 7 queries and 13.301 ms. Project and assignment deletion selectors remain fixed at four and two queries respectively.
- Defect found and fixed: project deletion, assignment deletion, and assignment-coverage pages were missing from the primary Projects navigation activation conditions. Only the shared navigation route-state list was expanded; the new route-inventory regression verifies the active state and `aria-current` behavior for every Milestone 3 page. No backend, model, service, permission, CSRF, or workflow behavior changed.
- Commands run:
  - `python manage.py test frontend.tests.test_milestone3_verification --verbosity 2`
  - aggregate 171-test Milestone 3 Django test command covering all project, requirement, assignment, coverage, deletion, leave, attendance, and closeout modules
  - `python manage.py test frontend.tests --verbosity 1`
  - `python manage.py test --verbosity 1`
  - source audit for Attendance references in matching, recommendation, optimization, Pareto, and team-metric services
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py check`
  - edited-file trailing-whitespace scan
  - `git diff --check`
- Result: all 3 consolidated M3.10 tests passed in 0.622 s; all 171 aggregate Milestone 3 tests passed in 5.471 s; all 271 frontend tests passed in 12.688 s; and the complete 285-test project suite passed in 13.859 s. Django system checks and migration drift checks pass, and the final diff/whitespace checks report no errors.
- Lessons result: `LESSONS_LEARNED.md` now records the reusable requirement to verify active navigation across the complete route family, including nested relationship and confirmation routes.

## Milestone 3 exit criteria

- [x] Authorized users can safely inspect and maintain projects, requirements, assignments, assignment-skill coverage, leave, and attendance without relying on Django admin.
- [x] Viewers retain read-only access, managers/planners retain the approved planning-write scope, and HR Administrators retain the approved operational maintenance scope.
- [x] Project pages make status, dates, estimates, mandatory effort, requirements, assignments, and coverage understandable without duplicating `core` calculations.
- [x] Existing validation failures for dates, qualification, overlap, allocation, leave, proficiency, quantity, uniqueness, and project consistency appear as clear field or form feedback.
- [x] Destructive actions require explicit, permitted, CSRF-protected POST confirmation and explain consequences in business-friendly language.
- [x] Leave remains date-based, attendance remains descriptive, and neither workflow silently changes employee status or recommendation semantics.
- [x] Read pages avoid N+1 queries, performance baselines are recorded, the complete test suite passes, and Django reports no system-check issues.
- [x] Milestone 4 remains unstarted until Milestone 3 receives explicit approval.

## Completed Milestone 2 task breakdown

### M2.1 Employee directory

- [x] Add the namespaced employee-list route and activate the Workforce navigation entry.
- [x] Build an optimized employee-list selector with an explicit allow-list of sort options.
- [x] Add name search, status and department filters, sorting, and pagination.
- [x] Render the desktop-first employee directory with the shared page header, form, table, status badge, pagination, and empty-state components.
- [x] Require `core.view_employee` and test anonymous, forbidden, and permitted access.
- [x] Test filtering, sorting, pagination, template rendering, query count, and warm response time.

Completion evidence:

- Created files: `frontend/forms/employees.py`, `frontend/selectors/employees.py`, `frontend/views/employees.py`, `frontend/templates/frontend/employees/list.html`, `frontend/templates/frontend/employees/_employee_row.html`, and `frontend/tests/test_employee_directory.py`.
- Modified files: `frontend/urls.py`, `frontend/templates/frontend/components/navigation.html`, `frontend/templates/frontend/components/table.html`, `frontend/static/frontend/css/theme.css`, `frontend/CURRENT_TASKS.md`, and `frontend/LESSONS_LEARNED.md`.
- Routing and access result: `frontend:employee_list` resolves to `/employees/`; the Workforce navigation item links to it and receives the active-page state. The route redirects anonymous users, returns 403 for authenticated users without `core.view_employee`, and renders for the viewer role.
- Selector result: the directory selects only displayed employee fields, searches all first/last-name terms, filters by valid employee status and exact department, applies only declared sort keys, and always adds deterministic name/primary-key ordering. Department choices use one stable distinct-values query.
- Interface result: the read-only, desktop-first page provides name search, status and department filters, seven allow-listed sort choices, 20-row pagination that preserves query parameters, a result summary, stored employee details, status badges, and distinct filtered/unpopulated empty states. No employee detail link or create/update/delete action was added.
- Query result: a populated viewer request with 24 employees uses 7 queries: the 4-query authenticated shell plus one department-facet query, one paginator count, and one employee-page query. Rendering performs no per-employee queries.
- Response-time baseline: over 25 warm Django test-client GETs with 24 employees and in-memory SQLite, median response time was 10.960 ms, p95 12.160 ms, minimum 10.422 ms, and maximum 12.205 ms. The measurement includes Django request handling and template rendering but excludes browser/network latency and static-file transfer.
- Commands run:
  - `python manage.py test frontend.tests.test_employee_directory --verbosity 2`
  - `python manage.py test frontend.tests --verbosity 2`
  - `python manage.py test --verbosity 2`
  - `python manage.py check`
  - `git diff --check`
- Result: all 10 focused employee-directory tests passed in 0.505 s; all 39 frontend tests passed in 5.704 s; the complete 53-test project suite passed in 6.631 s; Django reported no system-check issues; `git diff --check` passed with only the previously recorded line-ending normalization warnings on pre-M2.1 files.
- Architecture result: M2.1 uses the existing `Employee` model and shared frontend components. It adds no model, migration, detail/write route, workload or availability calculation, JavaScript business logic, or `core` business-logic change.
- Follow-up lesson: keep list pages at a fixed number of bulk queries and reserve rich service-backed planning context for detail pages. The reusable rule is recorded in `LESSONS_LEARNED.md`.

### M2.2 Employee detail and workforce context

- [x] Add the namespaced employee-detail route with the employee read guard.
- [x] Build an optimized selector/presenter for the employee profile and related planning records.
- [x] Show capacity, current workload, upcoming leave, active assignments, and the employee's skill profile using existing `core` services for calculated values.
- [x] Label weekday-based capacity and keep status distinct from dated leave.
- [x] Add useful empty states plus permission, missing-record, rendering, query-count, and response-time tests.

Completion evidence:

- Created files: `frontend/presenters/employees.py`, `frontend/templates/frontend/employees/detail.html`, `frontend/templates/frontend/employees/_assignment_row.html`, and `frontend/tests/test_employee_detail.py`.
- Modified files: `frontend/selectors/employees.py`, `frontend/views/employees.py`, `frontend/urls.py`, `frontend/templates/frontend/employees/_employee_row.html`, `frontend/templates/frontend/components/navigation.html`, `frontend/static/frontend/css/theme.css`, `frontend/tests/test_employee_directory.py`, and this task file.
- Routing and access result: `frontend:employee_detail` resolves to `/employees/<employee_id>/`; employee names in the directory link to their profiles, Workforce remains the active navigation area on both pages, anonymous users are redirected to login, authenticated users without `core.view_employee` receive 403, permitted viewers receive 200, and missing employees return 404.
- Selector result: one selector loads the employee, upcoming approved leave through `get_approved_leaves()`, active/planned assignments ending on or after the profile date with their projects, and skills with their definitions in four fixed queries. Related collections are evaluated before rendering, so assignment and skill rows do not issue per-record queries.
- Presenter result: the presenter calls `calculate_current_workload()`, `calculate_available_hours()`, and `calculate_daily_available_hours()` for calculated values. The template only formats those results and stored fields; no workload, availability, capacity, or leave calculation was reproduced in the frontend.
- Interface result: the read-only employee profile shows core employment details; weekly capacity, current workload, unallocated weekly hours, and effective availability today; current/upcoming assignments; upcoming approved leave; and skill levels with experience. It explicitly labels the Monday-to-Friday capacity assumption, distinguishes employment status from dated leave, and provides specific empty states for assignments, leave, and skills. No create, update, or delete action was added.
- Query result: a populated viewer request with two relevant assignments, one upcoming approved leave, and two skills uses 12 queries: the four-query authenticated shell plus four selector queries and four queries issued by the existing scalar calculation services on an active weekday with no current leave. Rendering remains fixed-cost as related-record counts grow.
- Response-time baseline: over 25 warm Django test-client GETs with in-memory SQLite, the complete employee profile request recorded a median response time of 10.986 ms, p95 12.465 ms, minimum 9.787 ms, and maximum 14.913 ms. The measurement includes Django request handling, service calls, queries, and template rendering but excludes browser/network latency and static-file transfer.
- Commands run:
  - `python manage.py test frontend.tests.test_employee_detail frontend.tests.test_employee_directory --verbosity 2`
  - `python manage.py test frontend.tests --verbosity 2`
  - `python manage.py test --verbosity 2`
  - `python manage.py check`
  - `git diff --check`
- Result: all 20 focused employee detail/directory tests passed in 1.101 s; all 49 frontend tests passed in 7.094 s; the complete 63-test project suite passed in 8.507 s; Django reported no system-check issues; and `git diff --check` passed with only the known LF-to-CRLF working-copy warnings for `core/services/optimization.py`, `hr_workforce/settings.py`, and `hr_workforce/urls.py`.
- Architecture result: M2.2 remains read-only and inside the Django monolith. It adds no model, migration, write flow, JavaScript business logic, separate frontend, or `core` business-logic change.
- Follow-up lesson: none. Existing lessons already require service-owned calculations, weekday labeling, separation of status and dated leave, and fixed query budgets.

### M2.3 Employee create and update flows

- [x] Add an `Employee` model form that preserves field-level validation and English feedback.
- [x] Add create and update routes, views, templates, success messages, and predictable redirects.
- [x] Enforce `core.add_employee` and `core.change_employee` independently.
- [x] Test valid writes, invalid submissions, anonymous redirects, forbidden actions, permitted actions, and unchanged records after validation failure.

Completion evidence:

- Created files: `frontend/templates/frontend/employees/_employee_form.html`, `frontend/templates/frontend/employees/create.html`, `frontend/templates/frontend/employees/edit.html`, and `frontend/tests/test_employee_forms.py`.
- Modified files: `frontend/forms/employees.py`, `frontend/views/employees.py`, `frontend/urls.py`, `frontend/templates/frontend/employees/list.html`, `frontend/templates/frontend/employees/detail.html`, `frontend/templates/frontend/components/navigation.html`, `frontend/static/frontend/css/theme.css`, `frontend/LESSONS_LEARNED.md`, and this task file.
- Form result: `EmployeeForm` is a `ModelForm` over all eight editable employee fields. It preserves Django/model required, type, choice, decimal precision, and non-negative validators; adds accessible date/number widgets, autocomplete hints, English labels, and planning-specific help text; and introduces no parallel domain-validation rule.
- Routing result: `frontend:employee_create` resolves to `/employees/new/`, and `frontend:employee_update` resolves to `/employees/<employee_id>/edit/`. Successful creates and updates redirect to the resulting employee profile; missing update targets return 404 through the standard object lookup.
- Permission result: create requires `core.add_employee` and update independently requires `core.change_employee`. Anonymous users are redirected to login, viewers receive 403 for GET and POST, and tests prove an add-only user cannot edit while a change-only user cannot create. The existing HR Administrator role can perform both actions.
- Interface result: authorized users see Add employee from the directory and Edit employee from the profile; read-only users do not see either action. Both routes use the existing shell, breadcrumbs, messages, shared field component, visible required/error semantics, a two-section desktop form, clear cancel paths, and a responsive single-column fallback. Workforce remains the active navigation area.
- Validation and feedback result: invalid POSTs render field-specific errors and `aria-invalid` associations without changing stored data. Successful writes show confirmation messages. Database save failures show safe error feedback without exposing exception details.
- Transaction result: both saves run inside `transaction.atomic()`. Tests simulate failures after the SQL insert/update has executed and confirm that the insert is removed or the prior employee values are restored by rollback.
- Commands run:
  - `python manage.py test frontend.tests.test_employee_forms --verbosity 2`
  - `python manage.py test frontend.tests --verbosity 2`
  - `python manage.py test --verbosity 2`
  - `python manage.py check`
  - `git diff --check`
- Result after the initial implementation: all 10 focused employee-form tests passed in 0.288 s; all 59 frontend tests passed in 6.169 s; and the complete 73-test project suite passed in 7.312 s. The default Django test client did not enforce CSRF checks, so these results did not expose the isolated-include defect found during manual testing.
- Architecture result: M2.3 stays within the server-rendered Django monolith and changes no model, migration, `core` service, business calculation, deletion flow, skill workflow, or deployment setting.
- Follow-up lesson: bound `ModelForm` validation can update the request-local model instance before a save occurs even when the form ultimately fails. The reusable rule for stable pre-edit labels and persistence checks is recorded in `LESSONS_LEARNED.md`.

CSRF defect correction evidence:

- Cause: `_employee_form.html` already contained `{% csrf_token %}`, but both `create.html` and `edit.html` included that partial with the Django template `only` option and did not pass `csrf_token`. The isolated include therefore had no token value and emitted no hidden `csrfmiddlewaretoken` input in a real request.
- Fix: both include sites now pass `csrf_token=csrf_token` explicitly while retaining their intentionally isolated context. No view, permission, validation, transaction, or model behavior changed.
- POST-form audit: the login form contains a direct `{% csrf_token %}`; both desktop and compact-navigation logout forms render the token from their non-isolated navigation includes; and the shared confirmation-state POST form contains `{% csrf_token %}`. No other internal POST form introduced so far has the same omission.
- Regression coverage: `test_employee_forms.py` now uses `Client(enforce_csrf_checks=True)`. One test proves tokenless create and update requests both receive 403 without changing data. A second extracts the token specifically from each rendered employee form, submits create and update with the matching CSRF cookie, and proves both writes redirect and persist.
- Real-browser result: Google Chrome loaded the local Django login, rendered a hidden CSRF input in the employee-create form, created a uniquely named employee with a 302 redirect to its profile, rendered a hidden CSRF input in the employee-edit form, updated the position and capacity with a 302 redirect, and displayed the saved values and success message. The development server recorded successful POSTs for both routes; the temporary account, employee, browser profile, and server were removed afterward.
- Corrected files: `frontend/templates/frontend/employees/create.html`, `frontend/templates/frontend/employees/edit.html`, `frontend/tests/test_employee_forms.py`, and this task file.
- Corrected verification:
  - `python manage.py test frontend.tests.test_employee_forms --verbosity 2` — 12 tests passed in 0.299 s.
  - `python manage.py test --verbosity 2` — all 75 tests passed in 7.332 s.
  - `python manage.py check` — no issues.

### M2.4 Skill directory and maintenance

- [x] Add namespaced skill list and detail routes with `core.view_skill` protection.
- [x] Add category filtering/grouping, deterministic ordering, pagination where needed, and useful empty states.
- [x] Add skill create and update forms and views protected by `core.add_skill` and `core.change_skill`.
- [x] Reuse the shared layout, table, form, feedback, and confirmation-ready patterns.
- [x] Test read/write permissions, filtering, validation, rendering, and query efficiency.

Completion evidence:

- Created files: `frontend/forms/skills.py`, `frontend/selectors/skills.py`, `frontend/presenters/skills.py`, `frontend/views/skills.py`, `frontend/templates/frontend/components/workforce_tabs.html`, `frontend/templates/frontend/skills/_skill_row.html`, `frontend/templates/frontend/skills/list.html`, `frontend/templates/frontend/skills/detail.html`, `frontend/templates/frontend/skills/_skill_form.html`, `frontend/templates/frontend/skills/create.html`, `frontend/templates/frontend/skills/edit.html`, and `frontend/tests/test_skill_management.py`.
- Modified files: `frontend/urls.py`, `frontend/templates/frontend/employees/list.html`, `frontend/templates/frontend/employees/detail.html`, `frontend/templates/frontend/components/navigation.html`, `frontend/static/frontend/css/theme.css`, `frontend/LESSONS_LEARNED.md`, and this task file.
- Routing and access result: `frontend:skill_list`, `frontend:skill_detail`, `frontend:skill_create`, and `frontend:skill_update` resolve under `/skills/`. List/detail require `core.view_skill`, create requires `core.add_skill`, and update independently requires `core.change_skill`. Anonymous users are redirected, authenticated users without the required permission receive 403, permitted viewers can read, and HR Administrators can maintain skills.
- Selector and presenter result: the directory selects only displayed skill fields, annotates employee-profile usage counts in the page query, filters by exact category, orders by category/name/primary key, paginates 24 rows, and groups the evaluated page into stable category sections without further queries. Detail loads the skill and usage count in one query.
- Interface result: Workforce now has accessible Employees/Skills section tabs; the primary Workforce navigation remains active across skill routes; employee profile skill names link to permitted skill details. The desktop-first Skill directory has a category filter, grouped tables, usage counts, query-preserving pagination, and distinct filtered/unpopulated empty states. The detail page shows the stored skill definition and read-only employee-profile usage, including an unused-skill empty state.
- Form and feedback result: `SkillForm` exposes the existing `Skill.name` and `Skill.category` model fields without adding parallel domain rules. Required/max-length validation renders at the relevant fields with accessible error identifiers. Valid creates/updates redirect to detail with success messages; validation and database failures keep records consistent and display safe English feedback.
- CSRF and transaction result: both isolated create/edit template includes pass `csrf_token` explicitly to the shared Skill POST form. Enforced-CSRF tests prove tokenless requests are rejected and tokens extracted from both rendered forms permit successful browser-equivalent submissions. Saves run within `transaction.atomic()`, and simulated post-write database failures roll back both inserts and updates.
- Query result: the populated Skill directory uses 7 queries: the 4-query authenticated shell plus one category-facet query, one paginator count, and one annotated page query. Skill detail uses 5 queries: the shell plus one annotated detail query. Neither total grows per displayed skill or employee-profile reference.
- Response-time baseline: in the complete-suite run using in-memory SQLite, 25 warm Django test-client GETs over 29 skills recorded directory median 8.551 ms, p95 9.760 ms, minimum 8.164 ms, and maximum 9.881 ms. The detail page recorded median 3.922 ms, p95 4.412 ms, minimum 3.649 ms, and maximum 4.873 ms. Measurements include Django request handling and template rendering but exclude browser/network latency and static-file transfer.
- Commands run:
  - `python manage.py test frontend.tests.test_skill_management --verbosity 2`
  - `python manage.py test --verbosity 2`
  - `python manage.py check`
  - `git diff --check`
- Result: all 22 focused M2.4 tests passed in 0.689 s; the complete 97-test project suite passed in 7.981 s; Django reported no system-check issues; and `git diff --check` passed with only the known LF-to-CRLF working-copy warnings for `core/services/optimization.py`, `hr_workforce/settings.py`, and `hr_workforce/urls.py`.
- Architecture result: M2.4 stays within the server-rendered Django monolith and changes no model, migration, `core` service, business calculation, proficiency-management flow, deletion flow, JavaScript business logic, or deployment setting. M2.5 has not started.
- Follow-up lesson: isolated template includes do not inherit the CSRF token unless it is passed explicitly. The reusable rule and enforced-client test requirement are recorded in `LESSONS_LEARNED.md`.

### M2.5 Employee proficiency management

- [x] Manage `EmployeeSkill` records from the employee workflow rather than as a disconnected administration screen.
- [x] Add proficiency create/update forms with level and years-of-experience validation and employee/skill duplicate protection.
- [x] Add removal as a confirmed POST action protected by `core.delete_employeeskill`.
- [x] Use a transaction for compound employee-profile edits and preserve field-specific errors.
- [x] Test valid changes, duplicate skills, invalid proficiency/experience, permission boundaries, rollback behavior, and empty skill profiles.

Completion evidence:

- Created files: `frontend/forms/proficiencies.py`, `frontend/views/proficiencies.py`, `frontend/templates/frontend/employees/proficiencies/_form.html`, `frontend/templates/frontend/employees/proficiencies/create.html`, `frontend/templates/frontend/employees/proficiencies/edit.html`, `frontend/templates/frontend/employees/proficiencies/confirm_remove.html`, and `frontend/tests/test_employee_proficiencies.py`.
- Modified files: `frontend/selectors/employees.py`, `frontend/urls.py`, `frontend/templates/frontend/employees/detail.html`, `frontend/templates/frontend/components/navigation.html`, `frontend/templates/frontend/components/workforce_tabs.html`, `frontend/static/frontend/css/theme.css`, `frontend/LESSONS_LEARNED.md`, and this task file.
- Workflow result: employee profiles now expose Add skill, Edit, and Remove actions only when the signed-in user has the corresponding `EmployeeSkill` permission. The add, edit, and removal pages retain the Workforce navigation state, identify the employee and skill context, and return to the employee profile after success. View-only profiles keep the stored proficiency information without maintenance actions.
- Routing and scoping result: namespaced employee-centered routes resolve at `/employees/<employee_id>/skills/add/`, `/employees/<employee_id>/skills/<employee_skill_id>/edit/`, and `/employees/<employee_id>/skills/<employee_skill_id>/remove/`. Update/removal selectors scope the relationship to both identifiers, so an `EmployeeSkill` cannot be edited or removed through another employee's URL.
- Form and validation result: the create form uses the existing `EmployeeSkill` model fields and validators for the employee, skill, level, and years of experience. Its normal skill picker omits skills already assigned to the employee; bound submissions still reach the model uniqueness constraint, which provides explicit duplicate feedback. The employee is server-bound and cannot be changed by POST data. The update form exposes only level and years of experience, so it cannot reassign the relationship to a different employee or skill.
- Constraint result: proficiency levels outside 1–5 and negative experience are rejected at their fields through the existing model validators. The existing unique employee/skill constraint prevents repeated relationships, including stale or forged submissions. No parallel business-validation rule was introduced.
- Removal result: GET renders an explicit confirmation describing the employee, skill, current level, and experience without changing data. Only a confirmed POST removes the `EmployeeSkill` link; the `Employee` and `Skill` records remain untouched. Success and safe failure messages explain the outcome.
- Permission result: create requires `core.add_employeeskill`, update requires `core.change_employeeskill`, and confirmation/removal requires `core.delete_employeeskill`. Anonymous users are redirected, viewers receive 403, HR Administrators can complete every action, and add/change/delete-only users are tested independently.
- CSRF and transaction result: isolated create/edit form includes pass `csrf_token` explicitly, and the isolated shared confirmation component receives it explicitly as well. Enforced-CSRF tests reject tokenless create, update, and removal requests and complete all three actions with tokens extracted from the rendered forms. Create, update, and removal writes run in `transaction.atomic()`; simulated post-write database failures prove that inserts, updates, and deletes roll back.
- Commands run:
  - `python manage.py test frontend.tests.test_employee_proficiencies --verbosity 2`
  - `python manage.py test --verbosity 2`
  - `python manage.py check`
  - `git diff --check`
- Result: all 17 focused M2.5 tests passed in 0.365 s; the complete 114-test project suite passed in 8.256 s; Django reported no system-check issues; and `git diff --check` passed with only the known LF-to-CRLF working-copy warnings for `core/services/optimization.py`, `hr_workforce/settings.py`, and `hr_workforce/urls.py`.
- Architecture result: M2.5 changes only `EmployeeSkill` relationship workflows inside the server-rendered Django monolith. It does not delete an employee or skill definition, add a migration, change `core` models or services, duplicate matching/recommendation logic, or start M2.6.
- Follow-up lesson: parent-scoped relationship forms must keep the server-owned parent field inside the `ModelForm` validation set when a multi-field uniqueness constraint depends on it. The reusable pattern is recorded in `LESSONS_LEARNED.md`.

### M2.6 Safe employee and skill deletion

- [x] Build read-only impact selectors that load the named people/skills and business-facing counts needed to explain employee or skill deletion.
- [x] Show the affected workforce information before confirmation without changing deletion behavior.
- [x] Implement employee and skill deletion as CSRF-protected, POST-only actions guarded by their delete permissions.
- [x] Re-fetch and validate the target at submission time, then provide clear success or missing-record feedback.
- [x] Test named impact details, business-friendly empty wording, GET rejection, CSRF-aware POST behavior, forbidden deletes, permitted deletes, and resulting cascades.

Completion evidence:

- Created files: `frontend/selectors/deletions.py`, `frontend/presenters/deletions.py`, `frontend/views/deletions.py`, `frontend/templates/frontend/components/cascade_impact.html`, `frontend/templates/frontend/employees/confirm_delete.html`, `frontend/templates/frontend/skills/confirm_delete.html`, and `frontend/tests/test_safe_deletion.py`.
- Modified files: `frontend/urls.py`, `frontend/templates/frontend/components/page_header.html`, `frontend/templates/frontend/components/navigation.html`, `frontend/templates/frontend/components/workforce_tabs.html`, `frontend/templates/frontend/employees/detail.html`, `frontend/templates/frontend/skills/detail.html`, `frontend/static/frontend/css/theme.css`, `frontend/LESSONS_LEARNED.md`, and this task file.
- Routing and access result: `frontend:employee_delete` resolves to `/employees/<employee_id>/delete/`, and `frontend:skill_delete` resolves to `/skills/<skill_id>/delete/`. Employee and skill detail pages expose visually secondary destructive actions only to users with the corresponding delete permission; Workforce navigation remains active on confirmation pages.
- Impact selector result: each confirmation target loads in two fixed queries: one annotated target query for business counts and one ordered prefetch for the named relationships. Employee impact lists actual skill names and proficiency levels, then counts project assignments, leave entries, and attendance entries. Skill impact lists actual employee names and proficiency levels, then counts project requirements. Rendering does not issue a query per named item.
- Confirmation result: both pages use the existing impact and confirmation cards but now say `What will be deleted`, explain consequences in workforce-planning language, and avoid database/framework terms and generic related-record totals. An employee with no related information sees `This employee has no related information. Only the employee profile will be deleted.` Related employees see named skills plus plain assignment, leave, and attendance counts. Skill deletion lists the employees using the skill and the number of project requirements using it. The existing cancel path, visual layout, styling, colors, spacing, and interaction are unchanged.
- HTTP and CSRF result: GET renders confirmation without deleting, PUT is rejected with 405, and only POST reaches the deletion branch. The isolated confirmation includes pass `csrf_token` explicitly to the shared POST component. Enforced-CSRF tests reject tokenless employee and skill deletions and successfully submit tokens extracted specifically from each rendered confirmation form.
- Permission and stale-state result: employee deletion requires `core.delete_employee`, while skill deletion independently requires `core.delete_skill`. Anonymous users are redirected, viewers receive 403, delete-only permissions are model-specific, stale GETs return 404, and stale POSTs redirect to the appropriate directory with an informational message instead of failing or deleting another record.
- Cascade result: confirmed employee deletion still removes only the employee plus related proficiencies, assignments, assignment-skill coverage, leave, and attendance; project and skill definitions remain. Confirmed skill deletion still removes only the skill plus related employee proficiencies, project requirements, and assignment-skill coverage; employee, project, and assignment records remain. Tests continue to verify indirect descendants even though the confirmation page intentionally does not expose technical relationship details. No relationship or `on_delete` behavior changed.
- Transaction and feedback result: each target is re-fetched with fresh impact information on submission and deletion runs inside `transaction.atomic()`. Successful and failed outcomes now use natural business wording instead of generic record totals. Simulated failures after Django begins cascading prove the target and related information roll back and render safe error feedback.
- Commands run:
  - `python manage.py test frontend.tests.test_safe_deletion --verbosity 2`
  - `python manage.py check`
  - `git diff --check`
- Result after the business-language refinement: all 15 focused M2.6 tests passed in 0.464 s; Django reported no system-check issues; and `git diff --check` passed with only the known LF-to-CRLF working-copy warnings for `core/services/optimization.py`, `hr_workforce/settings.py`, and `hr_workforce/urls.py`. Before this presentation-only refinement, the complete 128-test project suite passed in 9.168 s.
- Architecture result: M2.6 adds no model, migration, relationship, cascade-rule, matching, optimization, recommendation, or deployment change. It does not start M2.7.
- Follow-up lesson: verify the complete deletion graph internally, but present only recognizable business consequences and named context to the user. The reusable rule is recorded in `LESSONS_LEARNED.md`.

### M2.7 Milestone 2 verification

- [x] Verify every employee, skill, and proficiency route name, authentication rule, permission boundary, template, and state.
- [x] Run empty-state, validation, destructive-action, and critical desktop workflow tests.
- [x] Record list/detail query counts and warm response times relative to the authenticated-shell baseline; confirm no avoidable N+1 queries.
- [x] Run the complete Milestone 2 test set and `python manage.py check`.
- [x] Update completion evidence, retain `LESSONS_LEARNED.md` unchanged because no new reusable lesson was found, and close Milestone 2 without starting Milestone 3.

Completion evidence:

- Route and template result: all 13 Milestone 2 namespaced routes reverse and resolve at their documented paths: employee list/detail/create/update/delete; employee-centered proficiency create/update/remove; and skill list/detail/create/update/delete. Route tests rendered every page-specific template and important partial, confirmed natural links between directories, details, forms, and confirmations, and kept Workforce navigation active throughout.
- Authentication and permission result: anonymous access redirects to login; authenticated users without the required model permission receive 403; viewers and managers/planners retain read-only Employee, Skill, and EmployeeSkill access through the exact synchronized role map; HR Administrators retain all required maintenance permissions. Add, change, and delete permissions are independently tested for Employee, Skill, and EmployeeSkill routes, including both GET and POST mutation attempts.
- Employee directory result: verified multi-term first/last-name search, combined status/department filters, the seven-key sorting allow-list and safe fallback, deterministic ordering, 20-row pagination with preserved query parameters, the desktop table, active navigation, and separate filtered/unpopulated empty states.
- Employee detail result: verified core profile fields, weekday-labelled capacity, current workload and available hours returned by existing `core` services, relevant assignments, upcoming approved leave, skill/proficiency context, fixed-query related collections, section-specific empty states, and missing-employee handling. No calculation is duplicated in frontend code.
- Employee maintenance result: verified create/update routes and templates, naturally placed actions, valid persistence and redirects, field-specific invalid-state feedback, viewer/anonymous rejection, independent add/change permissions, transaction rollback after simulated database failures, success/error messages, and stable stored data after failed writes.
- Skill result: verified category filtering/grouping, deterministic 24-row pagination, directory/detail rendering, usage and unused-skill states, missing-detail handling, create/update validation, independent add/change permissions, success/error feedback, and rollback after simulated database failures.
- Proficiency result: verified employee-scoped add/edit/remove routes, duplicate relationship prevention through existing model validation, level 1–5 and non-negative experience validation, immutable employee/skill scope during edits, explicit confirmed removal, mismatched/stale relationship handling, independent add/change/delete permissions, success/error feedback, and rollback after simulated failures.
- Safe deletion result: verified business-friendly named impact information, profile/skill-only states, no deletion on GET, 405 for unsupported methods, explicit POST confirmation, model-specific delete permissions, stale GET/POST outcomes, successful direct and indirect cascades, preserved top-level Employee/Skill/Project/Assignment objects where appropriate, and rollback after simulated deletion failures.
- CSRF result: all nine Milestone 2 POST workflows are covered with `Client(enforce_csrf_checks=True)`: Employee create/update; Skill create/update; proficiency add/edit/remove; and Employee/Skill delete. Tokenless requests receive 403 without mutation, while tokens extracted from each rendered form allow the intended write.
- Important-state result: tests cover populated and empty pages, filtered-empty results, unused skills, employees without related planning context, valid success flows, field and non-field validation errors, forbidden access, missing detail targets, mismatched proficiency ownership, stale deletion targets, and database-failure feedback with transactional consistency.
- Query baseline: all totals include the four-query authenticated role-based shell. The Employee directory uses 7 queries (3 page-specific), Employee detail uses 12 (8 page-specific, including existing scalar calculation services), Skill directory uses 7 (3 page-specific), and Skill detail uses 5 (1 page-specific). Exact assertions remain stable as fixture rows grow, so no N+1 regression was found.
- Response-time baseline: 25 warm Django test-client GETs per page using in-memory SQLite recorded Employee directory median 12.477 ms, p95 13.805 ms, minimum 11.740 ms, maximum 41.398 ms; Employee detail median 8.821 ms, p95 9.137 ms, minimum 8.404 ms, maximum 9.585 ms; Skill directory median 8.498 ms, p95 9.901 ms, minimum 8.137 ms, maximum 10.297 ms; and Skill detail median 4.054 ms, p95 4.406 ms, minimum 3.719 ms, maximum 5.356 ms. Measurements include Django request handling, ORM/service work, and template rendering but exclude browser/network latency and static-file transfer.
- Commands run:
  - `python manage.py test frontend.tests.test_permissions frontend.tests.test_employee_directory frontend.tests.test_employee_detail frontend.tests.test_employee_forms frontend.tests.test_skill_management frontend.tests.test_employee_proficiencies frontend.tests.test_safe_deletion --verbosity 2`
  - `python manage.py test --verbosity 2`
  - `python manage.py check`
  - `git diff --check`
- Verification result: all 92 critical Milestone 2 workflow/permission tests passed in 2.594 s; the complete 129-test project suite passed in 8.889 s; Django reported no system-check issues; and `git diff --check` passed with only the known LF-to-CRLF working-copy warnings for `core/services/optimization.py`, `hr_workforce/settings.py`, and `hr_workforce/urls.py`.
- Defects: none found during M2.7. No application, model, service, template, static, migration, permission, or test code was changed by this verification task.
- Lessons result: no new reusable lesson was discovered, so `frontend/LESSONS_LEARNED.md` was not changed for M2.7.
- Milestone result at the M2.7 handoff: every Milestone 2 exit criterion was satisfied and Milestone 3 was left unstarted pending the approval that has now been granted.

## Milestone 2 exit criteria

- [x] Authorized HR users can safely create, update, and delete employees, skills, and employee proficiency records.
- [x] Viewers and managers/planners can inspect the employee directory, employee details, skills, and proficiency data without HR write access.
- [x] Employee lists support useful search, filtering, deterministic sorting, pagination, and empty states.
- [x] Employee detail pages show capacity, workload, upcoming leave, active assignments, and skills without duplicating `core` calculations.
- [x] Employee and skill deletions explain their impact and require a permitted, CSRF-protected POST confirmation.
- [x] Validation and permission failures are clear, records remain consistent after failed writes, and relevant multi-record edits are atomic.
- [x] Query/response baselines are recorded, milestone tests pass, and Django reports no system-check issues.

## Completed work

Task M1.1 — Protect the frontend/backend contract before adding views.

### M1.1 Service and validation contract

- [x] Record the supported input and output shapes for matching and recommendation services in focused tests.
- [x] Add a deterministic end-to-end service test covering feasible teams, Pareto filtering, selection, comparison, and structured explanations without calling Gemini.
- [x] Add high-value model validation tests for assignment qualification, overlapping assignments, total allocation, approved leave, and assignment-skill consistency.
- [x] Add tests for a project with missing/zero mandatory effort and for a project with no feasible team.
- [x] Capture a repeatable performance baseline using the generated sample dataset.
- [x] Run the targeted tests and `python manage.py check`.

Completion evidence to record here:

- Commit or changed files: `core/test_service_contracts.py`, `core/test_model_validation.py`, and this task file. No commit was created.
- Commands run:
  - `python manage.py test core.test_service_contracts core.test_model_validation -v 2`
  - `python manage.py shell -c "..."` to verify generated sample-data counts and time the full deterministic recommendation pipeline for `HR Platform` with `time.perf_counter()`.
  - `python manage.py check`
  - `git diff --check`
- Result: 12 targeted tests passed in 0.579 s; Django reported no system-check issues; `git diff --check` passed.
- Performance baseline: the generated sample database contains 10 active employees, 8 skills, 40 employee skills, 3 projects, 9 requirements, 7 assignments, 10 assignment-skill links, 3 leave records, and 210 attendance records. For `HR Platform`, the pipeline produced 88 feasible teams, 15 Pareto teams, 3 recommendations, 2 comparisons, and 3 deterministic explanations. Feasible-team generation took 20.231 s and the complete deterministic pipeline took 20.232 s.
- Follow-up lesson, if any: None. The missing/zero mandatory-effort behavior was already captured in `LESSONS_LEARNED.md`.

Task M1.2 — Frontend-facing prerequisites.

### M1.2 Frontend-facing prerequisites

- [x] Fix mojibake in strings that can appear in forms, choices, errors, or record labels; keep source files UTF-8.
- [x] Confirm that mandatory requirements need positive effort before recommendations can run and encode that as form/preflight feedback.
- [x] Inventory development-only settings that later need environment configuration without changing deployment behavior yet.
- [x] Re-run service contract tests after prerequisite fixes.

Completion evidence:

- Changed files: added `.editorconfig` and `core/services/recommendation_preflight.py`; updated `core/services/optimization.py`, `core/test_service_contracts.py`, `core/test_model_validation.py`, `frontend/PLAN.md`, `frontend/LESSONS_LEARNED.md`, and this task file. No commit was created.
- Encoding result: runtime-facing model labels, help text, validation messages, and deterministic explanation strings are valid UTF-8. The earlier apparent mojibake was a Windows PowerShell decoding artifact. `.editorconfig` now declares UTF-8 for source and documentation, and regression assertions protect representative model and explanation text.
- Preflight result: `get_recommendation_preflight(project)` returns a stable `can_generate_recommendations` flag plus field-addressable blockers. Missing or zero effort on any mandatory requirement blocks `find_all_feasible_teams(project)` before team enumeration, including when other mandatory requirements are valid.
- Configuration inventory: `frontend/PLAN.md` records the current hard-coded secret key, debug mode, empty hosts, SQLite database, UTC/en-us policy, incomplete static setup, non-standard `MAILERS`, implicit Gemini credentials, and absent production HTTPS/cookie settings. Runtime settings were not changed.
- Commands run:
  - `python manage.py test core.test_service_contracts core.test_model_validation -v 2`
  - `python manage.py check`
  - UTF-8/mojibake searches with `rg` and explicit `Get-Content -Encoding utf8` inspection.
- Result: 14 targeted tests passed in 1.079 s; Django reported no system-check issues.
- Behavior change: recommendation team enumeration now returns no teams when preflight finds missing or non-positive mandatory effort; zero effort remains permitted for optional requirements. This implements the approved M1.2 rule; no additional product decision is required.
- Follow-up lesson: on Windows, explicitly decode BOM-less source files as UTF-8 before diagnosing mojibake. The reusable correction is recorded in `LESSONS_LEARNED.md`.

Task M1.3 — Django app scaffold.

### M1.3 Django app scaffold

- [x] Create the `frontend` Django app structure described in `PLAN.md`.
- [x] Add it to `INSTALLED_APPS` and include a namespaced `frontend.urls` from the project URL configuration.
- [x] Create namespaced template and static directories.
- [x] Add an authenticated landing route and a health-level template render test.

Completion evidence:

- Created files: the `frontend` app/config/URL modules; package markers for forms, views, selectors, presenters, template tags, and tests; the landing view; minimal base and landing templates; namespaced template/static directory placeholders; and landing-route smoke tests.
- Modified files: `hr_workforce/settings.py`, `hr_workforce/urls.py`, `frontend/LESSONS_LEARNED.md`, and this task file.
- Routing result: `frontend:landing` resolves to `/`; authenticated users receive the English landing template, and anonymous users are redirected to Django's default login URL pending M1.4.
- Architecture result: the interface remains in the existing Django monolith. No API, React/Vue application, frontend build system, model, migration, or `core` business-logic change was introduced.
- Commands run:
  - `python manage.py test frontend.tests.test_landing -v 2`
  - `python manage.py test -v 2`
  - `python manage.py check`
- Result: 2 landing tests passed in 0.030 s; the complete 16-test suite passed in 1.057 s; Django reported no system-check issues.
- Follow-up lesson: keep URL/template/static names app-scoped. The default login redirect target exists as a setting but will not resolve until the explicitly deferred M1.4 authentication routes are added.

Task M1.4 — Authentication and permissions.

### M1.4 Authentication and permissions

- [x] Add login and logout flows using Django authentication.
- [x] Define the initial HR administrator, manager/planner, and viewer permission mapping.
- [x] Add reusable permission guards for read and write views.
- [x] Test anonymous redirects, forbidden actions, and permitted actions.

Completion evidence:

- Created files: `frontend/roles.py`, `frontend/permissions.py`, the `sync_frontend_roles` management-command package, `frontend/templates/frontend/auth/login.html`, `frontend/tests/test_authentication.py`, and `frontend/tests/test_permissions.py`.
- Modified files: `frontend/urls.py`, `frontend/views/landing.py`, `frontend/templates/frontend/dashboard/landing.html`, `frontend/tests/test_landing.py`, `hr_workforce/settings.py`, `frontend/PLAN.md`, `frontend/LESSONS_LEARNED.md`, and this task file.
- Authentication result: `/login/` uses Django's `LoginView` with English feedback; `/logout/` uses POST-only `LogoutView`; login, login-redirect, and logout-redirect settings use namespaced frontend routes.
- Permission result: reusable model read/write guards redirect anonymous users and return 403 for authenticated users without permission. The landing page now requires `core.view_employee`.
- Initial role mapping: HR Administrators receive 36 add/change/delete/view permissions across all nine `core` models; Managers / Planners receive nine view permissions plus add/change on the four planning models; Viewers receive nine view permissions and no writes.
- Provisioning result: `python manage.py sync_frontend_roles` idempotently creates the three groups and resets their `core` permissions to the declared mapping. Tests exercise the command against the isolated test database; the local development database was not modified.
- Architecture result: no `core` business logic, domain model, API, separate frontend application, or frontend build system was changed or added.
- Commands run:
  - `python manage.py test frontend.tests -v 2`
  - `python manage.py test -v 2`
  - `python manage.py check`
- Result: all 12 frontend tests passed in 5.808 s; the complete 26-test suite passed in 6.991 s; Django reported no system-check issues.
- Approval still required: before production, confirm whether all three roles may view every domain record, whether manager/planner writes should remain limited to add/change on planning records with no deletes, whether recommendation execution should continue to rely on project view permission or use a custom permission, and who may assign users to the canonical groups.
- Follow-up lesson: role synchronization is explicit and exact rather than a startup side effect; this prevents an unapproved provisional mapping from silently rewriting operator-managed permissions.

Task M1.5 — App shell and shared components.

### M1.5 App shell and shared components

- [x] Add pinned Bootstrap assets and the small project theme.
- [x] Build the base template, responsive navigation, breadcrumbs, page header, and message area.
- [x] Build shared form field, table, pagination, status badge, confirmation, loading, empty-state, and error-state components.
- [x] Add consistent date, decimal-hour, percentage, and status formatting helpers.
- [x] Verify keyboard navigation, visible focus, semantic headings, labels, and color contrast.

Completion evidence:

- Created files: pinned local Bootstrap 5.3.8 CSS and bundled JavaScript plus its MIT license; `frontend/static/frontend/css/theme.css`; `frontend/static/frontend/js/app.js`; `frontend/templatetags/frontend_format.py`; 13 templates under `frontend/templates/frontend/components/`; and `frontend/tests/test_ui_foundation.py`. The three static-directory `.gitkeep` placeholders were removed after real assets were added.
- Modified files: `frontend/templates/frontend/base.html`, `frontend/templates/frontend/auth/login.html`, `frontend/templates/frontend/dashboard/landing.html`, `frontend/views/landing.py`, `frontend/tests/test_authentication.py`, `frontend/tests/test_landing.py`, `frontend/LESSONS_LEARNED.md`, and this task file.
- Asset result: Bootstrap is served locally with versioned filenames and no CDN runtime dependency. SHA-256 is `D85327D99C7A3EE1F9B5D0500D1370ACEA3AD2DB39C163C2F51F232BAEDBDEDE` for CSS and `E4FD49181388C48EC5040BD3FE66F57C29C8E67FCD8502B3354B96EC7AB47CC7` for bundled JavaScript.
- Interface result: authenticated users receive a responsive workforce-planning shell with desktop navigation, a mobile off-canvas menu, breadcrumbs, page headers, messages, and prepared Dashboard, Workforce, Projects, Planning, and Recommendations areas. Anonymous users receive the themed sign-in layout. Future-area labels are non-interactive until their routes are implemented.
- Component and formatting result: reusable form, table, pagination, badge, confirmation, loading, empty, and error states render from namespaced Django templates; template filters consistently present dates, decimal hours, already-calculated percentages, and status labels/tones without deriving business values.
- Accessibility result: the shell uses native links, buttons, labels, landmarks, one page-level heading, a skip link, no positive `tabindex`, clear focus-visible styling, reduced-motion handling, responsive breakpoints, and text-plus-dot status cues. Automated contrast checks cover primary text/button and status-badge pairs; every checked pair is at least 4.5:1, with the lowest at 6.04:1.
- Commands run:
  - `python manage.py test frontend.tests --verbosity 2`
  - `python manage.py test --verbosity 2`
  - `python manage.py check`
  - `git diff --check`
- Result: all 24 frontend tests passed in 5.491 s; the complete 38-test suite passed in 6.578 s; Django reported no system-check issues; `git diff --check` passed with only pre-existing line-ending normalization warnings on previously modified files.
- Visual-review note: a live development server started successfully, but no Chrome, Edge, or in-app browser surface was available to the automation environment. Manual inspection instructions are included in the task handoff.
- Architecture result: no `core` model, service, calculation, migration, API, SPA, CRUD workflow, dashboard metric, or deployment setting was changed.
- Follow-up lesson: Django's generated `aria-describedby` identifiers must be preserved when rendering a `BoundField` through a custom component; the reusable rule is recorded in `LESSONS_LEARNED.md`.

Task M1.6 — Foundation verification.

### M1.6 Foundation verification

- [x] Test route names, authentication, permissions, template rendering, and static files.
- [x] Measure initial page query counts and response time.
- [x] Run the milestone test set and `python manage.py check`.
- [x] Update `LESSONS_LEARNED.md` with reusable discoveries.
- [x] Close Milestone 1 while leaving Milestone 2 unstarted pending explicit approval.

Completion evidence:

- Created file: `frontend/tests/test_foundation_verification.py`.
- Modified files: `frontend/CURRENT_TASKS.md` and `frontend/LESSONS_LEARNED.md`. No application or `core` business-logic file was changed for M1.6.
- Route result: `frontend:landing`, `frontend:login`, and `frontend:logout` reverse to `/`, `/login/`, and `/logout/`; each path resolves back to the same namespaced route with app name and namespace `frontend`.
- Authentication and permission result: anonymous landing requests redirect to login; invalid login stays on the English form; valid login creates a session and redirects to the landing page; logout is POST-only and clears the session; authenticated users without read permission receive 403; viewer, manager/planner, and HR administrator read/write outcomes match the declared role map.
- Template result: the base, login, landing, and all 13 shared component templates compile; request-level tests render the login and authenticated landing templates with the expected shell, labels, navigation, feedback, and accessibility semantics.
- Static result: Django's staticfiles finder and `findstatic` locate the project theme, project JavaScript, pinned Bootstrap 5.3.8 CSS, pinned Bootstrap bundle, and vendor license; every asset is nonempty.
- Page query baseline: anonymous login GET uses 0 database queries. Authenticated viewer landing GET uses 4 database queries: session, user, direct user permissions, and group permissions.
- Page response baseline: measured over 25 warm Django test-client GETs per page using the in-memory SQLite test database and fully rendered templates. Login median was 1.674 ms, p95 2.099 ms, minimum 1.583 ms, and maximum 3.336 ms. Landing median was 2.806 ms, p95 3.186 ms, minimum 2.647 ms, and maximum 3.896 ms. This intentionally excludes browser/network latency and static-file transfer and is not a production latency budget.
- Recommendation baseline retained from M1.1: the generated local dataset produced 88 feasible teams, 15 Pareto teams, and 3 recommendations for `HR Platform`; the complete deterministic pipeline took 20.232 s.
- Commands run:
  - `python manage.py test frontend.tests.test_foundation_verification --verbosity 2`
  - `python manage.py test frontend.tests.test_authentication frontend.tests.test_permissions frontend.tests.test_landing --verbosity 2`
  - `python manage.py findstatic frontend/css/theme.css frontend/js/app.js frontend/vendor/bootstrap-5.3.8.min.css frontend/vendor/bootstrap-5.3.8.bundle.min.js frontend/vendor/BOOTSTRAP-LICENSE.txt --verbosity 2`
  - `python manage.py test core.test_service_contracts core.test_model_validation frontend.tests --verbosity 2`
  - `python manage.py check`
  - `git diff --check`
- Result: all 5 focused M1.6 tests passed in 0.178 s; all 12 authentication/permission/landing tests passed in 5.039 s; the complete 43-test Milestone 1 suite passed in 6.214 s; all five static assets were found; Django reported no system-check issues; `git diff --check` exited successfully with only the previously recorded line-ending normalization warnings.
- Follow-up lesson: treat the four authenticated shell queries as a fixed comparison baseline and measure future page-specific ORM work incrementally. The reusable rule is recorded in `LESSONS_LEARNED.md`.
- Remaining approvals: Milestone 2 must be explicitly approved before work starts. The previously recorded production decisions about final role/record scope, business calendar policy, recommendation persistence/acceptance, target scale/latency, database/hosting/static strategy, and Gemini privacy remain unresolved but do not invalidate Milestone 1.

## Milestone 1 exit criteria

- [x] An authenticated user can open a responsive app shell.
- [x] Anonymous and unauthorized users receive the intended redirect or forbidden response.
- [x] Shared components cover the common page, table, form, feedback, and empty/error states.
- [x] Frontend code calls documented `core` service contracts and does not duplicate calculations.
- [x] Targeted tests and Django system checks pass.
- [x] Baseline query and recommendation timings are recorded.

## Update procedure

After each task:

1. Check the completed item.
2. Add concise completion evidence under the task when it helps the next developer.
3. Move **Current focus** to the next unchecked task.
4. Add only reusable mistakes, constraints, or speedups to `LESSONS_LEARNED.md`.
5. When every exit criterion passes, replace the active milestone and task list with the next milestone from `PLAN.md`; completed history remains available in Git.

## Known blockers

None for starting M4.1 after approval. The initial model-permission mapping remains deliberately conservative: HR Administrators may maintain all operational records; Managers / Planners may add and change project planning records but may not delete them; and Viewers remain read-only. Final record-level role scope remains a production decision. Milestone 4 must retain the configured timezone and current Monday-to-Friday service assumptions while making those limits explicit; final business-calendar policy, dashboard scale/latency targets, recommendation persistence and acceptance, and production infrastructure remain unresolved release decisions.
