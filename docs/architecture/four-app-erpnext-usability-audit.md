# Four-App ERPNext Usability Audit

Date: 2026-07-18

Scope: Bude Inventory, HR, Sales, Helpdesk, and their shared `bude_api`
backend. The governing constraint is that Bude must not create custom
DocTypes. Features must use standard ERPNext, Frappe, and Frappe Helpdesk
DocTypes. Existing RFID Custom Fields remain permitted because they extend a
standard DocType rather than creating a new one.

## Outcome

Fifteen cross-app hardening passes now close the largest detail-screen context
gaps while keeping every existing API response backward-compatible:

| App | Standard record | Added operational context | Usability change |
|-----|-----------------|---------------------------|------------------|
| Inventory | `Item` | brand, sales/purchase/stock flags, valuation, UOMs, safety stock, lead time, shelf life, warranty, weight, end of life, origin | Item detail now supports stock-planning and handling decisions without opening ERPNext |
| HR | `Employee` | status, employee number, branch, holiday list, preferred email, addresses, contract end, notice days | Profile now groups employment, contact, address, and emergency information |
| Sales | `Customer`, `Contact`, `Address`, standard sales documents | customer type/status, currency, payment terms, tax details, primary contact/address, website, industry, market segment | Customer 360 now has a commercial summary and readable contact/address/document cards |
| Helpdesk | `HD Ticket` | response/resolution deadlines, SLA status, customer/contact, source, first response, opening/resolution dates | Ticket detail now exposes requester and SLA context needed to prioritize work |

The second pass adds one independently loaded planning or insight surface per
app:

| App | Standard records | Second-pass delivery |
|-----|------------------|----------------------|
| Inventory | `Item Reorder`, `Bin`, `Batch`, `Stock Ledger Entry` | Reorder thresholds, projected stock, suggested quantities, material-request type, and expired/expiring batch warnings |
| HR | `Employee Education`, `Employee Internal Work History`, `Employee External Work History` | A Career section with education and internal history plus privacy-safe external experience |
| Sales | `Customer Credit Limit`, `Sales Invoice` | Company credit limits, currency-separated receivable aging, the ten oldest overdue invoices, and a visible 500-row truncation warning |
| Helpdesk | `HD Ticket`, `HD Article` | Server-time SLA countdowns and published knowledge suggestions authorized through ticket visibility |

The third pass adds independently loaded day-to-day context without introducing
new schema:

| App | Standard records | Third-pass delivery |
|-----|------------------|---------------------|
| Inventory | `Item Default`, `Purchase Receipt`, `Purchase Receipt Item` | Default supplier and buying setup plus recent receipt quantities, rates, warehouses, and dates |
| HR | `Shift Assignment`, `Shift Type`, `Holiday List`, `Holiday` | Current shift and upcoming holiday/weekly-off preview on Profile |
| Sales | `Sales Invoice`, `Sales Invoice Item` | Currency-separated buying history with top purchased items, quantities, invoice counts, latest purchase dates, and a scan-limit warning |
| Helpdesk | `Version`, `HD Ticket` | Privacy-filtered ticket activity; requesters see operational field changes while assignment events remain agent-only |

The fourth pass closes the remaining high-value operational gaps identified by
the audit:

| App | Standard records or local facility | Fourth-pass delivery |
|-----|------------------------------------|----------------------|
| Inventory | `Serial No` | Serial-level warranty and AMC status, including active, expiring, expired, and unknown summaries |
| HR | `Attendance` | A recent 30-day attendance trend with status totals, average working hours, late entries, and early exits |
| Sales | `Sales Order`, `Delivery Note` | Order delivery/billing progress, overdue-order visibility, and recent delivery notes |
| Helpdesk | Flutter `SharedPreferences` | Separately scoped saved filters for requester tickets and the agent queue, without adding server schema |

The fifth pass improves physical context and direct actionability:

| App | Standard records or platform facility | Fifth-pass delivery |
|-----|---------------------------------------|---------------------|
| Inventory | `Warehouse`, `Bin` | Independently loaded storage locations with hierarchy/type, address/contact context, and on-hand, reserved, ordered, and projected quantities |
| HR | `Leave Allocation`, `Leave Application` | Current-period balances now explain new allocation, carry-forward, encashment, usage, allocation dates, and percentage consumed |
| Sales | Device phone, email, browser, and maps handlers | Capability-checked call, email, map, and website actions on Customer 360 and linked contact/address cards |
| Helpdesk | Device email handler and clipboard | Capability-checked requester email and one-tap ticket-reference copying on Ticket Detail |

The sixth pass adds decision guidance from standard operational history:

| App | Standard records | Sixth-pass delivery |
|-----|------------------|---------------------|
| Inventory | `Stock Ledger Entry`, `Bin` | Recent inbound/outbound movement, average daily demand, current/projected stock, estimated days of cover, latest movement, and a visible 1,000-row scan warning |
| HR | `Employee Skill Map`, `Employee Skill` | Optional employee skills with five-point proficiency and evaluation dates in the Profile Career section |
| Sales | `Quotation` | Independently loaded quotation counts and per-record guidance to convert, follow up, renew, or take no action based on status and validity |
| Helpdesk | `HD Ticket` | Visibility-authorized related tickets from the same requester, independently loaded and navigable from Ticket Detail |

The seventh pass makes open commitments, learning, pricing, and closure context
visible at the point of work:

| App | Standard records | Seventh-pass delivery |
|-----|------------------|-----------------------|
| Inventory | `Purchase Order Item`, `Sales Order Item` | Independently loaded open incoming supply and outgoing demand, pending quantities, due dates, warehouse context, and net committed stock; the reconciliation action row also wraps safely on narrower layouts |
| HR | `Employee Skill Map`, `Employee Training` | Optional standard training history and completion dates in the Profile Career section |
| Sales | `Item Price` | Independently loaded customer-specific item prices with price list, currency, UOM, validity, and active/upcoming/expired status |
| Helpdesk | `HD Ticket` | Metadata-filtered resolution details plus customer feedback and rating on Ticket Detail, without exposing `feedback_extra` |

The eighth pass adds quality, scheduling, pipeline, and support-load context:

| App | Standard records | Eighth-pass delivery |
|-----|------------------|----------------------|
| Inventory | `Quality Inspection` | Independently loaded inspection outcomes with accepted/rejected summaries, inspection type, source document, batch, sample size, inspector, and remarks |
| HR | `Training Event`, `Training Event Employee` | Employee-scoped scheduled training with time, location, type, mandatory status, trainer, and certificate availability |
| Sales | `Opportunity` | Independently loaded customer pipeline with stage, probability, expected closing, overdue warnings, owner, currency, value, and probability-weighted totals |
| Helpdesk | `HD Ticket` | Agent-only customer/requester workload with open, urgent, and resolved counts plus recent-ticket navigation and a 100-row scan warning |

The ninth pass makes reservations, performance progress, ownership, and active
work allocation visible:

| App | Standard records | Ninth-pass delivery |
|-----|------------------|---------------------|
| Inventory | `Stock Reservation Entry` | Independently loaded active reservations with source document, warehouse, reserved, delivered, and remaining demand |
| HR | `Appraisal`, `Appraisal Goal` | Privacy-safe current appraisal cycle, self/final scores, goal progress, and manual goal weight and achievement |
| Sales | `Sales Team` | Independently loaded customer account owners, contact numbers, and contribution percentages without commission or incentive data |
| Helpdesk | `ToDo`, `HD Ticket` | Agent-only active assignments with assignee, priority, due date, assigner, and description, authorized through ticket visibility |

The tenth pass adds substitution, career progression, return, and response
shortcuts:

| App | Standard records | Tenth-pass delivery |
|-----|------------------|---------------------|
| Inventory | `Item Alternative`, `Item`, `Bin` | Independently loaded one-way and two-way substitutes with on-hand/projected quantities and direct navigation to the alternative Item |
| HR | `Employee Promotion`, `Employee Property History` | Submitted promotion history limited to career-property changes; CTC, salary, and every non-whitelisted property remain excluded |
| Sales | `Sales Invoice` | Independently loaded submitted returns/credit notes with original-invoice references, currency totals, outstanding values, and a visible 500-row scan limit |
| Helpdesk | `HD Saved Reply`, `HD Saved Reply Team`, `HD Ticket` | Agent-only global, personal, and ticket-team saved replies with preview and one-tap insertion into the reply composer |

