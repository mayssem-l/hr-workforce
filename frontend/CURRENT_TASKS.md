# Current Tasks

Last updated: 2026-09-10

## Active milestone

**Milestone 7 — Shared calendar and planning visualizations**

Status: In progress. Milestones 0 through 6 are complete, Milestone 6 is closed with all nine exit criteria satisfied, and Tasks M7.1–M7.6 are complete. Task M7.7 is the current focus and remains not started pending explicit approval.

Goal: let planners inspect projects, assignments, approved leave, project timelines, and service-backed workload/capacity evidence across shared calendar views without losing accessible record detail or exposing data outside existing permissions.

Implementation constraints: keep the interface server-rendered inside the Django monolith and preserve all validated Milestone 1–6 routes, workflows, calculations, permissions, CSRF behavior, validation, transactions, navigation, return context, visual identity, and manager-friendly English wording; build calendar reads from existing Project, Assignment, Employee, and Leave records through selectors and presenters; reuse the existing workload, leave, and effective-availability services for calculated evidence; never reproduce schedule, overlap, workload, capacity, leave, matching, feasibility, optimization, recommendation, or attendance calculations in templates or JavaScript; keep attendance descriptive and outside planning decisions; use the configured Django timezone and retain the current Monday-to-Friday/no-holiday capacity assumption unless an approved task changes it; make the server-rendered list view the accessible fallback and keep charts supplemental to readable values or tables; expose event records only through explicitly tested model-permission boundaries; pin any approved FullCalendar or Chart.js assets when their task begins; and measure realistic date ranges and event volumes before adding bounds, caching, or background infrastructure.

## Current focus

Task M7.7 — Workload and capacity visualizations. Not started; awaiting explicit approval.

## Milestone 7 task breakdown

### M7.1 Shared calendar workspace foundation

- [x] Add one namespaced, GET-only shared-calendar route and connect it to the authenticated application navigation while preserving the current shell, active-state behavior, and responsive visual identity.
- [x] Define the explicit read-permission contract for project, assignment, employee, and approved-leave calendar context, including truthful restricted-source behavior that never reveals an unauthorized record.
- [x] Add one server-validated calendar view-state form for the configured date context and the planned month, week, and list modes, with deterministic defaults, inclusive dates, safe stale/invalid parameters, and an obvious reset path.
- [x] Render a read-only calendar workspace foundation with manager-friendly scope, timezone, weekday-capacity, and accessible-list-fallback guidance; do not load events, charts, FullCalendar, or Chart.js yet.
- [x] Test routing, methods, authentication, canonical roles, missing permissions, navigation, valid/invalid/default view state, empty foundation rendering, query count, and proof that no calendar-event query or planning calculation runs yet.

Scope boundary: M7.1 establishes the shared route, access contract, view-state contract, and page structure only. It does not add event data, filters beyond the foundational date/view state, interactive calendar assets, timelines, charts, calculations, or writes.

Completion evidence:

- Created files: `frontend/calendar_access.py`, `frontend/forms/calendar.py`, `frontend/presenters/calendar.py`, `frontend/templates/frontend/calendar/workspace.html`, `frontend/tests/test_calendar_foundation.py`, and `frontend/views/calendar.py`.
- Modified files: `frontend/CURRENT_TASKS.md`, `frontend/templates/frontend/components/navigation.html`, and `frontend/urls.py`. No model, migration, core service, selector, recommendation, assignment, validation, transaction, CSS, JavaScript, or Milestone 1–6 workflow changed.
- Route and navigation result: authenticated users with project, assignment, and employee read permissions can open the namespaced GET-only `/calendar/` workspace from the existing responsive navigation, where Calendar receives the active state. Anonymous users redirect to sign-in; users missing any required base permission receive 403; all three canonical roles render successfully.
- Permission result: the reusable source-access contract requires project context for project schedules, project/assignment/employee context for assignments, and employee/leave context for approved leave. Leave access remains optional at the workspace boundary: when it is absent, the page reports that source as restricted without querying or revealing employee, project, assignment, or leave records or counts.
- View-state result: one server-bound GET form reuses the existing inclusive reporting-period validation, defaults omitted dates to the configured current calendar month and omitted mode to Month, accepts Month/Week/List, preserves exact same-day boundaries, rejects malformed/reversed/over-366-day ranges and stale modes with field errors, and provides a canonical `/calendar/` reset.
- Presentation and boundary result: the read-only page reuses the established shell and components to show the validated period, selected mode, configured timezone, source-access states, Monday-to-Friday/no-holiday capacity assumption, and planned accessible-list fallback. It intentionally returns an empty foundation with no event selector/endpoint, ORM event read, chart, FullCalendar/Chart.js asset, planning calculation, write, or frontend-derived value.
- Query and response baseline: the calendar foundation uses 4 fixed authenticated-shell queries and zero `core_*` table queries. Across 25 warm Django test-client GETs in the final complete-suite run it recorded a 5.355 ms median and 6.575 ms p95.
- Test result: all 13 focused M7.1 tests pass; 39 relevant shell/dashboard/planning/Milestone 6 regression tests pass; and the final complete project suite passes all 545 tests in 40.245 s. An earlier complete-suite attempt observed the existing threaded duplicate-submission timing test return two safe 409 responses instead of one 200 and one 409; that test passed immediately in isolation and the clean complete-suite rerun passed without an application change.
- Check result: `python manage.py check`, migration drift, compilation, strict UTF-8/trailing-whitespace checks for the M7.1 files, and `git diff --check` pass. `frontend/LESSONS_LEARNED.md` was not changed because M7.1 introduced no genuinely new reusable lesson. M7.2 remains unstarted pending explicit approval.

### M7.2 Consolidated calendar event selector and permission-safe endpoint

- [x] Build one optimized selector that returns a stable calendar-event contract for projects, assignments, and approved leave overlapping the validated inclusive range, preserving stored dates, statuses, ownership, and source identity.
- [x] Add a namespaced, GET-only event endpoint that serves only the selector's current records and validates its date window and request parameters without exposing model internals or unrelated records.
- [x] Apply source-specific model-permission checks before selection and serialization so restricted project, assignment, employee, or leave data is omitted or denied according to the M7.1 access contract.
- [x] Include canonical, permission-aware links from returned events to the existing project, assignment, employee, or leave workflows without inventing an edit path or accepting an arbitrary return destination.
- [x] Test exact model-to-event parity, inclusive boundaries, multi-day overlap, statuses, empty sources, stale/deleted records, permission combinations, deterministic order, fixed query behavior, and safe endpoint output.

Scope boundary: M7.2 adds the authoritative read-only event data boundary. It does not add the complete filter set, render month/week calendar widgets, calculate conflicts or capacity, or introduce a write API.

Completion evidence:

- Created files: `frontend/selectors/calendar.py` and `frontend/tests/test_calendar_events.py`.
- Modified files: `frontend/CURRENT_TASKS.md`, `frontend/LESSONS_LEARNED.md`, `frontend/calendar_access.py`, `frontend/forms/calendar.py`, `frontend/presenters/calendar.py`, `frontend/urls.py`, and `frontend/views/calendar.py`. The M7.1 template, navigation, view-state behavior, styling, and empty foundation remain unchanged; no model, migration, core service, recommendation/handoff path, JavaScript, calculation, or write behavior changed.
- Selector result: `get_calendar_events()` returns one immutable `CalendarEventRecord` contract for current Project, Assignment, and approved Leave records whose stored dates overlap the validated inclusive period. It preserves stable source-qualified identity, stored start/end dates and status, project/employee ownership context, leave type, and display labels; related employee/project data is joined in the assignment and leave queries; and the merged result is ordered deterministically by start date, end date, source, title, and record ID.
- Endpoint result: the namespaced GET-only `/calendar/events/` route reuses the M7.1 base permission and reporting-period rules, requires exactly one `start_date` and `end_date`, rejects missing, malformed, reversed, over-366-day, repeated, or currently unsupported parameters with a safe HTTP 400 JSON state, and returns a minimal stable envelope with the inclusive range, configured timezone, source-access states, count, and permitted events. POST returns 405, anonymous access redirects to sign-in, and missing base permissions return 403 before selection.
- Permission and link result: project, assignment, and employee read permissions remain required; approved leave is queried only with both employee and leave read access and is rechecked before serialization. Project-detail, employee-detail, and filtered approved-leave-directory links are included only when the user satisfies the established destination route's permissions. No edit URL, client-supplied return destination, arbitrary redirect, description, effort, capacity, allocation, role, attendance, or unrelated model field is exposed.
- Boundary result: the M7.1 workspace still performs no event query and renders no records. Templates and JavaScript do not call the endpoint or contain overlap, permission, date, planning, capacity, matching, feasibility, optimization, recommendation, or attendance calculations. The endpoint view calls the shared selector once and performs no direct ORM query.
- Query and response baseline: the selector uses 3 fixed data queries with all sources. The authenticated endpoint uses 7 fixed queries (4 shell/permission plus 3 source queries), or 6 when leave is restricted because no `core_leave` query runs. Across 25 warm all-source GETs returning 4 events in the complete-suite run, the endpoint recorded a 4.357 ms median, 4.854 ms p95, and 2,166-byte response.
- Test result: all 13 focused M7.2 tests pass; the combined M7.1 foundation and focused regression set passes all 52 tests; and the complete project suite passes all 558 tests in 41.369 s. Coverage includes exact source/model parity, both inclusive project boundaries, multi-day records, raw and display statuses, only approved leave, ownership context, deterministic repetition/order, empty and deleted records, strict parameters, all canonical roles, every missing base permission, leave omission before query and serialization, link permissions, fixed queries, minimal payload fields, and source boundaries.
- Check result: `python manage.py check`, migration drift, compilation, strict UTF-8/trailing-whitespace checks for M7.2 files, and `git diff --check` pass. The multi-source query-and-serialization permission defense was recorded in `frontend/LESSONS_LEARNED.md`. M7.3 remains unstarted pending explicit approval.

### M7.3 Calendar filters and source legend

- [x] Add server-validated source, department, employee, project, and date filters using current permitted records and allow-listed values, with deterministic choices and safe handling of stale or forged parameters.
- [x] Apply one shared normalized filter context to the calendar page, event endpoint, and future list/month/week links so changing views never changes the meaning of the selected evidence.
- [x] Add a clear text-and-color legend for project, assignment, and approved-leave sources, including restricted and empty-source states that remain understandable without color.
- [x] Preserve filters in canonical calendar URLs, reset links, event evidence links, pagination/view controls where applicable, and returns from existing record workflows only where their established return contract permits it.
- [x] Test every filter alone and in combination, special characters, stale/deleted choices, unauthorized IDs, source toggles, URL serialization, legend parity, deterministic results, and query-count stability.

Scope boundary: M7.3 filters and explains the existing M7.2 event contract. It does not add browser-side filtering, interactive month/week rendering, timelines, workload/capacity charts, or new domain rules.

Completion evidence:

- Created file: `frontend/tests/test_calendar_filters.py`.
- Modified files: `frontend/CURRENT_TASKS.md`, `frontend/LESSONS_LEARNED.md`, `frontend/forms/calendar.py`, `frontend/presenters/calendar.py`, `frontend/selectors/calendar.py`, `frontend/static/frontend/css/theme.css`, `frontend/templates/frontend/calendar/workspace.html`, `frontend/tests/test_calendar_events.py`, `frontend/tests/test_calendar_foundation.py`, and `frontend/views/calendar.py`. No model, migration, core service, permission mapping, record write, recommendation/handoff workflow, or JavaScript changed.
- Filter result: the shared GET form extends the validated inclusive M7.1 date and Month/Week/List state with allow-listed project, assignment, and approved-leave source choices plus deterministic current department, employee, and project choices. Initial requests select every permitted source; a submission marker distinguishes that default from an explicitly empty source selection. Stale, deleted, forged, unknown, and permission-restricted choices fail closed with manager-readable English errors before event selection.
- Selection result: the existing M7.2 selector remains the single event-record boundary and now accepts the normalized filter contract. People filters constrain assignment and approved-leave records, project filters constrain project and assignment records, and combined filters require every applicable context. Unselected and restricted sources are skipped before their event query, approved leave remains approved-only, the inclusive overlap rules and immutable event fields are unchanged, and merged results retain the established deterministic order.
- Context and navigation result: one presenter-owned canonical query string carries the exact dates, view, ordered sources, department, employee, project, and submission state across the workspace, `/calendar/events/`, and future list/month/week controls. Employee and approved-leave evidence links retain the selected inclusive date range through their established filters; the calendar reset remains the canonical `/calendar/` route; project evidence links keep their established canonical form; and no unsupported arbitrary return destination was introduced.
- Legend and accessibility result: project, assignment, and approved-leave cards now pair distinct source markers with explicit Included/matching, Included/empty, Not included, or Restricted text. The source checkbox group has a semantic fieldset, legend, labels, help/error associations, visible keyboard focus, and color-independent validation feedback. The page continues to state the configured timezone and Monday-to-Friday/no-public-holiday assumption and intentionally leaves event-list rendering to M7.4.
- Boundary result: templates and JavaScript contain no filtering, overlap, permission, workload, capacity, feasibility, optimization, recommendation, or attendance calculation. The workspace and endpoint both call the shared selector with the same normalized context; no FullCalendar, Chart.js, browser-side filtering, timeline, chart, conflict rule, or write was added.
- Query and response baseline: with three employees, two projects, three assignments, three approved leave records, and eight matching events, the authenticated workspace and all-source endpoint each use 9 fixed queries (4 authenticated shell/permission, 2 current-choice, and 3 selected event-source queries). Across 25 warm requests in the final complete-suite run, the page recorded an 11.100 ms median / 12.320 ms p95, while the endpoint recorded a 5.833 ms median / 6.119 ms p95 and a 4,859-byte response. Selecting assignment plus approved leave uses 8 queries; assignment only uses 7, with unselected source reads absent.
- Test result: all 13 focused M7.3 tests pass; the combined M7.1–M7.3 suite passes all 39 tests; and the complete project suite passes all 571 tests in 41.910 s. Coverage includes defaults, each source and record filter, combined semantics, special characters, canonical serialization, shared page/endpoint context, evidence-link dates, every legend state, explicit empty selection, stale/deleted/forged choices, restricted/unknown sources, deterministic event parity, source-query omission, query budgets, and frontend source boundaries.
- Check result: `python manage.py check`, migration drift, compilation, strict UTF-8/trailing-whitespace checks for the M7.3 files, and `git diff --check` pass. The reusable absent-versus-explicitly-empty multi-value GET lesson was recorded in `frontend/LESSONS_LEARNED.md`. M7.4 remains unstarted pending explicit approval.

### M7.4 Accessible calendar list view

- [x] Render the filtered event contract as the primary semantic list fallback, preserving exact event values and deterministic chronological/source ordering without reconstructing date or overlap rules in the presenter or template.
- [x] Keep multi-day projects, assignments, and approved leave explicit with source, period, status, employee/project context, and permission-aware links to the existing records that explain each entry.
- [x] Provide captioned tables or structured lists, headings, status text, filtered/unfiltered empty states, restricted-source states, and pagination or another measured server-side bound for realistic event volumes.
- [x] Preserve the same filter/view context through list navigation and ensure the complete evidence remains usable with JavaScript disabled and by keyboard and screen-reader users.
- [x] Test boundary-day inclusion, overlapping entries, same-day events, deterministic pagination, large/empty results, permissions, accessible markup, no-JavaScript behavior, query budgets, and no frontend calculation.

Scope boundary: M7.4 provides the complete accessible event view over M7.2/M7.3 data only. It does not add FullCalendar, project timelines, workload/capacity charts, conflict scoring, or writes.

Completion evidence:

- Created files: `frontend/templates/frontend/calendar/_event_row.html` and `frontend/tests/test_calendar_list.py`.
- Modified files: `frontend/CURRENT_TASKS.md`, `frontend/LESSONS_LEARNED.md`, `frontend/presenters/calendar.py`, `frontend/static/frontend/css/theme.css`, `frontend/templates/frontend/calendar/workspace.html`, `frontend/tests/test_calendar_foundation.py`, and `frontend/views/calendar.py`. No form, selector, event endpoint, URL, JavaScript, model, migration, core service, permission rule, business calculation, write workflow, or recommendation/handoff behavior changed.
- Contract result: the workspace paginates the already filtered and permission-checked `CalendarEventRecord` sequence, then uses the same `build_calendar_event_payload()` presenter as `/calendar/events/` for every displayed row. The server-rendered list therefore retains the endpoint's exact event identity, source, stored dates, status, employee/project/leave context, permission-aware evidence links, and deterministic selector order without reproducing filtering, overlap, or domain rules.
- Accessible-list result: every valid Month, Week, and List selection now includes the same complete chronological evidence table beneath the existing filter context and source legend. A caption, seven scoped column headings, semantic `<time datetime>` values, visible status text, text-plus-color source labels, explicit not-applicable values, and keyboard-reachable record links keep multi-day, same-day, project, assignment, and approved-leave evidence readable without JavaScript.
- Pagination and state result: server-side pagination limits rendering to 25 rows per page, provides deterministic invalid/out-of-range behavior through Django's paginator, and preserves the full M7.3 GET context in page links. Filter submissions return to page one. Empty valid periods and empty narrowed results receive distinct manager-friendly states, invalid filters render no evidence table, and permission-restricted sources remain truthfully identified by the existing legend with no unauthorized row or link.
- Boundary result: the list calls no new ORM selector and introduces no browser request or browser-side filtering. Templates and JavaScript contain no permission, date-overlap, project, assignment, leave, workload, capacity, matching, feasibility, optimization, recommendation, or attendance calculation. FullCalendar, timelines, charts, conflict scores, drag/edit behavior, and record writes remain outside M7.4.
- Query and response baseline: with 80 matching project/assignment/approved-leave events, the authenticated workspace stays fixed at 9 queries (4 authenticated shell/permission, 2 current filter-choice, and 3 event-source queries) while rendering 25 rows. Across 25 warm GETs in the clean complete-suite run it recorded a 22.776 ms median, 23.870 ms p95, and a 50,512-byte first-page response; query count does not grow with event volume.
- Test result: all 12 focused M7.4 tests pass; the combined M7.1–M7.4 suite passes all 51 tests; and the clean complete project suite passes all 583 tests in 42.205 s. Coverage includes exact page/endpoint parity, established ordering, boundary-day and multi-day overlap, same-day records, raw/display status and context, evidence-link permissions/date preservation, identical evidence across view modes, filtered/period/invalid empty states, leave restriction, stale deletion, deterministic pagination, canonical filter continuity, 80-event fixed-query behavior, semantic markup, and no-JavaScript/source boundaries. An initial complete-suite run observed the previously documented threaded SQLite duplicate-submission test return two safe 409 responses; it passed immediately in isolation, and the unchanged clean complete-suite rerun passed.
- Check result: `python manage.py check`, migration drift, compilation, strict UTF-8/trailing-whitespace checks for M7.4 files, and `git diff --check` pass. The reusable warning against using an empty paginated collection as a valid-state sentinel was recorded in `frontend/LESSONS_LEARNED.md`. M7.5 remains unstarted pending explicit approval.

### M7.5 Interactive month and week calendar views

- [x] Add pinned local FullCalendar assets and progressively enhance the shared workspace with month and week views that consume only the M7.2 permission-safe endpoint and M7.3 normalized filter state.
- [x] Keep the server-rendered M7.4 list view available as the explicit accessible fallback and ensure failed, blocked, or unavailable JavaScript never removes the underlying evidence.
- [x] Preserve source legend meanings, event order/data, current filters, selected period, and record links across month, week, and list mode changes without browser-side business calculations.
- [x] Provide manager-friendly loading, empty, endpoint-failure, and large-result feedback plus keyboard-reachable controls, visible focus, responsive overflow, and reduced-motion behavior.
- [x] Test pinned assets, endpoint requests, mode/filter continuity, project/assignment/leave event parity, navigation, failure fallback, keyboard structure, responsive hooks, and absence of duplicated date or planning logic in JavaScript.

Scope boundary: M7.5 adds interactive visualization of the existing event contract only. It does not add new event sources, edit events in the browser, infer conflicts, calculate workload/capacity, or change stored records.

Completion evidence:

