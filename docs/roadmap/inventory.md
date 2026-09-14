# Bude RFID Inventory — Roadmap

Enterprise inventory management platform built on ERPNext, Frappe, and Flutter, delivering barcode and RFID-driven inventory visibility through standard ERPNext workflows.

---

## Legend

| Badge | Meaning |
|-------|---------|
| ✅ Done | Shipped and on `main` |
| 🔄 In Progress | Active development |
| 🔲 Planned | Scoped, not yet started |
| 💡 Idea | Under consideration, not formally scoped |

---

## Phase 1 — Core Inventory Workflows ✅

Foundation: authentication, item lookup, barcode scanning, stock operations, and offline sync.

| Area | Feature | Status |
|------|---------|--------|
| **Backend** | `bude_api` Frappe app skeleton — whitelist decorator, `success`/`failure` envelope | ✅ |
| **Backend** | `auth.login` / `auth.session_info` — API key auth, session dict | ✅ |
| **Backend** | `items.search`, `items.get_by_barcode`, `items.get_stock` | ✅ |
| **Backend** | `warehouses.list` | ✅ |
| **Backend** | `stock.create_transfer`, `stock.create_receipt`, `stock.create_reconciliation` | ✅ |
| **Backend** | `purchase_orders.list_open` | ✅ |
| **Backend** | `health.ping` (version endpoint) | ✅ |
| **Mobile** | Onboarding — company URL setup, connection probe | ✅ |
| **Mobile** | Login screen + JWT / API-key session management | ✅ |
| **Mobile** | Item search + item detail (stock by warehouse) | ✅ |
| **Mobile** | Camera barcode scanner (`mobile_scanner`, `CameraBarcodeAdapter`) | ✅ |
| **Mobile** | Stock transfer screen (warehouse → warehouse) | ✅ |
| **Mobile** | Goods receipt screen (against PO or free) | ✅ |
| **Mobile** | Stock reconciliation / count screen | ✅ |
| **Mobile** | Offline-first sync queue (Hive) + `SyncEngine` + `PendingQueueScreen` | ✅ |
| **Mobile** | Hardware Abstraction Layer (HAL) — `BarcodeAdapter`, `RfidAdapter`, `DeviceAdapter` interfaces | ✅ |
| **Mobile** | `AndroidDeviceProbe` via `bude.hardware/probe` method channel | ✅ |
| **Mobile** | Vendor stubs: Chainway, Zebra, Urovo, Honeywell, GenericUHF | ✅ |
| **Mobile** | Animated splash, polished nav cards, branding (logo, company name) | ✅ |
| **Infra** | CI/CD skeleton (GitHub Actions) | ✅ |

---

## Phase 2 — Enterprise Foundation ✅

Design system, internationalisation, settings architecture, and dashboard intelligence.

| Area | Feature | Status |
|------|---------|--------|
| **Backend** | `branding.get` — feature flags from installed apps (`transfer`, `receipt`, `reconciliation`) | ✅ |
| **Mobile** | Design token system — `AppColors`, `AppSpacing`, `AppRadius`, `AppTypography` (Inter) | ✅ |
| **Mobile** | Material 3 light / dark / system theme — `AppTheme.light()` / `AppTheme.dark()` | ✅ |
| **Mobile** | `themeModeProvider` + `localeProvider` derived from `SettingsNotifier` | ✅ |
| **Mobile** | i18n foundation — `flutter_localizations`, English + Arabic ARBs (80+ keys) | ✅ |
| **Mobile** | RTL layout via `Locale('ar')` — automatic direction flip | ✅ |
| **Mobile** | `AppSettings` model expanded to 13 typed fields (theme, locale, scan behaviour, sync, defaults, auto-logout) | ✅ |
| **Mobile** | `SettingsNotifier` with typed mutators; `SharedPreferences` persistence | ✅ |
| **Mobile** | Settings screen redesigned — 6 sections (Appearance, Connection, Defaults, Scanning, Sync & Offline, Account) | ✅ |
| **Mobile** | `OfflineBanner` — animated, driven by `connectivityProvider` | ✅ |
| **Mobile** | `SyncStatusIndicator` — AppBar chip with live pending count, taps to `/sync` | ✅ |
| **Mobile** | `EmptyStateView`, `ShimmerList`, `BudeSectionHeader` core UI components | ✅ |
| **Mobile** | Dashboard — offline banner, adaptive 2→3 column grid (≥600 dp), feature-flag gated cards, recently-used chip row | ✅ |
| **Mobile** | `Branding.featureFlags` field — disables nav cards when ERPNext feature is unavailable | ✅ |