The eleventh pass makes batch selection, career movement, cash collection, and
SLA policy easier to understand at the point of work:

| App | Standard records | Eleventh-pass delivery |
|-----|------------------|------------------------|
| Inventory | `Batch`, `Stock Ledger Entry`, `Item` | Independently loaded FEFO-ordered available batches with warehouse quantity, manufacture/expiry dates, supplier, source document, and truncation guidance |
| HR | `Employee Transfer`, `Employee Property History` | Submitted transfer history limited to a strict career-property allowlist; salary and every non-whitelisted change remain excluded |
| Sales | `Payment Entry`, `Payment Entry Reference` | Independently loaded submitted customer receipts with invoice allocations, unallocated amounts, payment references, currency totals, and a visible 500-row scan limit |
| Helpdesk | `HD Service Level Agreement`, `HD Service Level Priority`, `HD Service Day`, `HD Ticket` | Visibility-authorized SLA name, current-priority response/resolution targets, working hours, holiday list, outside-hours warning, and hold context |

The twelfth pass adds production readiness, lifecycle progress, customer
retention, and classification guidance:

| App | Standard records | Twelfth-pass delivery |
|-----|------------------|-----------------------|
| Inventory | `BOM`, `BOM Item`, `Bin`, `Item` | Independently loaded active/default BOM, scaled direct-component requirements, on-hand/projected quantities, shortages, possible output, cost, source warehouse, supplier sourcing, and inspection requirement |
| HR | `Employee Separation`, `Employee Boarding Activity`, `Task` | Privacy-safe separation dates, status, and offboarding task progress; exit interviews, activity descriptions, roles, users, and assignees remain excluded |
| Sales | `Loyalty Point Entry` | Independently loaded active point balances grouped by program/company, tier, upcoming expiry, recent earn/redeem activity, invoice references, and a visible 500-row scan limit |
| Helpdesk | `HD Ticket Type`, `HD Ticket Template`, `HD Ticket Template Field` | Visibility-authorized type description, recommended priority, template guidance, and required-field checklist; customer-hidden fields remain agent-only |

The thirteenth pass connects planning context to active execution and ownership:

| App | Standard records | Thirteenth-pass delivery |
|-----|------------------|--------------------------|
| Inventory | `Work Order`, `Item` | Independently loaded active production quantities, progress, remaining output, planned dates, overdue state, WIP/target warehouses, BOM, Sales Order, project, transferred material, and process loss |
| HR | `Employee` | Metadata-filtered confirmation, contract, retirement, resignation-letter, and relieving milestones grouped into an Employment lifecycle section |
| Sales | `Dunning`, `Overdue Payment` | Independently loaded submitted collection notices, unresolved counts, currency totals, fees, interest, outstanding values, invoice-level overdue days/levels, and a visible 500-row scan limit |
| Helpdesk | `HD Team`, `HD Team Member`, `HD Agent`, `HD Agent Status` | Agent-only team routing rule, active/away/unavailable counts, and member availability authorized through ticket visibility |

The fourteenth pass adds execution detail, team membership, service obligations,
and customer-organization context:

| App | Standard records | Fourteenth-pass delivery |
|-----|------------------|--------------------------|
| Inventory | `Work Order Operation`, `Work Order` | Active Work Orders now expand into operation status, workstation, completed/pending quantity, planned/actual time, inspection/subcontracting flags, and operation-level overdue state |
| HR | `Employee Group`, `Employee Group Table` | Profile shows the employee's standard group memberships and aggregate group size without exposing coworker identities, email addresses, or user IDs |
| Sales | `Maintenance Schedule`, `Maintenance Schedule Detail` | Independently loaded submitted maintenance schedules show pending, completed, and overdue visits plus item, serial, assigned salesperson, actual date, and next obligation |
| Helpdesk | `HD Customer`, `HD Customer Member`, `Contact` | Visibility-authorized customer identity, type, domain, country, and ERPNext link; contact rosters remain agent-only and are loaded independently |