- Created files: `frontend/static/frontend/vendor/fullcalendar-6.1.21.index.global.min.js` with `frontend/static/frontend/vendor/FULLCALENDAR-6.1.21-LICENSE.md` (pinned FullCalendar 6.1.21 standard bundle, MIT), `frontend/static/frontend/js/calendar.js`, and `frontend/tests/test_calendar_interactive.py`.
- Extended files: `frontend/presenters/calendar.py` (FullCalendar-ready `calendar` serialization per event with exclusive end date plus `view_links` mode navigation), `frontend/templates/frontend/calendar/workspace.html` (visualization section with view switcher, endpoint/period/timezone data attributes, loading/empty/failure/large-result states, noscript fallback, and conditional local asset includes), and `frontend/static/frontend/css/theme.css` (view switcher, source-colored FullCalendar event hooks, scrollable viewport, mobile stacking, focus-visible states, and reduced-motion handling). No model, migration, core service, selector contract, endpoint rule, permission mapping, record write, or Milestone 1–6 workflow changed.
- Asset result: the pinned bundle is served locally (no CDN reference anywhere), discoverable through staticfiles, and identified by version banner plus MIT license file. List mode loads neither the bundle nor the visualization script.
- Visualization result: month and week modes fetch only the M7.2 permission-safe endpoint URL built from the M7.3 normalized filter state, map each returned `event.calendar` payload onto non-editable FullCalendar entries in exact contract order with source/status ARIA labels, and keep the full M7.4 chronological list rendered beneath in every mode. Empty results, endpoint failures, missing library, and invalid filter states each keep the list evidence while reporting a manager-friendly status; results above 200 entries add an explicit crowded-view notice pointing at the list.
- Continuity result: the view switcher preserves every date, source, department, employee, project, and submission parameter across month/week/list links, resets pagination on mode change, marks the current mode with `aria-current`, and carries the selected period and timezone into the calendar configuration.
- Boundary result: the script performs no date arithmetic, overlap, permission, filtering, workload, capacity, matching, feasibility, optimization, recommendation, or attendance calculation and enables no drag, resize, select, or navigation side effect; failed or disabled JavaScript never removes server-rendered evidence.
- Query and response baseline: month/week/list workspace and endpoint states stay fixed at 9 queries (4 authenticated shell/permission, 2 current filter-choice, and 3 selected event-source queries). Across 25 warm GETs in the final complete-suite run, the interactive page recorded an 11.885 ms median / 13.840 ms p95 with a 24,679-byte response.
- Test result: all 12 focused M7.5 tests pass; the combined M7.1–M7.5 suite passes all 63 tests; and the complete project suite passes all 595 tests in 43.397 s. Coverage includes month/week asset loading with list fallback, exact endpoint URL and normalized state, filter-preserving view links with pagination reset, per-source FullCalendar parity with exclusive end dates, restricted-source omission, loading/failure/empty/no-script markup, invalid-state asset exclusion, fixed page/endpoint queries, warm timing, pinned-asset identity, JS/template source boundaries, and theme focus/responsive/reduced-motion hooks.
- Check result: `python manage.py check`, migration drift, compilation, strict UTF-8/trailing-whitespace checks for the M7.5 files, and `git diff --check` pass. M7.6 remains unstarted pending explicit approval.

- Defect correction (post-approval browser finding, no scope change): the visual calendar rendered blank with only compressed slivers on the left edge despite `Interactive calendar ready with N entries`. Root cause was render order in `frontend/static/frontend/js/calendar.js`: `calendar.render()` ran while `[data-calendar-viewport]` still carried the `hidden` attribute, so FullCalendar measured a zero-width container (its styles ship inside the pinned bundle and were verified present; no application CSS overrides its layout). The fix unhides the viewport immediately before `render()` and re-hides it only if rendering throws, preserving the identical failure UI. A source-order regression assertion was added to `test_calendar_interactive.py`. Full 608-test suite, Django checks, and all baselines remain green. Tell-tale confirmation in the browser: resizing the window before the fix snapped the grid into place via FullCalendar's resize handling.

### M7.6 Project timelines

- [x] Add a project-focused timeline using the shared event selector for the project's stored period, its assignments, and relevant permitted approved-leave context, preserving the existing project and planning navigation.
- [x] Reuse M7.3 filter/date context and M7.4 readable evidence structures so the timeline supplements rather than replaces exact project, assignment, employee, and leave records.
- [x] Show overlapping schedules and source/status distinctions truthfully without creating a conflict score, changing assignment rules, or treating current coverage as future feasibility.
- [x] Link timeline evidence to the existing project planning, assignment, coverage, employee, and leave workflows with canonical return context and permission-aware actions.
- [x] Test project/date scoping, overlaps, boundary dates, empty and restricted evidence, stale/deleted records, navigation, list parity, accessibility, deterministic ordering, and fixed query behavior.

Scope boundary: M7.6 adds read-only project schedule visualization from the shared event contract. It does not alter planning readiness, matching, recommendation results, staffing confirmation, or domain validation.

Completion evidence:

- Created files: `frontend/presenters/timeline.py`, `frontend/views/timeline.py`, `frontend/templates/frontend/projects/timeline.html`, and `frontend/tests/test_project_timeline.py`.
- Modified files: `frontend/selectors/calendar.py` (employee filter additionally accepts an internal employee-ID set; single-string behavior unchanged), `frontend/urls.py` (`projects/<project_id>/timeline/` as `project_timeline`), `frontend/templates/frontend/components/navigation.html` (Projects stays active on the timeline route), `frontend/templates/frontend/projects/detail.html` and `frontend/templates/frontend/planning/workspace.html` (permission-gated `View project timeline` entry links), `frontend/static/frontend/css/theme.css` (timeline bands, scrollable viewport, mobile stacking), `frontend/CURRENT_TASKS.md`, and `frontend/LESSONS_LEARNED.md`. No model, migration, core service, selector contract change, endpoint rule, permission mapping, record write, JavaScript, or Milestone 1–6 workflow changed.
- Timeline result: the GET-only view loads the stored project (404 when missing), then reuses `get_calendar_events()` twice over the exact stored period — once project-scoped for the project band plus assignments, once for approved leave of exactly the assigned employees — merging both calls in the established deterministic selector order. Leave is skipped before its query without leave access and reported as restricted. Bands position each entry inside the stored period with clamped percentages, continuation markers for overhang, and source colors plus text; the band chart is hidden from assistive technology while the identical complete table carries the evidence.
- Parity and link result: table rows reuse `build_calendar_event_payload()` plus one permission-aware `View coverage` link per assignment row (gated on the same four view permissions as the coverage route), so rows match the endpoint contract exactly; header links return to the same planning workspace and project profile, and entry links were added from project detail and the planning workspace without changing their return contracts.
- Boundary result: only routed-project records render; other-project assignments and out-of-period leave are excluded; boundary-day records are included; overlapping assignments render as overlapping bands with an explicit no-conflict statement and no score, feasibility claim, or coverage-as-feasibility wording; deleted records disappear on the next GET; templates, presenter, and view contain no workload, capacity, matching, feasibility, optimization, recommendation, attendance, or write logic.
- Query and response baseline: the timeline uses 4 fixed authenticated-shell queries plus 1 project, 2 scoped event-source, and 0–1 leave queries (8 with leave, 7 restricted), independent of assignment volume. Across 25 warm GETs with 4 entries in the final complete-suite run it recorded an 8.351 ms median / 9.704 ms p95 with a 19,139-byte response.
- Test result: all 13 focused M7.6 tests pass; the combined M7.1–M7.6 suite passes all 76 tests; and the complete project suite passes all 608 tests in 44.546 s (one first-run observation of the previously documented threaded duplicate-submission timing test returning two safe 409s; it passed in isolation and the unchanged clean rerun passed with no application change). Coverage includes routing/methods/auth/roles/permissions/navigation, scoping, overlaps, boundary/overhang bands, empty/restricted states, stale/deleted records, entry-link workflows, selector parity and order, heading/caption/time semantics, deterministic band math, fixed queries across growing volumes, warm timing, and source boundaries.
- Check result: `python manage.py check`, migration drift, compilation, strict UTF-8/trailing-whitespace checks for the M7.6 files, and `git diff --check` pass. M7.7 remains unstarted pending explicit approval.

### M7.7 Workload and capacity visualizations

- [ ] Add workload/capacity evidence only where it directly explains the selected calendar or project period, reusing the existing workload and effective-availability services with bulk-prefetched records rather than recreating formulas.
- [ ] Define one presenter-owned, deterministic display contract for employee/project capacity values, units, range assumptions, unavailable/zero states, and any chart serialization returned by the existing services.
- [ ] Render readable values or captioned tables before supplemental charts, and add pinned local Chart.js assets only for relationships that materially improve planning understanding.
- [ ] Keep attendance separate and descriptive, retain Monday-to-Friday/no-holiday wording, and avoid implying a schedule conflict, staffing score, feasibility result, or recommendation that the backend did not calculate.
- [ ] Test exact service parity, weekday/weekend and leave/assignment boundaries, zero denominators, empty/restricted datasets, chart-to-table parity, keyboard and no-JavaScript fallbacks, fixed queries, and source boundaries.

Scope boundary: M7.7 visualizes existing service-owned workload and capacity evidence. It does not introduce a new calculation, modify matching/optimization/recommendations, use attendance in planning, or write schedule data.

### M7.8 Performance, accessibility, timezone, and boundary hardening

- [ ] Profile calendar pages, event endpoints, list mode, project timelines, and workload/capacity evidence against the authenticated-shell baseline for realistic date ranges, source mixes, employee counts, and large event volumes.
- [ ] Verify inclusive boundaries, overlapping and same-day events, configured-timezone serialization, month/week transitions, deterministic filtering/pagination, stale/deleted records, and repeated warm requests.
- [ ] Add range limits, pagination adjustments, caching, or other infrastructure only when measurements establish a need and the correction preserves permission checks, canonical event parity, accessible fallback, and current service behavior.
- [ ] Verify keyboard navigation, focus visibility, headings/landmarks, form labels/errors, legends, table captions/scopes, color-independent source meaning, responsive overflow, reduced motion, and JavaScript-failure behavior.
- [ ] Run focused Milestone 4–6 regressions and source audits proving calendar work does not duplicate calculations, expose restricted records, alter CRUD/planning/recommendation/staffing workflows, or let attendance affect planning.

Scope boundary: M7.8 hardens and measures implemented Milestone 7 behavior. It introduces no new product feature or infrastructure unless a measured defect requires the smallest compatible correction.

### M7.9 Milestone 7 verification

- [ ] Verify every Milestone 7 route, endpoint, template, navigation state, filter, legend, calendar mode, list fallback, timeline, chart, authentication rule, and model-permission boundary.
- [ ] Reconcile every project, assignment, approved-leave event and every displayed workload/capacity value against current models, the shared selector contract, and existing core services for populated, boundary, stale, restricted, and empty scenarios.
- [ ] Confirm month, week, and list views preserve identical filter meaning; event endpoints never disclose unauthorized records; charts retain readable equivalents; and frontend code contains no duplicated schedule or planning calculations.
- [ ] Run the complete project suite, `python manage.py check`, migration drift, compilation, UTF-8, whitespace, source audits, and `git diff --check`; record final query/response/large-volume baselines and reusable lessons.
- [ ] Close Milestone 7 only when every exit criterion passes, leaving Milestone 8 unstarted pending explicit approval.

Scope boundary: M7.9 is verification and finalization only. It adds no new feature unless a real defect is found, and any correction must remain narrowly within Milestone 7.

## Milestone 7 exit criteria

- [ ] A permitted planner can open one consolidated calendar that accurately presents projects, assignments, and approved leave through a shared, deterministic event contract.
- [ ] Source, department, employee, project, and inclusive date filters are validated server-side, preserved across views, and paired with a clear color-independent legend.
- [ ] Month, week, and list modes present the same permitted event evidence, and the complete list fallback remains readable and usable without JavaScript.
- [ ] Calendar event endpoints enforce the approved model permissions and reveal no unauthorized project, assignment, employee, or leave record.
- [ ] Project timelines preserve exact schedule evidence and connect managers to the existing project, assignment, coverage, employee, leave, and planning workflows without inventing conflict logic.
- [ ] Workload/capacity visualizations exactly match existing service outputs, have readable equivalents, state the current calendar assumptions, and keep attendance outside planning decisions.
- [ ] Date boundaries, overlaps, configured timezone, empty/restricted/stale states, large volumes, deterministic ordering, query behavior, responsive layout, and keyboard accessibility are verified.
- [ ] The complete test suite and Django checks pass, frontend code duplicates no core calculation, all Milestone 1–6 behavior remains valid, and Milestone 8 remains unstarted until explicit approval.

## Completed Milestone 6 task breakdown

### M6.1 Explicit recommendation execution and orchestration boundary

- [x] Add one explicit recommendation-generation action from the existing project planning workspace, using a namespaced POST-only route, CSRF protection, the approved project/planning read contract, and the current recommendation-execution permission policy.
- [x] Prevent accidental or duplicate submissions, expose accessible in-progress feedback for the synchronous request, and prove that opening or refreshing an ordinary planning GET never starts enumeration, optimization, recommendation selection, explanations, or Gemini.
- [x] Introduce one thin frontend orchestration function that calls the existing pipeline exactly once and in order: `find_all_feasible_teams(project)`, `find_pareto_teams(feasible_teams)`, `select_recommended_teams(pareto_teams)`, `compare_recommendations(recommendations)`, and `build_recommendation_explanations(recommendations, comparisons)`.
- [x] Return a minimal server-rendered result foundation with project/run context, elapsed time, recommendation count, and safe success/empty/error framing while preserving the Projects navigation family and a clear return to the same planning workspace.
- [x] Test routing, methods, CSRF, permissions, duplicate-submit handling, pipeline order and arguments, single invocation, missing/deleted projects, exceptions, no mutation, navigation, and the no-work-on-GET boundary.

Scope boundary: M6.1 establishes the explicit execution lifecycle and the single deterministic orchestration boundary. It does not design full recommendation cards, render allocation matrices or comparisons, call Gemini, persist results, cache runs, start background work, or create assignments.

Completion evidence:

- Created files: `frontend/forms/recommendations.py`, `frontend/orchestration/__init__.py`, `frontend/orchestration/recommendations.py`, `frontend/presenters/recommendations.py`, `frontend/recommendation_execution.py`, `frontend/templates/frontend/recommendations/result.html`, `frontend/tests/test_recommendation_execution.py`, and `frontend/views/recommendations.py`.
- Modified files: `frontend/CURRENT_TASKS.md`, `frontend/LESSONS_LEARNED.md`, `frontend/static/frontend/js/app.js`, `frontend/templates/frontend/components/navigation.html`, `frontend/templates/frontend/planning/workspace.html`, `frontend/tests/test_project_planning_workspace.py`, `frontend/urls.py`, and `frontend/views/planning.py`. No model, migration, core service, optimization rule, permission mapping, domain validation, assignment transaction, or attendance behavior changed.
- Execution result: a readiness-approved planning workspace now issues an identity- and project-bound signed one-time request token and exposes one explicit CSRF-protected POST action. The route enforces the same six-model planning read contract for Viewers, Managers / Planners, and HR Administrators, resolves the current project, atomically claims the token in Django's configured cache, and invokes one thin orchestration function. That function calls feasible-team enumeration, Pareto filtering, selection, adjacent comparison, and deterministic explanation exactly once each and in the documented order, returning the original service values plus full-pipeline elapsed time without calculation in the view, presenter, template, or JavaScript.
- Interaction and state result: JavaScript immediately marks the form busy, announces progress through an `aria-live` status, changes and disables the submit button, and rejects another same-page submit. Server-side token claiming rejects replay with HTTP 409, including browser refresh/resubmit, while a newly opened planning workspace issues a fresh request. The result foundation preserves project dates and estimate, selected recommendation count, elapsed seconds, safe completed/empty/invalid/duplicate/failure wording, active Projects navigation, and a direct return to the same project planning workspace. It renders no strategy cards, allocations, comparisons, generated summaries, or assignment action, and explicitly confirms that staffing records were unchanged.
- Boundary and safety result: ordinary planning GETs and rejected GETs to the generation endpoint invoke no recommendation service. Invalid, wrong-project, and wrong-user tokens return HTTP 400 without pipeline work; repeated tokens return 409; pipeline exceptions return a generic logged HTTP 503 without exposing exception text; missing and deleted project targets return 404; and all tested states leave projects, requirements, assignments, assignment-skill coverage, employees, employee skills, and leave records unchanged. Source audits confirm the frontend contains no matching, availability, feasibility, solver, metric, Pareto, selection, comparison, explanation, attendance, Gemini, or OR-Tools calculation duplicate.
- Query and response baseline: the ready planning GET remains fixed at 21 queries. Seven warm Django test-client result POSTs with the expensive pipeline mocked use 5 queries each and recorded a 4.469 ms median / 5.647 ms p95 with a 9,858-byte response in the complete-suite run. The orchestration itself records the real full-pipeline elapsed time for each completed browser request; realistic enumeration/solver profiling remains explicitly assigned to M6.8.
- Test result: all seven focused M6.1 tests passed in 0.515 s after the final boundary additions, and the complete project suite passed all 422 tests in 25.357 s. Coverage includes exact pipeline order/arguments/identity/single calls, route resolution, POST-only behavior, authentication, every required permission, all canonical roles, enforced CSRF, accessible progress, duplicate and fresh-token behavior, success/empty/error states, token binding, missing/deleted projects, no mutation, navigation, query budgets, and frontend source boundaries.
- Check result: `python manage.py check`, migration-drift, compilation, strict UTF-8/trailing-whitespace checks for the M6.1 files, and `git diff --check` pass. M6.2 remains unstarted pending explicit approval.

### M6.2 Strategy cards and team-level evidence

- [x] Present zero to three strategy cards in the exact service-selected order, using the existing compact-match, balanced-alternative, and capacity-alternative categories and labels without inventing missing placeholders.
- [x] Show each returned team member and the service-owned team score, available hours, allocated hours, remaining capacity, maximum utilization, utilization spread, and team size with explicit units and project-period context.
- [x] Keep project, requirement, candidate, and employee links permission-aware and preserve the recommendation result's return path without exposing records outside the routed project and signed-in user's read scope.
- [x] Render responsive, keyboard-readable cards and a semantic summary table or equivalent evidence structure using the current planning workspace design and color-independent status wording.
- [x] Test exact presenter parity with service dictionaries, ordering, formatting, zero/one/two/three-card layouts, ties, permissions, missing related records, responsive markup, and source boundaries excluding metric recalculation.

Scope boundary: M6.2 presents selected strategy summaries and team-level service evidence only. It does not add allocation matrices, narrative comparisons, Gemini enrichment, persistence, or assignment creation.

Completion evidence:

- Created files: `frontend/templates/frontend/recommendations/_strategy_card.html` and `frontend/tests/test_recommendation_strategy_cards.py`.
- Modified files: `frontend/CURRENT_TASKS.md`, `frontend/presenters/recommendations.py`, `frontend/static/frontend/css/theme.css`, `frontend/templates/frontend/recommendations/result.html`, `frontend/tests/test_recommendation_execution.py`, and `frontend/views/recommendations.py`. `frontend/LESSONS_LEARNED.md` was not changed for M6.2 because its existing service-ownership, presenter pass-through, permission, navigation, and responsive-evidence lessons already cover the reusable findings.
- Presenter result: `build_recommendation_strategy_cards()` iterates only the selected recommendation sequence returned by M6.1 and preserves each category, label, selection reason, team member, team score, service-owned team size, total available hours, allocated hours, remaining capacity, maximum utilization, and utilization spread without deriving or adjusting any value. References to the original recommendation, team result, and metrics dictionary are retained for exact parity verification. Tied metrics remain tied and do not change service order.
- Strategy layout result: completed runs with one to three selected strategies render exactly that many cards in service order; zero results render no card, table, or invented placeholder. Each semantic article has a labelled heading, exact backend selection reason, definition-list metrics with explicit score/hour/percentage/percentage-point units, and an ordered list containing every returned team member. A captioned summary table repeats the same passed-through values with column and row scopes, and a horizontally scrollable wrapper plus one-column mobile metric layout preserves usability within the existing visual identity.
- Navigation and boundary result: project, stored-requirement, candidate-evidence, and employee-profile links are emitted only when the signed-in user has their required read permissions. Every project link uses the routed project ID; employee links include the routed project period and the canonical same-project planning return destination. Deleted or otherwise missing employee objects remain readable but unlinked. No allocation matrix, requirement allocation, coverage comparison, deterministic narrative comparison, Gemini result, recommendation persistence, assignment action, or staffing mutation is rendered or introduced.
- Calculation separation result: the result view still invokes the M6.1 orchestration function once and passes its selected recommendations to the presenter. AST and source audits confirm that the strategy presenter calls no `sum`, `len`, `round`, `min`, `max`, team-metric, or team-score calculation; templates use only existing display filters; JavaScript contains none of the team metric fields; and matching, OR-Tools, Pareto filtering, recommendation selection, comparison, and explanation services remain unchanged.
- Query and response baseline: seven warm Django test-client POSTs rendering three strategies and six total member rows, with the expensive pipeline mocked to isolate presentation overhead, remain fixed at 5 queries and recorded a 6.044 ms median / 6.307 ms p95 with an 18,790-byte response in the complete-suite run. The actual pipeline elapsed time continues to be measured by the unchanged M6.1 orchestration boundary.
- Test result: all eight focused M6.2 tests passed in 0.174 s; the combined M6.1–M6.2 run passed all 15 tests in 0.686 s; and the complete project suite passed all 430 tests in 25.553 s. Coverage includes exact dictionary/object/value parity, selected order, tied scores, zero/one/two/three results, missing placeholders, every member, decimal and zero formatting, semantic markup, permission-aware scoped links, canonical return context, deleted/missing employee references, responsive source contracts, no metric recalculation, no mutation, and fixed query/rendering overhead.
- Check result: `python manage.py check`, migration-drift, compilation, strict UTF-8/trailing-whitespace checks for all M6.2 files, and `git diff --check` pass. The interrupted run exposed one singular display defect (`1 people`) and one test-only HTML-escaping mismatch; the display now renders `1 person`, and the test now compares the escaped rendered URL without changing application navigation. M6.3 remains unstarted pending explicit approval.

