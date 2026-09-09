# HR Workforce Interface Plan

Last updated: 2026-09-08

## Project goal

Build a clear, secure Django interface that helps managers and HR staff maintain workforce data, understand capacity and workload over time, plan projects, and compare explainable team recommendations.

The interface must make the existing decision logic visible rather than reimplement it. Skills, workload, leave, experience, feasibility, effort allocation, Pareto filtering, and recommendation selection remain controlled by the services in `core/services/`. Managers should be able to see why a team is feasible, where its capacity goes, and what trade-offs distinguish it from the other options.

## Current baseline

The repository currently contains:

- A Django project with one domain app, `core`.
- Models for employees, skills, employee skills, projects, skill requirements, assignments, assignment skill coverage, leave, and attendance.
- Django admin screens for every domain model.
- Services for workload, leave availability, effective project capacity, attendance summaries, employee/project matching, OR-Tools effort allocation, team metrics, Pareto filtering, recommendation selection, deterministic explanations, and optional Gemini summaries.
- A deterministic sample-data command and a populated local SQLite database with 10 employees, 8 skills, 3 projects, and related planning records.
- No application URLs beyond Django admin, no user-facing views or forms, and no automated tests beyond the empty Django test placeholder.
- An empty `frontend/` directory before these planning documents were added.

`python manage.py check` currently passes. A smoke run for the first sample project found 88 feasible teams, 15 Pareto teams, and the compact, balanced, and capacity recommendations in about 20.4 seconds. That timing is a design constraint for the recommendation experience.

## Product principles

1. **Explain every decision.** Show source metrics, skill coverage, allocated effort, strengths, and trade-offs beside each recommendation.
2. **Keep calculations in the backend.** Templates and browser code format results; they do not reproduce scoring or feasibility rules.
3. **Validate before expensive work.** Project dates, mandatory requirements, effort, eligible employees, and capacity should be checked before team enumeration and OR-Tools execution.
4. **Make destructive effects visible.** Employee and project deletion currently cascade into related data, so confirmations must identify affected records.
5. **Design for real workflows.** Lists need search, filters, sorting, pagination, useful empty states, and links to the next action.
6. **Preserve a deterministic fallback.** Structured explanations are always shown. Gemini may improve wording, but it must never decide, rank, or block the recommendation result.
7. **Make charts supplemental.** Every visualization must have a readable value, table, or text equivalent.
8. **Measure before adding infrastructure.** Start with server-rendered requests and recorded timings. Add a job queue only if the agreed response-time target cannot be met safely in a web request.

## Architecture

### Application boundaries

```text
Browser
  -> frontend URLs and Django views
     -> forms and formsets (input validation)
     -> selectors/presenters (query and display shaping)
     -> core services (matching, capacity, optimization, explanations)
        -> Django ORM and core models
        -> OR-Tools CP-SAT
        -> Gemini, optional and isolated
  <- Django templates, partial responses, charts, and accessible tables
```

The planned `frontend` Django app owns presentation and interaction. The existing `core` app continues to own the domain model and decision-support logic.

### Planned frontend layout

```text
frontend/
  apps.py
  urls.py
  forms/
  views/
  selectors/
  presenters/
  templatetags/
  templates/frontend/
    base.html
    components/
    dashboard/
    employees/
    projects/
    planning/
    calendar/
  static/frontend/
    css/
    js/
    vendor/
  tests/
  PLAN.md
  CURRENT_TASKS.md
  LESSONS_LEARNED.md
```

- **Views** handle HTTP concerns, permissions, messages, and redirects. Keep them thin.
- **Forms and inline formsets** expose model validation and translate validation failures into field-level feedback.
- **Selectors** centralize optimized read queries using `select_related`, `prefetch_related`, annotations, and pagination.
- **Presenters** convert ORM objects and service dictionaries into stable, template-friendly structures. They also centralize number, date, status, and chart serialization.
- **Core services** remain the only implementation of business calculations and recommendation selection.
- **Templates and browser code** handle rendering, small interactions, progressive enhancement, and charts.

### Request and recommendation flow

1. A signed-in user selects a project and opens its planning workspace.
2. The view performs cheap preflight checks and shows actionable blockers before optimization.
3. The user explicitly starts recommendation generation with a POST request.
4. A frontend orchestration function calls, in order:
   - `find_all_feasible_teams(project)`
   - `find_pareto_teams(feasible_teams)`
   - `select_recommended_teams(pareto_teams)`
   - `compare_recommendations(recommendations)`
   - `build_recommendation_explanations(recommendations, comparisons)`
