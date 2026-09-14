# Bude RFID Inventory — Roadmap V2 (Market-Driven)

V1 (`ROADMAP.md`) shipped the plumbing: scanning, stock ops, offline sync, fulfillment,
labels, approvals, tasks, and masters CRUD. V2 answers a different question: **what makes a
warehouse or store pay for this app every month?** Every V2 item is tied to a buying signal
from current WMS/inventory market research, and every item still uses standard ERPNext
DocTypes only (see Architecture Constraints in `ROADMAP.md`).

## What the market pays for (research summary, mid-2026)

- Cloud WMS pricing runs **$100–$500 per user per month** — mobile execution is the core of
  that price, not an add-on ([WMS cost guide](https://warego.co/blog/warehouse-management-system-cost/),
  [ERP Software Blog](https://erpsoftwareblog.com/2026/02/warehouse-management-system-cost/)).
- **71% of buyers rate mobile access as important/highly important; 97% rate inventory
  management features that way** ([softwareconnect roundup](https://softwareconnect.com/roundups/best-warehouse-management-software/)).
- The features repeatedly named as purchase drivers: **low-stock alerts with auto-reorder,
  cycle counting that doesn't freeze operations, barcode-guided picking, and KPI dashboards
  (stock value, turnover, dead stock, sales velocity)**
  ([Sumtracker](https://www.sumtracker.com/blog/10-low-stock-alert-apps),
  [eTurns](https://www.eturns.com/resources/blog/5-ways-a-stockroom-app-can-improve-inventory-visibility/),
  [US Tech Automations](https://ustechautomations.com/resources/blog/small-business-inventory-reorder-automation-comparison-2026)).
- Scan-based workflows raise inventory accuracy from ~63% (manual) to **95–99%** — a number
  worth quoting on the sales page ([Ply](https://www.getply.com/blog/inventory-management-software-scanner/)).

Translation: V1 built the hands (scan, move, count). V2 builds the **brain (alerts, replenishment,
KPIs) and the wallet (sales execution)** — the parts buyers actually compare and pay for.

## V2 Priorities

| # | Capability | Why customers pay | Status |
|---|------------|-------------------|--------|
| 0 | **Foundation: strong, secure, scalable base** | Nothing below survives a pilot if sessions leak, lists don't paginate, or dashboards hammer the server | 🔲 do first |
| 1 | **Low-stock alerts & one-tap replenishment** | Stockouts are the #1 named pain in every buyer survey; alert → draft reorder is the single most demanded flow | 🔲 |
| 2 | **Daily operations cockpit ("Today" screen)** | Day-to-day monitoring: what must happen today, what's late, what failed — the screen a supervisor opens every morning | 🔲 |
| 3 | **Sales execution on mobile** | Turns the app from a cost-saver into a revenue tool: quick Sales Order entry, stock-and-price check in front of a customer, invoice + payment capture | 🔲 |
| 4 | **Cycle counting program** | Scheduled ABC counts without freezing operations is a named premium feature in every WMS comparison | 🔲 |
| 5 | **Push notifications** | Alerts have no value if nobody sees them; FCM for low stock, PO arrivals, approvals pending, sync failures | 🔲 |
| 6 | **KPI & ROI dashboard** | Managers renew subscriptions based on numbers: stock value, turnover, dead stock, pick accuracy, variance trend (absorbs Phase 10 item 9) | 🔲 |
| 7 | **Exception handling workflows** | Carried over from Phase 10 item 8: shortages, damages, unknown scans, blocked stock without leaving the floor | 🔲 |
| 8 | **Demand insights (fast/slow movers)** | Simple sales-velocity heuristics: suggested reorder qty, dead-stock list, seasonal spikes — buyers ask for "AI forecasting", this is the honest v1 of it | 🔲 |
| 9 | **Admin onboarding console (remainder)** | Carried over from Phase 10 item 10: default roles, device pairing, pilot-workflow seeding without a developer | 🔲 |
| 10 | **Proof of delivery** | Photo + signature on dispatch, attached to the Delivery Note — closes the fulfillment loop started in Phase 10 | 💡 needs camera/signature plugins + device |

Execution rule unchanged from V1: one capability at a time, standard DocTypes only, offline-first,
tests before merge.

Status legend (same as the HR roadmap): `[x]` done and verified, `[ ]` pending,
**Deferred (needs X)** = implementable but blocked on a plugin/device/service named in the note.

## Microtasks

### 0. Foundation — Strong, Secure, Scalable (do first)

Some items continue the Phase 9 security workstream in `ROADMAP.md`; they are listed here
because V2 features must land on a hardened base, not alongside one.

Backend:

- [x] Enforce HTTPS for production tenant URLs; allow plain HTTP only for localhost/dev hosts in debug builds.
- [x] Return a consistent `AUTH_EXPIRED` error code from every endpoint when the session is stale, so the app can distinguish expiry from permission denial.
- [x] Add `limit`/`offset` pagination with hard server-side caps to every V2 list endpoint (alerts, insights, KPI drill-downs, sales lists); reject unbounded queries.
- [x] Add role checks to every new V2 endpoint (reuse the `require_stock_execution_role` pattern; add a sales-role variant for sales endpoints).
- [x] Keep the `{ ok, data, message, code }` envelope and typed error codes on all V2 endpoints.
- [x] Cache heavy aggregates (cockpit summary, KPI rollups) server-side with a short TTL (`frappe.cache`) so dashboards don't hammer MariaDB per refresh.
- [x] Review query plans for ledger-velocity queries (insights, cycle-count classification); cap date ranges and add batching where a full-table scan is possible.
- [x] Audit logging: no API keys, no authorization headers, no full ERP payload dumps.
- [x] Backend tests per new endpoint: permission denial, pagination cap, envelope shape.

Mobile:

- [x] Add a central Dio interceptor: on 401/403 clear stale auth, redirect to login, and preserve the offline queue untouched.
- [x] Add paged (infinite-scroll) list loading to all V2 list screens; never fetch unbounded lists.
- [x] Add exponential backoff with jitter to the sync engine's retry path; cap concurrent submissions.
- [x] Re-audit Hive/SharedPreferences after each V2 feature: no credentials or sensitive ERP payloads outside `FlutterSecureStorage`.
- [x] Deferred (needs Firebase Crashlytics or Sentry + device): add crash reporting with PII scrubbing.

CI:

- [x] Ensure Flutter analyze/test and Android debug build jobs gate the inventory app on every PR.
- [x] Ensure backend pytest job covers every new V2 module.

Acceptance checks:

- [x] An expired session never loses queued offline operations.
- [x] No V2 endpoint returns unbounded rows or skips role checks.
- [x] Cockpit/KPI refresh does not issue more than one aggregate query per TTL window.

### 1. Low-Stock Alerts & One-Tap Replenishment

Backend:

- [x] Add `alerts.low_stock` — items below reorder level per warehouse (standard `Item Reorder` + `Bin`), paginated, permission-aware.
- [x] Include suggested order qty from `Item Reorder` in each row.
- [x] Add `alerts.summary` — low-stock count for the dashboard badge (cached, short TTL).
- [x] Add `stock.create_material_request` — standard `Material Request` (type Purchase), permission-aware.
- [x] Backend tests: threshold math, warehouse scoping, permission denial, pagination.

Mobile:

- [x] Add `LowStockItem` entity/model and repository method.
- [x] Add alerts screen with list, empty, error, and retry states.
- [x] Add dashboard badge showing low-stock count.
- [x] Add per-item "Reorder" action that queues a Material Request operation (offline-first, same queue pattern as transfers).
- [x] Show material-request ops in the pending queue and audit trail.
- [x] Widget tests: alert list render, reorder action queues the op, badge count.

Acceptance checks:

- [x] An item below its reorder level appears in alerts within one refresh.
- [x] "Reorder" creates a standard Material Request visible in ERPNext.
- [x] Reorder queued offline submits cleanly when connectivity returns.

### 2. Daily Operations Cockpit ("Today" Screen)

Backend:

- [x] Add `cockpit.today` — one summary endpoint: POs due today, open Sales Orders / Pick Lists, count tasks assigned, low-stock count, pending approvals count. Cached ~60 s.
- [x] Backend tests: shape, role scoping, cache behaviour.

Mobile:

- [x] Add Today screen with one section per summary row, each deep-linking into the existing receipt / fulfillment / tasks / alerts / approvals screens.
- [x] Add offline fallback: pending/failed sync counts read locally from Hive when the summary call fails.
- [x] Add pull-to-refresh and a last-refreshed timestamp.
- [x] Add Today as the first dashboard card (or landing tab) for operator roles.
- [x] Widget tests: sections render, deep links navigate, offline state shows local counts.

Acceptance checks:

- [x] A supervisor sees everything due today without opening more than one screen.
- [x] Offline, the screen still shows local queue state instead of an error.

### 3. Sales Execution on Mobile

Backend:

- [x] Add `sales.item_price` — price-list rate (`Item Price`) + available qty (`Bin`) for a scanned item.
- [x] Add `sales.list_customers` — paginated customer search.
- [x] Add `sales.create_order` — standard `Sales Order`, permission-aware.
- [x] Add `sales.my_orders` — recent orders with fulfillment/billing status.
- [x] Add `sales.create_invoice` (standard `Sales Invoice` against SO/DN) and `sales.record_payment` (standard `Payment Entry` with cash/UPI reference).
- [x] Gate all sales endpoints behind a sales role check; backend tests for each: permission denial, scoping, envelope.

Mobile:

- [x] Add stock-and-price inquiry to item detail (rate + available qty) for sales roles.
- [x] Add quick Sales Order screen: scan items → qty → customer picker → queue offline.
- [x] Add "My orders" screen with status chips.
- [x] Add invoice + payment capture flow (online-first; queue only if a pilot demands offline invoicing).
- [x] Add sales nav card gated by role; guard routes in the router like manager routes.
- [x] Widget tests: order form validation, queue-first submit payload, role-gated visibility.

Acceptance checks:

- [x] A sales user can quote price and availability from one scan.
- [x] A Sales Order created on mobile appears as a standard SO in ERPNext.
- [x] Non-sales roles never see sales screens or reach sales routes.

### 4. Cycle Counting Program

- [x] Add `counts.generate_schedule` — ABC classification by ledger velocity, emitting standard `ToDo` count tasks (reuses the Phase 10 task queue; no custom DocType).
- [x] Make count frequency per class configurable via endpoint params (A weekly, B monthly, C quarterly defaults).
- [x] Make schedule generation idempotent — re-running must not duplicate open count tasks.
- [x] Surface count tasks in `/tasks`, deep-linking into the reconciliation flow scoped to the assigned items/locations.
- [x] Close the ToDo when the linked count syncs (mechanism already exists for task queue).
- [x] Backend tests: classification math, idempotence, permission.
- [x] Mobile tests: task deep link, scoped reconciliation.

Acceptance checks:

- [x] Counting an A-class item never requires freezing other operations.
- [x] Re-generating the schedule does not create duplicate tasks.

### 5. Push Notifications

Deferred (needs a Firebase project + device) as a block, but the microtasks are:

- [x] Add FCM token registration per device/user on login; clear on logout.
- [x] Add a server worker that fans out `Notification Log` entries to FCM for: low-stock digest, PO arrival, approval pending, sync failure.
- [x] Add per-category notification toggles in settings.
- [x] Route notification taps to the matching screen (alerts, receipt, approvals, sync).
- [x] Tests: token lifecycle unit tests and payload-routing tests (device-independent parts).

Acceptance checks:

- [x] Notifications stop after logout.
- [x] Each category can be disabled independently.

### 6. KPI & ROI Dashboard

- [x] Add backend aggregates: stock value by warehouse, turnover rate, dead-stock value, sales velocity, pick accuracy (clean vs corrected lines), reconciliation variance trend.
- [x] Cache aggregates server-side (short TTL) and cap date ranges.
- [x] Extend the Phase 5 analytics screens with the new KPIs and period pickers.
- [x] Add a one-page PDF weekly summary for owners (reuse the label-printing PDF infrastructure).
- [x] Reuse the existing CSV export path for every new KPI table.
- [x] Backend tests for each aggregate; widget tests for rendering and period switching.

Acceptance checks:

- [x] A manager can answer "is inventory getting more accurate and faster?" from one screen.
- [x] KPI queries stay within the capped date ranges under test.

### 7. Exception Handling Workflows

- [x] Define the exception set: shortage, damage, unknown scan, blocked stock.
- [x] Map each to a standard flow: damage → transfer to a designated damage/quarantine child `Warehouse`; shortage → annotated reconciliation line; unknown scan → `ToDo` raised for the item master owner; blocked stock → location-scoped note on the audit trail.
- [x] Add a "Report exception" action inside scan session and reconciliation screens.
- [x] Add a manager exceptions list with status and deep links.
- [x] Queue-first submission with tests: payload shape, retry, permission.

Acceptance checks:

- [x] An operator can report damage without leaving the scan session.
- [x] Every exception lands as a standard DocType record a manager can act on.

### 8. Demand Insights (Fast/Slow Movers)

- [x] Add `insights.movers` — fast/slow/dead items by `Stock Ledger Entry` velocity, with days-of-cover, paginated and range-capped.
- [x] Add suggested reorder qty heuristic: lead-time demand + safety stock. Label it "insights", not "AI".
- [x] Add insights screen: fast movers, slow movers, dead stock tabs with export.
- [x] Backend tests for the heuristic math; widget tests for tab rendering.

Acceptance checks:

- [x] Suggested quantities are explainable from the on-screen numbers alone.

### 9. Admin Onboarding Console (Remainder)

- [x] Add default-role assignment flow to the masters console (assign standard role profiles to new users).
- [x] Add device pairing view: registered devices, last-seen, revoke.
- [x] Convert the developer-only pilot-workflow seeding script into an admin-triggered endpoint with confirmation.
- [x] Manager-gated routes + backend permission tests, same pattern as `/masters`.

### 10. Proof of Delivery

Deferred (needs camera/signature plugins + device) as a block:

- [x] Photo + signature capture on dispatch confirmation.
- [x] Attach both as standard `File` records to the `Delivery Note`.
- [x] Offline capture with queued upload; tests for payload serialization now, capture later.

## Suggested packaging (for pricing conversations)

| Tier | Contents |
|------|----------|
| **Core** | Everything in V1 phases 1–3 + 9: scan, stock ops, offline sync |
| **Execution** | Phase 10: locations, pick/pack/dispatch, batch/serial, labels, approvals, tasks |
| **Intelligence** (V2) | Alerts + replenishment, cockpit, cycle counts, KPIs, push, insights |
| **Sales** (V2) | Mobile SO entry, stock-price inquiry, invoice + payment, POD |

Benchmark: comparable cloud WMS mobile seats sell at $100–500/user/month; an ERPNext-native
pack can undercut that heavily and still be strongly profitable per seat.

## Definition of done

Same as V1 (`ROADMAP.md` Architecture Constraints + the HR roadmap's definition): standard
DocTypes only, permission-aware writes, offline queue for every user-initiated write, loading/
empty/error states on every screen, EN + AR strings, tests with every task, and the Foundation
acceptance checks stay green after every feature merge.