### M6.3 Allocation matrix and mandatory coverage evidence

- [x] Render each recommendation's existing OR-Tools employee-by-required-skill allocation matrix without rerunning the solver or calculating allocation values in frontend code.
- [x] Show required effort, allocated effort, remaining effort, employee capacity usage, and mandatory coverage outcomes from the returned optimization result with clear hours, percentages, and stored-requirement context.
- [x] Distinguish requirement-level coverage evidence from whole-team feasibility and keep optional versus mandatory requirements, zero values, and unavailable evidence explicit.
- [x] Provide captioned, scoped, horizontally scrollable tables and readable empty/error alternatives for every allocation or coverage presentation.
- [x] Test exact matrix/value parity, employee and requirement ordering, fractional/unit boundaries, complete and incomplete coverage states, stale/deleted related records, accessibility, and proof that rendering performs no service or solver call.

Scope boundary: M6.3 exposes allocation and mandatory-coverage evidence already returned by the existing solver. It does not change feasibility, allocation, team metrics, recommendation selection, explanations, or stored assignments.

Completion evidence:

- Created files: `frontend/templates/frontend/recommendations/_allocation_evidence.html` and `frontend/tests/test_recommendation_allocation_evidence.py`.
- Modified files: `frontend/CURRENT_TASKS.md`, `frontend/LESSONS_LEARNED.md`, `frontend/presenters/recommendations.py`, `frontend/static/frontend/css/theme.css`, and `frontend/templates/frontend/recommendations/_strategy_card.html`. No model, migration, view, form, URL, JavaScript, core service, OR-Tools constraint/objective, matching rule, Pareto filter, recommendation-selection rule, validation rule, permission mapping, CSRF behavior, transaction, or assignment workflow changed.
- Presenter result: each M6.2 card now receives allocation evidence shaped solely from its original selected team result. Matrix columns preserve the first returned allocation order by requirement, rows preserve the exact `employee_capacities` order, and populated cells retain the original allocation dictionary and its exact `hours` value. Required level and required effort come directly from the returned requirement object; per-employee available hours, allocated hours, and utilization retain the original capacity dictionary and values; coverage rows retain the backend's requirement order, quantities, mandatory flag, satisfaction flag, qualified employees, and original coverage dictionary.
- Sparse and unavailable evidence result: the existing solver emits only positive allocation rows, so a missing employee/requirement pair is shown as an explicit dash labelled `No allocation row returned`, not a frontend-derived numeric zero. An explicitly returned zero remains `0.00 h`. The current backend contract does not return a separate per-requirement allocated total or remaining-effort total, so the coverage table says `Not returned separately` and explicitly refuses to infer that value. Missing, empty, unreadable, and non-feasible solver/capacity/allocation/coverage evidence render as distinct English states rather than reconstructed data.
- Interface result: every strategy card now includes a solver feasibility statement, an employee-by-mandatory-requirement allocation matrix, exact employee capacity usage, and all returned mandatory and optional coverage rows. Manager-facing copy distinguishes headcount/qualification coverage from whole-team effort feasibility, labels mandatory and optional outcomes independently, uses explicit hour/percentage units and stored-requirement context, keeps links permission-aware with the same planning return destination, and confirms that the result is advisory. Captioned tables use column and row scopes, sit inside horizontally scrollable containers, and keep cards in a full-width sequential layout so large evidence tables remain readable within the established visual identity.
- Boundary and safety result: allocation evidence is built after the unchanged M6.1 pipeline returns and does not call matching, availability, feasibility, OR-Tools, team metrics, Pareto filtering, recommendation selection, comparison, or explanation services during presentation. AST/template/JavaScript audits exclude frontend aggregation or formula calls; result rendering creates, changes, or deletes no project, requirement, employee, proficiency, assignment, or assignment-coverage record. Deleted employee or requirement references remain readable and unlinked rather than producing stale URLs.
- Query and response baseline: seven warm Django test-client POSTs rendering one strategy with two employees, two allocation columns, and three coverage rows, with the expensive pipeline mocked to isolate presentation overhead, remain fixed at 5 queries and recorded a 6.199 ms median / 6.499 ms p95 with a 24,591-byte response in the complete-suite run. The existing M6.1 orchestration continues to record real pipeline elapsed time separately.
- Test result: all eight focused M6.3 tests passed in 0.161 s; the combined M6.1–M6.3 regression passed all 23 tests in 0.785 s; and the complete project suite passed all 438 tests in 26.053 s. Coverage includes original dictionary/object/value parity, employee and requirement order, fractional values, explicit zero versus omitted sparse cells, units, complete/incomplete/optional coverage, missing/empty/non-feasible evidence, deleted related objects, scoped captions and headings, permission-aware return links, no calculation duplication, no staffing mutation, and fixed query/rendering overhead.
- Check result: `python manage.py check`, migration-drift, compilation, strict UTF-8/BOM/trailing-whitespace checks for the M6.3 implementation files, and `git diff --check` pass. The first focused test run exposed two test-expectation defects only: an explicit empty allocation list was incorrectly expected to be unavailable, and the semantic row-header count omitted the existing summary/capacity/coverage rows. Both assertions were corrected without changing application behavior. M6.4 remains unstarted pending explicit approval.
- Approved presentation refinement: the simplified M6.2 first-look cards were restored above the detailed evidence in a three-column desktop grid, with two- and one-column responsive fallbacks. The accessible high-level summary table remains directly after the cards, while each full M6.3 allocation, capacity, feasibility, and coverage block renders exactly once in a separate full-width section below. The refinement modified `frontend/templates/frontend/recommendations/result.html`, `frontend/templates/frontend/recommendations/_strategy_card.html`, `frontend/static/frontend/css/theme.css`, `frontend/tests/test_recommendation_strategy_cards.py`, and `frontend/tests/test_recommendation_allocation_evidence.py`; all 16 relevant tests, `python manage.py check`, strict text checks, and `git diff --check` passed, and result requests remained fixed at 5 queries.

### M6.4 Deterministic strengths, trade-offs, and recommendation comparison

- [x] Present the existing deterministic strengths and trade-offs for each selected recommendation as the authoritative explanation, with manager-friendly labels that preserve the service meaning.
- [x] Present existing adjacent-recommendation comparisons in selected order and make the changed team members, capacity, utilization, score, size, and trade-offs understandable without recalculating comparison values.
- [x] Keep recommendation absence distinct from failure: do not invent a comparison for the first card or a strategy that the selection service did not return.
- [x] Add semantic headings, lists/tables, status text, and responsive layouts that remain useful without color or optional generated wording.
- [x] Test exact explanation/comparison parity, deterministic repeated output, zero/one/two/three recommendation counts, equal metrics, ordering, accessibility, and source boundaries excluding frontend comparison logic.

Scope boundary: M6.4 renders only deterministic explanations and comparisons already produced by the approved pipeline. It does not call Gemini, change selected teams, alter metrics, or create staffing records.

Completion evidence:

- Created files: `frontend/templates/frontend/recommendations/_decision_evidence.html` and `frontend/tests/test_recommendation_decision_evidence.py`.
- Modified files: `core/services/optimization.py`, `core/test_service_contracts.py`, `frontend/CURRENT_TASKS.md`, `frontend/LESSONS_LEARNED.md`, `frontend/presenters/recommendations.py`, `frontend/static/frontend/css/theme.css`, and `frontend/templates/frontend/recommendations/result.html`. No model, migration, view, form, URL, orchestration order, JavaScript, matching rule, feasibility rule, OR-Tools constraint/objective, Pareto filter, recommendation-selection rule, team metric, permission, CSRF behavior, transaction, or assignment workflow changed.
- Deterministic explanation result: `build_recommendation_decision_evidence()` aligns each existing explanation to the selected recommendation's service-owned category and label, preserves selected order, and passes through the original team-name, strength, and trade-off lists plus references to the original recommendation and explanation dictionaries. The active deterministic service's French result sentences were a real English-only interface defect; those sentences were translated at their authoritative backend source while preserving every existing branch, input value, numeric format, key, list order, comparison dependency, and deterministic outcome. No wording translation or explanation logic was added to the frontend.
- Adjacent comparison result: comparison cards iterate the existing `comparisons` sequence without reordering and pass through the original `from_label`, `to_label`, team-size change, team-score change, remaining-capacity change, maximum-utilization change, utilization-spread change, and original comparison dictionary. The service does not return added/removed-member sets, so the interface shows the complete earlier and later team-name lists already returned by their deterministic explanations rather than calculating a set difference. Copy explains that each signed change is the later strategy minus its immediate predecessor; equal service deltas remain explicit zeroes.
- Interface result: the approved first-look M6.2 card grid and high-level summary table remain first, followed by one new `Why these strategies differ` panel, then every unchanged M6.3 allocation/capacity/coverage detail block. The new panel renders one semantic explanation card per returned strategy with independently labelled Strengths and Trade-offs lists, then zero to two ordered adjacent-comparison cards with complete earlier/later teams and the five exact service deltas. Explicit English empty and unavailable states distinguish a legitimately absent strength, trade-off, or adjacent strategy from unreadable evidence. Responsive three/two/one-column explanation layouts, stacked small-screen team/metric evidence, headings, ordered/unordered lists, definition lists, and color-independent labels preserve the current visual identity and accessibility structure.
- Boundary and safety result: frontend presentation performs no subtraction, absolute-value conversion, set difference, scoring, aggregation, comparison, or explanation generation. AST/template/JavaScript audits exclude arithmetic and calls to comparison, explanation, team-metric, and team-score services outside the unchanged M6.1 orchestration boundary. Gemini is not called or rendered, and generating or viewing evidence creates, changes, or deletes no project, requirement, employee, proficiency, assignment, or assignment-coverage record.
- Query and response baseline: seven warm Django test-client POSTs rendering three deterministic explanations and two adjacent comparisons, with the expensive pipeline mocked to isolate presentation overhead, remain fixed at 5 queries and recorded a 7.361 ms median / 7.523 ms p95 with a 37,143-byte response in the complete-suite run. The unchanged M6.1 orchestration continues to record real full-pipeline elapsed time separately.
- Test result: all eight focused M6.4 tests passed in 0.171 s; the combined core-contract and M6.1–M6.4 regression passed all 36 tests in 1.659 s; and the complete project suite passed all 446 tests in 26.213 s. Coverage includes exact dictionary/list/value identity and parity, deterministic repeated English output, selected and comparison ordering, full earlier/later team lists, signed and equal-zero deltas, zero/one/two/three recommendations, empty/unreadable evidence, semantic headings/lists/definition lists, responsive source contracts, no frontend calculation, no mutation, and fixed query/render overhead.
- Check result: `python manage.py check`, migration drift, compilation, strict UTF-8/BOM/trailing-whitespace validation for the M6.4 files, and `git diff --check` pass. M6.5 remains unstarted pending explicit approval.

### M6.5 Optional Gemini summary enrichment

- [x] Add optional manager-summary enrichment through the existing Gemini integration only after complete deterministic recommendation evidence is available.
- [x] Keep deterministic explanations visible and authoritative when credentials are absent, enrichment is disabled, the provider times out, returns malformed/partial output, or raises an error.
- [x] Prove Gemini cannot change feasibility, Pareto membership, recommendation order/category, team members, allocation, metrics, deterministic strengths/trade-offs, or assignment handoff data.
- [x] Bound provider waiting, avoid exposing credentials or unnecessary employee data in UI/logs/errors, and label generated wording as supplemental rather than calculated evidence.
- [x] Test disabled, successful, partial, timeout, malformed, and exception paths with mocked provider calls, zero external network dependence, stable result ordering, and unchanged deterministic fallback.

Scope boundary: M6.5 adds optional wording only. Gemini never decides, ranks, calculates, validates, blocks, or replaces a recommendation, and no production credential/privacy policy is inferred beyond the current approved integration boundary.

Completion evidence:

- Created files: `frontend/orchestration/recommendation_enrichment.py` and `frontend/tests/test_recommendation_gemini_enrichment.py`.
- Modified files: `core/services/llm_explanations.py`, `frontend/CURRENT_TASKS.md`, `frontend/LESSONS_LEARNED.md`, `frontend/presenters/recommendations.py`, `frontend/static/frontend/css/theme.css`, `frontend/templates/frontend/recommendations/_decision_evidence.html`, `frontend/tests/test_recommendation_execution.py`, `frontend/views/recommendations.py`, and `hr_workforce/settings.py`. No model, migration, matching rule, feasibility rule, OR-Tools constraint/objective, Pareto filter, recommendation-selection rule, team metric, deterministic explanation, permission, CSRF behavior, transaction, navigation, assignment handoff, or staffing record changed.
- Execution result: the recommendation POST still runs the complete deterministic M6.1 pipeline first. Only after its selected recommendations, adjacent comparisons, and deterministic explanations return does a separate optional enrichment boundary call the existing `generate_manager_summary()` integration once per explanation. The original pipeline result remains attached by identity, strategy categories/order and all service-owned recommendation/explanation objects remain unchanged, and the presenter only aligns supplemental text by the existing category/label pair.
- Configuration and waiting result: enrichment is explicitly opt-in through `GEMINI_MANAGER_SUMMARIES_ENABLED` and is off by default. Each provider request uses the provider-compatible `gemini-3.1-flash-lite` model, a 10,000 ms timeout, and one total attempt, bounding a result page to at most the three already selected strategies. The original 2,500 ms deadline was corrected after a live diagnostic proved that the provider rejects deadlines below 10 seconds and that the previously configured `gemini-3.5-flash-lite` generation path exceeded both 10- and 30-second diagnostic deadlines. A post-fix live check through the actual optional-enrichment boundary returned a non-empty, single-line, validator-accepted summary in 8.613 seconds using the configured model, configured timeout, unchanged prompt shape, synthetic evidence, and active credential. Credentials remain provider-managed and are neither stored in Django settings nor passed, rendered, or logged by the frontend.
- Validation and fallback result: generated output is accepted only when it is a non-empty, single-line, plain-text summary no longer than 400 characters whose numeric tokens already occur in the deterministic input. Malformed, empty, oversized, marked-up, multiline, numerically unsupported, timed-out, rate-limited, credential, and exception results are discarded per strategy. Generic disabled, partial, and unavailable states keep every deterministic strength, trade-off, comparison, allocation row, capacity value, and coverage outcome visible and usable; one provider failure cannot remove another valid summary or the recommendation result.
- Interface and privacy result: successful enrichment adds no global provider-status banner; each accepted generated summary appears immediately before that strategy's authoritative Strengths and Trade-offs under the manager-facing `Manager summary` label. The existing page-level deterministic explanation establishes the evidence hierarchy without a repeated per-card technical disclaimer. Disabled, partial, and unavailable fallback states remain visible and unchanged. The simplified three-card summary remains first and every M6.3/M6.4 evidence section remains below. The provider payload retains the existing narrow five-field contract—category, label, selected team names, deterministic strengths, and deterministic trade-offs—and sends no project, requirement, allocation, capacity, metric, attendance, assignment, or other employee data. Provider output is template-escaped; raw provider responses, prompts, exceptions, credentials, stack traces, and technical errors are never placed in the result context, UI, or warning logs.
- Boundary and safety result: source/AST checks prove Gemini runs after and outside the deterministic orchestrator, while the enrichment boundary calls no matching, availability, feasibility, solver, Pareto, selection, comparison, explanation, metric, or scoring service. Templates and JavaScript contain no enrichment or decision calculations. Successful, partial, and failed enrichment preserve strategy order and leave projects, requirements, employees, proficiencies, assignments, and assignment-skill coverage unchanged; recommendations remain advisory and expose no automatic staffing action.
- Query and response baseline: seven warm Django test-client result POSTs rendering three successful summaries after the provider-neutral wording refinement, with both the expensive deterministic pipeline and provider calls mocked to isolate presentation overhead, remain fixed at 5 queries and recorded a 7.242 ms median / 10.779 ms p95 with a 37,872-byte response. Real provider latency is intentionally excluded from this presentation baseline and bounded separately by the configured per-request timeout.
- Test result: after the provider-neutral presentation refinement, all eight focused M6.5 tests passed in 0.244 s and the shared M6.4–M6.5 evidence regression passed all 16 tests in 0.438 s. The earlier post-configuration core-contract and M6.1–M6.5 recommendation regression passed all 44 tests in 2.009 s, and the existing final 454-test milestone suite remains the prior M6.5 completion baseline. Coverage includes absence of the successful global provider banner and repeated disclaimer, the `Manager summary` label, opt-out, successful, partial, timeout, rate-limit, missing-credential, malformed, fabricated-number, and exception paths; per-item fallback; exact call order, 10,000 ms timeout, one-attempt behavior, and `gemini-3.1-flash-lite` model configuration; minimal payload; unchanged prompt constraints; generic UI/log safety; original object/value identity; stable category order; no mutation; no external network in automated tests; source isolation; and fixed query/rendering overhead.
- Check result: `python manage.py check`, migration drift, Python compilation, strict UTF-8/BOM/trailing-whitespace validation for all M6.5 files, and `git diff --check` pass. M6.6 remains unstarted pending explicit approval.

### M6.6 Recommendation result states and recovery paths

- [x] Handle no requirements, missing or non-positive mandatory effort, invalid dates, no eligible employees, insufficient pre-solver capacity, no feasible team after enumeration, and zero/one/two recommendation outcomes with distinct truthful states.
- [x] Detect changed planning inputs and stale/deleted project, requirement, employee, or recommendation references before presenting or acting on old evidence; never combine snapshots from different runs.
- [x] Recover from enumeration, solver, deterministic-explanation, and optional-enrichment failures without exposing tracebacks, leaking records, or mislabelling an incomplete run as a valid recommendation result.
- [x] Map every blocker, empty state, and recoverable failure to the existing planning evidence or permitted project, requirement, employee-skill, leave, assignment, and coverage workflow while preserving canonical return context.
- [x] Test every state, deterministic ordering, retry/refresh behavior, permission combinations, stale/deleted targets, safe error copy, and proof that cheap preflight blockers stop expensive downstream services.

Scope boundary: M6.6 hardens result and recovery states around the existing pipeline. It does not add a new calculation, silently repair data, persist incomplete results, or weaken validation and permissions.

Completion evidence:

- Codex partial work preserved: `frontend/selectors/recommendations.py` (input snapshot digest, reference-currency and envelope-completeness checks), `frontend/templates/frontend/recommendations/_recovery.html`, token `input_signature` binding plus `StaleRecommendationSubmissionToken` in `frontend/recommendation_execution.py` and `frontend/forms/recommendations.py`, per-stage `RecommendationPipelineStageError` in `frontend/orchestration/recommendations.py`, `build_unavailable_manager_summaries()` in `frontend/orchestration/recommendation_enrichment.py`, `build_project_planning_readiness()` extraction plus headcount counts in `frontend/presenters/planning.py`, readiness/result/error foundations with `planning_blocked` (422), `no_feasible_team` vs `no_recommendation`, and `one/two/three_strategies` variants in `frontend/presenters/recommendations.py`, snapshot-gated POST flow with readiness-first 422 and post-run currency checks in `frontend/views/recommendations.py`, snapshot-issued generation form in `frontend/views/planning.py`, recovery include plus `project_changed` return handling in `frontend/templates/frontend/recommendations/result.html`, and the M6.5 model/timeout/wording refinement carried in the same tree (`gemini-3.1-flash-lite`, 10,000 ms, `Manager summary` label).
- Continuation work completed: permission-aware recovery mapping with canonical return context in `frontend/presenters/recommendations.py` (`_returned_recovery_url`, `_leave_evidence_recovery_url`, `_readiness_repair_actions`, user-aware `_planning_recovery`, readiness/result/error foundations accepting `user`), view wiring of `request.user` through every foundation in `frontend/views/recommendations.py`, dedicated `frontend/tests/test_recommendation_result_states.py` (18 tests), repair of Codex-interrupted expectations (`test_recommendation_execution.py` result baseline 5 to 38 queries plus stage-wrapper source assertions; strategy/allocation/decision/enrichment result baselines 5 to 37 queries; deleted-reference view expectations updated to truthful 409 stale with direct presenter robustness retained; planning GET baselines 21 to 27 and 20 to 26 for the 6-query snapshot, with hardening/verification helpers recording snapshot cost separately).
- State result: readiness blockers return distinct 422 `planning_blocked` states (`invalid_project_dates`, `mandatory_effort_must_be_positive`, `no_mandatory_requirements`, `insufficient_eligible_headcount`, derived `no_eligible_employees` when eligible count is zero, `insufficient_qualified_capacity`, `stale_planning_inputs`); completed runs return `completed` with `one_strategy`/`two_strategies`/`three_strategies`; empty runs split truthfully into `no_feasible_team` versus `no_recommendation`; failures return `error`/`incomplete` (503), token/snapshot drift returns `stale` (409), and missing project returns `project_changed` (409) with project-list return and no planning/detail links.
- Currency result: the generation token binds the planning snapshot signature; the view compares starting, pre-run, completed, and presentation snapshots plus per-reference employee/requirement currency and rejects drift with 409 without mixing evidence. Deleted employee/requirement references returned by a mocked pipeline are treated as stale at the view boundary, while direct presenter calls still render deleted objects as readable and unlinked.
- Failure result: each pipeline stage maps to a logged generic 503 `error`; malformed envelopes and presentation failures map to 503 `incomplete`; enrichment exceptions fall back per strategy to `unavailable` with deterministic evidence intact; no traceback, exception text, credential, prompt, or raw provider output reaches the UI or warning logs; staffing records remain unchanged in every tested state.
- Recovery result: every 422/200-empty/409/503 state renders the shared recovery panel with a primary planning-workspace return anchored to the relevant evidence section. Readiness items include both the evidence anchor and permission-aware repair actions (`Edit project schedule`, `Enter requirement effort`, `Add mandatory requirement`, `Review approved leave`) built with `with_planning_return`; viewers see evidence-only recovery while managers see edit actions with `return_to`. `no_feasible_team` includes the approved-leave return for permitted users. All edit destinations reuse existing routes with canonical planning return.
- Query and response baseline (warm Django test-client, expensive pipeline/provider mocked): planning GET 27 queries where generation is allowed (4 shell + 17 planning + 6 snapshot) and 8 where blocked; result POST 38 queries for the execution fixture and 37 for strategy/allocation/decision/enrichment fixtures. Final full-suite medians/p95: M6.1 22.901 ms / 26.766 ms (20,130 bytes), M6.2 23.930 ms / 24.905 ms (33,557 bytes), M6.3 23.959 ms / 25.412 ms (28,386 bytes), M6.4 25.959 ms / 29.187 ms (37,471 bytes), M6.5 24.439 ms / 24.850 ms (37,881 bytes). Real pipeline/enrichment latency remains bounded separately by the synchronous request plus the 10,000 ms per-summary provider timeout.
- Test result: all 18 focused M6.6 tests pass; combined M6.1–M6.6 recommendation run passes all 57 tests; complete project suite passes all 472 tests. Coverage includes every readiness code, empty/outcome variants, ordering, stale/deleted at token/pre-run/post-run/presentation/reference layers, all five stage failures, incomplete envelopes, enrichment/presentation failures, stale retry with fresh token, duplicate handling, Viewer/Manager/HR plus unassigned and per-permission boundaries, safe-copy assertions, no-mutation checks, and fixed query/rendering overhead.
- Check result: `python manage.py check`, migration drift, compilation, strict UTF-8/trailing-whitespace checks for the M6.6 files, and `git diff --check` pass. M6.7 remains unstarted pending explicit approval.

### M6.7 Reviewed assignment confirmation handoff

- [x] Add a separate, explicit confirmation handoff from one current recommendation; never create or update assignments merely by generating, viewing, or selecting a recommendation card.
- [x] Show the proposed employees, roles/allocations, dates, and requirement coverage before submission, with a clear cancel path back to the same recommendation/planning context.
- [x] Immediately rerun the approved current-data checks before saving and reject stale, deleted, no-longer-qualified, over-capacity, overlapping-assignment, approved-leave, quantity, or project-consistency conflicts.
- [x] Reuse existing assignment and assignment-skill validation and permission rules, protect the confirmed POST with CSRF and duplicate-submit handling, and wrap any compound staffing save in `transaction.atomic()` so partial assignments or coverage cannot remain.
- [x] Test confirmation-only mutation, validation feedback, permission boundaries, CSRF, duplicate POST, stale data between review and save, rollback, exact records created, return continuity, and unchanged recommendation selection.

Scope boundary: M6.7 provides a reviewed staffing handoff only. Recommendations remain advisory; no automatic acceptance, silent write, validation bypass, persisted recommendation history, or change to assignment/coverage business rules is introduced.

Completion evidence:

- Created files: `frontend/assignment_handoff.py` (one-time confirmation tokens bound to user/project/category/snapshot), `frontend/forms/assignment_handoff.py`, `frontend/orchestration/assignment_handoff.py` (proposal derivation from service-returned utilization/skill/dates plus `full_clean` revalidation with combined quantity check, no new math), `frontend/presenters/assignment_handoff.py`, `frontend/views/assignment_handoff.py` (`project_recommendation_confirm` GET review plus POST save), `frontend/templates/frontend/recommendations/confirm.html`, and `frontend/tests/test_assignment_handoff.py` (17 tests).
- Modified files: `frontend/urls.py` (`projects/<id>/recommendations/confirm/<category>/`), `frontend/presenters/recommendations.py` (permission-aware per-card `Review staffing handoff` URL only with `add_assignment` plus `add_assignmentskill`), `frontend/templates/frontend/recommendations/_strategy_card.html` (handoff link, wording avoids the advisory `Create assignment` assertion), `frontend/templates/frontend/components/navigation.html` (Projects stays active on the confirm route), `frontend/CURRENT_TASKS.md`, and `frontend/LESSONS_LEARNED.md`. No model, migration, core service, matching/feasibility/OR-Tools/Pareto/selection/comparison/explanation rule, Gemini integration, M6.1–M6.6 execution/recovery behavior, or existing CRUD contract changed.
- Handoff result: each result card links to a category review that reruns readiness plus the deterministic pipeline, checks snapshot currency and reference currency, and derives unsaved `PLANNED` assignments (project dates, utilization-rate allocation rounded only for the integer field, skill-label roles) with solver-pair coverage. Review shows employees, schedule, allocation, role, status, and coverage with per-row validation errors and a cancel path to the same planning workspace. Confirming POST revalidates the token, claims it once, reloads current pipeline state, revalidates every proposal, and saves assignments plus coverage inside `transaction.atomic()` before redirecting to the planning workspace with a success message. Generation, result viewing, and review GETs never save; invalid/stale/duplicate/blocked/failed reviews never save.
- Revalidation result: snapshot drift, deleted project/requirement/employee, missing category, readiness blockers, stage failures, and incomplete envelopes all render truthful blocked/error/stale states with recovery and no save. `full_clean` on every proposed assignment and coverage rejects no-longer-qualified members, over-capacity totals, overlapping same-project assignments, approved leave overlap, quantity overflow (existing plus proposed), and project inconsistency; combined-quantity overflow across a multi-member proposal fails the whole review and any save attempt rolls back to zero new records.
- Boundary result: confirm GET/POST requires the six-model read contract plus `add_assignment` and `add_assignmentskill`; Viewers and unassigned users receive 403 without pipeline work beyond permission checks. CSRF middleware plus per-form tokens apply; `app.js` busy/disabled handling covers the confirm form; claimed tokens return 409 on replay (duplicate when nothing changed, stale once a save changes assignments). Source audits prove handoff code calls no matching/scoring/solver/Pareto/selection/comparison/explanation/Gemini/attendance logic and duplicates no backend calculation.
- Query and response baseline (warm Django test-client, pipeline mocked): confirm review GET 50 queries, confirm save POST 74 queries for the one-member fixture, review median 23.842 ms with an 11,494-byte review response in the focused run (24.004 ms / 11,490 bytes in the full suite). Result-card rendering grows by the handoff link only (M6.2 33,569 bytes, M6.3 28,390 bytes, M6.4 37,483 bytes, M6.5 37,893 bytes, M6.1 result 20,134 bytes). Real pipeline latency remains the synchronous orchestration cost; no caching, bounds, background work, or persistence added.
- Test result: all 17 focused M6.7 tests pass; combined M6.1–M6.7 recommendation run passes all 74 tests; complete project suite passes all 489 tests. Coverage includes routing/navigation, unknown-category/deleted 404s, review proposal exactness, handoff link permission gating, exact created records and redirect, generation/review confirmation-only behavior, overlap/leave/unqualified/quantity errors, multi-member atomic rollback, per-permission and CSRF/duplicate/stale/rollback/return paths, safe error copy, accessibility semantics, query baselines, and source boundaries.
- Check result: `python manage.py check`, migration drift, compilation, strict UTF-8/trailing-whitespace checks for the M6.7 files, and `git diff --check` pass. M6.8 remains unstarted pending explicit approval.

Refinement (approved handoff follow-up, no new milestone, M6.8 still unstarted):

- Result continuity without persistence: generation POSTs now store the exact pipeline result plus manager summaries in the configured cache under an unguessable run ID bound to project/user/snapshot (1-hour TTL, `frontend/recommendation_runs.py`; no model or migration). Result cards link reviews with `?run=`; a new GET `project_recommendation_result` view re-renders the identical strategies, metrics, explanations, summaries, and allocation evidence with zero pipeline calls after revalidating the snapshot and references, otherwise redirects to planning with a fresh-recommendation message. Reviews show `Back to recommendation results` whenever the run stays current and fall back to planning return otherwise; successful confirmations invalidate the run so old results can never look current.
- Re-planning diff instead of duplicate creates: handoff proposals now diff CURRENT target-period staffing against the RECOMMENDED team per employee (`KEEP`/`UPDATE`/`ADD`/`REMOVE`) and coverage (`KEEP`/`ADD`/`REMOVE`). `UPDATE` reuses the existing assignment row (status preserved, no downgrade); `REMOVE` cancels (never deletes, Managers keep working without delete permission); `KEEP` writes nothing. Coverage quantity is validated on final counts (surviving plus proposed) and per-link quantity errors are ignored only when the final count passes, so replacing coverage never reports a false conflict. Coverage-link deletions additionally require `delete_assignmentskill` at save time (403 otherwise, Managers unaffected for ADD/UPDATE-only plans); the confirm gate now also requires `change` on both models.
- Other-project assignments remain pure workload constraints and are never touched; full `Assignment`/`AssignmentSkill` revalidation, snapshot/stale protection, CSRF, one-time tokens, atomic saves with full rollback, and canonical planning returns are retained.
- Evidence: new `frontend/tests/test_handoff_reconciliation.py` (14 tests) covering UPDATE/KEEP/ADD/REMOVE diffs, coverage replace with the delete-permission gate (manager 403, HR success), back-to-results with identical values and no pipeline call, two-strategy hopping on one run, stale/expired/invalidated runs falling back to planning, missing-change-permission denial, untouched other-project work, mid-transaction rollback, viewer run-link denial, plus updated M6.7 overlap/quantity tests for the new semantics. Cached result GET baseline: 13 queries / 25,361 bytes (one-strategy fixture, pipeline never rerun); review/save baselines unchanged in shape (51/76 queries). Complete suite passes all 504 tests with the checks above green.

### M6.8 Performance, accessibility, and boundary hardening

- [x] Profile preflight, feasible-team enumeration, Pareto filtering, selection, explanation, optional enrichment, assignment confirmation, ORM queries, and complete response time separately for realistic project/workforce sizes, including the established 10-employee sample baseline.
- [x] Verify concurrent and repeated submissions, progress and duplicate-submit behavior, deterministic results, large allocation tables, zero/one/two/three cards, and stale data across long-running requests.
- [x] Add caching, bounded candidate generation, persisted run state, or background execution only if measured target-scale behavior requires it and the change can preserve service order, current-data validation, permissions, and deterministic results.
- [x] Verify keyboard/focus behavior, progress announcements, heading structure, card/table semantics, captions/scopes, color-independent interpretation, responsive overflow, reduced motion, and readable deterministic alternatives for all supplemental presentation.
- [x] Run focused Milestone 3–5 regressions and source audits proving recommendation views do not duplicate calculations, use attendance, bypass validation, reorder the pipeline, let Gemini affect decisions, or alter existing CRUD/planning contracts.

Scope boundary: M6.8 hardens and measures implemented Milestone 6 behavior. It introduces no new feature or infrastructure unless a measured defect or approved latency requirement makes the smallest compatible correction necessary.

Completion evidence:

- Created file: `frontend/tests/test_milestone6_hardening.py` (14 tests). No application, model, migration, service, selector, presenter, view, form, URL, template, CSS, or JavaScript behavior changed.
- Profiling result (real services, 4 employees, 1 mandatory requirement, 15 feasible / 15 pareto / 3 recommendations): feasible-team enumeration ~854–1059 ms dominates; Pareto filtering ~0.07–0.12 ms, selection ~0.01–0.02 ms, comparison ~0.01 ms, explanation ~0.02–0.03 ms. Repeated runs return identical categories, labels, team membership, and scores with zero staffing mutation. Real end-to-end generation plus confirmation on a 2-employee fixture completes in ~177–214 ms of response time with exactly 1 assignment and 1 coverage created. The established 10-employee sample baseline (~20.4 s for 88 feasible teams from `PLAN.md`) remains the reference for full-scale solver cost.
- Concurrency result: two threaded generation POSTs sharing one token yield exactly one 200 plus one 409; two threaded POSTs with fresh tokens both succeed with identical counts, labels, and strategy values. Same-page duplicate-submit blocking stays client-side (`aria-busy` guard) with server-side one-time token claims; multi-process cache guarantees remain backend-dependent per the existing lesson.
- Scale and determinism result: 1-strategy and 3-strategy renders of a large mocked pipeline (4 members each, 6 allocation columns, 6 coverage rows) use identical fixed query counts (37), proving rendering has no N+1 growth; the large response is 99,729 bytes inside the existing scrollable table shells. Zero/one/two/three-card variants remain covered by the M6.2/M6.6 suites. A mid-pipeline staffing change is detected by the completed-snapshot comparison and returns truthful 409 stale with no staffing write from the view.
- Infrastructure decision: no caching, candidate bounds, persisted run state, or background execution added. Presentation overhead is fixed (~22–26 ms medians), solver cost is intrinsic backend behavior already bounded by explicit user action plus the 10 s per-summary provider timeout, and back-navigation already avoids pipeline reruns through the ephemeral run cache. Background execution stays deferred until an approved latency target requires it.
- Accessibility result: planning, result, cached-result, and confirmation pages each render exactly one h1 with no heading-level jumps, unique IDs with valid ARIA references, captioned tables with column scopes, zero inline handlers, zero positive tab order, skip-link targets, polite progress announcements, and text (never color-only) status wording with deterministic fallbacks always rendered. Stylesheets retain `:focus-visible`, skip-link focus, `overflow-x` scrollable table shells, and `prefers-reduced-motion` handling.
- Boundary result: source audits prove both recommendation views call only the `run_recommendation_pipeline()` boundary (never the five services, solver, or optimization module directly), the frontend duplicates no matching/scoring/workload/availability/metric/solver/attendance/Gemini calculation, Gemini stays outside both orchestrators, the handoff save path keeps `full_clean` plus `transaction.atomic` with claimed tokens, all Milestone 6 routes resolve inside the Projects navigation family, and no Celery/background/thread-pool/asyncio infrastructure exists. Focused Milestone 3–5 verification/hardening suites (28 tests) and the complete 518-test suite pass with existing CRUD, permission, CSRF, validation, dashboard, and planning contracts unchanged.
- Check result: `python manage.py check`, migration drift, compilation, strict UTF-8/trailing-whitespace checks for the M6.8 file, and `git diff --check` pass. M6.9 remains unstarted pending explicit approval.

### M6.9 Milestone 6 verification

- [x] Verify every Milestone 6 route, template, navigation state, authentication/permission boundary, CSRF contract, execution state, strategy card, allocation row, explanation, comparison, Gemini fallback, recovery path, and assignment-confirmation outcome.
- [x] Reconcile every displayed team, score, capacity, utilization, allocation, coverage, Pareto/selection category, comparison, and deterministic explanation against existing core service outputs for populated, boundary, stale, empty, and failure scenarios.
- [x] Confirm recommendation generation remains explicit, attendance remains absent from planning decisions, Gemini remains optional wording, assignments remain separately confirmed and revalidated, and frontend code contains no duplicated matching, feasibility, optimization, or recommendation logic.
- [x] Run the complete project suite, `python manage.py check`, migration drift, compilation, UTF-8, whitespace, source audits, and `git diff --check`; record final query, pipeline, provider-fallback, and response-time baselines plus reusable lessons.
- [x] Close Milestone 6 only when every exit criterion passes, leaving Milestone 7 unstarted pending explicit approval.

Scope boundary: M6.9 is verification and finalization only. It adds no new feature unless a real defect is found, and any correction must remain narrowly within Milestone 6.

Completion evidence:

- Created file: `frontend/tests/test_milestone6_verification.py` (14 tests). No application, model, migration, service, selector, presenter, view, form, URL, template, CSS, or JavaScript behavior changed.
- Defects found: none in validated M6.1–M6.8 behavior. Verification exposed no application defect, so no narrow correction was applied; the only failures seen during the run were over-strict expectations inside the new verification file itself (envelope completeness, variant naming, and capacity fixtures), corrected without touching application code.
- Route and contract result: every Milestone 6 route resolves (`project_planning`, `project_recommendation_generate`, `project_recommendation_result`, `project_recommendation_confirm` plus the existing project/requirement/assignment/coverage workflows); GET-only/POST-only methods hold (405 otherwise); each renders its template with Projects navigation active; anonymous users redirect to sign-in; unassigned users and missing-permission users receive 403; CSRF-enforced clients get 403 without tokens on both generation and confirmation POSTs.
- Reconciliation result: a real-solver generation run matches fresh core service outputs exactly — categories, labels, order, team membership, team size/score, all six metrics, per-employee available/allocated/utilization values, every allocation cell hour, coverage quantities and satisfaction flags, comparison deltas, and full strengths/trade-offs/team lists. Repeated runs agree; the cached run record is retrievable and project-bound.
- Separation result: planning GETs invoke no pipeline or provider; inserting an absent attendance record leaves the input snapshot signature, readiness outcome, and generated values identical; successful and failed Gemini paths keep strategy selection, metrics, and evidence identical with only the enrichment state changing and no provider text leaking; generation and review never write while confirmation writes exactly one assignment plus coverage and redirects to planning.
- Final baselines (verification fixture, real solver): planning GET 26 queries, full-pipeline result POST 201 queries with 3 strategies in a 52,445-byte response. Presentation-only baselines stay fixed (result POSTs 37–38 queries, review 51, save 74, cached result GET 13). Provider latency stays bounded by the 10 s per-summary timeout; solver cost stays behind the explicit POST action.
- Test result: all 14 focused M6.9 tests pass and the complete project suite passes all 532 tests. `python manage.py check`, migration drift, compilation, strict UTF-8/trailing-whitespace checks, milestone-wide source audits, and `git diff --check` pass.
- Closure result: all nine Milestone 6 exit criteria pass (explicit guarded generation; single ordered orchestration boundary; faithful zero-to-three cards; exact allocation/coverage evidence; authoritative deterministic explanations with optional Gemini; truthful recovery states; separately confirmed transactional staffing; verified access/return/accessibility/query behavior; attendance isolation with no duplicated logic and a green suite). Milestone 6 is complete and closed; Milestone 7 remains unstarted pending explicit approval.

## Milestone 6 exit criteria

- [x] Recommendation generation starts only from an explicit, permission-checked, CSRF-protected action with accessible progress and duplicate-submit protection; ordinary planning GETs never run the expensive pipeline.
- [x] One tested frontend orchestration boundary calls feasible-team enumeration, Pareto filtering, recommendation selection, adjacent comparison, and deterministic explanations exactly once and in the documented order.
- [x] Zero to three strategy cards preserve the selected categories, order, members, scores, capacity, allocation, utilization, spread, and size values returned by existing services without frontend recalculation.
- [x] Allocation matrices and mandatory coverage evidence exactly match the existing OR-Tools result and remain readable, responsive, and explicit about units and project-period assumptions.
- [x] Deterministic strengths, trade-offs, and adjacent comparisons are always available; optional Gemini wording cannot affect selection, metrics, allocation, evidence, validation, or fallback behavior.
- [x] Incomplete, no-eligible, insufficient-capacity, no-feasible-team, one/two-result, provider/service failure, stale, deleted, and retry states are truthful, permission-safe, deterministic, and connected to useful recovery paths.
- [x] Any staffing action is a separate reviewed confirmation that revalidates current data, preserves existing Assignment and AssignmentSkill rules, uses CSRF and approved permissions, and commits compound writes transactionally or not at all.
- [x] Access rules, return continuity, accessibility, query behavior, duplicate/concurrent execution behavior, and realistic pipeline/response-time baselines are verified without changing existing dashboard, employee-insight, CRUD, or planning contracts.
- [x] Attendance remains outside recommendation decisions, frontend code duplicates no core calculation or selection logic, the complete suite and Django checks pass, and Milestone 7 remains unstarted until explicit approval.

