"""Grouped inventory.sales_orders endpoints: sales_order_queries."""

from ._sales_orders_shared import *  # noqa: F401,F403

def list_open(limit: int = 50, offset: int = 0, company: str | None = None) -> dict:
    """Return submitted Sales Orders with pending delivery quantities."""
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    try:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset or 0))
    except (TypeError, ValueError):
        return failure("limit and offset must be integers.", code="VALIDATION_BAD_LIMIT")

    filters = [
        ["docstatus", "=", 1],
        ["status", "not in", list(_CLOSED_STATUSES)],
    ]
    company = (company or "").strip()
    if company:
        filters.append(["company", "=", company])

    rows = frappe.get_list(
        "Sales Order",
        filters=filters,
        fields=[
            "name",
            "customer",
            "transaction_date",
            "delivery_date",
            "status",
            "company",
        ],
        order_by="transaction_date desc",
        limit_start=offset,
        limit_page_length=limit,
    )
    names = [row["name"] for row in rows]
    pending = _pending_summary_by_order(names)

    return success([
        {
            **row,
            "item_count": pending.get(row["name"], {}).get("item_count", 0),
            "pending_qty": pending.get(row["name"], {}).get("pending_qty", 0.0),
        }
        for row in rows
        if pending.get(row["name"], {}).get("item_count", 0) > 0
    ])

def get(name: str) -> dict:
    """Return Sales Order header and pending delivery lines."""
    name = (name or "").strip()
    if not name:
        return failure("name is required.", code="VALIDATION_REQUIRED")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    so = _sales_order(name)
    if isinstance(so, dict) and so.get("ok") is False:
        return so

    lines = _pending_lines(name)
    return success({**so, "items": lines})
