# Frappe API Layer (`bude_api`)

Copyright (C) 2026 Bude Global Enterprises. Licensed under the [GNU GPLv3](LICENSE).

Server-side extension for an ERPNext / Frappe site. Exposes whitelisted API methods that the Flutter client calls; **never** modifies ERPNext standard DocTypes.

## Status

Production-oriented API layer for the Bude inventory, HR, helpdesk, and sales
clients. The sales surface includes provider-neutral CRM, offline field work,
ERPNext order-to-cash, notification scheduling, and deployment diagnostics.

| Module | Purpose |
|---|---|
| `services/auth_service.py` | Wraps Frappe login/logout/session; token issuance |
| `services/erpnext_client.py` | Thin wrapper over Frappe ORM for standard DocTypes (Item, Stock Entry, Warehouse, etc.) |
| `api/health.py` | Whitelisted `ping` endpoint for client connectivity checks |
| `config/settings.py` | Reads environment + Frappe site_config values |

## Layout

```text
bude_api/
├── __init__.py
├── hooks.py                # Frappe app entrypoint
├── modules.txt
├── pyproject.toml          # package metadata for bench/pip
├── requirements.txt
├── config/
│   └── settings.py
├── services/
│   ├── auth_service.py
│   └── erpnext_client.py
├── api/
│   ├── auth.py
│   ├── health.py
│   └── items.py
├── middleware/
│   └── request_logger.py
├── utils/
│   └── response.py
└── tests/
    ├── test_auth.py
    ├── test_health.py
    └── test_items.py
```

## Install onto a Frappe bench

```bash
# from your frappe-bench directory
bench get-app bude_api /path/to/bude-rfid-inventory/backend/bude_api
bench --site <site> install-app bude_api
bench restart
```

## Calling endpoints

```
POST /api/method/login                            # Frappe built-in
GET  /api/method/bude_api.api.health.ping         # custom — returns service status
GET  /api/resource/Item?filters=[["disabled","=",0]]   # standard ERPNext REST
```

## Constraints

- No custom DocTypes.
- All persistence goes through ERPNext standard entities.
- Connectors for SAP / Zoho / other ERPs land under a future `integrations/` package using the Adapter pattern.

## Bude Sales CRM

The provider-neutral CRM API is exposed under
`/api/method/bude_api.api.sales_crm.*`. It uses standard ERPNext records by
default and can use Frappe CRM records when the optional `crm` app is installed
on the same site. A site always has one active provider; records are never
dual-written.

Add these keys to the site's `site_config.json`, then restart the bench:

```json
{
  "bude_sales_crm_enabled": 1,
  "bude_sales_crm_provider": "erpnext",
  "bude_sales_default_owner": "sales@example.com",
  "bude_sales_intake_secret": "replace-with-a-long-random-secret",
  "bude_sales_quote_response_secret": "use-a-separate-long-random-secret",
  "bude_sales_visit_max_accuracy_m": 100,
  "bude_sales_visit_geofence_m": 250,
  "bude_sales_commission_rate_percent": 2.5,
  "bude_sales_telemetry_enabled": 0,
  "bude_sales_plan": "pilot",
  "bude_sales_entitlement_status": "active"
}
```

Use `"frappe_crm"` only after installing Frappe CRM on the same site. CRM is
feature-flagged off when `bude_sales_crm_enabled` is absent. The bootstrap API
describes the provider, statuses, stages, sources, territories, writable/custom
fields, channel availability, and current-user capabilities.

Signed public intake sends compact JSON plus a current Unix `timestamp`, a hex
HMAC-SHA256 `signature` of `<timestamp>.<canonical-json>`, a channel key, and a
stable upstream `external_id`. Provider configuration, forms, email, assignment
rules, Meta, and optional WhatsApp setup remain in Frappe Desk; the mobile app
never stores connector credentials.

The CRM namespace includes bootstrap/capabilities, lead and deal CRUD,
duplicate and conversion choices, activities/timeline, tasks, private
attachments, provider-linked email, stage/outcome changes, quotation/order
handoff, analytics, manager bulk updates, connector health, and the signed
intake webhook. Mutations that can be replayed accept a stable
`client_request_id`; update operations accept `base_modified` and return a
`CONFLICT` response when the mobile revision is stale.

Attachments are stored as private standard `File` records, are permission
checked against their Lead/Opportunity/CRM parent, and are capped at 8 MB.
Outbound email creates a standard linked Communication through Frappe's mail
queue and refuses Lead records marked Do Not Contact.

Existing `Notification Log` fan-out recognizes these additional CRM
categories: lead assignment, task due/overdue, SLA breach, deal stage change,
and quotation expiry. Configure Firebase delivery and the existing device
registration endpoints to enable push transport; notification preferences are
per user.

The public `capture_intake` endpoint is for trusted server-to-server connectors
only. Keep `bude_sales_intake_secret` off every mobile client, use a fresh Unix
timestamp and stable external ID, and sign the exact canonical JSON payload.

The separate quotation-response secret signs expiring accept/decline links.
Accepted responses are written exactly once to the standard Quotation timeline;
payment links are standard ERPNext Payment Requests. Do not reuse either public
endpoint secret for another integration.

Run `bude_api.api.sales_crm.setup_doctor` after installation and upgrades. It
checks the selected provider, required DocTypes, scheduler, secrets, connector
capabilities, and role access without exposing credentials. The same report is
available to System Managers in **More > Setup doctor** in the sales app.

The scheduler calls the CRM reminder worker every 15 minutes. It creates
permission-aware `Notification Log` records for assignment, overdue follow-up,
SLA, stage, and quotation-expiry events; configured push delivery fans them out
to registered devices. Telemetry is disabled by default and, when explicitly
enabled, records only sanitized feature counters in the site's Error Log.

Field visit check-in validates GPS accuracy and optional distance from the
customer address. Offline visits remain clearly marked as unverified until
synced. Tune the two distance settings for the operating environment rather
than lowering them simply to remove validation failures.

See [the commercial pilot runbook](../../../documentation/sales/bude-sales-commercial-pilot.md)
for rollout, permissions, acceptance criteria, support, and packaging.
