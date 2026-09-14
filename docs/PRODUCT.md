# Bude RFID Inventory
## Product Showcase & Operator Guide

> **Audience:** warehouse managers, inventory operators, IT administrators, and sales engineers.
> **Format:** read top-to-bottom for a demo script, or jump to a module section for hands-on training.
> Every feature described here reflects the current state of `main`.

---

## 1. Executive Summary

Bude RFID Inventory is a mobile-first, offline-capable warehouse management companion built on **ERPNext / Frappe** with a native **Flutter** Android app. It extends standard ERPNext inventory workflows with barcode scanning, RFID-assisted lookup, and UHF RFID hardware support — without adding custom DocTypes or breaking existing processes.

A warehouse operator can scan items, move stock between locations, receive goods against a purchase order, and count shelves — all from a handheld device, with or without network connectivity. Operations queue locally and sync to ERPNext the moment the connection returns.

**What makes it different**

- **Zero custom DocTypes.** Every operation writes to standard ERPNext documents (`Stock Entry`, `Purchase Receipt`, `Stock Reconciliation`). No proprietary data layer to migrate or maintain.
- **Hardware-agnostic.** Chainway, Zebra, Urovo, Honeywell, and generic UHF BLE readers sit behind a single Hardware Abstraction Layer. Swap scanners without touching business logic.
- **Offline-first by design.** The sync queue persists operations locally in Hive; network is opportunistic. Operators are never blocked waiting for a signal.
- **Enterprise-ready from day one.** Multilingual (EN/AR RTL), theming, role-scoped screens, analytics dashboards, and CSV export are not add-ons — they ship in core.
- **ERP-connector architecture.** ERPNext is the first backend; Zoho, SAP B1, NetSuite, and Dynamics 365 connectors can be added without touching the mobile app.

---

## 2. Platform at a Glance

| # | Capability area | Status | Where to find it |
|---|-----------------|--------|-----------------|
| 1 | **Core Inventory** — item search, barcode/RFID lookup, stock transfer, receipt, reconciliation | ✅ Live | *Home* dashboard, scan screens |
| 2 | **Offline Sync** — Hive queue, SyncEngine, pending-ops viewer | ✅ Live | *Sync Queue* screen |
| 3 | **Hardware Abstraction Layer** — barcode + RFID adapters, vendor stubs | ✅ Live | `lib/core/hardware/` |
| 4 | **Enterprise Foundation** — Material 3 theming, i18n EN/AR RTL, settings | ✅ Live | *Settings* screen |
| 5 | **Operational Intelligence** — item ledger history, warehouse stock overview, bulk scan sessions | ✅ Live | *Warehouses*, *Item Detail* |
| 6 | **Analytics & Reporting** — stock aging, variance dashboard, transfer throughput, CSV export | ✅ Live | *Analytics* screen |
| 7 | **RFID Hardware Integration** — no-reader demo mode and lookup hardening live; real readers pending hardware | 🔄 In Progress | Phase 4 |
| 8 | **Role-Based Access & Multi-Entity** — role-scoped screens, multi-company, biometric | 🔲 Planned | Phase 6 |
| 9 | **Additional ERP Connectors** — Zoho, SAP B1, NetSuite, Dynamics 365 | 💡 Idea | Phase 7 |
| 10 | **Power-User Experience** — label printing live; command palette, batch RFID count, and push notifications under consideration | 🔄 In Progress | Phase 8 / 10 |

Legend: ✅ shipped on `main` · 🔲 scoped, not yet started · 💡 under consideration.

---

## 3. Core Inventory Workflows

The operational spine is **item lookup → scan → stock operation → sync**.

An operator opens the app, searches for an item by name or scans its barcode, sees real-time stock levels per warehouse, and initiates a transfer, receipt, or reconciliation. The operation is written to the local sync queue immediately; on submission it posts to ERPNext as a standard document.

**Stock transfer** moves quantity between two warehouses. **Goods receipt** receives items against an open Purchase Order (or free-form). **Stock reconciliation** counts a shelf and submits the delta — ERPNext generates the adjustment entry automatically.

**Bin / rack / shelf / staging execution** uses standard ERPNext child **Warehouse** records for physical locations. Operators still select the parent warehouse for compatibility, then optionally choose a child location; queued transfer, receipt, and count operations sync against that child Warehouse as the effective stock location.

**Sales Order fulfillment** guides operators through Pick, Pack, and Dispatch stages. V1 requires exact fulfillment of every pending Sales Order line before dispatch can be queued; sync creates a standard ERPNext **Delivery Note** linked back to the Sales Order lines.