The fifteenth pass links planning and customer context to execution calendars:

| App | Standard records | Fifteenth-pass delivery |
|-----|------------------|-------------------------|
| Inventory | `Job Card`, `Job Card Time Log`, `Work Order` | Active production now includes shop-floor Job Card status, operation, workstation, completed/pending quantity, pause and overdue state, inspection reference, time totals, log count, and last activity without exposing employee identities |
| HR | `Leave Block List`, `Leave Block List Date`, `Leave Block List Allow`, `Department` | Profile shows the next 90 days of company/department leave restrictions, including reason and leave type, while honoring user-specific allow-list exceptions |
| Sales | `Warranty Claim` | Independently loaded customer claims show open/resolved and under-coverage totals plus item, serial, complaint, warranty/AMC expiry, resolution, and resolver context |
| Helpdesk | `HD Service Holiday List`, `HD Holiday` | The independent SLA policy card now includes its calendar description and upcoming closure dates, distinguishing weekly offs from named holidays |

Optional fields are filtered through Frappe metadata before queries. This
prevents an older ERPNext or Helpdesk schema from breaking the entire screen
when a newer standard field is unavailable. Secondary sections return empty or
their own loading/error state without blocking the primary detail screen.

An automated backend architecture test now rejects:

- custom `doctype/` module directories in the primary Bude backend;
- writes that attempt to create `DocType` or `Custom DocType` definitions.

## Audit Findings

### Inventory

Strengths: complete scan-to-stock flows, offline queueing, warehouse stock,
ledger history, label printing, and RFID abstraction.

Warehouse hierarchy, location, and contact context is now available. Capacity
remains out of scope because the standard `Warehouse` schema has no capacity
field; adding one would violate the no-custom-field constraint for this audit.
Item Detail now also exposes movement velocity and estimated stock cover.
Recent Quality Inspection outcomes now make acceptance and rejection context
available without leaving the stock workflow. Active Stock Reservation Entries
now explain which demand has already claimed inventory and how much remains.
Standard Item Alternatives now expose viable substitutes and their current
availability. Batch-managed items now also expose positive available batches
in FEFO order with warehouse-aware quantities and traceable source documents.
Manufactured items now explain whether direct BOM components can cover the
requested output and identify exact shortages without leaving Item Detail.
Active Work Orders now show whether planned output is progressing or overdue
and where WIP and finished goods are routed. Each visible Work Order now also
shows its standard operation sequence, workstation, quantity progress, timing,
and operation-level delay.
Related Job Cards now expose current shop-floor execution, pause state, time-log
activity, and inspection references without returning worker identities.

### HR

Strengths: attendance/check-in, leave, expense claims, salary slips,
documents, approvals, and offline-capable mobile workflows.

The Profile Career section now includes both completed training history and
scheduled Training Events scoped to the employee. The current privacy-safe
Appraisal and its standard manual goals are visible without exposing
compensation, reflections, or private feedback. Submitted promotion history
uses a strict career-field allowlist so compensation changes remain private.
Submitted Employee Transfers use the same privacy boundary and show only
career changes plus standard company and new-employee references. Standard
separation progress is now visible to the linked employee without exposing
exit interviews or activity ownership. Confirmation, contract, retirement,
resignation, and relieving dates now form a clear employment lifecycle.
Standard Employee Group memberships now add collaboration context while only
an aggregate member count is returned, never coworker identities.
Applicable company and department Leave Block Lists now explain upcoming dates
when leave cannot be requested, with user allow-list exceptions enforced.

Highest-value remaining work:

1. Keep announcements and profile-change requests out of scope unless a
   standard Frappe/ERPNext record can represent them.

### Sales

Strengths: customer browse, Customer 360, visits, item availability/pricing,
quotation/order/invoice/payment workflows, dashboards, and team summaries.

