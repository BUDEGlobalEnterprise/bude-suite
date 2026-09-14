"""Alerts / notifications — computed live from standard DocTypes.

    GET/POST /api/method/bude_api.api.alerts.list_alerts   (auth required)

No custom DocTypes and nothing persisted: every alert is derived on demand
from Asset Maintenance Log, Asset, Bin, and Item. Categories:
maintenance_due, assets_in_maintenance, out_of_stock, low_stock.
"""

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.pagination import Page, parse_page

from ...utils.response import failure, success

from ..common.permissions import require_stock_execution_role

_PER_CATEGORY = 50

_LOW_STOCK_SCAN_LIMIT = 5000

_SUMMARY_CACHE_TTL_SEC = 60

def _whitelist():
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=False, methods=["GET", "POST"])

def _alert(category, severity, title, subtitle, ref_doctype, ref_name):
    return {
        "category": category,
        "severity": severity,
        "title": title,
        "subtitle": subtitle,
        "ref_doctype": ref_doctype,
        "ref_name": ref_name,
    }

def _maintenance_due() -> list:
    today = frappe.utils.nowdate()
    rows = frappe.get_all(
        "Asset Maintenance Log",
        filters=[
            ["maintenance_status", "in", ["Planned", "Overdue"]],
            ["due_date", "<=", today],
        ],
        fields=["name", "asset_name", "task", "due_date", "maintenance_status"],
        order_by="due_date asc",
        limit_page_length=_PER_CATEGORY,
    )
    return [
        _alert(
            "maintenance_due",
            "high",
            f"Maintenance due: {r.get('task') or r['name']}",
            f"{r.get('asset_name') or ''} · due {r.get('due_date')}",
            "Asset Maintenance Log",
            r["name"],
        )
        for r in rows
    ]

def _assets_in_maintenance() -> list:
    rows = frappe.get_all(
        "Asset",
        filters=[["status", "in", ["In Maintenance", "Out of Order"]]],
        fields=["name", "asset_name", "status", "location"],
        order_by="modified desc",
        limit_page_length=_PER_CATEGORY,
    )
    return [
        _alert(
            "assets_in_maintenance",
            "medium",
            f"{r.get('asset_name') or r['name']} — {r.get('status')}",
            r.get("location") or "",
            "Asset",
            r["name"],
        )
        for r in rows
    ]

def _stock_alerts() -> list:
    bins = frappe.get_all(
        "Bin",
        fields=["item_code", "warehouse", "actual_qty"],
        order_by="actual_qty asc",
        limit_page_length=500,
    )
    item_codes = list({row["item_code"] for row in bins})
    safety_stock = {}
    if item_codes:
        item_rows = frappe.get_all(
            "Item",
            filters=[["item_code", "in", item_codes]],
            fields=["item_code", "safety_stock"],
            limit=len(item_codes),
        )
        safety_stock = {row["item_code"]: float(row.get("safety_stock") or 0) for row in item_rows}

    out_rows = [row for row in bins if float(row.get("actual_qty") or 0) <= 0][:_PER_CATEGORY]
    low_rows = [
        {
            **row,
            "safety_stock": safety_stock.get(row["item_code"], 0),
        }
        for row in bins
        if 0 < float(row.get("actual_qty") or 0)
        and float(row.get("actual_qty") or 0) <= safety_stock.get(row["item_code"], 0)
    ][:_PER_CATEGORY]

    out = [
        _alert(
            "out_of_stock",
            "high",
            f"Out of stock: {r['item_code']}",
            f"{r['warehouse']} · {r['actual_qty']}",
            "Item",
            r["item_code"],
        )
        for r in out_rows
    ]
    low = [
        _alert(
            "low_stock",
            "medium",
            f"Low stock: {r['item_code']}",
            f"{r['warehouse']} · {r['actual_qty']} ≤ {r['safety_stock']}",
            "Item",
            r["item_code"],
        )
        for r in low_rows
    ]
    return out + low

def _low_stock_rows(warehouse: str | None = None) -> list[dict]:
    warehouse = (warehouse or "").strip()
    reorder_filters = []
    if warehouse:
        reorder_filters.append(["warehouse", "=", warehouse])

    reorder_rows = frappe.get_all(
        "Item Reorder",
        filters=reorder_filters,
        fields=[
            "parent",
            "warehouse",
            "warehouse_reorder_level",
            "warehouse_reorder_qty",
        ],
        order_by="warehouse asc, parent asc",
        limit_page_length=_LOW_STOCK_SCAN_LIMIT,
    )
    if not reorder_rows:
        return []

    item_codes = sorted({row["parent"] for row in reorder_rows if row.get("parent")})
    warehouses = sorted({row["warehouse"] for row in reorder_rows if row.get("warehouse")})
    bin_rows = frappe.get_all(
        "Bin",
        filters=[
            ["item_code", "in", item_codes],
            ["warehouse", "in", warehouses],
        ],
        fields=["item_code", "warehouse", "actual_qty", "projected_qty"],
        limit_page_length=max(1, min(len(item_codes) * max(len(warehouses), 1), 5000)),
    )
    bin_by_key = {(row["item_code"], row["warehouse"]): row for row in bin_rows}

    rows = []
    for reorder in reorder_rows:
        item_code = reorder.get("parent")
        row_warehouse = reorder.get("warehouse")
        if not item_code or not row_warehouse:
            continue
        reorder_level = float(reorder.get("warehouse_reorder_level") or 0)
        if reorder_level <= 0:
            continue
        bin_row = bin_by_key.get((item_code, row_warehouse), {})
        actual_qty = float(bin_row.get("actual_qty") or 0)
        if actual_qty > reorder_level:
            continue
        reorder_qty = float(reorder.get("warehouse_reorder_qty") or 0)
        suggested_qty = reorder_qty if reorder_qty > 0 else max(reorder_level - actual_qty, 0)
        rows.append(
            {
                "item_code": item_code,
                "warehouse": row_warehouse,
                "actual_qty": actual_qty,
                "projected_qty": float(bin_row.get("projected_qty") or actual_qty),
                "reorder_level": reorder_level,
                "suggested_qty": suggested_qty,
            }
        )

    rows.sort(key=lambda row: (row["warehouse"], row["actual_qty"], row["item_code"]))
    return rows

def _cache_get(key: str):
    try:
        cache = frappe.cache()
        getter = getattr(cache, "get_value", None) or getattr(cache, "get", None)
        return getter(key) if getter else None
    except Exception:
        return None

def _cache_set(key: str, value: dict, *, expires_in_sec: int) -> None:
    try:
        cache = frappe.cache()
        setter = getattr(cache, "set_value", None)
        if setter:
            setter(key, value, expires_in_sec=expires_in_sec)
            return
        setter = getattr(cache, "set", None)
        if setter:
            setter(key, value)
    except Exception:
        pass

__all__ = [name for name in globals() if not name.startswith("__")]
