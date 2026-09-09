# Lessons Learned

Last updated: 2026-09-08

## How to use this file

Record a lesson when it can prevent a repeated mistake, preserve an important business constraint, or make later development faster. Keep entries concrete: observation, consequence, and the action future work should take. Task completion history belongs in `CURRENT_TASKS.md` or Git, not here.

Review this file before starting a task and update it immediately after discovering a durable lesson.

## Repository and workflow

### Start new work from a known Git state

- **Observation:** The planning request arrived with `Prompt.md` as the only untracked file. It was committed locally as `ef00025` before analysis began.
- **Action:** Run `git status --short --branch` before each milestone. Preserve existing work and keep task changes reviewable.

### Use Windows-safe `rg` paths

- **Mistake discovered:** Passing `core\services\*.py` directly to `rg` failed on Windows because that path glob was not expanded.
- **Action:** Search the directory (`rg PATTERN core\services`) or use `rg -g "*.py" PATTERN core\services`.

### Keep the frontend inside the Django monolith and namespace its routes

- **Observation:** M1.3 established `frontend` as a server-rendered Django app with package-based views, app-namespaced templates/static paths, and the `frontend:` URL namespace. The authenticated landing view currently redirects anonymous users to Django's default `/accounts/login/`, whose route is intentionally deferred to M1.4.
- **Consequence:** Later views can grow within the existing Django process without introducing a second frontend application, while route and asset names remain isolated from `core` and admin.
- **Action:** Reverse frontend routes through the `frontend:` namespace, keep presentation code in this app, and add the actual login/logout routes before following anonymous redirects in browser flows.

### Keep canonical role synchronization explicit and exact

- **Observation:** The initial HR administrator, manager/planner, and viewer groups are code-defined, but final membership and record-level scope are not yet production-approved.
- **Consequence:** Automatically rewriting groups during application startup or every migration could silently override an operator's temporary permissions before the policy is final.
- **Action:** Run `python manage.py sync_frontend_roles` explicitly after migrations. The command is idempotent and resets each canonical group's `core` permissions to `ROLE_PERMISSION_MAP`; change the map in code instead of adding undocumented permissions directly to these groups.

### Django's baseline check passes, but coverage is absent

- **Observation:** `python manage.py check` reports no issues. No meaningful automated tests currently protect the models or services.
- **Consequence:** A green system check is not evidence that staffing rules still behave correctly.
- **Action:** Add focused domain/service contract tests before connecting mutations and recommendations to user-facing views.

### The generated dataset is useful as a stable smoke fixture

- **Observation:** The local database contains 10 employees, 8 skills, 40 employee skills, 3 projects, 9 requirements, 7 assignments, 10 assignment-skill links, 3 leave records, and 210 attendance records. The generator supports deterministic development data.
- **Action:** Use a fixed generator seed for repeatable demonstrations and performance checks. Never run its reset option against data that has not been positively identified as disposable.

## Domain and validation

### Keep domain calculations out of the UI

- **Observation:** `core/services/` already owns workload, leave availability, effective hours, attendance summaries, matching, optimization, metrics, Pareto filtering, recommendation selection, comparisons, and explanations.
- **Consequence:** Recomputing a score in JavaScript or a template would create conflicting answers.
- **Action:** Call the service layer and convert its result to a presentation object. Browser code may format or visualize a value but must not derive staffing decisions.

### Model validation is essential and `save()` does not invoke it automatically

- **Observation:** Important rules live in `clean()` methods on Project, Leave, Attendance, Assignment, and AssignmentSkill. Normal Django model `save()` calls do not automatically run `full_clean()`.
- **Action:** Use `ModelForm`/formset validation for UI writes. For programmatic writes, call `full_clean()` explicitly and use `transaction.atomic()` when related records are saved together.

### Bound ModelForms can mutate their in-memory instance before save

- **Observation:** During `_post_clean()`, Django copies valid submitted fields onto a bound `ModelForm` instance before the form is known to be fully valid. An invalid update therefore leaves the database unchanged but can alter the request-local model object.
- **Consequence:** Breadcrumbs, audit comparisons, or error-page labels built from that object after validation may accidentally show attempted values as though they were stored values.
- **Action:** Capture any stable pre-edit labels before binding or validating the form, and re-fetch from the database when verifying persistence after an invalid or failed save. Treat `form.instance` as submitted state, not proof of a committed change.