---

## Phase 3 — Operational Intelligence ✅

Item movement history, warehouse overview, and bulk multi-item scan sessions.

| Area | Feature | Status |
|------|---------|--------|
| **Backend** | `items.get_ledger` — Stock Ledger Entry history, newest-first, optional warehouse, limit 1–200 | ✅ |
| **Backend** | `warehouses.get_stock` — Bin rows per warehouse (actual / reserved / projected qty), limit 1–500 | ✅ |
| **Mobile** | `StockLedgerEntry` entity + model, `getLedger` on `ItemRepository` | ✅ |
| **Mobile** | `ItemDetailScreen` — tab controller: **Stock** tab (existing) + **History** tab (ledger timeline grouped by date, +/− colour) | ✅ |
| **Mobile** | `WarehouseStockLine` entity + model, `WarehouseRepository` + `WarehouseRemoteDataSourceImpl` | ✅ |
| **Mobile** | `WarehouseListScreen` (`/warehouses`) — shimmer, empty state, tap to detail | ✅ |
| **Mobile** | `WarehouseDetailScreen` (`/warehouse/:name`) — stock lines with actual / reserved quantities, item count header | ✅ |
| **Mobile** | Warehouses nav card on dashboard | ✅ |
| **Mobile** | `ScannedItem` value object, `ScanSessionMode` enum (`transfer \| receipt \| reconcile`) | ✅ |
| **Mobile** | `CameraPreviewAdapter` interface; `CameraBarcodeAdapter` implements it via `buildPreview()` | ✅ |
| **Mobile** | `ScanSessionScreen` (`/scan-session?mode=`) — continuous scan stream, duplicate-bump, qty editing, live camera viewfinder, "Use N items" FAB | ✅ |
| **Mobile** | Transfer / Receipt / Reconciliation — replaced single-shot scan with `_startScanSession`; reconciliation pre-fetches `expectedQty` for all items via `Future.wait` | ✅ |
| **Router** | 15 routes total — added `/warehouses`, `/warehouse/:name`, `/scan-session` | ✅ |

---

## Phase 4 — RFID Hardware Integration 🔲

Activate real vendor SDKs behind the existing HAL interfaces. Each vendor is an independent, self-contained task.

| Vendor | Adapter | Devices | Status |
|--------|---------|---------|--------|
| **Chainway** | `ChainwayBarcodeAdapter` + `ChainwayRfidAdapter` | C72, C66, R6 | 🟡 SDK bridge built; physical validation pending |
| **Zebra** | `ZebraBarcodeAdapter` + `ZebraRfidAdapter` | TC-series + RFD40 / RFID8500 sled | 🔲 |
| **Urovo** | `UrovoBarcodeAdapter` + `UrovoRfidAdapter` | DT40 RFID, i9000s | 🔲 |
| **Honeywell** | `HoneywellBarcodeAdapter` | CT40, EDA52, EDA61k | 🔲 |
| **Generic UHF** | `GenericUhfRfidAdapter` | BLE / USB / LLRP readers | 🔲 |
| **Demo RFID** | `DemoRfidAdapter` | No-reader development / demo mode | ✅ |

**Deliverables per vendor**
- Replace stub `throw VendorSdkUnavailableException()` bodies with real SDK calls
- Add `DeviceProbe` detection (model string, package query, or method-channel ping)
- Integration test harness against device emulator or physical unit
- Update `documentation/hardware-roadmap/integration-roadmap.md`

**Chainway integration notes**
- Cached public Chainway SDK archives under `vendor_sdk_cache/chainway/`.
- Bundled `DeviceAPI_ver20251103_release.aar` into `mobile-app/flutter_app/android/app/libs/`.
- Added Android method/event channels for Chainway barcode and UHF RFID.
- Replaced Chainway Dart stubs with real HAL adapters.
- Still requires validation on a C72/C66/R6 unit before marking complete; this is blocked until reader hardware is available.
- Added no-reader `DemoRfidAdapter` so EPC lookup and future inventory flows can be tested without physical RFID hardware.

