"""Manager outcomes, transparent crediting, and native-record playbooks."""

from __future__ import annotations

from datetime import date, timedelta

from ...utils.response import failure, success
from ..common.permissions import has_any_role, permission_denied, require_sales_role
from .service import SALES_MANAGER_ROLES, SalesCrmService

PLAYBOOKS = {
    "new_lead_3_touch": {
        "label": "New lead: 3-touch follow-up",
        "kind": "lead",
        "steps": [(0, "First response"), (2, "Second follow-up"), (5, "Final qualification follow-up")],
    },
    "deal_close_plan": {
        "label": "Deal: close plan",
        "kind": "deal",
        "steps": [(0, "Confirm next step"), (3, "Review decision and blockers"), (7, "Close-plan follow-up")],
    },
    "quotation_follow_up": {
        "label": "Quotation: response follow-up",
        "kind": "deal",
        "steps": [(2, "Confirm quotation received"), (7, "Quotation decision follow-up")],
    },
}


def manager_outcomes(frappe_module, days=30) -> dict:
    denied = require_sales_role(frappe_module)
    if denied:
        return denied
    if not has_any_role(frappe_module, SALES_MANAGER_ROLES):
        return permission_denied("Sales Manager access is required.")
    try:
        period_days = min(max(int(days), 7), 365)
    except (TypeError, ValueError):
        return failure("days must be between 7 and 365.", code="VALIDATION_DAYS")
    start = (date.today() - timedelta(days=period_days)).isoformat()
    quotations = _safe_list(
        frappe_module,
        "Quotation",
        ["name", "status", "owner", "grand_total", "transaction_date"],
        filters=[["transaction_date", ">=", start]],
        limit=1000,
    )
    quote_total = len(quotations)
    ordered = sum(1 for row in quotations if row.get("status") == "Ordered")
    lost = sum(1 for row in quotations if row.get("status") in {"Lost", "Cancelled", "Expired"})
    invoices = _safe_list(
        frappe_module,
        "Sales Invoice",
        ["name", "posting_date", "grand_total", "outstanding_amount", "currency"],
        filters=[["docstatus", "=", 1], ["posting_date", ">=", start], ["is_return", "=", 0]],
        limit=1000,
    )
    invoice_names = [row.get("name") for row in invoices if row.get("name")]
    sales_team = _safe_list(
        frappe_module,
        "Sales Team",
        ["parent", "sales_person", "allocated_percentage", "allocated_amount"],
        filters=[["parent", "in", invoice_names]],
        limit=5000,
    ) if invoice_names else []
    credited = {}
    commission_rate = _commission_rate(frappe_module)
    for row in sales_team:
        sales_person = row.get("sales_person") or "Unassigned"
        bucket = credited.setdefault(
            sales_person,
            {"sales_person": sales_person, "credited_revenue": 0.0, "estimated_commission": 0.0},
        )
        amount = float(row.get("allocated_amount") or 0)
        bucket["credited_revenue"] += amount
        bucket["estimated_commission"] += amount * commission_rate / 100
    communications = _safe_list(
        frappe_module,
        "Communication",
        ["name", "sender", "owner", "communication_medium", "creation"],
        filters=[["creation", ">=", start]],
        limit=5000,
    )
    tasks = _safe_list(
        frappe_module,
        "ToDo",
        ["name", "allocated_to", "status", "date", "creation"],
        filters=[["creation", ">=", start]],
        limit=5000,
    )
    activity = {}
    for row in communications:
        owner = row.get("sender") or row.get("owner") or "Unassigned"
        bucket = activity.setdefault(owner, {"owner": owner, "communications": 0, "tasks_completed": 0})
        bucket["communications"] += 1
    for row in tasks:
        owner = row.get("allocated_to") or "Unassigned"
        bucket = activity.setdefault(owner, {"owner": owner, "communications": 0, "tasks_completed": 0})
        if row.get("status") == "Closed":
            bucket["tasks_completed"] += 1
    outstanding_by_currency = {}
    for row in invoices:
        amount = float(row.get("outstanding_amount") or 0)
        if amount <= 0:
            continue
        currency = row.get("currency") or "Company Currency"
        outstanding_by_currency[currency] = outstanding_by_currency.get(currency, 0.0) + amount
    crm = SalesCrmService(frappe_module).analytics("team")
    crm_data = crm.get("data", {}) if crm.get("ok") else {}
    recommendations = _recommendations(crm_data, quote_total, ordered, lost, tasks)
    return success(
        {
            "period_days": period_days,
            "quotation": {
                "total": quote_total,
                "ordered": ordered,
                "lost": lost,
                "conversion_rate": round(ordered * 100 / quote_total, 1) if quote_total else 0,
            },
            "invoiced": round(sum(float(row.get("grand_total") or 0) for row in invoices), 2),
            "outstanding_by_currency": [
                {"currency": currency, "amount": round(amount, 2)}
                for currency, amount in sorted(outstanding_by_currency.items())
            ],
            "credited_revenue": sorted(credited.values(), key=lambda row: row["credited_revenue"], reverse=True),
            "commission_rate_percent": commission_rate,
            "activity_coverage": sorted(activity.values(), key=lambda row: row["owner"]),
            "recommendations": recommendations,
            "crm": crm_data,
        }
    )


