"""Grouped mobile endpoints: dashboard."""

from ._mobile_shared import *  # noqa: F401,F403

def dashboard(
    scope: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    sales_person: str | None = None,
    territory: str | None = None,
) -> dict:
    denied = require_sales_role(frappe)
    if denied:
        return denied
    owner_filter = [] if _is_sales_manager() or scope == "team" else [["owner", "=", _current_user()]]
    order_filters = [["status", "not in", list(CLOSED_STATUSES)], *owner_filter, *_doc_date_filters("Sales Order", from_date, to_date)]
    invoice_filters = [["docstatus", "=", 1], *owner_filter, *_doc_date_filters("Sales Invoice", from_date, to_date)]
    payment_filters = [["docstatus", "=", 1], *owner_filter, *_doc_date_filters("Payment Entry", from_date, to_date)]
    if territory:
        order_filters.append(["territory", "=", territory])
        invoice_filters.append(["territory", "=", territory])
    if sales_person and _is_sales_manager():
        _append_sales_person_filter(order_filters, "Sales Order", sales_person)
        _append_sales_person_filter(invoice_filters, "Sales Invoice", sales_person)
    followup_filters = [["status", "=", "Open"], *owner_filter]
    return success(
        {
            "open_orders": _count("Sales Order", order_filters),
            "order_value": _sum("Sales Order", "grand_total", order_filters),
            "invoice_value": _sum("Sales Invoice", "grand_total", invoice_filters),
            "collection_value": _sum("Payment Entry", "paid_amount", payment_filters),
            "open_followups": _count("ToDo", followup_filters),
            "is_manager": _is_sales_manager(),
        }
    )

def team_summary(from_date: str | None = None, to_date: str | None = None, territory: str | None = None, sales_person: str | None = None) -> dict:
    denied = require_sales_role(frappe)
    if denied:
        return denied
    if not _is_sales_manager():
        return permission_denied("A sales manager role is required for team summary.")
    filters = _doc_date_filters("Sales Order", from_date, to_date)
    if territory:
        filters.append(["territory", "=", territory])
    if sales_person:
        _append_sales_person_filter(filters, "Sales Order", sales_person)
    rows = frappe.get_list(
        "Sales Order",
        filters=filters,
        fields=["name", "owner", "grand_total", "status"],
        limit_page_length=5000,
    )
    sales_people = _sales_people_for_docs("Sales Order", [row["name"] for row in rows])
    buckets: dict[str, dict] = {}
    for row in rows:
        key = sales_people.get(row.get("name")) or row.get("owner") or "Unassigned"
        bucket = buckets.setdefault(key, {"sales_person": key, "orders": 0, "order_value": 0.0})
        bucket["orders"] += 1
        bucket["order_value"] += float(row.get("grand_total") or 0)
    return success({"rows": sorted(buckets.values(), key=lambda row: row["order_value"], reverse=True)})