## Completed Milestone 5 task breakdown

### M5.1 Project planning workspace foundation

- [x] Add one namespaced, GET-only project-planning route and connect it from the existing project detail workflow while preserving the Projects navigation state, responsive shell, and current visual system.
- [x] Define and enforce the complete read-permission contract for the stored project, requirement, assignment, assignment-coverage, employee, and skill context rendered by this first workspace slice.
- [x] Build a fixed-query selector and thin presenter over existing models/selectors for the project schedule, status, priority, criticality, project estimate, mandatory requirement effort total, stored requirements, current assignments, and assignment coverage.
- [x] Render a read-only workspace foundation with manager-friendly definitions, explicit project-estimate versus mandatory-effort context, distinct populated/incomplete/empty states, and natural links back to project detail and the project directory.
- [x] Test routing, missing/stale project handling, templates, navigation, permissions, GET-only behavior, stored totals, empty states, query count, and warm response time.

Scope boundary: M5.1 establishes the read-only route, access contract, stored planning context, and page structure only. It does not calculate readiness, rank candidates, explain exclusions, derive requirement gaps, add repair actions, run matching or availability services, enumerate teams, invoke optimization, or generate recommendations.

Completion evidence:

- Created files: `frontend/presenters/planning.py`, `frontend/views/planning.py`, `frontend/templates/frontend/planning/workspace.html`, `frontend/templates/frontend/planning/_requirement_row.html`, `frontend/templates/frontend/planning/_assignment_row.html`, and `frontend/tests/test_project_planning_workspace.py`.
- Modified files: `frontend/urls.py`, `frontend/presenters/projects.py`, `frontend/templates/frontend/components/navigation.html`, `frontend/templates/frontend/projects/detail.html`, `frontend/CURRENT_TASKS.md`, and `frontend/LESSONS_LEARNED.md`. No model, migration, core service, form, JavaScript, static asset, or CSS file changed.
- Route and navigation result: `frontend:project_planning` resolves to `/projects/<project_id>/planning/`, is GET-only, returns 404 for a missing current project, keeps Projects navigation active, and is linked from the existing project profile when the user can view the additional employee and skill context. Breadcrumbs and footer actions return naturally to the same project profile and project directory.
- Permission result: the workspace independently requires the six existing model permissions for `Project`, `ProjectSkillRequirement`, `Assignment`, `AssignmentSkill`, `Employee`, and `Skill`. Anonymous users redirect to sign-in; unassigned users and users missing any one permission receive 403; canonical Viewers, Managers / Planners, and HR Administrators retain access. POST and PUT receive 405 and leave every stored record unchanged.
- Selector and presenter result: the workspace reuses `get_project_profile()` and its established four-query project/requirement/assignment/coverage load. Stored-context shaping was extracted from the existing project presenter so the new thin planning presenter can reuse the exact project estimate, mandatory entered-effort total, requirement/assignment counts, and assignment-coverage links without calling the project profile's existing recommendation preflight. Existing project-detail presentation and tests remain unchanged in behavior.
- Interface result: the server-rendered workspace uses the existing page header, project overview, status badge, planning facts, surface cards, tables, empty states, buttons, spacing, colors, and responsive behavior. It shows stored schedule, status, priority, criticality, description, project estimate, mandatory entered effort, every requirement, every assignment status/date/allocation, and linked requirement coverage. Missing effort says `Not entered`; empty projects distinguish no requirements from no assignments. Project and mandatory-requirement estimates remain separately labelled with manager-friendly wording.
- Scope result: the page is read-only and contains no add/edit/remove action, inline form, readiness result, candidate rank, exclusion reason, derived requirement gap, or feasibility/recommendation claim. Mock and source-boundary tests prove it does not call recommendation preflight, matching, availability, attendance, feasible-team enumeration, optimization, recommendation selection/explanations, Gemini, or any browser-side business calculation.
- Query and timing result: a populated role-based request uses eight fixed queries: four for the authenticated shell plus the existing four-query stored project context. In the final complete-suite run, 25 warm Django test-client GETs with three requirements, two assignments, and two coverage links recorded 7.440 ms median, 8.073 ms p95, 6.896 ms minimum, and 8.704 ms maximum. Measurements include request handling, ORM work, and template rendering but exclude browser/network latency and static-file transfer.
- Commands run:
  - `python manage.py test frontend.tests.test_project_planning_workspace --verbosity 2`
  - combined project-planning/project-detail/project-directory/Milestone-3-route/permission regression command
  - `python manage.py test frontend --verbosity 1`
  - `python manage.py test --verbosity 1`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py check`
  - `python -m compileall -q core frontend`
  - edited-file trailing-whitespace, strict UTF-8, and M5.1 service-boundary source scans
  - `git diff --check`
- Result: all 5 focused M5.1 tests passed in 0.397 s; all 33 related route/permission regressions passed in 2.003 s; all 349 frontend tests passed in 19.232 s; and the complete 363-test project suite passed in 20.032 s. Django system checks, compilation, migration drift, UTF-8, source-boundary, and whitespace checks pass.
- Defect result: no application defect was found or fixed. Existing validated backend behavior remains unchanged.
- Lessons result: `LESSONS_LEARNED.md` records the reusable rule to keep prefetched stored planning context separate from staged preflight, matching, feasibility, and recommendation assessment so an earlier page slice cannot invoke later services accidentally.

### M5.2 Readiness and preflight assessment

- [x] Add a read-only readiness presenter that calls `get_recommendation_preflight(project)` first and composes only existing model-validation and service outputs needed to explain whether planning inputs are ready for later optimization.
- [x] Surface manager-friendly blockers for invalid project dates, missing or non-positive mandatory effort, no mandatory requirements, insufficient eligible headcount, insufficient qualified capacity, and current data that no longer supports the displayed planning context.
- [x] Keep project estimate and mandatory requirement effort visibly separate, explain the current Monday-to-Friday/no-holiday capacity assumption, and distinguish a planning-input blocker from a proven no-feasible-team result.
- [x] Stop expensive downstream assessment when cheap preflight blockers already make the project incomplete; do not call feasible-team enumeration, OR-Tools, recommendation selection, explanations, Gemini, or attendance services.
- [x] Test complete, incomplete, invalid, empty, insufficient-headcount, insufficient-capacity, boundary-date, and freshly changed/stale-input scenarios, including service delegation and deterministic blocker ordering.

Scope boundary: M5.2 adds readiness signals and actionable blockers only. It does not render ranked candidates, make a feasibility claim that requires team enumeration, modify planning data, persist assessment state, or run the recommendation pipeline.

Completion evidence:

- Created file: `frontend/tests/test_project_planning_readiness.py`.
- Modified files: `core/services/effective_availability.py`, `core/services/optimization.py`, `frontend/presenters/planning.py`, `frontend/views/planning.py`, `frontend/templates/frontend/planning/workspace.html`, `frontend/tests/test_project_planning_workspace.py`, and `frontend/CURRENT_TASKS.md`. No model, migration, form, URL, permission, JavaScript, static asset, or CSS file changed; `frontend/LESSONS_LEARNED.md` was not changed because its existing prefetched-scalar-service lesson already covers the reusable performance finding.
- Readiness result: the workspace always calls `get_recommendation_preflight(project)` first, applies the existing `Project.clean()` date rule, and stops before workforce-capacity assessment for invalid dates, missing or zero mandatory effort, or no mandatory requirements. When those inputs pass, it reuses `build_optimization_context()` and structured output from the existing fast feasibility rules to report insufficient eligible active headcount or insufficient qualified effective capacity. Assessment results are calculated on each GET and are never persisted.
- State and ordering result: valid inputs receive `Ready for candidate assessment`; invalid dates, incomplete effort, empty mandatory demand, headcount gaps, capacity gaps, and a requirement snapshot that changes during assessment receive distinct English blockers. Blockers use a fixed category order and requirement primary-key order. A freshly corrected record is reassessed on the next request, while a changed in-flight requirement snapshot returns `Refresh planning inputs` rather than mixing old display context with current service evidence.
- Interface result: a new read-only `Planning readiness` card uses the existing surface-card and planning-state visual language. It keeps the project estimate and mandatory requirement effort separately labelled, explicitly warns when they differ without inventing a backend blocker, states the Monday-to-Friday/no-holiday capacity assumption, and explains that passing readiness does not prove that a feasible team exists. It also states that attendance remains descriptive only and does not affect staffing readiness.
- Service-boundary result: `get_fast_feasibility_issues()` now exposes the same pre-solver headcount and capacity decisions already owned by `passes_fast_feasibility_checks()`; the established Boolean function delegates to it with early exit, preserving its result and short-circuit behavior. M5.2 never calls candidate ranking, feasible-team enumeration, OR-Tools solving, Pareto/recommendation selection, deterministic/generated explanations, Gemini, or attendance services.
- Defect and performance result: the first integrated request exposed 367 queries because project capacity queried workload and leave for every employee on every weekday. The necessary fix bulk-prefetches active employees' skills, overlapping non-cancelled assignments outside the assessed project, and overlapping approved leave inside `build_optimization_context()`, then passes those records through the existing effective-availability service. A regression proves identical `16.00 h` legacy and prefetched results with competing workload, current-project exclusion, and approved leave. The populated workspace now uses 14 fixed queries: four authenticated-shell, four stored-context, one recommendation-preflight, and five optimization-context queries. In the final full-suite run, 25 warm Django test-client GETs recorded 11.213 ms median, 11.884 ms p95, 10.843 ms minimum, and 12.811 ms maximum.
- Test result: the focused M5.1/M5.2 run passed all 12 tests in 0.649 s; the expanded readiness plus core recommendation-contract run passed all 18 tests in 1.426 s; and the complete project suite passed all 371 tests in 20.472 s. Coverage includes complete, missing/zero effort, invalid and same-day date boundaries, optional-only/empty mandatory demand, exact headcount and capacity boundaries, current-project assignment exclusion, competing workload, approved leave, changed/stale requirements, service order, blocker order, estimates, permissions, GET-only behavior, query count, and pipeline non-invocation.
- Check result: `python manage.py check` reports no issues; `python manage.py makemigrations --check --dry-run` reports no changes; `python -m compileall -q core frontend`, strict UTF-8 decoding for all seven M5.2 implementation/test files, the downstream-service source scan, and `git diff --check` pass. The diff check reports only the repository's known LF-to-CRLF working-copy warnings.
- Scope result: no ranked candidate, exclusion explanation, per-requirement qualified-employee list, repair action, write path, persisted assessment, team enumeration, optimization run, or recommendation was added. M5.3 remains unstarted pending explicit approval.

### M5.3 Ranked eligible candidate evidence

- [x] Call `rank_employees_for_project(project)` through one tested orchestration boundary only after the M5.2 cheap preflight permits candidate assessment; do not recreate eligibility, weights, or score formulas in frontend code.
- [x] Present the returned eligible employees in deterministic rank order with the service-owned skill, workload, leave, experience, and final score components, units, period context, and manager-friendly definitions.
- [x] Link each candidate to the existing employee profile and relevant project requirement evidence without passing unsupported filters or implying selection for a team.
- [x] Provide distinct no-eligible-candidate and preflight-blocked states without displaying missing components as measured zero scores.
- [x] Test exact parity with the matching service, ties and deterministic ordering, inactive/unqualified employees, leave and workload boundaries, permissions, fixed-query behavior, and warm service/page timing.

Scope boundary: M5.3 displays the existing matching service's ranked candidate evidence only. It does not invent a score, explain non-candidates, allocate effort, enumerate teams, label a candidate as recommended, or create assignments.

Completion evidence:

- Created files: `frontend/templates/frontend/planning/_candidate_row.html` and `frontend/tests/test_project_planning_candidates.py`.
- Modified files: `core/services/workload.py`, `core/services/availability.py`, `core/services/matching.py`, `frontend/presenters/planning.py`, `frontend/views/planning.py`, `frontend/templates/frontend/planning/workspace.html`, `frontend/tests/test_project_planning_workspace.py`, `frontend/tests/test_project_planning_readiness.py`, and `frontend/CURRENT_TASKS.md`. No model, migration, form, URL, permission, JavaScript, static asset, or CSS file changed; `frontend/LESSONS_LEARNED.md` was not changed because its existing scalar-service/prefetch lesson already covers the reusable performance pattern.
- Orchestration result: `build_ranked_candidate_context(project, readiness)` is the single M5.3 boundary around `rank_employees_for_project(project)`. It returns without calling matching when M5.2 sets `candidate_assessment_allowed=False`; otherwise it calls the ranking service exactly once and preserves its result order and every returned component value without recalculation or resorting.
- Candidate result: eligible active employees render in the exact service order with a one-based display position and the service-owned skill, minimum workload-capacity, approved-leave availability, experience, and final-match values. Manager-friendly definitions identify score-versus-percentage units and the inclusive project period without copying score weights or formulas into frontend code. Equal-score employees retain the stable order returned by the service.
- Navigation and scope result: each employee name links to the existing profile with only its supported `start_date` and `end_date` parameters, and each row links to the existing stored project-requirements section. Copy explicitly says that candidate order does not select or recommend a team. Exact qualification rows, absence/exclusion reasons, requirement coverage gaps, optimization, and recommendations remain outside M5.3.
- State result: a readiness-blocked project shows `Candidate assessment paused` without calling matching, while an allowed assessment that returns no employees shows `No eligible candidates returned`. Neither state renders a candidate table or turns missing score evidence into numeric zero.
- Matching-performance result: the newly exposed ranking path contained employee/day query repetition. `rank_employees_for_project()` now bulk-loads current project requirements plus active employees' skills, overlapping non-cancelled assignments, and overlapping approved leave in five fixed queries, then passes those records into optional arguments on the existing matching, workload, and leave services. Scalar callers remain supported. Direct scalar-versus-prefetched tests prove exact workload, leave, component, eligibility, and final-score parity; the complete recommendation contract remains unchanged.
- Permission and read-only result: the established six-model planning-workspace read contract remains in force, including `Employee` view permission for candidate names/profile links. A user missing employee-view access receives 403 before candidate data is rendered. POST remains 405 and creates or changes no record.
- Query and timing result: the populated ranking service uses five fixed queries. A candidate workspace with one requirement, three eligible employees, one inactive qualified employee, one active unqualified employee, and no stored assignment rows uses 18 queries: four authenticated-shell queries, three stored-context queries (the empty assignment prefetch skips its child query), one recommendation-preflight query, five readiness-context queries, and five ranking queries. In the final complete-suite run, 25 warm Django test-client GETs recorded 12.435 ms median, 12.822 ms p95, 12.038 ms minimum, and 13.370 ms maximum.
- Test result: all 20 focused M5.1–M5.3 workspace tests passed in 1.115 s; the final focused workspace plus core recommendation-contract run passed all 25 tests in 1.934 s; and the final complete suite passed all 378 tests in 21.133 s. Coverage includes exact service parity, ties and repeated deterministic order, inactive/unqualified exclusion from the returned set, 0% workload and leave boundaries, links and supported period parameters, blocked/empty states, permissions, GET-only behavior, fixed query counts, source boundaries, and warm timing.
- Check result: `python manage.py check` reports no issues; `python manage.py makemigrations --check --dry-run` reports no changes; `python -m compileall -q core frontend`, strict UTF-8 decoding for all ten M5.3 implementation/test files, downstream-service/source-boundary scans, and `git diff --check` pass. The diff check reports only the repository's known LF-to-CRLF working-copy warnings.
- Defect result: no matching or scoring correctness defect was found. The ranking path's N+1 performance defect was fixed only by supplying prefetched records to the same validated services; service outputs and downstream recommendation behavior remain unchanged.
- Scope result: no non-candidate explanation, per-requirement qualification list, repair action, team allocation, feasibility enumeration, solver call, recommendation pipeline, attendance input, or persistence was added. M5.4 remains unstarted pending explicit approval.

### M5.4 Candidate exclusion explanations

- [x] Compare the current workforce with the exact employee set returned by `rank_employees_for_project(project)` and explain absence only through existing status, qualification, requirement, workload, leave, and service eligibility outcomes.
- [x] Centralize deterministic, manager-friendly exclusion labels and evidence links in a presenter without adding a shadow score, new eligibility rule, or speculative reason.
- [x] Distinguish inactive status, no qualifying requirement, incomplete project input, and other service-supported exclusion states; use a clear unavailable explanation when the existing backend cannot support a more specific claim.
- [x] Keep attendance completely absent from exclusion reasons and avoid implying that an excluded employee makes the whole project infeasible.
- [x] Test every supported exclusion reason, multiple simultaneous conditions, stale/deleted records, permissions, accessible status text, and exact agreement with the ranked candidate set.

Scope boundary: M5.4 explains why an employee is absent from the service-returned candidate list. It does not change matching behavior, rank excluded employees, create new rejection rules, or run optimization/recommendations.

Completion evidence:

- Created files: `frontend/selectors/planning.py`, `frontend/templates/frontend/planning/_candidate_exclusion_row.html`, and `frontend/tests/test_project_planning_exclusions.py`.
- Modified files: `frontend/presenters/planning.py`, `frontend/views/planning.py`, `frontend/templates/frontend/planning/workspace.html`, `frontend/tests/test_project_planning_candidates.py`, `frontend/tests/test_project_planning_workspace.py`, `frontend/CURRENT_TASKS.md`, and `frontend/LESSONS_LEARNED.md`. No model, migration, form, URL, permission, JavaScript, CSS, or core service file changed.
- Exact-set result: the view loads the current workforce and its skill evidence in two fixed queries only after readiness permits candidate assessment. `build_candidate_exclusion_context()` treats the employee IDs in the unchanged `rank_employees_for_project(project)` result as authoritative, subtracts that exact set from the current workforce, and never adds, removes, reranks, or rescores a candidate.
- Explanation result: an absent employee receives `Not active for matching` when status is not Active, or `No qualifying requirement` when the existing `employee_can_cover_requirement()` service confirms that current proficiency meets none of the stored project requirements. Status takes deterministic precedence when both conditions apply because it is the matching service's first gate. A qualifying active employee unexpectedly absent from a supplied service result receives `Explanation unavailable` rather than a guessed reason.
- State and stale-data result: incomplete project input keeps both matching and workforce comparison stopped and renders `Exclusion assessment paused`. A candidate snapshot containing an employee no longer present in the current workforce renders `Exclusion evidence unavailable` and asks for a refresh. A deleted employee is naturally absent from both the fresh workforce selector and fresh ranking result.
- Interface result: the existing planning workspace now includes a read-only `Why employees are not ranked` section with a captioned table, visible reason labels and explanations, employee-profile links carrying the supported project period, and an on-page project-requirements evidence link. Copy explicitly says that workload and approved dated leave shape scores without excluding an otherwise eligible active employee, and that one excluded employee does not by itself make the project infeasible. Exclusion reasons contain no attendance input or claim.
- Backend and scope result: the presenter delegates qualification to `employee_can_cover_requirement()` with prefetched requirements and skills and contains no eligibility formula, score, weight, workload/leave calculation, attendance query, feasibility enumeration, solver, recommendation selection, or generated explanation. Existing matching, availability, workload, feasibility, optimization, model validation, and recommendation behavior remain unchanged. M5.5 remains unstarted.
- Permission and read-only result: the established six-model planning read-permission contract still protects the page; a user without employee-view permission receives 403 before workforce evidence is loaded. The route remains GET-only, and a POST receives 405 without changing employee, proficiency, or project records.
- Query and timing result: the exclusion workforce selector uses two fixed queries for all employees and their current skill evidence. The complete M5.4 workspace fixture uses 20 queries and does not grow per employee. In the final complete-suite run, 25 warm Django test-client GETs with three eligible and four excluded employees recorded 14.121 ms median, 14.936 ms p95, 13.841 ms minimum, and 15.530 ms maximum.
- Test result: the final focused run passed all 6 M5.4 tests in 0.524 s; all 26 M5.1–M5.4 planning tests passed in 1.633 s; and the complete project suite passed all 384 tests in 20.951 s. Coverage includes exact candidate-set subtraction, both supported exclusion reasons, non-Active status variants, multiple simultaneous conditions, zero workload and leave score boundaries, incomplete input, unexplained service absence, stale/deleted employees, permissions, GET-only behavior, accessible visible status text, evidence links, fixed queries, and downstream-service/source boundaries.
- Check result: `python manage.py check` reports no issues; `python manage.py makemigrations --check --dry-run` reports no changes; and `python -m compileall -q core frontend` passes.
- Defect result: no application defect was found or fixed. The first combined regression run identified only two outdated M5.1 test expectations: its readiness-blocked fixture correctly retained the 14-query path because M5.4 skips workforce loading, and its old introduction-copy assertion predated the approved exclusion section. The expectations were updated without changing application behavior.
- Lessons result: `LESSONS_LEARNED.md` records the reusable rule to reconcile negative explanations against the authoritative service-returned set, reuse existing gate helpers, and fall back to unavailable whenever stored evidence cannot prove a reason.

### M5.5 Requirement qualification and coverage evidence

- [x] Show every stored project requirement with required level, priority, mandatory flag, quantity, effort, and current assignment-coverage context using existing requirement and assignment relationships.
- [x] Use existing matching/qualification and capacity services to expose the employees who can cover each requirement and the service-supported capacity evidence relevant to its required quantity.
- [x] Present covered quantity, remaining quantity, missing effort, no-qualified-employee, and insufficient-qualified-capacity states without treating current assignment coverage as proof of future feasibility.
- [x] Keep per-requirement employee and coverage ordering deterministic, fixed-query where records can be selected in bulk, and accessible through captioned tables or equivalent text.
- [x] Test optional and mandatory requirements, exact qualification levels, quantity boundaries, partial/complete coverage, overlapping assignments/leave, no requirements, no qualified employees, and consistency with the workspace readiness result.

Scope boundary: M5.5 adds read-only requirement-level qualification and current coverage evidence. It does not solve effort allocation, enumerate employee combinations, change coverage records, or claim that a qualified set is a feasible recommended team.

Completion evidence:

- Created files: `frontend/templates/frontend/planning/_requirement_evidence.html`, `frontend/templates/frontend/planning/_qualified_employee_row.html`, `frontend/templates/frontend/planning/_requirement_coverage_row.html`, and `frontend/tests/test_project_planning_requirement_evidence.py`.
- Modified files: `core/services/optimization.py`, `frontend/presenters/planning.py`, `frontend/views/planning.py`, `frontend/templates/frontend/planning/workspace.html`, `frontend/static/frontend/css/theme.css`, `frontend/CURRENT_TASKS.md`, and `frontend/LESSONS_LEARNED.md`. No model, migration, form, selector, URL, permission, or JavaScript file changed.
- Recovery result: the post-interruption audit found no partial M5.5 implementation. It preserved the complete approved M5.1–M5.4 work and continued from the still-unchecked M5.5 plan without restarting or duplicating prior work.
- Requirement result: every stored mandatory and optional requirement now has a deterministic evidence card showing skill, category, required level, priority, requirement type, required quantity, entered effort, current covered quantity, remaining quantity, qualified active headcount, and combined service-calculated available project capacity. Requirement order remains the established stored-context order.
- Qualification and capacity result: `get_requirement_capacity_evidence()` exposes the existing pre-solver per-requirement qualified employee set, headcount comparison, qualified capacity, and effort comparison. `get_fast_feasibility_issues()` now delegates those same decisions to the helper, preserving its issue codes, values, ordering, and short-circuit behavior. The M5.5 presenter consumes this output from the single optimization context already built by readiness; it does not query or recalculate matching, workload, leave, availability, or capacity.
- Availability result: qualified employee rows show exact current proficiency and available hours across the inclusive project dates. Those hours retain the existing Monday-to-Friday rules, exclude assignments to the assessed project, and include overlapping non-cancelled workload and approved dated leave. A regression fixture proves `40.00 h` for an unencumbered qualified employee and `16.00 h` for a qualified employee with 50% overlapping workload plus one approved leave day.
- Coverage result: current coverage uses the already-prefetched assignment/coverage relationships and the existing validation meaning of current coverage: Planned and Active assignments count; Completed and Cancelled assignments remain visible in the stored assignment table but do not satisfy current covered quantity. States distinguish quantity met, partial coverage, and no current coverage, with deterministic employee ordering and status text.
- State result: requirement evidence distinguishes qualified headcount available, qualified headcount below quantity, no qualified active employees, qualified capacity reaching entered effort, insufficient qualified capacity, missing/non-positive effort, paused qualification/capacity assessment, and no stored requirements. Stored requirement and coverage evidence remains visible when cheap readiness blockers correctly prevent optimization-context construction.
- Readiness consistency result: mandatory requirement headcount and capacity states come from the same helper and same prefetched optimization context used by readiness. A `56.00 h` qualified-capacity fixture passes a `40.00 h` target, then produces the same `insufficient_qualified_capacity` values in requirement evidence and readiness when the target becomes `60.00 h`.
- Interface and accessibility result: the planning workspace adds `Qualification, capacity, and current coverage` using the existing cards, facts, state panels, status badges, responsive tables, colors, typography, and breakpoints. Qualified-employee and current-coverage tables have visible headings, captions, column headers, row headers, status text, and profile links carrying only the supported project period. Copy repeatedly states that requirement evidence and stored coverage neither allocate effort nor prove a feasible whole-project team.
- Permission and read-only result: the established six-model workspace read contract still applies; a user missing employee-view permission receives 403. The route remains GET-only, and POST returns 405 without changing requirements, assignment coverage, or employee skills.
- Query and timing result: M5.5 adds no ORM query to an assessed workspace because it reuses the stored project relationships and readiness optimization context. The populated fixture uses 21 fixed page queries, including the four-query authenticated shell, four-query stored context, one preflight query, five optimization-context queries, five ranking queries, and two M5.4 workforce queries. In the final complete-suite run, 25 warm Django test-client GETs with three requirements, four active employees, and five stored coverage links recorded 18.008 ms median, 19.715 ms p95, 17.583 ms minimum, and 52.338 ms maximum.
- Test result: all 7 focused M5.5 tests passed in 0.642 s; the expanded M5.1–M5.5 planning plus core service-contract run passed all 38 tests in 3.234 s; and the complete project suite passed all 391 tests in 21.500 s. Coverage includes mandatory and optional requirements, exact and insufficient proficiency, exact quantity, partial/complete/no current coverage, completed/cancelled coverage exclusion, overlapping workload and approved leave, available-hour values, missing effort, no requirements, no qualified employees, capacity gaps, readiness parity, deterministic ordering, permissions, GET-only behavior, captions/scopes/status text, fixed queries, and downstream-pipeline source boundaries.
- Check result: `python manage.py check` reports no issues; `python manage.py makemigrations --check --dry-run` reports no changes; and `python -m compileall -q core frontend` passes.
- Defect result: one presentation defect was found and fixed during the focused run: the paused requirement-evidence title was present in presenter context but not rendered. The template now renders that state title alongside its explanation. A second initial failure was an over-broad source-test assertion that matched older readiness wording; the assertion was correctly narrowed to M5.5's own templates. No validated backend behavior defect was found.
- Lessons result: `LESSONS_LEARNED.md` records the reusable practice of exposing per-requirement evidence from the authoritative pre-solver service and making existing fast-feasibility checks delegate to it, so UI evidence and backend blockers cannot drift.

### M5.6 Repair navigation and workflow continuity

- [x] Map each incomplete-input, readiness, candidate, and requirement state to the existing project, requirement, assignment, employee-skill, leave, or employee-profile workflow that can provide evidence or repair it.
- [x] Show repair actions only when the signed-in user has the corresponding model permission; otherwise provide a truthful read-only explanation without exposing restricted records.
- [x] Preserve only destination-supported project and return context across workspace links, and provide an explicit path back to the same planning workspace after existing edits.
- [x] Keep all mutations inside the established CSRF-protected, validated, transactional workflows; the planning workspace remains GET-only and introduces no inline save or recommendation action.
- [x] Test every state-to-destination mapping, URL encoding, stale targets, permission combinations, return continuity, and zero-result destination.

Scope boundary: M5.6 connects the workspace to existing repair workflows only. It does not create a new mutation path, bypass validation, automatically change records, start optimization, or accept a recommendation.

Completion evidence:

- Created files: `frontend/navigation.py`, `frontend/presenters/planning_navigation.py`, and `frontend/tests/test_project_planning_repairs.py`.
- Modified files: `frontend/presenters/planning.py`; `frontend/views/planning.py`, `projects.py`, `requirements.py`, `assignments.py`, `coverage.py`, `employees.py`, `proficiencies.py`, and `leaves.py`; the shared table and affected existing form/detail templates under `frontend/templates/frontend/`; the planning workspace and its requirement, assignment, exclusion, evidence, and coverage row partials; `frontend/static/frontend/css/theme.css`; `frontend/tests/test_project_planning_workspace.py`; `frontend/CURRENT_TASKS.md`; and `frontend/LESSONS_LEARNED.md`. `core/services/optimization.py` received whitespace-only cleanup on three existing lines so the repository-wide diff check remains clean. No executable core calculation, model, migration, form class, selector, URL route, optimization, feasibility, recommendation, attendance, or JavaScript behavior changed.
- State-mapping result: project-date, missing-effort, no-mandatory-requirement, stale-input, insufficient-headcount, and insufficient-capacity readiness codes now point to the existing project, requirement, on-page evidence, refresh, or approved-leave destinations. Candidate blocked/empty/unavailable states point to readiness, current evidence, or refresh; exclusion rows point to period-aware employee profiles and, when permitted, existing employee/status or employee-skill maintenance. Requirement cards point to existing requirement, employee-skill evidence, assignment, coverage, and leave workflows according to their current stored/assessment state.
- Permission result: project, requirement, assignment, coverage, employee, employee-skill, and leave mutation links render only with their matching Django model permission. Leave evidence renders only with `core.view_leave`; users without it receive a truthful restricted-evidence explanation and no leave URL. Viewers remain read-only, Managers / Planners retain only their approved planning writes, and HR Administrators receive the established HR maintenance actions.
- Continuity and URL-safety result: the shared return helper accepts only a canonical local `frontend:project_planning` path, rejects schemes, hosts, nested query/fragment data, unrelated routes, cross-project returns on project-scoped flows, and deleted project targets, then rebuilds the canonical URL. Workspace links pass only destination-supported project dates, leave overlap/status filters, path IDs, and the encoded return target. Filter submissions retain that return target, and successful project, requirement, assignment, coverage, employee, proficiency, and leave workflows return to the same workspace; all original redirects remain unchanged without valid return context.
- Validation and mutation result: M5.6 adds no new POST endpoint, inline form, write service, or database transaction. Existing forms, model validation, `transaction.atomic()` blocks, permission decorators, CSRF inputs, error handling, and stale-record 404 behavior remain the only mutation paths. The planning route remains GET-only and POST returns 405 without changing project, requirement, assignment, coverage, proficiency, or leave records.
- Interface result: repair links use the existing workspace notice, state, card, button, table, typography, color, and responsive patterns. Manager-facing copy explains that repairs open validated existing workflows, distinguishes review actions from permitted updates, preserves the project period on employee profiles, provides explicit return links/cancel wording, and explains read-only or restricted states without exposing records.
- Query and boundary result: repair presentation performs no ORM or planning calculation on the workspace; the established populated M5.5 page remains at 21 fixed queries. Destination validation performs one existence check only when a return target is supplied. Zero-result approved-leave evidence retains its project filters and return path, while missing requirement/assignment destinations remain 404.
- Test result: all 10 focused M5.6 tests pass; the combined M5.1–M5.6 planning run passes all 43 tests; and the complete project suite passes all 401 tests. Coverage includes every readiness-code mapping, candidate and requirement destinations, Viewer/Manager/HR/custom restricted permissions, URL encoding and allow-list rejection, cross-project/deleted returns, stale record IDs, period/filter preservation, zero-result leave evidence, successful create/update/delete returns across existing workflows, GET-only behavior, and source boundaries excluding duplicated calculations or downstream recommendation work.
- Check result: `python manage.py check`, `python manage.py makemigrations --check --dry-run`, `python -m compileall -q core frontend`, edited-file UTF-8/trailing-whitespace scans, and `git diff --check` pass.
- Defect result: one initial leave-directory regression was found and fixed: a return-aware create URL was supplied to the empty-state template even for users without `add_leave`. The view now supplies that URL only with the corresponding permission, preserving the established read-only empty state. One M5.1 assertion was updated because its former prohibition on coverage navigation was intentionally superseded by M5.6.
- Lessons result: `LESSONS_LEARNED.md` records the reusable practice of resolving and canonicalizing a narrowly allow-listed return route, binding project-scoped workflows to the same project, and forwarding that context through both implicit form submissions and explicit confirmation/filter links.

### M5.7 Query, accessibility, and boundary hardening

- [x] Profile populated, incomplete, and large realistic planning workspaces against the authenticated-shell baseline; remove avoidable N+1 work without bypassing existing selectors or core services.
- [x] Verify project/requirement/assignment boundaries, no requirements, missing effort, no eligible employees, insufficient quantity/capacity, inactive employees, overlapping workload/approved leave, and stale or deleted targets.
- [x] Verify keyboard navigation, focus behavior, heading structure, status text, table captions/scopes, color-independent interpretation, responsive overflow, and readable alternatives for any supplemental visual.
- [x] Confirm deterministic candidate, exclusion, blocker, requirement, and evidence ordering across repeated warm requests, and record final query/service/response-time baselines.
- [x] Run focused Milestone 3 and 4 regressions and source audits proving that planning views do not duplicate calculations, use attendance, invoke team enumeration/OR-Tools/Gemini, or alter existing CRUD, permission, CSRF, validation, dashboard, and employee-insight contracts.

Scope boundary: M5.7 hardens and measures the implemented Milestone 5 workspace. It introduces no new feature unless a measured defect requires a narrowly scoped correction within the approved Milestone 5 plan.

Completion evidence:

- Created file: `frontend/tests/test_project_planning_hardening.py`.
- Modified file: `frontend/CURRENT_TASKS.md`. No application, model, migration, core service, selector, presenter, view, form, URL, template, CSS, JavaScript, permission, validation, CSRF, transaction, dashboard, employee-insight, planning-calculation, optimization, or recommendation behavior changed. `frontend/LESSONS_LEARNED.md` was not changed because the existing lessons on fixed-cost query budgets, authenticated-shell accounting, prefetched service parity, accessible evidence, and deterministic navigation already cover the reusable findings.
- Query result: the final role-based populated workspace uses 21 fixed queries: four authenticated-shell queries plus 17 planning queries. The large realistic workspace with 60 employees, 12 mandatory requirements, 24 current assignments/coverage links, 12 overlapping competing assignments, and six approved leave records also uses 21 queries, proving that query volume does not grow with workspace rows. The incomplete missing-effort workspace stops downstream assessment at eight queries: four shell plus four planning. No avoidable N+1 work was found, so no selector or service change was required.
- Final warm performance result: over seven Django test-client samples in the complete-suite run, the populated workspace recorded 9.279 ms service median / 9.977 ms p95 and 16.506 ms response median / 16.814 ms p95 with a 35,891-byte response. The incomplete workspace recorded 2.301 ms service median / 2.496 ms p95 and 7.051 ms response median / 7.265 ms p95 with a 21,986-byte response. The large workspace recorded 28.283 ms service median / 51.641 ms p95 and 62.747 ms response median / 63.696 ms p95 with a 173,951-byte response. Measurements include ORM and presenter work for service timing and full Django request/template rendering for response timing, but exclude browser/network latency and static-file transfer.
- Boundary result: behavioral tests keep project requirements, assignments, and coverage inside the routed project; preserve exact matching-service candidates; classify inactive and unqualified workforce records through the established exclusion presenter; and prove optimization-context available hours match the scalar effective-availability service with both overlapping workload and approved leave. Distinct no-requirement, missing-effort, no-eligible-employee, insufficient-headcount, insufficient-capacity, blocked-candidate, paused-evidence, cross-project, missing-project, and deleted project/requirement/assignment states all retain their established safe behavior and English messages.
- Determinism result: five repeated warm large-workspace requests preserve candidate, exclusion, requirement, per-requirement qualified-employee, current-coverage, requirement-state, and assignment order exactly. Three repeated capacity-boundary requests preserve blocker category and requirement-ID order. Existing M5 service-parity tests continue to prove that displayed candidate and capacity evidence comes from the current core services rather than a frontend recalculation.
- Accessibility result: rendered-page parsing proves one H1, no heading-level jumps, unique IDs, valid `aria-labelledby` / `aria-describedby` references, a working skip-link target, no positive tab order, no inline event handlers, and links with real destinations. Every planning table has exactly one caption, column and row header scopes, and one responsive overflow wrapper. Readiness, coverage, qualification, and capacity states include visible text labels rather than relying on color. The page has no supplemental chart, canvas, or SVG; its complete evidence is readable in semantic tables and definition lists. Source checks retain the global visible focus ring, reduced-motion handling, responsive requirement-state stacking, and Bootstrap horizontal table overflow.
- Architecture result: source audits prove the planning view/presenters/selectors/templates contain no scalar score, workload, leave, availability, or capacity recalculation; attendance query; feasible-team enumeration; OR-Tools solve; recommendation selection/explanation; or Gemini call. The approved orchestration boundaries remain singular: candidate ranking, optimization-context construction, and requirement-capacity evidence each have one frontend call site, and the planning page has no browser-side calculation.
- Regression and check result: all eight focused M5.7 tests passed in 1.609 s; the combined M5.1–M5.7 planning run passed all 51 tests in 4.450 s; the focused Milestone 3 CRUD/permission/CSRF/validation and Milestone 4 dashboard/employee-insight run passed all 189 tests in 9.308 s; and the complete project suite passed all 409 tests in 23.339 s. `python manage.py check` reports no issues; `python manage.py makemigrations --check --dry-run` reports no changes; `python -m compileall -q core frontend` and `git diff --check` pass, with only the repository's existing LF-to-CRLF working-copy warnings.
- Defect result: no measured application defect was found or corrected. M5.7 adds only regression/profiling coverage and completion evidence, preserving the validated backend and planning workspace behavior exactly. M5.8 remains unstarted pending explicit approval.

### M5.8 Milestone 5 verification

- [x] Verify every Milestone 5 route, template, navigation state, permission boundary, readiness state, candidate/exclusion mapping, requirement evidence row, repair link, and read-only contract.
- [x] Verify workspace values and blocker outcomes against existing models, model validation, selectors, and core preflight/matching/workload/leave/effective-availability services for feasible-looking, incomplete, infeasible-looking, stale, and empty scenarios.
- [x] Confirm the workspace makes no team-feasibility or recommendation claim without the later pipeline, attendance is absent from all planning inputs, and no frontend calculation duplicates a core rule.
- [x] Run the complete project suite, `python manage.py check`, migration-drift, compilation, UTF-8, whitespace, and `git diff --check`; record final query/performance baselines and reusable lessons.
- [x] Close Milestone 5 only when every exit criterion passes, leaving Milestone 6 unstarted pending explicit approval.

Scope boundary: M5.8 is verification and finalization only. It adds no new feature unless a real defect is found, and any correction must remain narrowly within Milestone 5.

Completion evidence:

- Created file: `frontend/tests/test_milestone5_verification.py`.
- Modified file: `frontend/CURRENT_TASKS.md`. No application, model, migration, core service, selector, presenter, view, form, URL, template, CSS, JavaScript, permission, validation, CSRF, transaction, planning calculation, optimization, recommendation, dashboard, or employee-insight behavior changed. `frontend/LESSONS_LEARNED.md` was not changed because the existing lessons already cover service ownership, staged planning assessment, prefetched parity, accessible evidence, fixed query costs, permission boundaries, safe return destinations, and route-family navigation.
- Route, template, navigation, access, and method result: `frontend:project_planning` still reverses and resolves at `/projects/<project_id>/planning/`, renders the workspace and all seven planning partials, and keeps Projects navigation active. Anonymous users redirect to sign-in, unassigned users are forbidden, and canonical Viewers, Managers / Planners, and HR Administrators retain access. Separate tests omitting each of the six required view permissions prove the complete project/requirement/assignment/coverage/employee/skill read boundary. POST and PUT remain 405 and do not mutate project, requirement, assignment, coverage, employee-skill, or leave records.
- Stored and service-value result: one acceptance fixture reconciles the project dates/estimate, mandatory effort total, requirement order, current assignment/coverage counts, exact candidate service results and score components, per-requirement qualified employees and capacity, current coverage/remaining quantity, and workforce exclusions against stored models, `get_project_profile()`, `get_recommendation_preflight()`, `rank_employees_for_project()`, `build_optimization_context()`, and `get_requirement_capacity_evidence()`. A competing assignment remains outside the routed project's stored assignment list while still affecting service-owned capacity, and approved leave retains its existing effective-availability meaning.
- State result: feasible-looking input passes readiness but is still labelled only as ready for candidate assessment. Missing mandatory effort stops candidate/exclusion assessment and pauses calculated requirement evidence; no eligible employees yields an insufficient-headcount blocker; exact eligible quantity with inadequate hours yields an insufficient-capacity blocker; no requirements yields a distinct empty requirement state; and an in-flight changed requirement yields only the stale-input refresh state. None of these states claims that a feasible team exists or does not exist.
- Candidate, exclusion, evidence, and repair result: candidates remain in the exact order and carry the exact skill, workload, leave, experience, and final-score components returned by the existing matching service. Inactive and unqualified employees receive only the supported deterministic exclusion reasons and no invented score. Mandatory and optional requirement evidence matches core capacity evidence and current stored coverage. HR repair actions resolve to the established project, requirement, assignment, coverage, employee, skill, and leave workflows with the canonical planning return path and supported project dates; Viewer mutation links remain absent while truthful read-only evidence remains visible.
- Separation result: inserting an absent attendance record leaves readiness, blocker order, every candidate score component, qualified capacity, coverage quantity, and requirement states identical. Runtime mocks prove a planning GET invokes candidate ranking once but does not call feasible-team enumeration, team-effort solving, recommendation selection, deterministic recommendation explanations, or Gemini summaries. Source audits prove planning Python/templates contain no duplicated scalar matching, workload, leave, availability, or capacity calculation and no attendance query, OR-Tools, Gemini, recommendation, or browser-side planning calculation. Visible copy continues to distinguish readiness, candidate ranking, and requirement evidence from a feasible-team or recommendation result.
- Final query and performance result: the M5.8 role-based acceptance workspace uses 21 fixed page queries: four authenticated-shell plus 17 planning queries. In the complete-suite run, seven warm samples recorded a 9.559 ms service median / 10.128 ms p95 and a 16.650 ms full-response median / 47.070 ms p95 with a 36,007-byte response. The final M5.7 scale baselines in the same run remained fixed: incomplete input used 4 service / 8 page queries with 2.372 ms service and 7.083 ms response medians; the populated workspace used 17 / 21 queries with 9.475 ms and 16.894 ms medians; and the 60-employee, 12-requirement, 24-coverage-link workspace used the same 17 / 21 queries with 27.974 ms and 62.021 ms medians. Measurements use the in-memory SQLite Django test client and exclude browser/network latency and static-file transfer.
- Test result: all six focused M5.8 tests passed in 1.385 s; all 57 combined M5.1–M5.8 planning tests passed in 5.360 s; the M5.8 plus core model/service-contract run passed all 20 tests in 1.737 s; and the complete project suite passed all 415 tests in 24.799 s. Coverage includes every Milestone 5 route/template, all required permissions, canonical roles, GET-only behavior, model/service parity, ready/incomplete/headcount/capacity/stale/empty states, candidate and exclusion mappings, requirement evidence, repair continuity, attendance isolation, downstream pipeline non-invocation, and final query/performance budgets.
- Check result: `python manage.py check` reports no issues; `python manage.py makemigrations --check --dry-run` reports no changes; `python -m compileall -q core frontend`, strict UTF-8 decoding and trailing-whitespace scanning across all 24 Milestone 5 planning/documentation files, planning source-boundary audits, and `git diff --check` pass. The diff check reports only the repository's existing LF-to-CRLF working-copy warnings.
- Defect result: no application defect was found or fixed. M5.8 adds only final acceptance coverage and completion evidence, preserving the validated backend and current planning workspace UI exactly.
- Closure result: all eight Milestone 5 exit criteria pass. Milestone 5 is complete and closed; Milestone 6 remains unstarted pending explicit approval.

## Milestone 5 exit criteria

- [x] A permitted planner can open one read-only project workspace that accurately combines stored dates, estimates, requirements, current assignments, coverage, and candidate context.
- [x] Readiness assessment exposes incomplete or unsupported planning inputs before expensive work and distinguishes those blockers from a proven no-feasible-team result.
- [x] Ranked candidates and their skill, workload, leave, experience, and final-score components exactly match `rank_employees_for_project()` without a duplicated formula.
- [x] Employees absent from the candidate list receive only service-supported, deterministic explanations and are never ranked with an invented score.
- [x] Every requirement shows accurate qualification, quantity, current coverage, effort, and capacity evidence without claiming that this proves team feasibility.
- [x] Every blocker and evidence state reaches an accurate existing record or permitted repair workflow while retaining clear return context.
- [x] Access rules, empty/boundary/stale states, accessibility, deterministic ordering, query behavior, and warm performance baselines are verified for realistic data.
- [x] Attendance remains outside planning decisions, no recommendation/optimization pipeline runs in Milestone 5, the complete suite and Django checks pass, and Milestone 6 remains unstarted until explicit approval.

## Completed Milestone 4 task breakdown

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

- [x] Define and test the reporting-period meaning of each planned KPI before rendering it: headcount by employee status, available capacity, allocated capacity, employees on approved dated leave, active projects, and over-capacity risk.
- [x] Build optimized selectors for stored aggregates and thin presenters that call existing workload, leave, and effective-availability services for calculated values; do not recreate service formulas in frontend code.
- [x] Render accessible KPI cards with units, reporting-period context, manager-friendly definitions, clear zero/empty states, and explicit weekday/date-based assumptions.
- [x] Keep employment status separate from dated approved leave and distinguish scheduled allocation from effective availability wherever both appear.
- [x] Test boundary dates, overlapping assignments and leave, inactive employees, weekends, project statuses, over-capacity cases, empty datasets, permission scopes, service delegation, fixed query behavior, and warm timing.

Scope boundary: M4.2 adds the six summary signals only. It does not add charts, employee timelines, attendance trends, recommendation inputs, or new calculation rules.

Completion evidence:

- Created files: `frontend/selectors/dashboard.py` and `frontend/tests/test_dashboard_kpis.py`.
- Modified files: `core/services/availability.py`, `core/services/effective_availability.py`, `core/services/workload.py`, `frontend/presenters/dashboard.py`, `frontend/views/landing.py`, `frontend/templates/frontend/dashboard/landing.html`, `frontend/static/frontend/css/theme.css`, `frontend/tests/test_dashboard_filters.py`, `frontend/tests/test_foundation_verification.py`, `frontend/CURRENT_TASKS.md`, and `frontend/LESSONS_LEARNED.md`.
- KPI-definition result: headcount is the filtered employee total with stored-status breakdown; effective available capacity is the sum of existing service-calculated daily available hours over selected Monday-to-Friday dates; scheduled allocation is the service-owned conversion of non-cancelled assignment percentages to daily hours over those same working dates; approved leave counts distinct filtered employees with an approved leave record overlapping any selected calendar date; projects active in period are stored projects whose dates overlap the inclusive period after the project-status filter; and over-capacity risk counts distinct filtered employees above 100% scheduled allocation on at least one selected working day.
- Filter and boundary result: all M4.1 start date, end date, department, employee-status, and project-status behavior remains intact. Tests cover both inclusive boundaries, overlapping assignments, overlapping approved leave without double-counting, pending and cancelled records, every project status, inactive and on-leave employment statuses, weekend-only periods, and filtered and fully empty datasets.
- Service-boundary result: the dashboard presenter delegates working-day selection, approved-leave overlap, effective daily availability, scheduled daily hours, and current workload to `core` services. The scalar service paths used inside the employee/day aggregation accept optional prefetched records while retaining their existing default ORM behavior; parity tests prove prefetched and legacy query-backed results agree. Templates and browser code perform no workforce calculation.
- Interface result: the existing dashboard context remains in place and now presents exactly six responsive, accessible summary cards with explicit units, inclusive reporting context, definitions, zero states, Monday-to-Friday/no-holiday wording, and clear separation between stored employment status, dated approved leave, scheduled work, and effective availability. No chart, timeline, attendance, drill-down, recommendation, or write action was introduced.
- Permission and method result: the existing dashboard guard still requires both `core.view_employee` and `core.view_project`; anonymous, no-permission, and single-permission behavior remains covered, canonical viewers retain access, and the route remains GET-only.
- Query and timing result: a populated role-based dashboard uses nine fixed queries: the four-query authenticated shell, one department-facet query, three prefetched KPI workforce queries, and one project count. Adding related assignments and projects does not increase the query count. The final complete-suite populated KPI run recorded a 9.729 ms median and 11.199 ms p95 across 25 warm requests; the empty initial dashboard uses seven queries and recorded an 8.011 ms median and 9.559 ms p95.
- Commands run:
  - `python manage.py test frontend.tests.test_dashboard_kpis frontend.tests.test_dashboard_filters frontend.tests.test_landing --verbosity 1`
  - focused 41-test KPI, filter, foundation, and core-service command
  - `python manage.py test frontend --verbosity 1`
  - `python manage.py test --verbosity 1`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py check`
  - `python -m compileall -q core frontend`
  - edited-file trailing-whitespace scan
  - `git diff --check`
