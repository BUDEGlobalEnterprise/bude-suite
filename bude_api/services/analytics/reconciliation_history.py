"""Grouped analytics.stock endpoints: reconciliation_history."""

from ._stock_analytics_shared import *  # noqa: F401,F403

def get_reconciliation_history(warehouse: str = None, limit: int = 20) -> dict:
    """Return submitted Stock Reconciliation docs with per-item variance.

    GET /api/method/bude_api.api.analytics.get_reconciliation_history

    variance = counted_qty - current_qty (positive = surplus, negative = deficit)
    """
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    limit = max(1, min(int(limit), 200))

    filters = {"docstatus": 1}
    if warehouse and warehouse.strip():
        filters["set_warehouse"] = warehouse.strip()

    recons = frappe.get_list(
        "Stock Reconciliation",
        filters=filters,
        fields=["name", "posting_date", "set_warehouse"],
        order_by="posting_date desc",
        limit_page_length=limit,
    )

    result = []
    for recon in recons:
        items_raw = frappe.get_list(
            "Stock Reconciliation Item",
            filters={"parent": recon["name"]},
            fields=["item_code", "item_name", "qty", "current_qty", "warehouse"],
        )
        items = []
        for item in items_raw:
            counted = float(item.get("qty") or 0)
            expected = float(item.get("current_qty") or 0)
            items.append({
                "item_code": item["item_code"],
                "item_name": item.get("item_name"),
                "counted_qty": counted,
                "expected_qty": expected,
                "variance": round(counted - expected, 6),
                "warehouse": item.get("warehouse") or recon.get("set_warehouse"),
            })
        result.append({
            "name": recon["name"],
            "posting_date": str(recon["posting_date"]) if recon.get("posting_date") else None,
            "warehouse": recon.get("set_warehouse"),
            "items": items,
        })

    return success(result)
