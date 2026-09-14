"""Asset reports + dashboard summary (standard DocTypes only).

    GET/POST /api/method/bude_api.api.reports.asset_summary
    GET/POST /api/method/bude_api.api.reports.asset_register
    GET/POST /api/method/bude_api.api.reports.maintenance_history
    GET/POST /api/method/bude_api.api.reports.asset_utilization

Everything is read-only and computed from Asset, Asset Movement, Asset
Maintenance Log, and Asset Repair. No custom DocTypes.
"""

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success


def _whitelist():
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=False, methods=["GET", "POST"])


@_whitelist()
def asset_summary() -> dict:
    """KPIs for the dashboard: counts + total book value."""
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    assets = frappe.get_all(
        "Asset",
        fields=["status", "value_after_depreciation"],
        limit_page_length=10000,
    )
    total_assets = len(assets)
    in_maintenance = len(
        [row for row in assets if row.get("status") in {"In Maintenance", "Out of Order"}]
    )
    total_value = sum(float(row.get("value_after_depreciation") or 0) for row in assets)

    horizon = frappe.utils.add_days(frappe.utils.nowdate(), 30)
    upcoming_logs = frappe.get_all(
        "Asset Maintenance Log",
        filters=[["maintenance_status", "=", "Planned"], ["due_date", "<=", horizon]],
        fields=["name"],
        limit_page_length=10000,
    )

    return success(
        {
            "total_assets": total_assets,
            "total_value": total_value,
            "in_maintenance": in_maintenance,
            "upcoming_maintenance": len(upcoming_logs),
        }
    )


@_whitelist()
def asset_register(
    location: str | None = None,
    status: str | None = None,
    category: str | None = None,
    limit: int = 500,
) -> dict:
    """Flat asset rows for a register / CSV export."""
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    limit = max(1, min(int(limit), 2000))
    filters: list = []
    if location:
        filters.append(["location", "=", location])
    if status:
        filters.append(["status", "=", status])
    if category:
        filters.append(["asset_category", "=", category])

    rows = frappe.get_all(
        "Asset",
        filters=filters,
        fields=[
            "name",
            "asset_name",
            "item_code",
            "asset_category",
            "location",
            "custodian",
            "status",
            "purchase_date",
            "purchase_amount",
            "value_after_depreciation",
        ],
        order_by="asset_category asc, name asc",
        limit_page_length=limit,
    )
    for r in rows:
        r["purchase_date"] = str(r.get("purchase_date") or "")
        r["gross_purchase_amount"] = r.pop("purchase_amount", None)
    return success(rows)


@_whitelist()
def maintenance_history(asset: str | None = None, limit: int = 100) -> dict:
    """Merged Asset Maintenance Log + Asset Repair timeline."""
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    limit = max(1, min(int(limit), 500))

    log_filters: list = []
    repair_filters: list = []
    if asset:
        log_filters.append(["asset_name", "=", asset])
        repair_filters.append(["asset", "=", asset])

    logs = frappe.get_all(
        "Asset Maintenance Log",
        filters=log_filters,
        fields=[
            "name",
            "asset_name",
            "task",
            "maintenance_status",
            "due_date",
            "completion_date",
        ],
        order_by="modified desc",
        limit_page_length=limit,
    )
    repairs = frappe.get_all(
        "Asset Repair",
        filters=repair_filters,
        fields=[
            "name",
            "asset",
            "failure_date",
            "repair_status",
            "repair_cost",
        ],
        order_by="modified desc",
        limit_page_length=limit,
    )

    merged = []
    for r in logs:
        merged.append(
            {
                "type": "maintenance",
                "name": r["name"],
                "asset": r.get("asset_name"),
                "title": r.get("task") or "Maintenance",
                "status": r.get("maintenance_status"),
                "date": str(r.get("completion_date") or r.get("due_date") or ""),
                "cost": None,
            }
        )
    for r in repairs:
        merged.append(
            {
                "type": "repair",
                "name": r["name"],
                "asset": r.get("asset"),
                "title": "Repair",
                "status": r.get("repair_status"),
                "date": str(r.get("failure_date") or ""),
                "cost": r.get("repair_cost"),
            }
        )
    merged.sort(key=lambda x: x["date"], reverse=True)
    return success(merged[:limit])


@_whitelist()
def asset_utilization(days: int = 90, limit: int = 100) -> dict:
    """Movement counts per asset over the last [days] — idle vs active."""
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    days = max(1, min(int(days), 730))
    limit = max(1, min(int(limit), 500))
    since = frappe.utils.add_days(frappe.utils.nowdate(), -days)

    movement_items = frappe.get_all(
        "Asset Movement Item",
        fields=["parent", "asset"],
        limit_page_length=5000,
    )
    parents = list({row["parent"] for row in movement_items})
    movements = {}
    if parents:
        movement_rows = frappe.get_all(
            "Asset Movement",
            filters=[
                ["name", "in", parents],
                ["transaction_date", ">=", since],
                ["docstatus", "=", 1],
            ],
            fields=["name", "transaction_date"],
            limit_page_length=len(parents),
        )
        movements = {row["name"]: row.get("transaction_date") for row in movement_rows}

    by_asset = {}
    for item in movement_items:
        parent = item["parent"]
        if parent not in movements:
            continue
        asset = item["asset"]
        bucket = by_asset.setdefault(asset, {"asset": asset, "moves": 0, "last_move": None})
        bucket["moves"] += 1
        last_move = movements[parent]
        if bucket["last_move"] is None or str(last_move) > str(bucket["last_move"]):
            bucket["last_move"] = last_move

    rows = sorted(
        by_asset.values(),
        key=lambda row: (-row["moves"], row["asset"]),
    )[:limit]
    for r in rows:
        r["last_move"] = str(r.get("last_move") or "")
    return success(rows)