- Result: all 25 focused dashboard tests passed in 0.976 s; all 41 combined KPI/filter/foundation/core tests passed in 2.327 s; all 293 frontend tests passed in 13.434 s; and the final complete 307-test project suite passed in 14.921 s. Django system checks, compilation, migration drift, and whitespace checks pass.
- Lessons result: `LESSONS_LEARNED.md` records the reusable pattern of supplying prefetched records to scalar core services so aggregate pages retain service-owned rules without employee-by-day query growth.

### M4.3 Capacity and utilization distributions

- [x] Add filtered workforce capacity and utilization distributions using the M4.1 reporting period and the same service-backed values established in M4.2.
- [x] Define stable, manager-readable distribution bands and centralize presentation shaping outside templates without changing the meaning of workload, capacity, or availability.
- [x] Render an accessible data table or text equivalent as the primary evidence for every visualization, with charts remaining supplemental and using the existing visual system.
- [x] Provide useful all-zero, no-employee, and incomplete-context states without presenting missing data as zero capacity.
- [x] Test band boundaries, exact table/chart agreement, filtered results, empty states, accessibility semantics, permission boundaries, deterministic serialization, query count, and warm timing.

Scope boundary: M4.3 visualizes the existing filtered workforce measures only. It does not add employee timelines, attendance trends, staffing scores, or browser-side business calculations.

