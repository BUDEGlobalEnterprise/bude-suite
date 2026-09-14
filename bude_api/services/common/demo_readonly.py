"""Read-only enforcement for the public demo login referenced in the project
README, independent of whatever roles that account holds.

The demo user is assigned real operational roles (Stock User, HR User, Sales
User, Accounts User, Agent) so the mobile apps' client-side navigation
renders normally -- those apps gate menu items on literal role-name strings,
so a custom low-privilege role would leave most of the UI hidden. Those
roles carry real write/submit/delete rights by default, which would let
anyone with the published password modify or delete real records if left
alone.

This was first attempted as a `has_permission` hook (see git history) but
Frappe's has_permission hook is only consulted when a specific document
*instance* is already in hand; it is never called for the plain
doctype-level list/create checks that make up most REST/RPC traffic, so it
silently did nothing for exactly the operations that matter here --
confirmed by a live test that reached ERPNext's field-validation stage
instead of being denied. Enforcing this at the request level, before
Frappe's ORM permission system even runs, does not have that gap: every
avenue into the site -- the mobile apps' API calls, the Frappe Desk UI's own
AJAX calls, and a bare curl request -- funnels through the same two URL
prefixes (`/api/resource/*`, `/api/method/*`), so blocking by path pattern
here covers all of them structurally, not just the ones this app happens to
call.

ponytail: a hardcoded username set and a hand-maintained allowlist, not a
DocType/config screen. This is a short, security-sensitive list that should
stay a one-line code review, not something editable at runtime by anyone
with Desk access.
"""

from __future__ import annotations

import urllib.parse

import frappe

# Users demoted to read-only regardless of their assigned roles. Extend this
# set, never any role's own permissions, if another read-only account is
# ever needed.
READ_ONLY_USERS = frozenset({
    "demo@budeglobal.in",
})

# Always allowed for a read-only user, regardless of the allowlist below.
_ALWAYS_ALLOWED_METHODS = frozenset({
    "login",
    "logout",
})

