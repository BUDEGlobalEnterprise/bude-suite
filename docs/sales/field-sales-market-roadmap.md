# Field-sales market evidence and product roadmap

Reviewed 4 August 2026. This is product evidence, not a claim that every listed
competitor implements every feature equally well.

## What customers are buying

The recurring field-sales job is broader than contact management: representatives
need accounts and context before a visit, a practical route, reliable work in
weak coverage, quick activity capture, accurate prices and stock, an order or
quote created at the customer, and a way to collect and prove payment. Managers
need coverage and outcome evidence without turning the product into surveillance.

This pattern is visible across current field-sales products. Outfield markets
offline account mapping, route optimization, GPS activity, pipelines, order and
inventory work; Dynamics Mobile emphasizes preloaded ERP data, geofence-verified
visits, orders, invoices, payments, and offline operation; Delta presents beat
planning, order punching, collections, GPS visits, and offline sync as one
workflow. These converging feature sets are a useful demand signal, though their
marketing claims are not independent performance evidence.

Sources:

- [Frappe CRM lead workflow](https://docs.frappe.io/crm/lead)
- [Frappe CRM assignment rules](https://docs.frappe.io/crm/assignment-rule)
- [Frappe CRM task reminders](https://docs.frappe.io/crm/task)
- [Frappe CRM releases](https://github.com/frappe/crm/releases)
- [Outfield field-sales product](https://www.outfieldapp.com/)
- [Dynamics Mobile field sales](https://www.dynamicsmobile.com/app/van-sales-distribution/)
- [Delta Field Sales Google Play listing](https://play.google.com/store/apps/details?id=com.deltatechnepal.delta_sales_app)

## Problems Bude must solve

| Customer problem | Product response | Commercial measure |
|---|---|---|
| Leads wait without an owner or next action | Today queue, assignment/SLA visibility, reminders, playbooks | first-response time and follow-up coverage |
| Reps retype CRM data into ERP orders | linked conversion and source-aware quote/order flow | order-entry time and correction rate |
| Connectivity makes a field app unreliable | cached field-day pack, offline queue, dependency resolution, replay IDs | sync success and duplicate rate |
| Routes and visits are difficult to verify | territory pack, optimized ordering, map handoff, GPS accuracy/geofence | visits completed and verified rate |
| Mobile totals differ from ERP | server-side price/UOM/tax/credit preview | rejected orders and pricing corrections |
| Quotes disappear after they are sent | PDF share, signed response, expiry reminders, linked order | response and quote-to-order conversion |
| Collections lack context and proof | outstanding queue, Payment Entry, allocation, receipt PDF | days-to-collect and overdue value |
| Managers see activity but not outcomes | funnel, weighted pipeline, revenue credit, coverage, recommendations | win rate, invoiced value, forecast error |
| Deployment failures consume trust | Setup Doctor, connector health, capability hiding, entitlement status | time-to-first-value and support load |

## Roadmap state

The end-to-end foundation above is implemented behind the CRM feature flag for
ERPNext and same-site Frappe CRM providers. The next release gate is real-site
certification: v15/v16 fixtures, a supported current Frappe CRM 1.x release,
poor-network field trials, Arabic device testing, and one complete accounting
cycle with each pilot's tax and credit configuration.

After pilots, prioritize only evidence-backed gaps:

1. Time-window/capacity route optimization and manager-created beat plans when
   route adherence or travel time is a demonstrated cost.
2. Configurable visit/merchandising forms and photo evidence for distribution
   verticals that require retail execution.
3. Cheque/mobile-wallet collection methods and approval workflows where local
   payment behavior requires them.
4. Renewal, reorder, and churn-risk prompts based on actual ERP purchase cadence.
5. AI summaries, objection coaching, next-best action, and forecasting only
   after permission-safe activity and outcome data is sufficiently complete.

The defensible wedge is therefore not “another CRM.” It is a supported,
offline, ERPNext-native field revenue workflow whose value can be demonstrated
in response time, order accuracy, route coverage, conversion, and cash collected.