5. The presenter builds recommendation cards, comparison data, coverage rows, employee allocations, and deterministic explanations.
6. Gemini summaries are requested only as optional enrichment. A timeout, missing credential, or provider failure leaves the deterministic result intact.
7. Recommendations are advisory. Creating assignments remains a separate reviewed action that uses normal model validation and a database transaction.

### Access model

Use Django authentication, sessions, CSRF protection, model permissions, and groups. The initial policy should support:

- **HR administrators:** manage employees, skills, leave, attendance, and planning data.
- **Managers/planners:** view workforce data, manage projects where permitted, and run recommendations.
- **Viewers:** read dashboards and planning results without editing data.

The exact group membership policy must be confirmed before production use. Until then, deny write actions unless the user has the corresponding Django model permission.

M1.4 establishes this conservative initial model-permission mapping:

| Group | Read permissions | Write permissions |
| --- | --- | --- |
| HR Administrators | View all `core` models. | Add, change, and delete all `core` models. |
| Managers / Planners | View all `core` models. | Add and change projects, project skill requirements, assignments, and assignment-skill coverage. No delete permissions and no HR-record writes. |
| Viewers | View all `core` models. | None. |

Run `python manage.py sync_frontend_roles` after migrations to create these groups or reset their permissions to this exact mapping. Recommendation execution will initially rely on project view access; a custom permission and any department/project-level record scope remain production policy decisions.

### Data and validation rules

- Use `ModelForm`/formset validation and `transaction.atomic()` for multi-record edits.
- Never use bulk writes for domain records unless validation is performed explicitly first.
- Preserve the model rules around date ranges, skill qualification, assignment overlap, allocation limits, approved leave, requirement quantities, and assignment-skill consistency.
- Treat mandatory requirements with missing or zero `estimated_effort_hours` as a visible planning blocker. Recommendation preflight stops team enumeration when any exist; the lower-level optimization context continues to construct effort variables only for positive effort.
- Show the project estimate and the sum of mandatory requirement effort together so discrepancies are obvious.
- Make the weekday-only, Monday-to-Friday capacity assumption explicit until a holiday/work-schedule model exists.
- Do not imply that attendance affects recommendations; the current matching and optimization services do not use it.

### Development configuration inventory

M1.2 records the current development configuration without changing runtime or deployment behavior. These items remain release-hardening work:

| Concern | Current development state | Required later action |
| --- | --- | --- |
| `SECRET_KEY` | A development key is committed in `settings.py`. | Require a secret supplied by the deployment environment and fail safely when it is absent. |
| `DEBUG` | Hard-coded to `True`. | Read an explicitly parsed environment value and default production deployments to `False`. |
| Hosts and origins | `ALLOWED_HOSTS` is empty and no deployment-specific trusted origins are configured. | Configure allowed hosts and any required CSRF trusted origins per environment. |
| Database | Local SQLite at `BASE_DIR / "db.sqlite3"`. | Confirm PostgreSQL and supply validated connection settings through the environment. |
| Locale and timezone | `LANGUAGE_CODE` is `en-us`; `TIME_ZONE` is `UTC`. | Confirm the business locale/timezone policy before changing either value. |
| Static files | Only `STATIC_URL` is configured. | Confirm the production static root, collection, storage, and serving strategy. |
| Email | A non-standard `MAILERS` dictionary points at the console backend. | Replace it with Django's standard email settings and environment-provided provider credentials when email is introduced. |
| Gemini | `genai.Client()` obtains credentials outside Django settings. | Define the approved credential source, data/privacy policy, timeout, and failure handling before enabling summaries in production. |
| HTTPS and cookies | Production proxy, HTTPS redirect, HSTS, and secure cookie settings are not configured. | Set them for the selected hosting topology and verify with deployment checks. |

## Technologies

### Already in the repository

| Area | Technology | Role |
| --- | --- | --- |
| Application | Python, Django 6.1 | Web framework, ORM, forms, authentication, templates |
| Development data | SQLite | Current local database |
| Optimization | OR-Tools 9.15 CP-SAT | Feasibility checks and effort allocation |
| LLM enrichment | `google-genai` with Gemini | Optional manager-friendly wording |
| Sample data | Faker | Deterministic development dataset generation |
| Supporting packages | Decimal-based Python logic, NumPy, pandas | Calculation ecosystem; only use where the code requires it |

### Planned interface stack

