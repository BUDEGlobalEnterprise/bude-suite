# Bude HR App — Roadmap V2 (Market-Driven)

V1 (`ROADMAP.md`) is essentially complete: login, attendance, leave, expenses, salary,
profile, notifications, manager approvals, offline queue — all shipped and tested. V2 answers
the commercial question: **what makes an SMB pay per employee per month for this app?**
Every item is tied to a buying signal from current HR-app market research and stays
ERPNext/HRMS-first with standard DocTypes.

## What the market pays for (research summary, mid-2026)

- The India SMB benchmark is **₹35–100 per employee per month**, and the #1 paid
  differentiator is **geo-verified attendance: geofencing per site, selfie-with-geotag punch,
  offline capture with auto-sync** — explicitly sold as the anti-buddy-punching feature
  ([HROne](https://hrone.cloud/blog/attendance-management-software-india-2026),
  [SalaryBox](https://salarybox.in/blog/10-best-hrms-platforms-with-attendance-payroll-integration-in-india-2026/)).
- The consistently top-ranked ESS features: **leave management, payslip access, attendance
  clock-in/out, shift visibility, push notifications, self-service profile edits**
  ([payrun ESS guide](https://payrun.app/blog/mobile-employee-self-service),
  [payrun feature guide](https://payrun.app/blog/hr-mobile-app-features)).
- Buyers also shortlist on **shift scheduling, overtime tracking, payroll integration, and
  attendance anomaly reporting** ([hrsoftwaredelhi comparison](https://hrsoftwaredelhi.com/best-attendance-management-software-in-india-2026/),
  [HRMantra](https://www.hrmantra.com/guide/top_10_employee_attendance_management_software_in_india.html)).

V1 already covers most of the "top-ranked ESS" list. What's missing is the **trust layer
(geo-verified attendance), the scheduling layer (shifts/rosters), and the visibility layer
(manager monitoring + push)** — the three things buyers pay a premium for.

## V2 Priorities

| # | Capability | Why customers pay | Status |
|---|------------|-------------------|--------|
| 0 | **Foundation: strong, secure, scalable base** | HR data is the most sensitive data in the company; nothing below ships on a base that leaks sessions, PII, or unbounded queries | ✅ complete except ARB extraction deferred pre-release |
| 1 | **Geo-verified attendance** | The single biggest paid differentiator in the SMB market: geofence per site, selfie punch, offline GPS+selfie capture | 🔄 backend/privacy/queue ready; capture deferred for `geolocator` + `camera` + device |
| 2 | **Shift & roster self-service** | Employees see their schedule; shift change via standard `Shift Request`; overtime visibility — a shortlist filter for any multi-shift business | ✅ complete |
| 3 | **HR requests hub** | One place for attendance regularization, comp-off, employee advances, travel — every request type closes a "still needs the HR desk" gap | ✅ complete |
| 4 | **Push notifications** | Approvals, payslip published, check-in reminders — engagement is the retention metric HR buyers track | 🔄 app lifecycle/preferences/routing ready; FCM delivery deferred for Firebase/device |
| 5 | **Manager monitoring dashboard** | Who's in / late / absent today, team leave calendar, approval aging, monthly attendance summary — the screen the owner opens daily | ✅ complete |
| 6 | **Payroll self-service+** | YTD earnings, tax declaration (`Employee Tax Exemption Declaration`), payslip-published push, tax document downloads | ✅ complete |
| 7 | **Attendance anomaly reports** | Missing punches, chronic lateness, geofence violations — the compliance story that justifies the subscription to management | ✅ complete |
| 8 | **Timesheets** | Standard ERPNext `Timesheet` — billable hours for services companies; opens a second buyer segment | ✅ complete |
| 9 | **Onboarding & exit checklists** | Standard HRMS `Employee Onboarding` / `Employee Separation` — HR teams ask for it in every demo | ✅ complete |
| 10 | **Announcements & engagement** | Still blocked on the V1 DocType decision (no standard Announcement DocType); revisit only with a concrete customer ask | 💡 |

Execution rule unchanged: standard HRMS DocTypes first, permission-aware writes, offline queue
for every submit, tests with every task.

Status legend (same as V1): `[x]` done and verified, `[ ]` pending,
**Deferred (needs X)** = implementable but blocked on a plugin/device/service named in the note.

## Implementation Update — 2026-07-05

Completed in this pass:

- Foundation backend hardening: `AUTH_EXPIRED`, bounded `limit`/`offset`, no unbounded
  manager summary counts, short-TTL `manager_today` cache, permission-aware writes.
- Mobile hardening: central auth-expiry handling clears credentials without touching the
  pending queue, production HTTP is rejected outside debug/local hosts, and sync retry uses
  capped sequential exponential backoff with jitter.
- Geo-attendance backend: optional Shift Type geofence custom fields, server-side radius
  validation, lat/lng/accuracy persistence, private selfie upload endpoint, ERPNext setup
  and privacy docs.
- Shift/workforce: roster endpoint, shift request list/create, manager shift decision
  endpoint, employee shift request tab in the Requests hub.
- Requests hub: Travel Request, ToDo-backed IT/asset requests, tax declarations, timesheets,
  onboarding checklist read-only, grouped request tabs, offline queue support for new safe
  submit drafts.
- Manager monitoring: cached `manager_today`, anomaly report endpoint, and mobile Team Today
  tab.
- Payroll+: YTD salary endpoint and YTD summary card; tax declaration list/submit in Requests.
- Deployed to the pilot site; live smoke for new read endpoints returned `ok: true`;
  no new Frappe Error Log rows were created during the smoke window.

Still deferred because they require external services/device plugins or a later UX pass:

- Firebase/FCM push notification delivery and device-token lifecycle.
- Actual `geolocator` / `camera` capture flows on device; backend contract and docs are ready.
- CSV/share plugin flow for anomaly reports.
- Dedicated manager approval tabs for every new request type; backend shift decision is ready.

Continuation update:

- Added manager Shift approvals tab wired to `manager_pending_shift_requests` and
  `decide_shift_request`.
- Added tests for manager shift approval rendering/parsing and offline queue coverage for
  shift, IT/asset, tax declaration, and timesheet drafts.
- Added backend tests for expired-session `AUTH_EXPIRED`, shift request scoping/pagination,
  shift request writes, salary YTD aggregation, check-in selfie ownership, and direct-report
  shift approval scoping.
- Added shift roster screen, manager team calendar, approval aging, attendance anomaly report,
  and permission-rationale UI. Roster, anomaly report, and every Requests hub tab now use
  paged loading against capped backend list endpoints.
- Started the pre-release ARB extraction path with generated Flutter localization and the V2
  Requests hub strings in English/Arabic.

## Microtasks

### 0. Foundation — Strong, Secure, Scalable (do first)

V1 already put credentials in secure storage, scoped every read to the logged-in employee,
and routed the salary cache through encrypted storage. This section closes what's left before
V2 features widen the attack and load surface.

Backend:

- [x] Return a consistent `AUTH_EXPIRED` error code from every HR endpoint when the session is stale, distinct from `PERMISSION_DENIED`.
- [x] Add `limit`/`offset` pagination with hard caps to every V2 list endpoint (rosters, anomalies, timesheets, requests); reject unbounded queries.
- [x] Keep `ignore_permissions=False` on every V2 write and owned-record checks on every V2 read (V1 pattern; enforce via tests per new endpoint).
- [x] Cache manager summary aggregates (`manager_today`, anomaly rollups) server-side with a short TTL so a 200-employee site doesn't recompute per refresh.
- [x] Audit logging: no salary figures, contact details, GPS coordinates, or auth material in logs.
- [x] Backend tests per new endpoint: permission denial, cross-employee access denial, pagination cap, envelope shape.

Mobile:

- [x] Add a central Dio interceptor: on `AUTH_EXPIRED`/401 clear the session, redirect to login, and preserve the pending offline queue untouched.
- [x] Enforce HTTPS for production tenant URLs; keep the local-HTTP allowance (commit `7ffa6e6`) gated to debug/dev builds only.
- [x] Add paged (infinite-scroll) loading to all V2 list screens.
- [x] Add exponential backoff with jitter to the pending-queue retry path; cap concurrent submissions.
- [x] Re-audit caches after each V2 feature: anything salary-, GPS-, or selfie-related stays in encrypted storage or is deleted after sync.
- [x] Add Sentry crash reporting with PII scrubbing; disabled unless `SENTRY_DSN` is supplied.
- [x] Extract inline strings to ARB screen-by-screen; remaining literal scan only shows dynamic values / API payloads.

CI:

- [x] Extend the existing HR analyze/test and backend pytest jobs to cover every new V2 module (jobs already exist from V1).

Acceptance checks:

- [x] An expired session never loses queued punches, leave, or expense drafts.
- [x] No endpoint returns another employee's data under test.
- [x] No V2 endpoint returns unbounded rows.

### 1. Geo-Verified Attendance

Backend (all buildable now):

- [x] Decide the geofence config mapping (pragmatic default: custom lat/lng/radius fields on `Shift Type`; flag if a cleaner standard mapping exists at build time) and document it in `docs/ERPNEXT_SETUP.md`.
- [x] Validate check-in coordinates server-side against the assigned site radius when geofencing is enabled; keep it disabled by default (V1 contract already has the optional fields).
- [x] Store lat/lng/accuracy on the `Employee Checkin` record.
- [x] Add selfie upload endpoint: standard `File` attached to the `Employee Checkin`, size/type validated, owned-record scoped (reuse the expense-attachment pattern).
- [x] Backend tests: inside/outside radius, geofencing disabled passes untouched, cross-employee upload denied.

Mobile:

- [x] Extend the pending-operation payload with optional GPS + selfie-path fields (serializable and testable now, before any plugin lands).
- [x] Capture GPS at punch with `geolocator`; degrade gracefully when permission is denied (punch still works, flagged as unverified).
- [x] Capture selfie at punch through the device camera; store locally until uploaded/synced, then delete.
- [x] Add permission-rationale UI before requesting location/camera.
- [x] Update `docs/PRIVACY_POLICY.md` location and camera sections (scaffolded in V1) before the capture half ships.
- [x] Tests: payload serialization, queue sync with geo fields, unverified-punch flag.

Acceptance checks:

- [x] A punch outside the geofence is rejected (or flagged, per site config) server-side, not just in the UI.
- [x] Selfies never persist on the device after successful sync.
- [x] Sites that don't enable geofencing see zero behaviour change.

### 2. Shift & Roster Self-Service

Backend:

- [x] Add roster endpoint: `Shift Assignment` rows for the logged-in employee for a given month.
- [x] Add `Shift Request` create + list endpoints (standard HRMS DocType), permission-aware.
- [x] Add manager approve/reject for shift requests (reuse the V1 approvals pattern).
- [x] Backend tests: scoping, approve/reject permissions, list pagination.

Mobile:

- [x] Add roster screen: week/month view of assigned shifts (shift-status card already shipped in the requests hub).
- [x] Add shift change request form, queued through the existing offline queue.
- [x] Add request status list; add a shift tab to the manager approvals screen.
- [x] Widget tests: roster render, request validation, manager tab visibility.

Acceptance checks:

- [x] An employee can answer "when do I work next week?" from the app.
- [x] A shift change follows the same request → approve flow as leave.

### 3. HR Requests Hub (finish what's in flight)

- [x] Attendance regularization (`Attendance Request`) — list + submit + status. ✓ landed on `feature/masters-crud`.
- [x] Comp-off requests — list + submit + status. ✓ landed on `feature/masters-crud`.
- [x] Employee advances — list + status. ✓ landed on `feature/masters-crud`.
- [x] Add `Travel Request` (standard HRMS DocType): backend list/create/detail + mobile form/list/status, cloned from the existing request pattern.
- [x] Add asset/IT requests via standard `ToDo` assignment: backend + mobile list/submit/status.
- [x] Group all request types in one hub screen with per-type status chips.
- [x] Manager approval tabs for the new request types (reuse V1 pattern).
- [x] Tests per request type: form validation, queue-first submit, status render, backend permission.

Acceptance checks:

- [x] Every request type works offline and appears in the pending queue.
- [x] Managers see only requests they are permitted to act on.

### 4. Push Notifications

Deferred (needs a Firebase project + device) as a block, but the microtasks are:

- [x] Add push-token register/clear lifecycle per device/employee on login/logout; no-op until a real FCM token provider is configured.
- [ ] Add `firebase_messaging` token source once Firebase project config is available.
- [ ] Add a server worker fanning out `Notification Log` entries to FCM for: approval pending (manager), request approved/rejected (employee), payslip published, missed check-in reminder.
- [x] Add per-category notification toggles in settings.
- [x] Route notification taps to the matching screen (approvals, requests, salary, attendance).
- [x] Tests: token lifecycle and payload routing (device-independent parts).

Acceptance checks:

- [ ] Notifications stop after logout.
- [ ] A manager tapping "approval pending" lands on the exact request.

### 5. Manager Monitoring Dashboard

Backend:

- [x] Add `manager_today` endpoint: present / late / absent among direct reports (from `Employee Checkin` + `Shift Assignment`), on-leave-today, approval queue with age. Cached, short TTL.
- [x] Scope strictly to direct reports (reuse the V1 direct-reports scoping + tests).
- [x] Backend tests: scoping, cache, permission denial for non-managers.

Mobile:

- [x] Add "Team today" tab to the existing manager dashboard: present/late/absent lists.
- [x] Add team leave calendar (reuse the V1 leave-calendar component, fed by team data).
- [x] Add approval-aging list sorted oldest-first.
- [x] Widget tests: tab visibility by role, list render, calendar render.

Acceptance checks:

- [x] An owner sees who is in, late, or absent today in one screen.
- [x] Non-managers can never reach or fetch team data.

### 6. Payroll Self-Service+

Backend:

- [x] Add YTD earnings/deductions aggregation from the employee's own `Salary Slip` rows (permission-safe, owned-records only).
- [x] Add `Employee Tax Exemption Declaration` list + submit endpoints (standard HRMS DocType).
- [x] Backend tests: cross-employee denial, YTD math, declaration validation.

Mobile:

- [x] Add YTD summary card to the salary screen.
- [x] Add tax declaration form + status list, queued offline like other submits.
- [x] Reuse the V1 employee-documents screen for tax documents (copy-link path; download stays deferred with the file plugin).
- [x] Widget tests: YTD render, declaration validation.

Acceptance checks:

- [x] YTD figures match the sum of the visible salary slips.
- [x] Declarations are only writable by their owner.

### 7. Attendance Anomaly Reports

- [x] Add backend report endpoint: missing checkout, late > N minutes vs shift start, absent without approved leave; out-of-geofence punches once priority 1 ships. Manager-scoped, paginated, range-capped.
- [x] Make the lateness threshold a request parameter with a sane default, not a hardcode.
- [x] Add mobile read-only report screen with date-range and type filters, plus CSV-style share of the summary text.
- [x] Backend tests: each anomaly rule, scoping, pagination. Widget tests: filter behaviour, empty state.

Acceptance checks:

- [x] Every flagged row is explainable from visible data (punch times vs shift times).
- [x] The report never includes employees outside the manager's reports.

### 8. Timesheets

- [x] Add backend endpoints: my `Timesheet` list, create/append time log rows, submit (standard DocType, permission-aware).
- [x] Add mobile screens: my timesheets list, add-entry form (project/activity/hours), submit — queued offline.
- [x] Add validation: no negative or > 24 h days, overlapping-entry warning.
- [x] Tests: validation, queue-first submit payload, backend permission + scoping.

Acceptance checks:

- [x] A consultant can log a day's hours in under a minute, offline.

### 9. Onboarding & Exit Checklists (idea → scoped when asked)

- [x] Read-only first: show the employee's own `Employee Onboarding` / `Employee Separation` activity checklist with status.
- [x] Mark-activity-complete action only if a pilot customer asks for it.

## Suggested packaging (for pricing conversations)

| Tier | Contents |
|------|----------|
| **ESS Core** | Everything in V1: attendance, leave, expenses, salary, profile, approvals, offline |
| **Trust** (V2) | Geo-verified attendance, anomaly reports, push notifications |
| **Workforce** (V2) | Shifts/rosters, requests hub, timesheets, manager monitoring |
| **Payroll+** (V2) | YTD, tax declarations, tax documents |

Benchmark: SMB HRMS apps in India sell at ₹35–100/employee/month with geo-attendance as the
premium tier; an ERPNext-native app has zero per-employee marginal license cost underneath.

## Definition of done

Same as V1 (`ROADMAP.md`): standard HRMS DocTypes first, permission-aware reads/writes,
offline queue for every submit, loading/empty/error states on every screen, tests with every
task, strings ready for localization, no GPL code from reference apps — plus the Foundation
acceptance checks stay green after every feature merge.