**Batch, serial, lot, and expiry support** uses standard ERPNext **Batch** and **Serial No** records. In BUDE, "lot" means ERPNext Batch; mobile receipt, transfer, count, and Sales Order dispatch payloads carry optional tracking allocations that sync offline-first.

**Label printing V1** generates item, bin/location, pallet, and receipt labels without custom DocTypes. Operators can open the *Labels* screen, print/share PDF labels, or export ZPL for thermal label printers. Item detail, warehouse locations, receipt queued confirmations, and receipt rows in the sync queue can launch label printing with the relevant local payload.

**Approval and audit controls V1** route high-variance counts and high-quantity transfers into the existing pending-approval queue. A Stock Manager must approve with second-user credentials before sync, and the audit trail records approval reason, approver, approval time, operation summary, retry/error state, and ERP links when available.

**Guided warehouse task queue V1** turns open Purchase Orders, Sales Orders, Asset Maintenance Logs, and supported Frappe ToDo assignments into a mobile *Tasks* queue. Operators can filter assigned work, open the right receipt/fulfillment/maintenance workflow, and let the offline sync queue close related ToDos after successful ERP sync.

**Bulk scan sessions** let operators scan multiple items continuously before committing: the camera viewfinder stays open, duplicates increment quantity, and the operator edits counts inline before hitting *Use N items* to pass the list to any operation screen.

**Offline-first sync queue** (Hive) stores every pending operation locally. The `SyncEngine` retries on connectivity restore. The *Pending Queue* screen shows status, errors, and lets operators retry or discard individual operations.

**Phase 9 hardening status**

- **Item lookup hardening is done.** The lookup flow keeps `Read RFID` visible even when no reader is available, shows an inline reader-unavailable error, resolves manual input, barcode handoff, and RFID EPC reads, supports demo RFID mode, maps network failures to retryable offline UI, and covers bind-then-resolve behavior in tests.
- **Stock transfer hardening is done.** The queue-first transfer flow has golden-flow coverage for scan-session handoff, duplicate scan quantity merge, inline quantity editing, source/target validation, warehouse-load failure, empty-lines state, failed sync retry, and queued payload shape including company, locations, and tracking allocations.
- **Goods receipt hardening is done.** The receipt flow has golden-flow coverage for free and PO-backed receipt payloads, scan-session handoff, duplicate quantity merge, inline quantity editing, target warehouse requirement, warehouse and PO load failures, empty-lines state, failed sync retry, and queued payload shape including company, location, PO, quantities, and tracking allocations.
- **Stock reconciliation hardening is done.** The count flow has golden-flow coverage for warehouse-required state, scan-session handoff, expected quantity and variance display, duplicate quantity merge, inline count editing, supervisor approval promotion, empty/error states, failed sync retry, and queued payload shape including company, location, quantities, and tracking allocations.
- **Label printing V1 is done.** The app now has `/labels`, request builders, PDF and ZPL generation, quantity/size/format controls, pallet ID generation, item/bin/pallet/receipt forms, and tests for generators, validation, route extras, and launch points from item detail, warehouse locations, receipt queue snackbar, and pending queue receipt rows.
- **Approval and audit controls V1 is done.** Transfer and count approval thresholds live in Settings, pending approvals reuse the existing supervisor route, approvals add `approved_by` and `approved_at` metadata, and audit summaries expose approval reasons, quantities, locations, tracking, status, retry errors, and ERP links.
- **Backend permission hardening is done.** Stock execution endpoints now require ERPNext stock roles, permission failures return a clean `PERMISSION_DENIED` envelope, and mobile-facing backend reads use permission-aware Frappe APIs instead of bypassing document permissions.
- **Guided warehouse task queue is done.** Backend task aggregation uses permission-aware ERPNext/Frappe reads for Purchase Orders, Sales Orders, Asset Maintenance Logs, and supported ToDos; mobile `/tasks` groups and filters work, launches existing queue-first workflows, and closes standard ToDos only after the related sync operation succeeds.

---

## 4. Enterprise Foundation

**Settings screen — 6 sections**

| Section | What it controls |
|---------|-----------------|
| **Appearance** | Light / dark / system theme; language (English, العربية) |
| **Connection** | Company ERPNext URL, API-key credentials |
| **Defaults** | Default source and target warehouse pre-filled on operation screens |
| **Scanning** | Auto-advance after successful scan; vibration / sound feedback |
| **Sync & Offline** | Sync interval; manual *Sync Now* trigger |
| **Account** | Display name, role badge, sign out |

**Design system** — Material 3 with a custom token layer (`AppColors`, `AppSpacing`, `AppRadius`, `AppTypography`). Light and dark themes adapt automatically. RTL layouts flip via `Locale('ar')` with no extra code.