def automation_templates(frappe_module) -> dict:
    denied = require_sales_role(frappe_module)
    if denied:
        return denied
    return success(
        {
            "templates": [
                {"key": key, "label": value["label"], "kind": value["kind"], "steps": len(value["steps"])}
                for key, value in PLAYBOOKS.items()
            ]
        }
    )


def apply_automation(frappe_module, template, kind, name, client_request_id=None) -> dict:
    denied = require_sales_role(frappe_module)
    if denied:
        return denied
    playbook = PLAYBOOKS.get(str(template or ""))
    if not playbook:
        return failure("Unknown automation template.", code="VALIDATION_TEMPLATE")
    if kind != playbook["kind"] or not str(name or "").strip():
        return failure(f"This template requires a {playbook['kind']}.", code="VALIDATION_REFERENCE")
    service = SalesCrmService(frappe_module)
    created = []
    for index, (after_days, title) in enumerate(playbook["steps"]):
        due = (date.today() + timedelta(days=after_days)).isoformat()
        result = service.create_task(
            {
                "title": title,
                "priority": "High" if after_days == 0 else "Medium",
                "due_date": due,
                "reference_kind": kind,
                "reference_name": name,
            },
            f"{client_request_id}:{index}" if client_request_id else None,
        )
        if result.get("ok") is not True:
            return result
        created.append(result.get("data", {}).get("task", {}))
    return success({"template": template, "created": created})


def _recommendations(crm, quote_total, ordered, lost, tasks):
    rows = []
    if int(crm.get("stale_leads") or 0) > 0:
        rows.append({"severity": "high", "title": f"Reassign or follow up {crm['stale_leads']} stale leads", "route": "/leads?stale=1"})
    if int(crm.get("overdue_tasks") or 0) > 0:
        rows.append({"severity": "high", "title": f"Clear {crm['overdue_tasks']} overdue CRM tasks", "route": "/crm-tasks"})
    if quote_total >= 5 and ordered / quote_total < 0.25:
        rows.append({"severity": "medium", "title": "Quotation conversion is below 25%; review pricing and follow-up", "route": "/pipeline"})
    open_tasks = sum(1 for row in tasks if row.get("status") != "Closed")
    if open_tasks > 20:
        rows.append({"severity": "medium", "title": f"Team task load is high: {open_tasks} open tasks", "route": "/crm-tasks"})
    if lost > ordered and lost > 2:
        rows.append({"severity": "medium", "title": "More quotations are being lost than ordered", "route": "/manager"})
    if not rows:
        rows.append({"severity": "info", "title": "No urgent sales risks detected in this period", "route": "/manager"})
    return rows


def _safe_list(frappe_module, doctype, fields, *, filters=None, limit=500):
    try:
        return frappe_module.get_list(
            doctype,
            fields=fields,
            filters=filters or [],
            limit_page_length=limit,
        )
    except Exception:
        return []


def _commission_rate(frappe_module):
    try:
        return max(float(frappe_module.conf.get("bude_sales_commission_rate_percent") or 0), 0)
    except Exception:
        return 0.0