Customer-specific pricing is now visible without leaving Customer 360. Further
Opportunity stage, probability, weighted value, and closing risk are now also
visible without leaving Customer 360. Customer account ownership and
contribution are also visible without exposing commissions or incentives.
Submitted credit notes now explain recent returns and their original invoices.
Submitted receipts now show what was paid, which invoices were allocated, and
what remains unallocated without exposing bank account details. Loyalty
balances and expiring points now add retention context to Customer 360.
Submitted Dunning notices now connect overdue aging to the collection action,
invoice, interest, fee, escalation level, and unresolved status.
Submitted Maintenance Schedules now make upcoming and overdue service
obligations visible alongside the customer's commercial history.
Standard Warranty Claims now connect customer, serial, coverage, complaint, and
resolution history without leaving Customer 360.
Further work should focus on sales
accessibility and workflow shortcuts rather than adding schema.

### Helpdesk

Strengths: requester and agent queues, replies, internal notes, attachments,
assignment, filters, offline drafts, and standard Helpdesk status workflows.

The identified high-priority standard-schema gap is closed. Further work should
focus on accessibility and platform integrations rather than adding Helpdesk
schema. Agents now also have customer-level ticket workload context without
exposing that cross-ticket view to requesters. Active Frappe ToDo assignments
are likewise agent-only and scoped to the visible ticket.
Agents can also preview and insert Helpdesk saved replies while personal and
team scope is enforced by the backend. Ticket SLA policy context now explains
the configured targets and working calendar behind the live countdowns.
Ticket type and template guidance now explain the intended classification
while requester-hidden template fields stay private. Agents can also see the
ticket team's routing rule and current member availability.
The linked HD Customer's organization context is available to every authorized
ticket viewer, while its Contact roster is restricted to agents.
SLA holiday calendars now expose upcoming support closures alongside working
hours and live response/resolution targets.

## Source of Truth

Field choices were checked against the upstream standard schemas:

- [ERPNext Item schema](https://github.com/frappe/erpnext/blob/develop/erpnext/stock/doctype/item/item.json)
- [ERPNext Item Reorder schema](https://github.com/frappe/erpnext/blob/develop/erpnext/stock/doctype/item_reorder/item_reorder.json)
- [ERPNext Item Default schema](https://github.com/frappe/erpnext/blob/develop/erpnext/stock/doctype/item_default/item_default.json)
- [ERPNext Serial No schema](https://github.com/frappe/erpnext/blob/develop/erpnext/stock/doctype/serial_no/serial_no.json)
- [ERPNext Warehouse schema](https://github.com/frappe/erpnext/blob/develop/erpnext/stock/doctype/warehouse/warehouse.json)
- [ERPNext Stock Ledger Entry schema](https://github.com/frappe/erpnext/blob/develop/erpnext/stock/doctype/stock_ledger_entry/stock_ledger_entry.json)
- [ERPNext Quality Inspection schema](https://github.com/frappe/erpnext/blob/develop/erpnext/stock/doctype/quality_inspection/quality_inspection.json)
- [ERPNext Stock Reservation Entry schema](https://github.com/frappe/erpnext/blob/develop/erpnext/stock/doctype/stock_reservation_entry/stock_reservation_entry.json)
- [ERPNext Item Alternative schema](https://github.com/frappe/erpnext/blob/develop/erpnext/stock/doctype/item_alternative/item_alternative.json)
- [ERPNext Batch schema](https://github.com/frappe/erpnext/blob/develop/erpnext/stock/doctype/batch/batch.json)
- [ERPNext BOM schema](https://github.com/frappe/erpnext/blob/develop/erpnext/manufacturing/doctype/bom/bom.json)
- [ERPNext BOM Item schema](https://github.com/frappe/erpnext/blob/develop/erpnext/manufacturing/doctype/bom_item/bom_item.json)
- [ERPNext Work Order schema](https://github.com/frappe/erpnext/blob/develop/erpnext/manufacturing/doctype/work_order/work_order.json)
- [ERPNext Work Order Operation schema](https://github.com/frappe/erpnext/blob/develop/erpnext/manufacturing/doctype/work_order_operation/work_order_operation.json)
- [ERPNext Job Card schema](https://github.com/frappe/erpnext/blob/develop/erpnext/manufacturing/doctype/job_card/job_card.json)
- [ERPNext Job Card Time Log schema](https://github.com/frappe/erpnext/blob/develop/erpnext/manufacturing/doctype/job_card_time_log/job_card_time_log.json)
- [ERPNext Purchase Order Item schema](https://github.com/frappe/erpnext/blob/develop/erpnext/buying/doctype/purchase_order_item/purchase_order_item.json)
- [ERPNext Sales Order Item schema](https://github.com/frappe/erpnext/blob/develop/erpnext/selling/doctype/sales_order_item/sales_order_item.json)
- [ERPNext Item Price schema](https://github.com/frappe/erpnext/blob/develop/erpnext/stock/doctype/item_price/item_price.json)
- [ERPNext Customer schema](https://github.com/frappe/erpnext/blob/develop/erpnext/selling/doctype/customer/customer.json)
- [ERPNext Customer Credit Limit schema](https://github.com/frappe/erpnext/blob/develop/erpnext/selling/doctype/customer_credit_limit/customer_credit_limit.json)
- [ERPNext Sales Invoice schema](https://github.com/frappe/erpnext/blob/develop/erpnext/accounts/doctype/sales_invoice/sales_invoice.json)
- [ERPNext Sales Invoice Item schema](https://github.com/frappe/erpnext/blob/develop/erpnext/accounts/doctype/sales_invoice_item/sales_invoice_item.json)
- [ERPNext Payment Entry schema](https://github.com/frappe/erpnext/blob/develop/erpnext/accounts/doctype/payment_entry/payment_entry.json)
- [ERPNext Payment Entry Reference schema](https://github.com/frappe/erpnext/blob/develop/erpnext/accounts/doctype/payment_entry_reference/payment_entry_reference.json)
- [ERPNext Loyalty Point Entry schema](https://github.com/frappe/erpnext/blob/develop/erpnext/accounts/doctype/loyalty_point_entry/loyalty_point_entry.json)
- [ERPNext Dunning schema](https://github.com/frappe/erpnext/blob/develop/erpnext/accounts/doctype/dunning/dunning.json)
- [ERPNext Overdue Payment schema](https://github.com/frappe/erpnext/blob/develop/erpnext/accounts/doctype/overdue_payment/overdue_payment.json)
- [ERPNext Sales Order schema](https://github.com/frappe/erpnext/blob/develop/erpnext/selling/doctype/sales_order/sales_order.json)
- [ERPNext Delivery Note schema](https://github.com/frappe/erpnext/blob/develop/erpnext/stock/doctype/delivery_note/delivery_note.json)
- [ERPNext Quotation schema](https://github.com/frappe/erpnext/blob/develop/erpnext/selling/doctype/quotation/quotation.json)
- [ERPNext Opportunity schema](https://github.com/frappe/erpnext/blob/develop/erpnext/crm/doctype/opportunity/opportunity.json)
- [ERPNext Sales Team schema](https://github.com/frappe/erpnext/blob/develop/erpnext/selling/doctype/sales_team/sales_team.json)
- [ERPNext Maintenance Schedule schema](https://github.com/frappe/erpnext/blob/develop/erpnext/maintenance/doctype/maintenance_schedule/maintenance_schedule.json)
- [ERPNext Maintenance Schedule Detail schema](https://github.com/frappe/erpnext/blob/develop/erpnext/maintenance/doctype/maintenance_schedule_detail/maintenance_schedule_detail.json)
- [ERPNext Warranty Claim schema](https://github.com/frappe/erpnext/blob/develop/erpnext/support/doctype/warranty_claim/warranty_claim.json)
- [ERPNext Employee schema](https://github.com/frappe/erpnext/blob/develop/erpnext/setup/doctype/employee/employee.json)
- [ERPNext Employee Group schema](https://github.com/frappe/erpnext/blob/develop/erpnext/setup/doctype/employee_group/employee_group.json)
- [ERPNext Employee Group Table schema](https://github.com/frappe/erpnext/blob/develop/erpnext/setup/doctype/employee_group_table/employee_group_table.json)
- [HRMS Leave Block List schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/leave_block_list/leave_block_list.json)
- [HRMS Leave Block List Date schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/leave_block_list_date/leave_block_list_date.json)
- [HRMS Leave Block List Allow schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/leave_block_list_allow/leave_block_list_allow.json)
- [HRMS Attendance schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/attendance/attendance.json)
- [HRMS Leave Allocation schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/leave_allocation/leave_allocation.json)
- [HRMS Employee Skill Map schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/employee_skill_map/employee_skill_map.json)
- [HRMS Employee Skill schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/employee_skill/employee_skill.json)
- [HRMS Employee Training schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/employee_training/employee_training.json)
- [HRMS Training Event schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/training_event/training_event.json)
- [HRMS Training Event Employee schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/training_event_employee/training_event_employee.json)
- [HRMS Appraisal schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/appraisal/appraisal.json)
- [HRMS Appraisal Goal schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/appraisal_goal/appraisal_goal.json)
- [HRMS Employee Promotion schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/employee_promotion/employee_promotion.json)
- [HRMS Employee Transfer schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/employee_transfer/employee_transfer.json)
- [HRMS Employee Property History schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/employee_property_history/employee_property_history.json)
- [HRMS Employee Separation schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/employee_separation/employee_separation.json)
- [HRMS Employee Boarding Activity schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/employee_boarding_activity/employee_boarding_activity.json)
- [ERPNext Task schema](https://github.com/frappe/erpnext/blob/develop/erpnext/projects/doctype/task/task.json)
- [HRMS Shift Assignment schema](https://github.com/frappe/hrms/blob/develop/hrms/hr/doctype/shift_assignment/shift_assignment.json)
- [ERPNext Holiday schema](https://github.com/frappe/erpnext/blob/develop/erpnext/setup/doctype/holiday/holiday.json)
- [Frappe Version schema](https://github.com/frappe/frappe/blob/develop/frappe/core/doctype/version/version.json)
- [Frappe ToDo schema](https://github.com/frappe/frappe/blob/develop/frappe/desk/doctype/todo/todo.json)
- [Frappe Helpdesk HD Ticket schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_ticket/hd_ticket.json)
- [Frappe Helpdesk HD Article schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_article/hd_article.json)
- [Frappe Helpdesk HD Saved Reply schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_saved_reply/hd_saved_reply.json)
- [Frappe Helpdesk HD Saved Reply Team schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_saved_reply_team/hd_saved_reply_team.json)
- [Frappe Helpdesk HD Service Level Agreement schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_service_level_agreement/hd_service_level_agreement.json)
- [Frappe Helpdesk HD Service Level Priority schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_service_level_priority/hd_service_level_priority.json)
- [Frappe Helpdesk HD Service Day schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_service_day/hd_service_day.json)
- [Frappe Helpdesk HD Ticket Type schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_ticket_type/hd_ticket_type.json)
- [Frappe Helpdesk HD Ticket Template schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_ticket_template/hd_ticket_template.json)
- [Frappe Helpdesk HD Ticket Template Field schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_ticket_template_field/hd_ticket_template_field.json)
- [Frappe Helpdesk HD Team schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_team/hd_team.json)
- [Frappe Helpdesk HD Team Member schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_team_member/hd_team_member.json)
- [Frappe Helpdesk HD Agent schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_agent/hd_agent.json)
- [Frappe Helpdesk HD Agent Status schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_agent_status/hd_agent_status.json)
- [Frappe Helpdesk HD Customer schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_customer/hd_customer.json)
- [Frappe Helpdesk HD Customer Member schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_customer_member/hd_customer_member.json)
- [Frappe Helpdesk HD Service Holiday List schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_service_holiday_list/hd_service_holiday_list.json)
- [Frappe Helpdesk HD Holiday schema](https://github.com/frappe/helpdesk/blob/develop/helpdesk/helpdesk/doctype/hd_holiday/hd_holiday.json)