**i18n** — 80+ localisation keys in English and Arabic ARB files. Every new screen must add both before merge.

---

## 5. Operational Intelligence

### Item Detail

The item detail screen has two tabs:

- **Stock tab** — current quantity by warehouse (actual, reserved, projected).
- **History tab** — Stock Ledger Entry timeline, newest-first, grouped by date. Inbound lines are green; outbound are red.

### Warehouse Overview

The *Warehouses* screen lists all ERPNext warehouses. Tapping one opens **Warehouse Detail**: every bin line with actual and reserved quantities, plus an item count header. Pull-to-refresh on both screens.

### Bulk Scan Sessions

Tap *Scan Session* from any operation screen to open a continuous camera scan. Items accumulate in a list; qty is editable inline; duplicates auto-increment. Hit *Use N items* to load the list into the parent operation. Works for transfer, receipt, and reconciliation.

---

## 6. Analytics & Reporting

**Screen:** *Analytics* (bottom nav)

| Report | What it shows |
|--------|--------------|
| **Stock Aging** | Items idle for N days per warehouse; threshold picker (7 / 14 / 30 / 60 / 90 d); sorted by days idle |
| **Variance Dashboard** | Submitted reconciliation history — counted vs expected per line, colour-coded surplus / deficit, expandable cards |
| **Transfer Throughput** | Operations per day from local Hive queue; stacked bar chart; 7 / 14 / 30-day period picker |
| **Export to CSV** | Warehouse stock or item ledger exported as `.csv` via system share sheet |

---

## 7. Hardware Abstraction Layer

All hardware-specific code lives in `lib/core/hardware/vendors/`. Business code only imports from `lib/core/hardware/adapters/`. Swapping a scanner vendor requires touching one file.

**Barcode adapters** — `BarcodeAdapter` interface with a `startScan()` stream. Camera adapter is always available (`CameraBarcodeAdapter` via `mobile_scanner`). Vendor adapters delegate to the manufacturer SDK.

**RFID adapters** — `RfidAdapter` interface with a `startInventory()` stream of EPC strings. A development/demo adapter is available when no physical reader is present; real vendor validation remains blocked until reader hardware is available.

**Device probe** — `AndroidDeviceProbe` interrogates the device at launch via `bude.hardware/probe` method channel and selects the correct adapters automatically. No manual configuration needed on Chainway, Zebra, or Urovo devices.

| Vendor | Barcode | RFID | Devices | Status |
|--------|---------|------|---------|--------|
| **Chainway** | ✅ Stub | ✅ Stub | C72, C66, R6 | 🔲 Real SDK — Phase 4 |
| **Zebra** | ✅ Stub | ✅ Stub | TC-series + RFD40/RFID8500 | 🔲 Real SDK — Phase 4 |
| **Urovo** | ✅ Stub | ✅ Stub | DT40 RFID, i9000s | 🔲 Real SDK — Phase 4 |
| **Honeywell** | ✅ Stub | — | CT40, EDA52, EDA61k | 🔲 Real SDK — Phase 4 |
| **Generic UHF** | — | ✅ Stub | BLE / USB / LLRP readers | 🔲 Real SDK — Phase 4 |
| **Demo RFID** | — | ✅ Simulated | Dev / demo without reader | ✅ Live |

---

## 8. Backend API (bude_api)

`bude_api` is a lightweight Frappe app that sits on top of an existing ERPNext installation. It adds whitelisted API methods only — no custom DocTypes, no schema migrations beyond optional RFID EPC fields.

> **First-time setup:** run `bench migrate` after installing `bude_api` to create the `bude_epc` custom fields on Item and Stock Entry Detail.

**Endpoint groups**

| Group | Key endpoints |
|-------|--------------|
| `auth` | `login`, `session_info` — API-key authentication, session dictionary |
| `items` | `search`, `get_by_barcode`, `get_stock`, `get_ledger` |
| `warehouses` | `list`, `get_stock` |
| `stock` | `create_transfer`, `create_receipt`, `create_reconciliation` |
| `purchase_orders` | `list_open` |
| `analytics` | `get_stock_aging`, `get_reconciliation_history` |
| `warehouse_tasks` | `list_open`, `complete` — mobile task queue aggregation and ToDo completion |
| `branding` | `get` — feature flags from installed apps |
| `health` | `ping` — version probe |

All responses use a `{ success, data, message }` envelope. Errors return `success: false` with a human-readable `message`.

---

## 9. Architecture Principles