Completion evidence:

- Created files: `frontend/templates/frontend/dashboard/_distribution.html` and `frontend/tests/test_dashboard_distributions.py`.
- Modified files: `core/services/effective_availability.py`, `frontend/presenters/dashboard.py`, `frontend/views/landing.py`, `frontend/templates/frontend/dashboard/landing.html`, `frontend/static/frontend/css/theme.css`, `frontend/CURRENT_TASKS.md`, and `frontend/LESSONS_LEARNED.md`.
- Measure result: each filtered employee's M4.2 effective available hours and scheduled allocation hours are compared with the same period's service-owned stored weekday capacity. The existing Monday-to-Friday assumption remains unchanged; employee status, approved leave, non-cancelled assignment workload, and over-capacity behavior retain their M4.2 meanings.
- Band result: effective availability uses No effective capacity at 0%, Limited above 0% and below 25%, Partial from 25% to below 75%, and Strong at 75% or more. Scheduled utilization uses Unallocated at 0%, Light above 0% and below 50%, Moderate from 50% to below 80%, High from 80% through 100%, and Over capacity above 100%. Boundaries and deterministic one-decimal share serialization are centralized in the dashboard presenter.
- Evidence result: each distribution renders an accessible captioned table first, including band definition, employee count, and workforce share. Supplemental CSS bars consume the exact same server-shaped band records and serialized shares, are hidden from assistive technology to avoid duplicate narration, and introduce no browser-side workforce calculation or JavaScript change.
- State result: no matching employees and periods without Monday-to-Friday dates suppress the distributions with distinct explanations. Employees without positive stored weekly capacity are placed in a Not classified row rather than a 0% capacity band. Separate all-zero messages explain genuine zero effective availability and zero scheduled work.
- Filter, access, and scope result: the existing inclusive reporting period plus department and employee-status filters scope both distributions; project status retains its M4.1/M4.2 project-only meaning. The existing employee/project read-permission guard and GET-only route remain unchanged. No chart library, employee timeline, attendance trend, staffing score, drill-down, write action, model, or migration was added.
- Query and timing result: the populated dashboard remains at nine fixed queries, unchanged from M4.2, because the distributions reuse the already-prefetched employee measures. The final complete-suite M4.3 fixture recorded a 10.203 ms median and 11.179 ms p95 across 25 warm Django test-client requests with seven employees.
- Commands run:
  - `python manage.py test frontend.tests.test_dashboard_distributions --verbosity 1`
  - `python manage.py test frontend.tests.test_dashboard_distributions frontend.tests.test_dashboard_kpis frontend.tests.test_dashboard_filters --verbosity 1`
  - `python manage.py test frontend --verbosity 1`
  - `python manage.py test --verbosity 1`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py check`
  - `python -m compileall -q core frontend`
  - edited-file trailing-whitespace scan
  - `git diff --check`
- Result: all 9 focused M4.3 tests passed in 0.429 s; all 31 combined dashboard distribution/KPI/filter tests passed in 1.360 s; all 302 frontend tests passed in 13.955 s; and the complete 316-test project suite passed in 15.064 s. Django system checks, compilation, migration drift, and whitespace checks pass.
- Lessons result: `LESSONS_LEARNED.md` records the reusable requirement to render accessible evidence and supplemental visuals from one presenter-owned band sequence and one deterministic serialized share.

### M4.4 Employee workload and availability timeline

- [x] Extend the existing employee profile with a reporting-period workload and effective-availability timeline driven by the shared M4.1 date contract.
- [x] Use existing workload and effective-availability services for each displayed value, preserving assignment status/date, inactive employee, weekend, approved-leave, and daily-capacity semantics.
- [x] Show readable daily or period-bucket evidence with assignment and approved-leave context, an accessible table equivalent, and explicit Monday-to-Friday assumptions.
- [x] Preserve the selected reporting period when moving between dashboard evidence and an employee profile, with clear empty and partial-data states.
- [x] Test service delegation, date boundaries, weekends, overlapping work, approved versus non-approved leave, inactive status, missing employees, permissions, accessibility, query behavior, and warm timing.

Scope boundary: M4.4 adds read-only employee insight. It does not edit assignments or leave, create a shared calendar, alter availability formulas, or run recommendations.

Completion evidence:

- Created files: `frontend/templates/frontend/employees/_timeline_row.html` and `frontend/tests/test_employee_timeline.py`.
- Modified files: `core/services/workload.py`, `frontend/forms/dashboard.py`, `frontend/presenters/dashboard.py`, `frontend/presenters/employees.py`, `frontend/selectors/employees.py`, `frontend/static/frontend/css/theme.css`, `frontend/templates/frontend/employees/detail.html`, `frontend/tests/test_employee_detail.py`, `frontend/views/employees.py`, `frontend/views/landing.py`, `frontend/CURRENT_TASKS.md`, and `frontend/LESSONS_LEARNED.md`.
- Reporting-period result: the employee profile now uses the same required, inclusive start/end contract and current-calendar-month defaults as the dashboard. Valid dates remain in the GET form, the reporting-period-only dashboard return link retains both dates, and invalid or reversed periods show field errors while leaving the established point-in-time profile visible and unchanged.
- Daily evidence result: every calendar date in the selected period receives service-calculated stored daily capacity, scheduled workload percentage, scheduled daily hours, and effective available hours. The evidence preserves inclusive assignment boundaries, non-cancelled assignment status rules, overlapping workloads above 100%, weekends, inactive employees, and dated approved-leave behavior; pending, rejected, and cancelled leave remain non-effective.
- Context and accessibility result: contributing assignment names, stored statuses, allocations, and date boundaries plus approved-leave type, status, and dates explain each daily value. The complete evidence is a captioned table with row and column headers; a horizontally scrollable daily strip is supplemental and hidden from assistive technology. Monday-to-Friday/no-holiday assumptions and the distinction between employment status and dated approved leave remain explicit.
- Empty and partial-state result: distinct messages cover no overlapping assignments, no approved leave, weekend-only periods, invalid dates, and missing stored weekly capacity without treating missing capacity as available work. The existing profile identity, current capacity cards, assignment list, skills, and upcoming approved-leave sections remain intact.
- Service and query result: the timeline presenter delegates every workforce value to existing core services using prefetched assignment and leave records. `get_current_assignments()` exposes the workload service's existing contributing-record rule so evidence does not duplicate status/date logic. The employee selector still loads the employee, scoped leave, scoped assignment/project, and skill collections in four fixed queries, and the populated authenticated page remains at 12 total queries regardless of the four-day fixture's related-record count.
- Permission and scope result: the existing `core.view_employee` guard still redirects anonymous users and rejects authenticated users without permission; missing employees return 404. The timeline adds no assignment or leave edit, mutation endpoint, JavaScript calculation, model, migration, holiday calendar, formula change, attendance summary, recommendation behavior, or M4.5 work.
- Query and timing result: the final complete-suite M4.4 fixture used 12 queries and recorded an 11.483 ms median and 15.005 ms p95 across 25 warm Django test-client requests for four calendar dates, four assignment records, and three leave records.
- Commands run:
  - targeted 20-test employee-profile and M4.4 timeline command
  - combined 56-test core-service, dashboard filter/KPI/distribution, employee-profile, and timeline command
  - `python manage.py test frontend --verbosity 1`
  - `python manage.py test --verbosity 1`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py check`
  - `python -m compileall -q core frontend`
  - edited-file trailing-whitespace scan
  - `git diff --check`
- Result: all 20 targeted profile/timeline tests passed in the final 1.217 s rerun; all 56 combined service/dashboard/profile/timeline tests passed in 3.778 s; all 312 frontend tests passed in 15.403 s; and the final complete 326-test project suite passed in 16.888 s. Django system checks, compilation, migration drift, and whitespace checks pass.
- Lessons result: `LESSONS_LEARNED.md` records the reusable rule that explanatory contributing records should come from the same service-owned eligibility selector as their scalar calculation, preventing evidence from drifting from backend date/status semantics.

### M4.5 Descriptive attendance summaries and trends

- [x] Add reporting-period attendance summaries using the existing attendance service outputs for total, present, absent, late, remote, and half-day records plus the existing absenteeism and late-rate definitions.
- [x] Present attendance as descriptive operational history with clear record-count denominators, date context, and accessible trend evidence; never label it as a staffing score or recommendation factor.
- [x] Link attendance summaries to the filtered attendance records that explain them while preserving employee and date context where supported.
- [x] Handle no records, partial time coverage, and status-only records without inventing missing observations or changing employee status.
- [x] Test service delegation, date boundaries, every attendance status, zero-denominator behavior, filtered links, empty states, permissions, table/chart agreement, query count, and warm timing; retain a regression proving recommendation inputs are unchanged.

Scope boundary: M4.5 is read-only and descriptive. It does not change attendance calculations, attendance CRUD, employee availability, matching, optimization, or recommendation selection.

Completion evidence:

- Created files: `frontend/templates/frontend/employees/_attendance_status_row.html`, `frontend/templates/frontend/employees/_attendance_record_row.html`, and `frontend/tests/test_employee_attendance_insights.py`.
- Modified files: `core/services/attendance.py`, `frontend/presenters/employees.py`, `frontend/selectors/employees.py`, `frontend/views/employees.py`, `frontend/templates/frontend/employees/detail.html`, `frontend/static/frontend/css/theme.css`, `frontend/tests/test_employee_detail.py`, `frontend/tests/test_employee_timeline.py`, `frontend/CURRENT_TASKS.md`, and `frontend/LESSONS_LEARNED.md`.
- Summary result: employee profiles with attendance access now show reporting-period attendance record totals; Present, Absent, Late, Remote, and Half day counts; existing absenteeism rate; and existing late rate. The summary uses the same inclusive M4.1/M4.4 start and end dates, labels every denominator as attendance records, and identifies the late-rate denominator as non-absent records.
- Trend and evidence result: a captioned status table is the primary status-mix evidence, and supplemental CSS bars consume the exact same presenter-owned status sequence, count, and deterministic one-decimal share. A chronological recorded-attendance table is the primary trend evidence, with a supplemental date/status strip from the same ordered records. Recorded arrival/departure times remain visible where stored, while status-only records explicitly say which times are not recorded.
- Coverage and zero-state result: the page states that dates without records are not inferred as any attendance status and never treats the selected period's calendar or working days as attendance observations. No-record periods suppress rate interpretation and trends with a clear empty state. Zero-denominator service fallbacks display as `Not available` for no records or no non-absent records, while a measured zero with a positive denominator remains a valid 0% rate.
- Evidence-link result: the total, absent, late, and nonzero status summaries link to the existing attendance directory with only parameters that destination validates: employee, attendance status where applicable, inclusive `from_date`, inclusive `to_date`, and ascending date sort. Tests follow a filtered link and prove its record matches the source summary.
- Service-boundary result: attendance record selection, status totals, absenteeism, and late rate remain owned by `core.services.attendance`. Its scalar APIs now accept optional prefetched records while preserving the default ORM path, and parity tests prove both paths return identical values. `non_absent_days` is included in the service summary so presentation code does not recreate the late-rate denominator.
- Permission, read-only, and isolation result: the established employee profile remains accessible with `core.view_employee`; attendance is queried and rendered only when the user also has `core.view_attendance`. No attendance record or employee status changes on GET. No attendance CRUD, model, migration, workforce calculation, availability, matching, optimization, recommendation, or M4.6 behavior was added or changed. A before/after matching regression proves adding an Absent attendance record does not change any recommendation input component.
- Query and timing result: an authorized populated employee profile uses 13 fixed queries: the prior 12-query profile/timeline budget plus one period-scoped attendance query. The final complete-suite M4.5 fixture recorded a 12.611 ms median and 13.807 ms p95 across 25 warm Django test-client requests with five in-period records spanning every attendance status.
- Commands run:
  - `python manage.py test frontend.tests.test_employee_attendance_insights --verbosity 2`
  - combined 55-test employee profile/timeline/attendance insight/directory command
  - combined 91-test core contract, dashboard, employee profile/timeline, attendance insight/directory command
  - `python manage.py test frontend --verbosity 1`
  - `python manage.py test --verbosity 1`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py check`
  - `python -m compileall -q core frontend`
  - edited-file trailing-whitespace scan
  - `git diff --check`
- Result: all 12 focused M4.5 tests passed in 0.726 s; all 55 combined employee/attendance tests passed in 2.455 s; all 91 combined service/dashboard/employee/attendance tests passed in 4.771 s; all 324 frontend tests passed in 15.431 s; and the complete 338-test project suite passed in 16.423 s. Django system checks, compilation, migration drift, and whitespace checks pass.
- Lessons result: `LESSONS_LEARNED.md` records the reusable requirement to distinguish a service's safe numeric zero fallback from a measured zero rate whenever the denominator is absent.

### M4.6 Aggregate evidence and drill-down continuity

- [x] Connect every dashboard KPI and distribution to the filtered employee, project, assignment, leave, or on-page evidence that explains the aggregate.
- [x] Define an explicit mapping from each aggregate to its evidence destination and preserve only query parameters that the destination understands.
- [x] Provide manager-friendly context when an aggregate is broader than an existing directory filter, using an on-page evidence table instead of a misleading link.
- [x] Preserve reporting-period and applicable department/status context through dashboard-to-profile and profile-to-directory navigation, with clear return paths.
- [x] Test every aggregate/evidence mapping, URL encoding, stale parameters, zero-result destinations, permission boundaries, and consistency between displayed totals and linked records.

Scope boundary: M4.6 integrates existing Milestone 4 views and evidence. It adds no new KPI, visualization, calculation, write workflow, or recommendation behavior.

Completion evidence:

- Created files: `frontend/templates/frontend/dashboard/_employee_evidence_row.html`, `frontend/templates/frontend/dashboard/_leave_evidence_row.html`, `frontend/templates/frontend/dashboard/_project_evidence_row.html`, and `frontend/tests/test_dashboard_evidence.py`.
- Modified files: `frontend/selectors/dashboard.py`, `frontend/presenters/dashboard.py`, `frontend/views/landing.py`, `frontend/views/employees.py`, `frontend/views/attendance.py`, `frontend/views/leaves.py`, `frontend/templates/frontend/components/table.html`, `frontend/templates/frontend/dashboard/landing.html`, `frontend/templates/frontend/dashboard/_distribution.html`, `frontend/templates/frontend/employees/detail.html`, `frontend/templates/frontend/employees/list.html`, `frontend/templates/frontend/employees/_employee_row.html`, `frontend/templates/frontend/attendance/list.html`, `frontend/templates/frontend/attendance/_attendance_row.html`, `frontend/templates/frontend/leaves/list.html`, `frontend/templates/frontend/leaves/_leave_row.html`, `frontend/static/frontend/css/theme.css`, `frontend/tests/test_dashboard_distributions.py`, `frontend/tests/test_employee_detail.py`, `frontend/tests/test_employee_timeline.py`, `frontend/tests/test_employee_attendance_insights.py`, and `frontend/CURRENT_TASKS.md`.
- Aggregate-mapping result: headcount and its nonzero stored-status counts open the exact filtered employee directory. Effective available capacity, scheduled allocation, both distributions, and over-capacity risk point to one on-page employee evidence table built from the existing KPI/distribution measures; each row links to that employee's reporting-period timeline, where the contributing assignments are already exposed by the service-backed M4.4 evidence. Approved dated leave points to a distinct-employee on-page table and then to the exact employee/approved/overlap-date leave records. Active projects point to an on-page overlap table because the project directory's start-after/end-before contract asks a different question.
- Consistency result: employee evidence totals equal the displayed available and scheduled KPI totals, risk rows expose the same above-100% dates used by the risk count, leave evidence keeps multiple overlapping records from inflating the distinct-employee KPI, project evidence contains exactly the filtered overlapping project set, and every nonzero distribution band reaches the employee evidence while zero bands remain truthful non-links. No presenter, template, or JavaScript duplicates a workforce or attendance formula.
- Filter and navigation result: destination-specific query builders translate dashboard `employee_status` to the employee directory's `status`, serialize special characters safely, and omit unsupported aggregate filters from leave-record links. Validated start date, end date, department, employee status, and project status travel from dashboard evidence to employee profiles; profiles retain them when changing dates and provide explicit returns to the same dashboard and filtered workforce view. The workforce directory carries that context into profile links, while leave and attendance directories retain their supported inclusive dates and employee context and provide a clear profile/dashboard return.
- Broader-aggregate result: the dashboard explains why distinct approved-leave employees and date-overlapping projects are shown on-page rather than linking to semantically different directory filters. Populated, filtered-empty, and fully zero destinations remain usable and explicit.
- Permission and read-only result: the established dashboard requirement of `core.view_employee` plus `core.view_project` is unchanged. Record-level leave dates, types, and directory links render only with `core.view_leave`; users who retain dashboard access without that permission receive a clear restricted-evidence state. Existing employee-profile attendance permission behavior remains unchanged. M4.6 adds no POST action, model change, mutation, recommendation behavior, or browser-side business calculation.
- Query result: the populated dashboard remains fixed at nine queries because the existing project aggregate query now returns its evidence rows instead of issuing a separate evidence query. Employee profiles use fourteen fixed queries after validating the complete dashboard filter context through the stored department choices; selector and service ownership are unchanged.
- Commands run:
  - `python manage.py test frontend.tests.test_dashboard_evidence --verbosity 2`
  - combined dashboard-evidence/distribution/employee-profile/timeline/attendance-insight command
  - `python manage.py test frontend --verbosity 1`
  - `python manage.py test --verbosity 1`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py check`
  - `python -m compileall -q core frontend`
  - UTF-8 mojibake source scan
  - `git diff --check`
- Result: all 9 focused M4.6 tests passed in 0.280 s; all 50 combined evidence/distribution/profile/timeline/attendance tests passed in 2.582 s; all 333 frontend tests passed in 16.890 s; and the complete 347-test project suite passed in 17.774 s. Django system checks, compilation, migration drift, UTF-8 source, and whitespace checks pass.
- Lessons result: no reusable lesson beyond the existing service-ownership, destination-filter allow-list, accessible evidence, permission-boundary, and navigation-context guidance was discovered, so `LESSONS_LEARNED.md` was not changed for M4.6.

### M4.7 Query, accessibility, and boundary hardening

- [x] Profile dashboard, distribution, employee-timeline, and attendance-summary queries against the authenticated-shell baseline and remove avoidable N+1 work without bypassing existing services.
- [x] Verify realistic populated, large-range, boundary-date, weekend, empty, and filtered-empty cases; keep any reporting range guard manager-friendly and consistent across views if measurement proves one necessary.
- [x] Verify keyboard navigation, heading structure, focus behavior, status text, chart alternatives, table captions, and color-independent interpretation across Milestone 4 pages.
- [x] Confirm filters and calculations remain deterministic across pagination and repeated warm requests, and record the final query and response-time baselines.
- [x] Run focused regression suites for Milestones 2 and 3 to prove the dashboard work did not change CRUD, validation, permissions, CSRF, deletion, leave, attendance, matching, or recommendation contracts.

Scope boundary: M4.7 hardens and measures implemented Milestone 4 behavior. It introduces no product feature unless a measured defect requires a narrowly scoped correction.

Completion evidence:

- Created file: `frontend/tests/test_milestone4_hardening.py`.
- Modified files: `core/services/workload.py`, `frontend/forms/dashboard.py`, `frontend/presenters/employees.py`, `frontend/selectors/employees.py`, `frontend/tests/test_employee_detail.py`, `frontend/tests/test_employee_timeline.py`, `frontend/tests/test_employee_attendance_insights.py`, `frontend/CURRENT_TASKS.md`, and `frontend/LESSONS_LEARNED.md`.
- Query defect and correction: the employee profile selector already loaded assignments and leave for the current date and selected timeline, but three scalar profile values issued four additional ORM queries. The selector now retains calculation collections from the union of current, upcoming-display, and timeline scopes, and the presenter passes them through the existing service-owned optional-record paths. `calculate_available_capacity` and `calculate_available_hours` gained optional assignment collections while their default query-backed behavior remains unchanged. An edge-status parity test includes a non-cancelled completed assignment that overlaps the calculation date and proves the prefetched workload, weekly availability, and daily effective availability exactly match the legacy service paths with zero presenter queries.
- Query result: the filtered dashboard and both distributions remain fixed at nine queries: four authenticated-shell queries plus department choices, employees, assignments, approved leave, and projects. A populated attendance-authorized employee profile containing workload timeline and attendance summary now uses ten fixed queries: four shell queries, one department-choice query, and five selector queries for employee, leave, assignments/projects, skills, and attendance. This removes the four avoidable scalar queries from M4.6's fourteen-query profile without changing selector cardinality or service semantics.
- Reporting-range defect and correction: a presenter-only probe confirmed linear unbounded daily expansion (366 days/2.3 ms, 1,826 days/10.8 ms, and 9,131 days/62.8 ms before template rendering), while an accepted 366-day profile response is 351,640 bytes. The shared reporting form now accepts at most 366 inclusive calendar days and attaches the manager-friendly `Choose a reporting period of 366 days or fewer.` error to the end date. Both dashboard and employee profile use this same validation; 366 days render normally and 367 days suppress calculated reporting content while leaving the profile's stored overview intact.
- Final realistic warm baseline over seven Django test-client GETs using in-memory SQLite: the 24-employee/31-day dashboard used 9 queries, 22.013 ms median, 22.681 ms p95, and 62,809 response bytes; the 31-day employee timeline plus 20 attendance records used 10 queries, 24.626 ms median, 25.560 ms p95, and 75,363 bytes; the 24-employee/366-day dashboard used 9 queries, 47.871 ms median, 70.142 ms p95, and 56,435 bytes; and the 366-day employee timeline/attendance page used 10 queries, 72.507 ms median, 73.538 ms p95, and 351,640 bytes. Measurements include request handling, ORM/service work, and template rendering but exclude browser/network latency and static-file transfer.
- Accessibility result: automated rendered-markup audits cover the populated dashboard and employee insight page. Both have English document language, a skip link before main content, a programmatically focusable main landmark, unique IDs, resolved `aria-labelledby`/`aria-describedby` references, one initial `h1` with no skipped heading levels, captions on every table, row/column scope on every table header, no positive tabindex or inline event handlers, and keyboard-native links/buttons. Supplemental distribution, workload, and attendance visuals remain `aria-hidden`; their readable tables expose identical labels and values first. Status labels and timeline states remain visible text with decorative status dots hidden, and the theme retains global `:focus-visible`, visible skip-link focus, and reduced-motion handling.
- Boundary and determinism result: same-day and inclusive assignment/leave/project boundaries remain covered by the KPI/timeline suites; 366/367-day edges, weekend-only periods, unconfigured capacity, no working days, no employees, filtered-empty workforce, no projects, attendance zero denominators, and invalid date order all retain distinct non-misleading states. Three repeated dashboard requests returned identical KPI values, distribution band order/count/share serialization, and employee evidence order. A 24-employee directory stayed deterministic across its 20-row first page and 4-row second page with no overlap and an identical repeated second page.
- Regression result: the focused Milestone 2 suite covers model/service contracts, matching and recommendation contracts, permissions, employee/skill/proficiency CRUD, validation, CSRF, deletion, failure rollback, and directories; all 106 tests passed. The focused Milestone 3 suite covers route/role/CSRF verification plus project, requirement, assignment, coverage, deletion, leave, and attendance workflows; all 156 tests passed. Source inspection found no workforce calculation in views/templates/JavaScript and no Attendance reference in matching, optimization, recommendation preflight, or explanation services.
- Commands run:
  - presenter-only reporting-range timing probe
  - `python manage.py test frontend.tests.test_milestone4_hardening --verbosity 2`
  - combined 83-test Milestone 4 hardening/service command
  - focused 106-test Milestone 2 regression command
  - focused 156-test Milestone 3 regression command
  - frontend calculation/attendance source audits
  - `python manage.py test frontend --verbosity 1`
  - `python manage.py test --verbosity 1`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py check`
  - `python -m compileall -q core frontend`
  - edited-file trailing-whitespace and UTF-8 source scans
  - `git diff --check`
- Result: all 6 focused hardening tests passed in 1.935 s; all 83 combined Milestone 4/service tests passed in 6.296 s; all 106 Milestone 2 regressions passed in 4.128 s; all 156 Milestone 3 regressions passed in 5.001 s; all 339 frontend tests passed in 17.824 s; and the complete 353-test project suite passed in 18.829 s. Django system checks, compilation, migration drift, UTF-8, and whitespace checks pass.
- Lessons result: `LESSONS_LEARNED.md` records the reusable rule that a selector reused across display, timeline, and scalar-service consumers must prefetch the union of their scopes, keep consumer-specific collections separate, and prove service parity with edge-status data before lowering a query budget.

### M4.8 Milestone 4 verification

- [x] Verify every Milestone 4 route, template, navigation state, filter contract, drill-down, authentication rule, role boundary, and model permission.
- [x] Verify KPI, distribution, employee-timeline, and attendance-summary values against existing models and service outputs for populated, boundary, and empty scenarios.
- [x] Verify every visualization has an equivalent readable table or text representation and every aggregate reaches accurate filtered evidence.
- [x] Confirm attendance remains descriptive and absent from staffing recommendation inputs, and confirm no frontend calculation duplicates a `core` service rule.
- [x] Run the complete project test suite, `python manage.py check`, migration-drift, whitespace, and `git diff --check`; record final query/performance baselines and reusable lessons.
- [x] Close Milestone 4 only when every exit criterion passes, leaving Milestone 5 unstarted pending explicit approval.

Scope boundary: M4.8 is verification and finalization only. It adds no new feature unless a real defect is found, and any correction must remain narrowly within Milestone 4.

Completion evidence:

- Created file: `frontend/tests/test_milestone4_verification.py`.
- Modified file: `frontend/CURRENT_TASKS.md`. No application, template, style, JavaScript, model, migration, or backend service file changed for M4.8, and `frontend/LESSONS_LEARNED.md` remains unchanged.
- Route, template, and navigation result: the dashboard, employee directory/profile, leave directory, and attendance directory routes reverse and resolve at their documented paths, render every Milestone 4 page and populated evidence partial, and retain the correct Dashboard or Workforce active navigation state. Dashboard filters use the shared inclusive period plus department, employee-status, and project-status contract; employee, leave, and attendance destinations receive only their supported translated parameters and retain the documented return paths.
- Authentication and permission result: anonymous requests redirect to sign-in; unassigned users are forbidden; canonical Viewers, Managers / Planners, and HR Administrators can open every read surface; the dashboard continues to require both `core.view_employee` and `core.view_project`; employee profiles require `core.view_employee`; and leave/attendance record destinations independently require their matching model permissions. A dashboard-authorized user without leave or attendance permission receives restricted evidence rather than record disclosure.
- Service-value result: an independent populated acceptance fixture reconciles all six dashboard KPIs, both distributions, every employee evidence total, the employee daily timeline, and attendance counts/rates directly against stored models and the existing workload, availability, leave, and attendance services. Same-day inclusive boundaries, weekend-only periods, filtered-empty data, and a completely empty workforce/project set retain distinct truthful states. The focused Milestone 4 suites continue to cover 366/367-day range edges, every distribution boundary, invalid dates, status variants, zero denominators, and missing/unconfigured data.
- Visualization and evidence result: capacity, utilization, workload, and attendance visuals remain supplemental and `aria-hidden`; captioned tables provide their readable values and context. Every nonzero distribution band reaches the filtered employee evidence, every KPI reaches an exact directory or on-page evidence destination, approved leave reaches the exact employee/approved/overlap-date records, and project overlap remains on-page rather than using semantically different project-directory date filters.
- Attendance and calculation-boundary result: inserting an absent attendance record leaves the employee/project match result, recommendation preflight, and optimization context identical. Source audits find no Attendance dependency in matching, matching-v1, optimization, recommendation-preflight, or deterministic/LLM explanation services. Views, selectors, templates, and browser JavaScript contain no duplicated calls or implementations of the workforce and attendance calculations; presenters continue to delegate values to `core` services and only shape display context.
- Final query and performance baseline: the role-based dashboard remains fixed at nine queries and the attendance-authorized employee profile remains fixed at ten, including the 366-day boundary. In the final complete-suite run over seven warm Django test-client GETs using in-memory SQLite, the 24-employee/31-day dashboard recorded 22.332 ms median, 23.168 ms p95, and 62,809 response bytes; the 31-day employee timeline plus 20 attendance records recorded 25.402 ms median, 26.327 ms p95, and 75,363 bytes; the 24-employee/366-day dashboard recorded 47.916 ms median, 70.840 ms p95, and 56,435 bytes; and the 366-day employee timeline/attendance page recorded 73.671 ms median, 75.154 ms p95, and 351,640 bytes. Measurements include request handling, ORM/service work, and template rendering but exclude browser/network latency and static-file transfer.
- Commands run:
  - `python manage.py test frontend.tests.test_milestone4_verification --verbosity 2`
  - combined 83-test Milestone 4 verification/service command
  - `python manage.py test frontend --verbosity 1`
  - `python manage.py test --verbosity 1`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py check`
  - `python -m compileall -q core frontend`
  - frontend calculation and staffing-attendance source audits
  - edited-file trailing-whitespace and UTF-8 source scans
  - `git diff --check`
- Result: all 5 focused M4.8 tests passed in 0.621 s; all 83 combined Milestone 4 verification/service tests passed in 5.803 s; all 344 frontend tests passed in 18.133 s; and the complete 358-test project suite passed in 19.481 s. Django system checks, compilation, migration drift, UTF-8, source-boundary, and whitespace checks pass.
- Defect result: no application defect was found, so no application behavior or UI was changed. Initial verification-test assumptions were corrected within the new test module before the passing runs and did not require a product correction.
- Lessons result: no new reusable lesson was discovered beyond the existing route-inventory, service-ownership, accessible-evidence, filter-allow-list, permission-boundary, prefetch-scope, zero-denominator, and authenticated-shell baseline guidance, so `LESSONS_LEARNED.md` was not changed.
- Closure result: every Milestone 4 exit criterion passes. Milestone 4 is complete and approved; Milestone 5 is initialized, with application work still unstarted pending explicit approval for M5.1.

## Milestone 4 exit criteria

- [x] Managers can apply one consistent reporting period plus department, employee-status, and project-status filters across the workforce dashboard.
- [x] Dashboard KPIs show headcount, available capacity, allocated capacity, approved dated leave, active projects, and over-capacity risk with clear service-backed meanings.
- [x] Capacity and utilization distributions have accessible evidence equivalents and remain consistent with the filtered KPI values.
- [x] Employee profiles provide service-backed workload and effective-availability timelines with assignment, weekday, status, and approved-leave context.
- [x] Attendance summaries and trends use existing attendance services, remain descriptive, and do not affect matching or recommendations.
- [x] Every aggregate links to accurate filtered records or on-page evidence that explains it, without passing unsupported or misleading filters.
- [x] Read views enforce the approved permissions, handle boundary and empty states, avoid avoidable N+1 queries, and have recorded warm performance baselines.
- [x] The complete test suite and Django checks pass, Milestone 4 contains no duplicated core calculation, and Milestone 5 remains unstarted until explicit approval.

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

None for starting M7.5 after explicit approval. Milestones 0 through 6 are complete and closed, and M7.1–M7.4 are complete. The working tree still contains uncommitted Milestone 6 closure and handoff-refinement files and must be preserved. The initial model-permission mapping remains deliberately conservative: HR Administrators may maintain all operational records; Managers / Planners may add and change project planning records but may not delete them; and Viewers remain read-only. The shared calendar requires project, assignment, and employee read access and treats approved leave as an optional, truthfully restricted source; future calendar tasks must keep the M7.2 selector and serialization permission checks aligned. Record-level scope, the business timezone/holiday/part-time/weekend policy, target scale/latency, concurrent multi-process cache policy, Gemini credentials/privacy, recommendation audit/history requirements, production database/hosting/static configuration, and release infrastructure remain unresolved production decisions and must not be inferred during Milestone 7. Use the configured timezone and current Monday-to-Friday/no-holiday service assumptions until an approved task changes them.
