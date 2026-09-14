# Architecture Overview

## Goals

- Build a cross-platform inventory client on top of **ERPNext** without modifying ERPNext.
- Start barcode-first; allow RFID hardware to plug in later without rewrites.
- Keep the mobile app usable offline; sync state to ERPNext as connectivity allows.
- Keep the door open for future ERP backends (Zoho, SAP, NetSuite, Dynamics 365).

## High-level layout

```
+----------------------+        HTTPS         +-------------------------+
|  Flutter Client      |  <--------------->   |  Frappe API Layer       |
|  (Android/iOS/Win/   |   JSON / REST        |  (bude_api app)         |
|   Web)               |                      |                         |
|  - Riverpod state    |                      |  - whitelisted methods  |
|  - Hive offline      |                      |  - thin wrapper over    |
|  - Repository layer  |                      |    Frappe ORM           |
+----------------------+                      +-----------+-------------+
                                                          |
                                                          v
                                              +-----------+-------------+
                                              | ERPNext (standard       |
                                              | DocTypes only)          |
                                              +-------------------------+
```

## Mobile (Flutter) — Clean Architecture

Three layers per feature module:

| Layer | May import | Contains |
|---|---|---|
| `presentation` | `domain` | Screens, widgets, state notifiers |
| `domain` | (nothing project-specific) | Entities, repository contracts, use cases |
| `data` | `domain` | API clients, DTOs, repository implementations, local cache |

State management: **Riverpod**. Offline cache: **Hive**. HTTP: **Dio**.

## Backend (Frappe) — Adapter pattern over ERPNext

`bude_api` exposes whitelisted endpoints. It does **not** create new DocTypes — all persistence routes through ERPNext standard entities (Item, Stock Entry, Warehouse, Serial No, Batch, ...).

When future ERPs (SAP, Zoho, ...) are added, each will live behind the same interface as `ERPNextClient`, so the mobile app stays unchanged.

## Hardware abstraction

The `barcode` module starts with a camera-based scanner. RFID readers (Chainway, Zebra, Urovo) land later behind a `Scanner` interface so the presentation layer is hardware-agnostic.

## Multi-tenancy

The mobile app stores per-site connection config (ERPNext URL + credentials) so one binary can serve multiple tenants.
