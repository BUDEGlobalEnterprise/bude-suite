# Bude Sales commercial pilot

## Product position

Bude Sales is the offline-first field-sales and collections layer for ERPNext.
It preserves ERPNext as the accounting and inventory system of record while
giving representatives a phone workflow from lead capture through payment.
Frappe CRM can be selected as the CRM provider on the same site; Bude never
merges providers or dual-writes records.

The initial customer profile is a distributor, manufacturer, wholesaler, or
service business with 5–100 field representatives, unreliable mobile coverage,
and an existing or planned ERPNext deployment. The measurable promise is fewer
missed follow-ups, less order re-entry, faster collections, and trustworthy
field activity—not a generic replacement for every CRM.

## What the pilot includes

- Today queue, lead inbox, duplicate checks, qualification, tasks, activities,
  conversion, pipeline, loss reasons, and manager playbooks.
- A cached field-day pack with accounts, tasks, catalog, route ordering, map
  handoff, GPS-verified visits, and an explicit unverified offline fallback.
- ERP-authoritative UOM, pricing, discount, tax, stock, and credit previews;
  replay-safe quotations, orders, invoices, and payments.
- Quotation PDF sharing, expiring signed accept/decline links, linked document
  progression, Payment Requests, outstanding collections, and receipt sharing.
- Manager outcomes for response and task coverage, quotation conversion,
  invoiced/outstanding value, credited revenue, commission estimates, and
  recommended interventions.
- English and Arabic/RTL UI, role-aware access, setup diagnostics, notification
  preferences, opt-in sanitized telemetry, and connector health visibility.

## Site configuration

1. Install ERPNext and `bude_api`; optionally install a compatible Frappe CRM
   release on the same site.
2. Set `bude_sales_crm_enabled` and exactly one provider: `erpnext` or
   `frappe_crm`.
3. Generate different long random values for `bude_sales_intake_secret` and
   `bude_sales_quote_response_secret`.
4. Configure the default owner, visit accuracy/geofence, commission rate, and
   plan/entitlement fields described in `backend/bude_api/README.md`.
5. Run migrations, restart workers and scheduler, then open **Setup doctor** as
   a System Manager and clear every required failure.
6. Configure email, Firebase push, Meta, WhatsApp, and telephony only when the
   corresponding provider/app is installed. Missing optional connectors must
   not block manual sales work.

## Permissions and operating model

- Sales Users see assigned or otherwise permitted leads, deals, customers, and
  commercial documents. Sales Managers receive team lists, bulk actions,
  outcomes, recommendations, and playbooks.
- Accounts permissions remain mandatory for submitting invoices and payments.
  Inventory fulfillment remains in the inventory app, with status and deep
  links exposed to Sales.
- Do Not Contact blocks outbound email and WhatsApp. Connector secrets stay on
  the server. Public payloads are signed, size-limited, replay-protected, and
  logged with sensitive fields removed.
- A pilot administrator owns provider configuration, assignment/SLA rules,
  users, territories, price lists, tax templates, credit limits, and failed
  connector retries in Frappe Desk.

## Four-week pilot

Week 0 imports and deduplicates accounts/leads, assigns territories, trains one
manager and a small rep cohort, and records baseline response, order-entry, and
collection times. Week 1 validates manual lead-to-quote and offline field days.
Week 2 enables quotation responses and collections. Week 3 tunes assignment,
SLA, route, and playbook rules. Week 4 reviews outcomes and decides rollout.

Exit criteria:

- A representative captures a complete lead in under one minute.
- Offline lead plus dependent note/task syncs to exactly one server record.
- Every active lead/deal has an owner and next action.
- Lead/deal through quotation, order, invoice, and payment stays linked without
  re-entry or provider DocType names appearing in normal UI.
- GPS verification, authoritative totals, credit warnings, quotation responses,
  and payment allocation work on real pilot data.
- Existing Customer 360, inventory, invoicing, payment, and sync flows have no
  regression; all cross-role and cross-territory checks pass.

## Commercial packaging hypothesis

The codebase's open-source license makes operations and outcomes the strongest
commercial layer. Start with a paid implementation package plus a managed plan
priced per active field representative per month, with a site minimum. Include
hosting/upgrades, mobile release management, backups, setup diagnostics,
connector monitoring, and a defined response SLA. Charge separately for data
cleanup/migration, custom integrations, WhatsApp/telephony usage, and bespoke
workflows.

Do not fix a public price until two design-partner pilots expose actual support
cost. Track activation (first lead/visit/order), weekly active reps, follow-up
coverage, quote conversion, collection cycle, sync failure rate, and support
minutes per active rep. A customer should expand only when those measures show
economic value; AI assistance stays an optional later tier after clean activity
and outcome data exists.

## Release and rollback

Run the backend and Flutter suites, static analysis, and Android/web release
builds before every pilot release. Enable CRM per site, pilot ERPNext mode
first, and certify Frappe CRM mode against the installed stable release before
production. Rollback disables `bude_sales_crm_enabled`; existing customer and
order-to-cash screens continue to work and no CRM records are migrated or
deleted. Export Frappe backups before application or provider upgrades.
