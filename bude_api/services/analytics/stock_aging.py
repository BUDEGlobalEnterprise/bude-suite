"""Grouped analytics.stock endpoints: stock_aging."""

from ._stock_analytics_shared import *  # noqa: F401,F403

def get_stock_aging(warehouse: str, threshold_days: int = 30, limit: int = 100) -> dict:
    """Items in a warehouse that have had no stock movement for >= threshold_days.

    GET /api/method/bude_api.api.analytics.get_stock_aging

    Returns rows ordered by days_idle DESC (longest idle first).
    Items with no ledger entry at all are included (never moved).
    """
    warehouse = (warehouse or "").strip()
    if not warehouse:
        return failure("warehouse is required.", code="VALIDATION_REQUIRED")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    threshold_days = max(1, min(int(threshold_days), 365))
    limit = max(1, min(int(limit), 500))

    # Validate warehouse exists.
    warehouse_rows = frappe.get_list(
        "Warehouse",
        filters=[["name", "=", warehouse]],
        fields=["name"],
        limit=1,
    )
    if not warehouse_rows:
        return failure(f"Warehouse '{warehouse}' not found.", code="VALIDATION_UNKNOWN_WAREHOUSE")

    bins = frappe.get_list(
        "Bin",
        filters=[["warehouse", "=", warehouse]],
        fields=["item_code", "actual_qty"],
        order_by="item_code asc",
        limit_page_length=5000,
    )
    item_codes = [row["item_code"] for row in bins]
    item_names = _item_names(item_codes)
    last_movement = _last_movement_dates(warehouse, item_codes)
    today = _today()

    rows = []
    for row in bins:
        item_code = row["item_code"]
        last_date = last_movement.get(item_code)
        days_idle = None if last_date is None else _days_between(today, last_date)
        if days_idle is not None and days_idle < threshold_days:
            continue
        rows.append({
            "item_code": item_code,
            "item_name": item_names.get(item_code),
            "actual_qty": row.get("actual_qty"),
            "last_movement_date": str(last_date) if last_date else None,
            "days_idle": days_idle,
        })

    rows.sort(
        key=lambda row: (
            -1 if row.get("days_idle") is None else -row["days_idle"],
            row["item_code"],
        )
    )
    rows = rows[:limit]
    for row in rows:
        if row.get("days_idle") is None:
            row["days_idle"] = None

    return success(rows)