### Translate model validation wording at the form boundary

- **Observation:** A model can correctly attach a validation error to the right field while its backend-oriented message still names Python fields, which is less natural in a manager-facing form.
- **Consequence:** Reimplementing the rule in the view or JavaScript risks drifting from the model, while exposing the raw message weakens otherwise clear form feedback.
- **Action:** Keep `ModelForm` model validation as the source of truth and replace only the field-level presentation message through the form's error-message mapping. Verify that the original invalid value is still rejected, the error remains attached to the expected field, and stored data is unchanged.

### Keep server-owned parent fields in scoped relationship-form validation

- **Observation:** `EmployeeSkill` uniqueness depends on both `employee` and `skill`. Excluding the route-owned employee field entirely from a `ModelForm` can also exclude it from model-level multi-field uniqueness validation.
- **Consequence:** A relationship form may miss a friendly duplicate error before the database constraint rejects the write, even though the view already knows the parent record.
- **Action:** Bind the parent on the form instance, keep its model field in the form as a disabled hidden value, and never trust submitted parent identifiers. For unbound create forms, omit already-related choices from the picker; for bound submissions, retain the model-valid choice set so stale or forged duplicates are handled by the existing model constraint rather than a parallel validation rule.

### Guard relationship-dependent model validation after a scoped choice fails

- **Observation:** A scoped `ModelChoiceField` correctly rejects a forged foreign key outside its queryset and omits that value from `cleaned_data`, but Django still runs `Model.clean()` during the `ModelForm` post-clean phase. If the model method unconditionally dereferences the rejected relationship, the invalid request can raise `RelatedObjectDoesNotExist` instead of returning the field error.
- **Consequence:** A valid server-side choice restriction can turn malicious or stale input into a 500 response even though no database mutation occurs.
- **Action:** Prefer model `clean()` methods that tolerate absent relationship IDs when core behavior can be changed. When preserving an existing model contract, let the scoped form retain the field error and skip relationship-dependent model post-clean only for that already-invalid relationship; continue normal model and constraint validation for every accepted choice.

### Assignment errors need field-level presentation

- **Observation:** Assignment validation rejects invalid dates, employees who cover none of the project's skill requirements, duplicate overlapping assignment periods for the same employee/project, total allocation above 100%, and overlap with approved leave.
- **Action:** Preserve Django's field-specific errors in the form. Do not flatten them into a generic banner.

### Assignment skill coverage has its own constraints

- **Observation:** An AssignmentSkill must refer to a requirement from the same project, the employee must possess the skill at the required level, and active/planned coverage cannot exceed `required_quantity`.
- **Action:** Filter form choices to valid requirements for the assignment, then retain server-side validation for race conditions and stale pages.

### Deletion can remove a large related graph

- **Observation:** Core relationships use cascading deletes. Deleting an employee, skill, or project may remove proficiency, requirement, assignment, coverage, leave, or attendance records.
- **Action:** Resolve and display affected record counts before a confirmed POST delete. Restrict deletes with Django permissions and consider archive/status workflows before production.

### Verify the deletion graph internally and describe business consequences in the UI

- **Observation:** The complete deletion graph includes indirect descendants that must be verified, but framework terms, generic record totals, and internal relationship names do not help a manager decide whether to continue. Multiple reverse joins can also multiply annotated counts unless each displayed aggregate is distinct.
- **Consequence:** Exposing raw cascade details makes a confirmation harder to understand, while ignoring indirect descendants in tests can hide real data loss.
- **Action:** Map and test every direct and indirect deletion path, including which top-level objects remain. In the confirmation UI, prefetch recognizable names where useful and show only business concepts such as employee skills, assignments, leave, attendance, employee profiles, and project requirements; keep displayed aggregate counts distinct and fixed-query.

### Mandatory effort needs a frontend preflight rule

- **Observation:** `estimated_effort_hours` is nullable, while optimization includes only mandatory requirements whose effort is greater than zero.
- **Consequence:** A mandatory skill can affect coverage yet contribute no effort variable, which can make a planning result confusing.
- **Action:** Call `get_recommendation_preflight(project)` to present its field-addressable blockers. `find_all_feasible_teams(project)` also returns before enumeration when this preflight fails, so a mixed project cannot silently ignore invalid mandatory effort.