---

## Phase 5 — Analytics & Reporting ✅

KPI dashboards, variance analysis, and data export.

| Feature | Description | Status |
|---------|-------------|--------|
| **Stock aging report** | Items idle for N days per warehouse; threshold picker (7/14/30/60/90 d); sorted by days idle | ✅ |
| **Variance dashboard** | Submitted reconciliation history — counted vs expected per line, colour-coded surplus/deficit, expandable cards | ✅ |
| **Transfer throughput** | Ops per day from local Hive queue; stacked `fl_chart` bar chart; 7/14/30-day period picker | ✅ |
| **Export to CSV** | Warehouse stock or item ledger as `.csv` via system share sheet (`share_plus`) | ✅ |
| **Pull-to-refresh** | `RefreshIndicator` on warehouse list, warehouse detail, and item history tab | ✅ |

**Backend** — `analytics.get_stock_aging`, `analytics.get_reconciliation_history` (standard ERPNext DocTypes, 9 pytest tests)

**New packages** — `fl_chart ^0.69.0`, `share_plus ^10.0.0`, `csv ^6.0.0`, `path_provider ^2.1.4`

---

## Phase 6 — Role-Based Access & Multi-Entity ✅

Enterprise controls for multi-site, multi-company deployments.

| Feature | Description | Status |
|---------|-------------|--------|
| **Role-scoped screens** | Hide or disable screens based on ERPNext user roles (`Stock Manager`, `Stock User`) | 🔲 |
| **Per-user default warehouse** | Pull `default_warehouse` from ERPNext User doc, pre-fill dropdowns | 🔲 |
| **Multi-company switcher** | Select active company from a list; scope all operations to that company | 🔲 |
| **Supervisor approval flow** | Large-variance reconciliations require a second user to approve before queuing | 🔲 |
| **Audit trail screen** | List all submitted ops by this device, with ERPNext doc link | 🔲 |
| **Biometric auto-login** | Face ID / fingerprint re-auth after auto-logout timer fires | 🔲 |

---

## Phase 7 — Additional ERP Connectors 💡

`erpnext_client.py` is the first `ErpClient` implementation. Each new connector lives alongside it and conforms to the same interface; the mobile app is unaware.

| Connector | Status |
|-----------|--------|
| ERPNext / Frappe | ✅ Shipped |
| Zoho Inventory | 💡 |
| SAP Business One (Service Layer) | 💡 |
| NetSuite (SuiteQL REST) | 💡 |
| Microsoft Dynamics 365 Business Central | 💡 |

---

## Phase 8 — Power-User Experience 💡

Quality-of-life features for high-throughput warehouse operators.

| Feature | Description |
|---------|-------------|
| **Command palette** | Keyboard / search shortcut (`⌘K` or swipe) to jump to any screen or barcode | 💡 |
| **Drag-and-drop dashboard** | Operator can re-order, pin, or hide nav cards | 💡 |
| **Print labels** | Generate ZPL / PDF labels for items, bins, pallets, and receipts | ✅ |
| **Batch RFID inventory** | Continuous UHF tag reads → auto-populate reconciliation list | 💡 |
| **Push notifications** | Server-side webhook → FCM/APNs for low-stock alerts or PO arrivals | 💡 |
| **Plugin marketplace** | Third-party bude_api modules discoverable and installable from the app | 💡 |

---

## Phase 9 - End-to-End Product Hardening IN PROGRESS

Goal: make the app production-ready as a complete warehouse operator workflow, not just a set of working screens. This phase is about stability, security, usability, visual consistency, and field confidence across ERPNext, offline sync, and hardware.

### Golden Business Flows

Every release candidate must pass these flows on a clean install and on an existing logged-in install:

| Flow | Happy path | Failure/offline path | Status |
|------|------------|----------------------|--------|
| **Tenant + login** | Configure ERPNext URL, verify health, login, restore session after restart | Invalid URL, bad credentials, expired session, tenant reset | PLANNED |
| **Dashboard command center** | Dashboard loads KPIs, alerts, quick actions, sync status, role-aware nav | Offline dashboard uses cached counts and clear empty/error states | PLANNED |
| **Item lookup** | Search item, scan barcode, read RFID EPC, open item/asset detail | Scanner unavailable, unknown EPC/barcode, network failure | DONE |
| **Stock transfer** | Scan multiple items, edit qty, choose warehouses, queue transfer, sync to ERPNext | Offline queue, failed sync retry, duplicate barcode handling | DONE |
| **Goods receipt** | Receive free items or against PO, validate warehouse/PO lines, queue and sync | PO mismatch, unknown item, failed submission retry | DONE |
| **Stock reconciliation** | Batch scan/count, compare expected qty, supervisor approval when needed | Large variance approval, failed retry, offline count preservation | DONE |
| **Asset operations** | Find asset, move asset, create repair, view maintenance state | Unknown asset, failed queue op, offline repair/movement draft | DONE |
| **Audit + reporting** | Review submitted/pending/failed ops, export CSV, open ERP references | Missing ERP link, no file permission, empty report states | PLANNED |
| **Hardware** | Camera fallback, Chainway barcode, Chainway UHF read/write/inventory | SDK missing, device unsupported, reader busy, permission failure | IN PROGRESS |

Note: physical RFID validation is blocked until a reader is available. Until then, no-reader demo mode covers lookup and adapter-level tests.

### Stability Workstream

- Four-app ERPNext usability audit completed through its fifteenth pass: Inventory adds reorder/expiry planning, supplier/receipt insight, serial warranty/AMC status, storage-location context, stock-cover guidance, open purchase/sales commitments, quality-inspection history, active stock reservations, alternative-item availability, FEFO batch availability, BOM component readiness, active Work Order/operation progress, privacy-safe Job Card execution context, and a responsive reconciliation action row; HR adds privacy-safe career history, shift/holiday previews, a 30-day attendance trend, explained leave balances, standard employee skills, completed and scheduled training, current appraisal progress, compensation-safe promotion/transfer history, privacy-safe separation progress, employment lifecycle milestones, Employee Group memberships without coworker identities, and allow-list-aware upcoming leave restrictions; Sales adds company credit limits, multi-currency aging, buying history, order/delivery progress, capability-checked customer contact actions, quotation conversion guidance, customer-specific item prices, a weighted Opportunity pipeline, customer account ownership, returns/credit-note context, allocated receipt history, loyalty balances, Dunning collection context, Maintenance Schedule obligations, and Warranty Claim history; Helpdesk adds server-time SLA countdowns, SLA policy/working-hour and holiday-calendar context, published article suggestions, privacy-filtered activity, locally saved requester/agent filters, ticket contact/reference actions, related requester tickets, resolution/feedback context, agent-only customer ticket workload, active ticket assignments, scoped saved replies, visibility-safe classification guidance, agent-only team routing/availability, and privacy-tiered HD Customer organization context. Secondary insights fail independently, APIs remain version-tolerant, and a backend architecture guard enforces the no-custom-DocType rule. See `documentation/architecture/four-app-erpnext-usability-audit.md`.
- Lookup hardening done: notifier tests now cover item/asset/serial/unregistered matches, offline/network mapping, auth/server errors, and bind-then-resolve; widget tests cover manual lookup, barcode handoff, RFID read, demo reader banner, unavailable reader, and retry.
- Stock-transfer hardening done: golden-flow widget coverage now verifies scan-session handoff, duplicate quantity merge, inline quantity edit, same-warehouse validation, queue-first submit, company/location/tracking payload shape, warehouse-load failure, empty-lines state, and failed sync retry.
- Goods-receipt hardening done: golden-flow widget coverage now verifies scan-session handoff, duplicate quantity merge, inline quantity edit, target warehouse requirement, optional PO and location payload shape, tracking allocations, warehouse/PO error states, empty-lines state, and failed sync retry.
- Stock-reconciliation hardening done: golden-flow widget coverage now verifies warehouse-required state, scan-session handoff, expected quantity/variance display, duplicate quantity merge, inline count edit, location/tracking payload shape, queue-first submit, supervisor approval promotion, warehouse/empty states, and failed sync retry.
- Asset-operations hardening done: test coverage now verifies asset search/filter/detail rendering and unknown-asset failure states, move-asset purpose-dependent validation and duplicate-asset prevention, repair-request validation, queue-first submit payload shape for movement/repair/maintenance-completion, remote data source URL/param/error-mapping, submitter success/fatal/retryable classification, and failed sync retry.
- Add smoke/widget tests for the golden screens: splash, onboarding, login, dashboard, lookup, scan session, transfer, receipt, reconciliation, assets, sync, settings.
- Add route-contract tests for every `GoRoute`, including required `extra` values such as reconciliation approval.
- Add sync queue recovery tests for app restart, duplicate operation IDs, failed operation retry, and pending-approval state.
- Add hardware fake adapters for barcode/RFID so scanner and lookup flows can be tested without physical devices.
- Add backend unit tests for newer assets, alerts, reports, and RFID scan endpoints to match existing stock/items coverage.
- Add one Android build job and one Flutter test/analyze job to CI as release gates.