| Area | Technology | Decision |
| --- | --- | --- |
| Rendering | Django Template Language and semantic HTML5 | Server-rendered, accessible pages with no separate API required |
| Styling | Bootstrap 5 plus a small project theme | Responsive layout and common components with limited custom CSS |
| Interactions | Vanilla JavaScript; HTMX where partial page updates materially improve a workflow | Progressive enhancement without a single-page application |
| Charts | Chart.js | Workload, capacity, status, and comparison charts |
| Calendar | FullCalendar | Projects, assignments, and approved leave timeline |
| Static assets | Django `staticfiles`, pinned vendor versions | Reproducible assets; avoid unpinned production CDN dependencies |
| Testing | Django `TestCase`/test client plus focused browser-flow tests | Permissions, validation, pages, and critical planning paths |
| Production data | PostgreSQL target; SQLite remains for local development | Confirm and configure during release hardening |

New browser libraries should be added only when their milestone begins and should be pinned, documented, and covered by a basic smoke test.

## Milestones

### Milestone 0 — Repository analysis and planning

Status: Complete

- Map the models, validation rules, service APIs, dependencies, routes, and test baseline.
- Run Django's system check and a deterministic recommendation smoke test.
- Create `PLAN.md`, `CURRENT_TASKS.md`, and `LESSONS_LEARNED.md`.
- Record constraints and discoveries that should guide implementation.

Exit criteria: the three planning files exist, agree on the next milestone, and no frontend implementation has started.

### Milestone 1 — Frontend foundation and service contracts

Status: Next

- Normalize frontend-facing text encoding and identify any configuration values that must move to environment variables.
- Write focused contract tests for the recommendation pipeline and high-risk model validation before wiring UI actions to it.
- Create the `frontend` Django app and connect it through `INSTALLED_APPS` and the root URL configuration.
- Establish named routes, namespaced templates, static assets, and the planned directory structure.
- Add login/logout flows and enforce model permissions on every read/write route.
- Build the base layout, navigation, breadcrumbs, messages, page header, form field, table, badge, confirmation, loading, empty, and error components.
- Define design tokens, responsive behavior, keyboard focus styles, and accessible color contrast.
- Add a small authenticated landing page and smoke tests proving routing, permissions, templates, and static files work.
- Establish query-count and response-time baselines for later comparison.

Exit criteria: an authenticated user can open the responsive app shell; unauthorized users are handled correctly; shared components render; the service contract tests and Django checks pass.

### Milestone 2 — Employee and skill management

- Build employee list, detail, create, update, and delete flows.
- Add search, status/department filters, sorting, and pagination.
- Show capacity, current workload, upcoming leave, active assignments, and skill profile on employee detail pages.
- Build skill list and CRUD flows, grouped or filtered by category.
- Manage employee skills from the employee workflow with proficiency and experience validation.
- Show cascade impact before employee or skill deletion and use POST-only confirmed deletes.
- Add permission, validation, empty-state, and query-efficiency tests.

Exit criteria: authorized users can safely maintain employees, skills, and employee proficiency data; viewers can inspect them; invalid or destructive actions have clear feedback.

### Milestone 3 — Project and operational data management

- Build project list, detail, create, update, and delete flows with status, priority, criticality, and date filters.
- Manage project skill requirements inline, including level, priority, mandatory flag, quantity, and effort hours.
- Show project estimate versus mandatory skill-effort total and flag incomplete planning inputs.
- Build assignment CRUD with employee eligibility hints, allocation, date, role, and status fields.
- Manage the skill requirements covered by each assignment.
- Build leave and attendance lists and CRUD flows with employee/date/status filters.
- Preserve all `clean()` validation errors in the correct form fields and wrap compound saves in transactions.
- Test overlap, capacity, leave, qualification, quantity, and cascade behavior through the HTTP layer.

Exit criteria: the main domain records can be maintained without Django admin and every backend validation failure is understandable in the interface.

### Milestone 4 — Workforce dashboard and employee insights

- Define a consistent date-range control and preserve it across dashboard links.
- Show workforce KPIs: headcount by status, available capacity, allocated capacity, employees on approved leave, active projects, and over-capacity risks.
- Add department, employee status, project status, and date filters.
- Visualize capacity and utilization distributions with accessible tabular equivalents.
- Build employee workload and availability timelines using the existing services.
- Add attendance summaries and trends while clearly separating them from staffing scores.
- Link every aggregate to the filtered records that explain it.
- Optimize queries and test boundary dates, empty datasets, and permission scopes.