### Show both project and requirement estimates

- **Observation:** `Project.estimated_hours` and the sum of mandatory requirement effort are stored independently. The sample projects currently keep them equal.
- **Action:** Display both totals in project planning and warn on a mismatch. Do not silently substitute one for the other.

### Current availability assumes a five-day weekday calendar

- **Observation:** Availability loops over Monday through Friday, divides weekly capacity by five, and has no holiday or individual schedule model.
- **Action:** Label results as weekday-based capacity. Do not imply holiday awareness, weekend work, or employee-specific schedules until those rules are modeled.

### Status and leave records serve different purposes

- **Observation:** Recommendations consider only employees with status `active`. Daily effective availability becomes zero for `inactive` employees or approved leave records; the `on_leave` status is not a substitute for dated leave in that calculation.
- **Action:** Keep status and leave editing distinct and explain their effects. Avoid inferring dated availability from employee status alone.

### Attendance is descriptive today

- **Observation:** Attendance services calculate summaries, absenteeism, and late rates, but attendance is not used by matching or optimization.
- **Action:** Keep attendance dashboards visually separate from recommendation evidence and never state that attendance changed a staffing score.

### Matching eligibility and score components are fixed backend behavior

- **Observation:** Active employees who meet at least one project requirement are candidates. The current final score is 55% skill fit, 20% minimum free capacity, 15% leave availability, and 10% experience.
- **Action:** Present these components directly from the returned service data. If weights or eligibility rules change, update the backend and tests first, then update explanatory copy.

## Recommendation pipeline

### Recommendation generation is already slow enough to shape the interaction

- **Observation:** On the included 10-employee dataset, one project generated 88 feasible teams, 15 Pareto teams, and 3 recommendations in about 20.4 seconds. Team enumeration grows combinatorially.
- **Consequence:** Running optimization on page load or every filter change would feel broken and consume unnecessary server capacity.
- **Action:** Require an explicit action, show progress, prevent duplicate submissions, record elapsed time, and benchmark realistic data. Consider caching, candidate bounds, or background jobs only after measuring the target scale.

### Preserve the full deterministic pipeline order

- **Observation:** The intended flow is feasible-team enumeration, Pareto filtering, strategy selection, adjacent comparison, and structured explanations.
- **Action:** Put that sequence behind one tested orchestration boundary. Do not let views call an arbitrary subset that could label an unfiltered team as a recommendation.

### Recommendation count can be smaller than three

- **Observation:** Selection returns up to three strategies based on team sizes: minimum, minimum plus one, and minimum plus two. Some Pareto sets will not contain every size.
- **Action:** Design for zero, one, two, or three cards. Never render empty placeholder recommendations or claim an absent strategy failed.

### OR-Tools results contain the evidence the UI needs

- **Observation:** Feasible team results include coverage, per-requirement allocations, employee capacities, matching components, and team metrics such as remaining hours and utilization spread.
- **Action:** Build a presenter over these returned values rather than launching more availability or solver calls while rendering the page.

### Gemini is optional wording, not decision logic

- **Observation:** The LLM receives only the selected category, label, team names, strengths, and trade-offs. It does not calculate or select teams and requires external credentials/network access.
- **Action:** Render deterministic explanations first. Use a short timeout and graceful fallback for Gemini; never delay or discard a valid recommendation because summary generation failed.

## Presentation and configuration

### Keep directory pages on fixed-cost bulk queries

- **Observation:** The employee directory renders 20 employee rows with three page-specific queries: one distinct department-facet query, one paginator count, and one limited employee query. Its total of seven includes the four-query authenticated shell and does not grow with the number of displayed employees.
- **Consequence:** Calling workload, availability, leave, assignment, or proficiency logic once per table row would introduce N+1 behavior and blur the boundary between a scannable directory and a planning-detail view.
- **Action:** Keep list selectors limited to bulk display fields, filters, deterministic ordering, facets, and pagination. Add service-backed planning context on detail pages through bulk selectors/prefetching, and retain exact query-count tests as rows and columns evolve.