### Security Workstream

- Enforce HTTPS for production tenant URLs, while allowing localhost/dev hosts only in debug/dev configuration.
- Keep API keys/session material in `FlutterSecureStorage`; audit Hive/SharedPreferences to ensure no credentials or sensitive ERP payloads are stored there.
- Add automatic session expiry handling: intercept 401/403, clear stale auth, redirect to login, and preserve pending offline work.
- Finish role-based access consistently across dashboard cards, shell navigation, direct routes, and backend endpoint permissions.
- Add server-side permission checks for report and analytics endpoints; mobile UI gating is convenience only. (Stock and asset write endpoints now require a stock execution role via `require_stock_execution_role`.)
- Add safe logging rules: no passwords, API secrets, authorization headers, or full ERP payload dumps in logs.

### UX And Visual Workstream

- Replace remaining hardcoded user-visible strings with ARB keys in English and Arabic.
- Standardize loading, empty, error, and retry states using shared components.
- Polish high-throughput scanner screens for gloves/warehouse use: large tap targets, strong contrast, clear reader status, audible/haptic feedback settings.
- Align dashboard cards, KPI cards, forms, and list rows to one visual density system; keep operational screens quiet and scannable.
- Add responsive screenshots or golden checks for phone, tablet, and desktop-width Flutter layouts.
- Verify RTL layout on Arabic for dashboard, settings, forms, scanner, and reports.

### Hardware Workstream

- Complete physical validation checklist for Chainway C72/C66/R6: device probe, barcode scan, UHF single read, continuous inventory, power level, write EPC, lock/kill safeguards.
- Keep Chainway SDK artifacts documented with source URL, version/date, checksum, and install steps.
- Implement Zebra, Urovo, Honeywell, and Generic UHF adapters one vendor at a time, behind existing HAL contracts.
- Add a device lab test script: install APK, run probe, scan known barcode, read known EPC, submit lookup result.
- Add production guardrails for destructive RFID operations: write/lock/kill require explicit confirmation and manager role.

### Release Readiness

- `flutter analyze --no-pub` passes.
- `flutter test --no-pub` passes.
- Android `:app:assembleDebug` passes, and release build/signing steps are documented.
- Backend `pytest` passes for `bude_api`.
- No unresolved high-severity review findings for auth, sync, stock operations, or hardware operations.
- Field pilot checklist completed on at least one real ERPNext site and one real Chainway device.

---

## Phase 10 - Market-Driven Warehouse Execution IN PROGRESS

Positioning: sell this as an **ERPNext Warehouse Execution Mobile Pack**, not only an RFID app. The paid value is faster warehouse work, fewer stock mistakes, stronger controls, and mobile execution that can later become RFID-assisted.

| Priority | Capability | Customer value | Status |
|----------|------------|----------------|--------|
| 1 | **Bin / rack / shelf / staging location execution** | Operators can receive, count, move, and stage stock at the real physical location level while still using standard ERPNext warehouse structures | DONE |
| 2 | **Picking, packing, and dispatch from Sales Orders** | Turns Sales Orders into guided mobile fulfillment work with fewer missed or wrong shipments | DONE |
| 3 | **Batch, serial, lot, and expiry support** | Supports regulated, perishable, warranty, and high-value inventory workflows that customers expect to pay for | DONE |
| 4 | **Label printing for items, bins, pallets, and receipts** | Makes mobile execution tangible on the floor through barcode/RFID-ready labels and receiving documents | DONE |
| 5 | **Approval and audit controls** | Gives managers confidence around variance, high-value movement, and compliance-sensitive changes | DONE |
| 6 | **Backend permission hardening** | Ensures mobile convenience never bypasses ERPNext roles, companies, warehouses, or document permissions | DONE |
| 7 | **Guided warehouse task queue** | Converts open ERP work into assigned, prioritized mobile tasks for operators and supervisors | DONE |
| 8 | **Exception handling workflows** | Captures shortages, damages, unknown scans, substitutions, and blocked stock without leaving the floor | PLANNED |
| 9 | **ROI / value dashboard** | Shows management measurable gains: faster receiving, fewer adjustments, pick accuracy, and inventory variance reduction | PLANNED |
| 10 | **Admin onboarding console** | Helps customers configure companies, warehouses, default roles, devices, and pilot workflows without developer help | PLANNED |