- **No custom DocTypes** — reads and writes use standard ERPNext documents only, including Sales Orders and Delivery Notes for fulfillment.
- **HAL isolation** — all hardware-specific code is confined to `lib/core/hardware/vendors/`.
- **Offline-first** — every user operation is queued locally before any network attempt.
- **Clean architecture** — each feature has independent `domain / data / presentation` layers. Cross-feature dependencies flow only through Riverpod providers.
- **i18n from day one** — all user-visible strings are ARB keys. New screens must add EN + AR entries before merge.

---

## 10. Guided Demo Walkthrough (10 minutes)

1. **Login & dashboard:** launch the app → enter the ERPNext URL → log in → show the adaptive dashboard grid with feature-flag-gated cards.
2. **Item search:** tap *Items* → type a partial name → open an item → show the **Stock** tab (qty per warehouse) then the **History** tab (ledger timeline).
3. **Barcode scan:** from the item search screen tap the scan icon → point the camera at any barcode → confirm the item resolves and stock is shown.
4. **Bulk scan session:** open *Stock Transfer* → tap *Scan Session* → scan 3–4 items → edit a quantity inline → hit *Use 4 items* → show the populated transfer form.
5. **Offline mode:** toggle airplane mode → initiate a stock reconciliation → submit → open the *Sync Queue* screen to show the pending operation → restore connectivity → watch it sync.
6. **Warehouses:** tap *Warehouses* → select a warehouse → show bin lines with actual / reserved quantities → pull to refresh.
7. **Analytics:** open the *Analytics* screen → show the *Stock Aging* report with a 30-day threshold → switch to *Variance Dashboard* → export a CSV.
8. **Settings:** open Settings → switch theme to dark → switch language to Arabic → confirm the RTL layout flips.

---

## 11. Hands-on Training Labs

> Each lab is a self-contained exercise for new operators or onboarding sessions.

**Lab A — Search and scan an item**
Open *Items*, search for any item name, open the result, check stock on the *Stock* tab, then open the *History* tab and identify the most recent inbound movement.

**Lab B — Complete a stock transfer**
Open *Stock Transfer*, select a source warehouse and a target warehouse, scan one item via the camera, set quantity to 2, submit. Verify the operation appears in the *Sync Queue* as pending (if offline) or succeeds immediately (if online).

**Lab C — Receive goods against a PO**
Open *Goods Receipt*, choose *Against Purchase Order*, pick an open PO from the list, scan the items as they are unboxed, and submit. Confirm a Purchase Receipt is created in ERPNext.

**Lab D — Cycle count a shelf**
Open *Stock Reconciliation*, select a warehouse, enter expected quantities for three items, submit, and confirm the variance appears. Check the *Variance Dashboard* in Analytics.

**Lab E — Read the stock aging report**
Open Analytics → *Stock Aging* → set threshold to 14 days → identify the top three items by days idle → export as CSV and share.

**Lab F — Simulate offline and sync**
Enable airplane mode. Submit a stock transfer. Open *Sync Queue* and confirm the operation is queued. Re-enable connectivity. Watch the operation sync and the queue clear.

---

## 12. Role Quick Reference

| Role | Primary screens |
|------|----------------|
| **Warehouse Operator** | Item search, Barcode scan, Stock Transfer, Goods Receipt, Reconciliation, Sync Queue |
| **Cycle Counter** | Item search, Reconciliation, Variance Dashboard, Warehouses |
| **Receiving Clerk** | Goods Receipt (against PO), Item History |
| **Warehouse Supervisor** | Analytics (aging, variance, throughput), Warehouses, Settings |
| **IT / ERPNext Admin** | Settings (URL, API key), bude_api install, bench migrate |

---

## 13. Sales Talking Points

- *"Zero new DocTypes."* — installs on any live ERPNext instance in minutes; no schema risk, no data migration.
- *"Works without Wi-Fi."* — the sync queue means operators are never blocked on signal. Data posts to ERPNext when the connection returns.
- *"One HAL, every scanner."* — Chainway, Zebra, Urovo, Honeywell, and generic UHF readers behind one interface. No rewrites when changing hardware.
- *"Enterprise i18n on day one."* — English and Arabic with full RTL layout; adding a new language is one ARB file.
- *"ERP-agnostic tomorrow."* — the connector layer means Zoho, SAP B1, or NetSuite can be added without a mobile app rewrite.
- *"Analytics you can share."* — stock aging, variance, and throughput export to CSV in two taps.

---

*This guide reflects the state of `main`. For the full feature roadmap and vendor SDK activation status, see [ROADMAP.md](roadmap/inventory.md) and [ROADMAP V2](roadmap/inventory-v2.md).*