### Count authenticated-shell queries separately from page data

- **Observation:** The current anonymous login page renders with zero database queries, while an authenticated viewer request to the landing shell uses four: session lookup, user lookup, direct user permissions, and group permissions.
- **Consequence:** Treating all queries on a future page as domain-data queries would hide the fixed authentication cost and make comparisons between anonymous, superuser, and role-based requests misleading.
- **Action:** Use a normal role-based user for page query tests, retain the four-query shell baseline, and measure each selector or page's ORM work as an explicit increment. Record whether timing samples are warm or cold and whether they include network and static-file transfer.

### Preserve Django's generated field-description identifiers

- **Observation:** Django 6 adds `aria-describedby` references such as `<field-id>_helptext` and `<field-id>_error` when a bound field has help text or validation errors. A custom field include can accidentally render the message under a different identifier while the control still points to Django's expected one.
- **Consequence:** The error remains visible but is no longer reliably announced with the field by assistive technology.
- **Action:** Render controls through `BoundField.as_widget()` and keep the exact generated help/error identifier convention in shared templates. Test the label `for`, control `id`, `aria-invalid`, and every `aria-describedby` target together.

### Pass CSRF tokens into isolated POST-form includes

- **Observation:** Django's `{% include ... only %}` intentionally removes the parent context. A form partial can contain `{% csrf_token %}` yet render no hidden input when the include site does not explicitly pass `csrf_token`.
- **Consequence:** The default Django test client still accepts the POST, but a real browser receives a 403 because CSRF middleware rejects the missing token.
- **Action:** Pass `csrf_token=csrf_token` into every isolated include that renders an internal POST form. Add a regression test with `Client(enforce_csrf_checks=True)` that rejects a tokenless POST and submits the token extracted from each rendered form successfully.

### Forward required context through every isolated include boundary

- **Mistake discovered:** A permission-aware project row was rendered through a shared table partial, but both template boundaries used `{% include ... only %}`. Passing the row alone meant the Actions header appeared while the nested Edit and Remove links silently disappeared because `perms` never reached the row template.
- **Consequence:** Multi-level isolated includes can produce internally inconsistent interfaces even when the outer page has the correct context and permissions.
- **Action:** Treat each isolated include as an explicit interface and forward every dependency through every layer. For permission-aware table rows, pass `perms` into the table partial and then into the row include, and assert the final rendered actions for each role.

### Verify navigation state across complete route families

- **Mistake discovered:** The Projects navigation item recognized the main project, requirement, and assignment screens but omitted project deletion, assignment deletion, and assignment-coverage routes, so those valid pages lost their active navigation state.
- **Consequence:** Testing only directory and edit screens can leave deeper confirmation or relationship workflows visually disconnected from their parent area.
- **Action:** Keep navigation activation and `aria-current` conditions aligned with the complete route family. Add a route-inventory regression that opens every workflow page and verifies both its intended template and active primary navigation area.

### Read BOM-less UTF-8 explicitly in Windows PowerShell

- **Mistake discovered:** PowerShell's default `Get-Content` decoding made valid UTF-8 characters such as `–` and `é` appear as mojibake during the initial audit. Reading with `Get-Content -Encoding utf8` and searching for the actual corrupted byte sequences confirmed that the source text was already valid.
- **Consequence:** Treating terminal display artifacts as source corruption could replace correct user-facing text or create noisy rewrites.
- **Action:** Keep the repository's `.editorconfig` UTF-8 rule, use explicit UTF-8 decoding when inspecting text on Windows, and retain regression assertions for model labels, help text, and deterministic explanations.

### Current settings are development-only

- **Observation:** The secret key is committed, debug mode is enabled, allowed hosts are empty, SQLite is configured, and the project timezone is UTC. The email setting is named `MAILERS`, which Django does not use as the standard email backend setting.
- **Action:** Keep local setup simple during UI work, but resolve environment configuration, timezone policy, standard email configuration, production database, and deployment checks before release.

### Prefer server-rendered integration for this repository

- **Observation:** The backend is Django-native, there is no REST API, and the workflows rely heavily on model validation and server-side services.
- **Action:** Start with Django templates, forms, sessions, and small progressive enhancements. Introduce an API or SPA only when a concrete workflow requires it.