# Exact `bude_api.api.*` dotted paths a read-only user may call. Generated
# from every whitelisted function in bude_api/api/ by prefix (get_, list_,
# search, ...), then hand-corrected: obvious false negatives (safe reads the
# prefix heuristic missed, e.g. session_info) were added; nothing was ever
# removed from what the heuristic already called a write, and nothing here
# was added without checking its source doesn't call .insert/.save/.submit/
# .delete/set_value. Deny-by-default: anything NOT in this set is blocked,
# including any endpoint added later without updating this list, and every
# native frappe/erpnext/hrms/helpdesk/crm whitelisted method this app never
# needed to enumerate in the first place.
ALLOWED_METHODS = frozenset({
    "bude_api.api.admin_onboarding.role_profiles",
    "bude_api.api.admin_onboarding.users",
    "bude_api.api.admin_onboarding.devices",
    "bude_api.api.alerts.list_alerts",
    "bude_api.api.alerts.low_stock",
    "bude_api.api.alerts.summary",
    "bude_api.api.analytics.get_stock_aging",
    "bude_api.api.analytics.get_reconciliation_history",
    "bude_api.api.analytics.kpi_summary",
    "bude_api.api.analytics.movers",
    "bude_api.api.assets.list_assets",
    "bude_api.api.assets.get_asset",
    "bude_api.api.assets.get_asset_movements",
    "bude_api.api.assets.list_locations",
    "bude_api.api.assets.list_asset_categories",
    "bude_api.api.assets.list_maintenance_logs",
    "bude_api.api.auth.google_config",
    "bude_api.api.auth.session_info",
    "bude_api.api.branding.get",
    "bude_api.api.cockpit.today",
    "bude_api.api.companies.list_companies",
    "bude_api.api.health.ping",
    "bude_api.api.helpdesk.my_tickets",
    "bude_api.api.helpdesk.support_pulse",
    "bude_api.api.helpdesk.setup_health",
    "bude_api.api.helpdesk.automation_status",
    "bude_api.api.helpdesk.channel_health",
    "bude_api.api.helpdesk.ticket_delivery",
    "bude_api.api.helpdesk.agent_tickets",
    "bude_api.api.helpdesk.ticket_detail",
    "bude_api.api.helpdesk.suggest_articles",
    "bude_api.api.helpdesk.related_tickets",
    "bude_api.api.helpdesk.customer_ticket_context",
    "bude_api.api.helpdesk.ticket_assignments",
    "bude_api.api.helpdesk.saved_replies",
    "bude_api.api.helpdesk.ticket_sla_context",
    "bude_api.api.helpdesk.ticket_classification",
    "bude_api.api.helpdesk.ticket_team_context",
    "bude_api.api.helpdesk.ticket_organization_context",
    "bude_api.api.helpdesk.ticket_activity",
    "bude_api.api.helpdesk.agents",
    "bude_api.api.helpdesk.masters",
    "bude_api.api.hr.profile",
    "bude_api.api.hr.employee_documents",
    "bude_api.api.hr.attendance_status",
    "bude_api.api.hr.attendance_history",
    "bude_api.api.hr.attendance_summary",
    "bude_api.api.hr.shift_status",
    "bude_api.api.hr.shift_roster",
    "bude_api.api.hr.shift_requests",
    "bude_api.api.hr.manager_pending_shift_requests",
    "bude_api.api.hr.attendance_calendar",
    "bude_api.api.hr.attendance_requests",
    "bude_api.api.hr.leave_balances",
    "bude_api.api.hr.holidays",
    "bude_api.api.hr.leave_requests",
    "bude_api.api.hr.leave_request_detail",
    "bude_api.api.hr.leave_attachments",
    "bude_api.api.hr.comp_off_requests",
    "bude_api.api.hr.expense_claims",
    "bude_api.api.hr.expense_types",
    "bude_api.api.hr.expense_claim_detail",
    "bude_api.api.hr.expense_attachments",
    "bude_api.api.hr.employee_advances",
    "bude_api.api.hr.travel_requests",
    "bude_api.api.hr.todo_requests",
    "bude_api.api.hr.grievances",
    "bude_api.api.hr.salary_slips",
    "bude_api.api.hr.salary_slip_detail",
    "bude_api.api.hr.salary_slip_pdf_url",
    "bude_api.api.hr.salary_ytd",
    "bude_api.api.hr.tax_declarations",
    "bude_api.api.hr.appraisals",
    "bude_api.api.hr.training_events",
    "bude_api.api.hr.notifications",
    "bude_api.api.hr.notification_detail",
    "bude_api.api.hr.manager_pending_leaves",
    "bude_api.api.hr.manager_pending_expenses",
    "bude_api.api.hr.manager_summary",
    "bude_api.api.hr.manager_direct_reports",
    "bude_api.api.hr.manager_team_attendance_exceptions",
    "bude_api.api.hr.manager_report_profile",
    "bude_api.api.hr.manager_team_calendar",
    "bude_api.api.hr.manager_today",
    "bude_api.api.hr.attendance_anomalies",
    "bude_api.api.hr.timesheets",
    "bude_api.api.hr.onboarding_checklists",
    "bude_api.api.hr.salary_tax_projection",
    "bude_api.api.items.search",
    "bude_api.api.items.list_groups",
    "bude_api.api.items.get_by_barcode",
    "bude_api.api.items.get_ledger",
    "bude_api.api.items.get_stock",
    "bude_api.api.items.get_storage_locations",
    "bude_api.api.items.get_movement_insight",
    "bude_api.api.items.get_supply_demand",
    "bude_api.api.items.get_quality_inspections",
    "bude_api.api.items.get_reservations",
    "bude_api.api.items.get_alternatives",
    "bude_api.api.items.get_batches",
    "bude_api.api.items.get_manufacturing_readiness",
    "bude_api.api.items.get_production_status",
    "bude_api.api.items.get_planning",
    "bude_api.api.items.get_buying_insight",
    "bude_api.api.items.get_serial_warranty",
    "bude_api.api.masters.list_masters",
    "bude_api.api.masters.list_records",
    "bude_api.api.masters.get_record",
    "bude_api.api.masters.list_link_options",
    "bude_api.api.mobile_permissions.get_my_mobile_permissions",
    "bude_api.api.mobile_permissions.get_effective_permission_preview",
    "bude_api.api.notifications.preferences",
    "bude_api.api.notifications.payloads",
    "bude_api.api.notifications.route_for_category",
    "bude_api.api.notifications.list_registered_devices",
    "bude_api.api.permissions.auth_expired",
    "bude_api.api.permissions.permission_denied",
    "bude_api.api.printing.document_pdf_url",
    "bude_api.api.printing.documents_pdf_url",
    "bude_api.api.purchase_orders.list_open",
    "bude_api.api.reports.asset_summary",
    "bude_api.api.reports.asset_register",
    "bude_api.api.reports.maintenance_history",
    "bude_api.api.reports.asset_utilization",
    "bude_api.api.sales.item_price",
    "bude_api.api.sales.list_customers",
    "bude_api.api.sales.my_orders",
    "bude_api.api.sales_crm.bootstrap",
    "bude_api.api.sales_crm.setup_doctor",
    "bude_api.api.sales_crm.entitlement",
    "bude_api.api.sales_crm.quotation_response_status",
    "bude_api.api.sales_crm.manager_dashboard",
    "bude_api.api.sales_crm.playbooks",
    "bude_api.api.sales_crm.list_leads",
    "bude_api.api.sales_crm.get_lead",
    "bude_api.api.sales_crm.check_duplicates",
    "bude_api.api.sales_crm.conversion_options",
    "bude_api.api.sales_crm.list_deals",
    "bude_api.api.sales_crm.get_deal",
    "bude_api.api.sales_crm.list_tasks",
    "bude_api.api.sales_crm.timeline",
    "bude_api.api.sales_crm.analytics",
    "bude_api.api.sales_mobile.masters",
    "bude_api.api.sales_mobile.dashboard",
    "bude_api.api.sales_mobile.customers",
    "bude_api.api.sales_mobile.customer_detail",
    "bude_api.api.sales_mobile.customer_buying_history",
    "bude_api.api.sales_mobile.customer_fulfillment",
    "bude_api.api.sales_mobile.customer_quotation_guidance",
    "bude_api.api.sales_mobile.customer_item_pricing",
    "bude_api.api.sales_mobile.customer_opportunities",
    "bude_api.api.sales_mobile.customer_account_team",
    "bude_api.api.sales_mobile.customer_returns",
    "bude_api.api.sales_mobile.customer_receipts",
    "bude_api.api.sales_mobile.customer_loyalty",
    "bude_api.api.sales_mobile.customer_dunnings",
    "bude_api.api.sales_mobile.customer_maintenance",
    "bude_api.api.sales_mobile.customer_warranty_claims",
    "bude_api.api.sales_mobile.items",
    "bude_api.api.sales_mobile.field_day",
    "bude_api.api.sales_mobile.collections_queue",
    "bude_api.api.sales_mobile.commercial_preview",
    "bude_api.api.sales_mobile.team_summary",
    "bude_api.api.sales_orders.list_open",
    "bude_api.api.sales_orders.get",
    "bude_api.api.scan.resolve_epc",
    "bude_api.api.tracking.batches",
    "bude_api.api.tracking.serials",
    "bude_api.api.warehouses.get_stock",
    "bude_api.api.warehouses.list",
    "bude_api.api.warehouses.list_locations",
    "bude_api.api.warehouse_tasks.list_open",
})