Exit criteria: managers can move from a high-level capacity signal to the employees, assignments, or leave records that caused it.

### Milestone 5 — Project planning workspace

- Build a project planning page combining dates, estimates, requirements, current assignments, remaining gaps, and candidate context.
- Add preflight checks for missing mandatory effort, insufficient eligible headcount, insufficient qualified capacity, invalid dates, and stale planning inputs.
- Show ranked eligible employees using `rank_employees_for_project()` and expose the skill, workload, leave, experience, and final score components.
- Explain why an employee is absent from the candidate list without inventing a new score.
- Show per-requirement qualified employees and coverage quantity.
- Provide direct links to repair incomplete requirements, skills, leave, or assignments.
- Test the workspace against feasible, infeasible, incomplete, and empty projects.

Exit criteria: a planner can understand whether a project is ready for optimization and can fix blockers from the same workflow.

### Milestone 6 — Team recommendation experience

- Add an explicit recommendation-generation action with CSRF protection, permission checks, duplicate-submit protection, and visible progress.
- Introduce a thin orchestration and presentation boundary around the existing service pipeline.
- Display up to three strategy cards: compact match, balanced alternative, and capacity alternative.
- Show team members, team score, available and allocated hours, remaining capacity, maximum utilization, utilization spread, and team size.
- Show the allocation matrix by employee and required skill, plus mandatory coverage results.
- Present deterministic strengths and trade-offs and comparisons between adjacent alternatives.
- Add optional Gemini summaries with timeout/error fallback and no change to selection or metrics.
- Handle no requirements, invalid effort, no eligible employees, no feasible team, one/two recommendations, and stale/deleted records.
- Benchmark realistic workforce sizes. Add result caching, bounded candidate generation, or a background job only when measurement shows it is necessary.
- Keep assignment creation as a separate confirmation workflow and revalidate against current data immediately before saving.

Exit criteria: a manager can compare feasible strategies, inspect their evidence, recover from failure states, and continue to a separately validated staffing action.

### Milestone 7 — Shared calendar and planning visualizations

- Build a consolidated calendar for projects, assignments, and approved leave.
- Add source, department, employee, project, and date filters with a clear legend.
- Provide month, week, and list views; the list view is the accessible fallback.
- Add project timelines and workload/capacity charts where they answer a specific planning question.
- Ensure event endpoints reveal only records the signed-in user may view.
- Test date boundaries, overlapping events, time zones, large result sets, and keyboard navigation.

Exit criteria: planners can see schedule conflicts and capacity changes over time without losing the underlying record detail.

### Milestone 8 — Quality, performance, security, and release readiness

- Complete CRUD, permission, service integration, accessibility, and critical browser-flow tests.
- Profile ORM queries and optimization calls; remove N+1 queries and set explicit performance budgets.
- Add structured error handling and logging without exposing employee data or provider credentials.
- Move secret key, debug mode, database configuration, allowed hosts, and Gemini credentials to environment-based configuration.
- Confirm the production database, static-file strategy, backup approach, HTTPS/session settings, and deployment process.
- Review data retention, audit needs, role definitions, and privacy expectations for HR data.
- Run Django deployment checks and a representative end-to-end acceptance pass.
- Update user-facing documentation and these planning files with final operational knowledge.

Exit criteria: the application meets the agreed security, accessibility, performance, and acceptance criteria in a production-like environment.

## Cross-cutting acceptance criteria

Every milestone should satisfy the following where applicable:

- Authorization is tested for anonymous, read-only, and write-capable users.
- Mutations use POST, CSRF protection, server-side validation, and transactional saves where multiple records change.
- Pages have useful empty, loading, success, validation, permission, and server-error states.
- Lists remain usable with realistic data through filtering and pagination.
- Dates, percentages, decimal hours, and statuses have consistent formatting.
- Query counts and expensive service timings are measured for the paths changed.
- UI text does not promise more than the backend calculates.
- `CURRENT_TASKS.md` is updated after each task, and new discoveries are added to `LESSONS_LEARNED.md` when they can prevent repeated work.

## Decisions to confirm before production

- Final role names and which records managers may view or edit.
- Business timezone, public holidays, part-time schedules, and whether weekends can be working days.
- Whether recommendations must be persisted for audit/history or can be recalculated on demand.
- Whether accepting a recommendation should create assignments automatically or only prefill a reviewed form.
- Expected employee count, project size, acceptable recommendation latency, and concurrent planner usage.
- Production database, hosting, static-asset policy, and Gemini data/privacy policy.