Phase 10 label-printing V1 is done: the Flutter app now has `/labels`, item/bin-location/pallet/receipt label requests, PDF generation and system print preview, ZPL export/share, label size and quantity controls, ad-hoc pallet IDs, and entry points from item detail, warehouse locations, receipt queued confirmations, and receipt rows in the sync queue.

Phase 10 approval and audit controls V1 is done: Settings exposes count variance and transfer quantity approval thresholds, counts and transfers above those thresholds queue as `pendingApproval`, supervisor approval records `approved_by` and `approved_at`, pending queue cards show approval reasons, and audit summaries include locations, quantities, tracking, retry/error state, approval metadata, and ERP links.

Phase 10 backend permission hardening is done: stock execution endpoints now require ERPNext stock roles, permission failures return a clean `PERMISSION_DENIED` envelope, and mobile-facing backend reads use permission-aware Frappe APIs instead of bypassing document permissions.

Phase 10 guided warehouse task queue is done: backend `warehouse_tasks.list_open` aggregates open Purchase Orders, Sales Orders, planned Asset Maintenance Logs, and supported Frappe `ToDo` assignments with permission-aware reads; mobile `/tasks` groups and filters work, deep-links into receipt, fulfillment, and asset maintenance, and closes standard ToDos after related queued operations sync successfully.

Phase 10 admin master-data console (companies + warehouses slice) is done: mobile `/masters` hub/records/form screens (manager-gated via the existing router guard) drive the generic `masters.py` CRUD registry end-to-end — list, search, create, edit, and enable/disable — across Company, Warehouse, Location, and 13 other standard ERPNext masters, with full mobile test coverage. Default-role assignment, device pairing, and pilot-workflow seeding (currently a developer-only `bench execute` script) remain unbuilt, so priority 10 ("Admin onboarding console") stays PLANNED overall.

Execution rule: implement these one by one. Start with optional bin/location execution using standard ERPNext warehouse/bin concepts; do not add custom DocTypes unless standard ERPNext cannot represent the workflow.

Bin / rack / shelf / staging execution is implemented by treating physical locations as standard ERPNext child `Warehouse` records. Mobile operators select a parent warehouse, optionally choose one child location, and queued transfer, receipt, and reconciliation operations submit that child Warehouse as the effective stock location.

Sales Order fulfillment is implemented as a mobile Pick → Pack → Dispatch flow. Operators choose an open Sales Order, scan or enter exact pending quantities for every line, confirm packing, and queue a standard ERPNext `Delivery Note` linked to the original Sales Order lines.

Batch, serial, lot, and expiry support is implemented with standard ERPNext `Batch` and `Serial No` records. "Lot" maps to ERPNext `Batch`; mobile stock flows store tracking allocations in queued payloads, and receipts can create standard batches with expiry before the stock document is submitted.

---

## Architecture Constraints

- **No custom DocTypes** — every read/write uses standard ERPNext DocTypes (`Stock Entry`, `Purchase Receipt`, `Stock Reconciliation`, `Sales Order`, `Delivery Note`, `Bin`, `Stock Ledger Entry`).
- **HAL isolation** — all hardware-specific code lives in `lib/core/hardware/vendors/`. Business code only imports from `lib/core/hardware/adapters/`.
- **Offline-first** — every user-initiated operation is queued locally first; network is opportunistic.
- **Clean architecture** — each feature has independent `domain / data / presentation` layers; cross-feature dependencies flow only through providers.
- **i18n from day one** — all user-visible strings are ARB keys; new screens must add EN + AR entries before merge.

---

## Contributing

See `documentation/architecture/development-guidelines.md` for branch conventions, commit format, and test requirements. All new backend endpoints need pytest coverage; all new mobile screens need `flutter analyze` to be clean before merge.