def _is_read_only_user() -> bool:
    return getattr(frappe.session, "user", None) in READ_ONLY_USERS


# Blocked outright on /api/resource/*, GET included -- financial and
# account-security doctypes that happen to be reachable through a doctype
# this account's roles can otherwise browse (e.g. HR User can normally read
# Salary Slip for its company).
_NO_READ_DOCTYPES = frozenset({
    "Salary Slip",
    "Salary Structure Assignment",
    "Bank Account",
    "Payment Entry",
    "Payment Request",
    "GL Entry",
    "User",
    "Role",
    "Role Profile",
})


def before_request():
    """Registered in hooks.py's `before_request`. Runs before Frappe routes
    the request to a handler or evaluates any DocType permission, so it is
    not subject to the has_permission-hook gap described above.
    """
    if not _is_read_only_user():
        return

    path = frappe.request.path or ""
    method = (frappe.request.method or "GET").upper()

    if path.startswith("/api/resource/"):
        # .../api/resource/<Doctype> or .../api/resource/<Doctype>/<name>
        doctype = urllib.parse.unquote(path[len("/api/resource/"):].split("/", 1)[0])
        if doctype in _NO_READ_DOCTYPES or method != "GET":
            frappe.throw(
                "This is a read-only demo account.",
                frappe.PermissionError,
            )
        return

    if path.startswith("/api/method/"):
        rpc_method = path[len("/api/method/"):].split("?", 1)[0]
        if rpc_method in _ALWAYS_ALLOWED_METHODS or rpc_method in ALLOWED_METHODS:
            return
        frappe.throw(
            "This is a read-only demo account.",
            frappe.PermissionError,
        )
