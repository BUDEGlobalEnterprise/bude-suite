"""Analytics endpoints — stock aging, reconciliation history, KPIs, and movers.

    GET /api/method/bude_api.api.analytics.get_stock_aging
    GET /api/method/bude_api.api.analytics.get_reconciliation_history
"""

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success

from ..common.permissions import require_stock_execution_role

_CACHE_TTL_SEC = 300

_MAX_RANGE_DAYS = 365

_MAX_LIMIT = 500

def _whitelist(allow_guest: bool = False):
    if frappe is None:
        def decorator(fn):
            return fn
        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=["GET", "POST"])

def _item_names(item_codes: list[str]) -> dict[str, str | None]:
    if not item_codes:
        return {}
    rows = frappe.get_list(
        "Item",
        filters=[["item_code", "in", item_codes]],
        fields=["item_code", "item_name"],
        limit=len(item_codes),
    )
    return {row["item_code"]: row.get("item_name") for row in rows}

def _last_movement_dates(warehouse: str, item_codes: list[str]) -> dict[str, object]:
    if not item_codes:
        return {}
    rows = frappe.get_list(
        "Stock Ledger Entry",
        filters=[
            ["warehouse", "=", warehouse],
            ["item_code", "in", item_codes],
            ["is_cancelled", "=", 0],
        ],
        fields=["item_code", "posting_date"],
        order_by="posting_date desc",
        limit_page_length=5000,
    )
    latest = {}
    for row in rows:
        latest.setdefault(row["item_code"], row.get("posting_date"))
    return latest

def _today() -> str:
    try:
        return frappe.utils.nowdate()
    except Exception:
        from datetime import date

        return date.today().isoformat()

def _days_between(today, previous) -> int:
    try:
        return int(frappe.utils.date_diff(today, previous))
    except Exception:
        from datetime import date

        current = date.fromisoformat(str(today))
        earlier = date.fromisoformat(str(previous))
        return (current - earlier).days

def _bounded_int(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))

def _stock_value(warehouse: str | None) -> float:
    filters = []
    if warehouse:
        filters.append(["warehouse", "=", warehouse])
    rows = frappe.get_list(
        "Bin",
        filters=filters,
        fields=["actual_qty", "valuation_rate"],
        limit_page_length=5000,
    )
    return round(
        sum(
            float(row.get("actual_qty") or 0) *
            float(row.get("valuation_rate") or 0)
            for row in rows
        ),
        2,
    )

def _turnover_qty(warehouse: str | None, from_date: str) -> float:
    return round(sum(_movement_by_item(warehouse, from_date).values()), 6)

def _dead_stock_value(warehouse: str | None, from_date: str) -> float:
    dead_codes = {row["item_code"] for row in _dead_items(warehouse, from_date, 500)}
    if not dead_codes:
        return 0.0
    filters = [["item_code", "in", sorted(dead_codes)]]
    if warehouse:
        filters.append(["warehouse", "=", warehouse])
    rows = frappe.get_list(
        "Bin",
        filters=filters,
        fields=["actual_qty", "valuation_rate"],
        limit_page_length=5000,
    )
    return round(
        sum(
            float(row.get("actual_qty") or 0) *
            float(row.get("valuation_rate") or 0)
            for row in rows
            if row.get("item_code") in dead_codes
        ),
        2,
    )

def _sales_velocity_qty(warehouse: str | None, from_date: str) -> float:
    filters = [["posting_date", ">=", from_date], ["docstatus", "=", 1]]
    rows = frappe.get_list(
        "Sales Invoice Item",
        filters=filters,
        fields=["item_code", "qty", "warehouse"],
        limit_page_length=5000,
    )
    total = 0.0
    for row in rows:
        if warehouse and row.get("warehouse") != warehouse:
            continue
        total += abs(float(row.get("qty") or 0))
    return round(total, 6)

def _pick_accuracy(from_date: str) -> float | None:
    rows = frappe.get_list(
        "Delivery Note",
        filters=[["posting_date", ">=", from_date], ["docstatus", "=", 1]],
        fields=["name", "remarks"],
        limit_page_length=5000,
    )
    total = len(rows)
    if total == 0:
        return None
    corrected = 0
    for row in rows:
        text = str(row.get("remarks") or "").lower()
        if "corrected" in text or "variance" in text:
            corrected += 1
    return round((total - corrected) / total, 4)

def _variance_trend(warehouse: str | None, from_date: str) -> list[dict]:
    filters = {"docstatus": 1}
    if warehouse:
        filters["set_warehouse"] = warehouse
    recons = frappe.get_list(
        "Stock Reconciliation",
        filters=filters,
        fields=["name", "posting_date", "set_warehouse"],
        order_by="posting_date asc",
        limit_page_length=5000,
    )
    trend = []
    for recon in recons:
        if str(recon.get("posting_date") or "") < str(from_date):
            continue
        items = frappe.get_list(
            "Stock Reconciliation Item",
            filters={"parent": recon["name"]},
            fields=["qty", "current_qty"],
            limit_page_length=1000,
        )
        variance = sum(
            abs(float(row.get("qty") or 0) - float(row.get("current_qty") or 0))
            for row in items
        )
        trend.append({
            "date": str(recon.get("posting_date")),
            "name": recon["name"],
            "absolute_variance_qty": round(variance, 6),
        })
    return trend

def _movement_by_item(warehouse: str | None, from_date: str) -> dict[str, float]:
    filters = [["posting_date", ">=", from_date], ["is_cancelled", "=", 0]]
    if warehouse:
        filters.append(["warehouse", "=", warehouse])
    rows = frappe.get_list(
        "Stock Ledger Entry",
        filters=filters,
        fields=["item_code", "actual_qty"],
        limit_page_length=5000,
    )
    result: dict[str, float] = {}
    for row in rows:
        item_code = row.get("item_code")
        if not item_code:
            continue
        result[item_code] = result.get(item_code, 0.0) + abs(
            float(row.get("actual_qty") or 0),
        )
    return result

def _bin_balances(warehouse: str | None, item_codes: list[str]) -> dict[str, float]:
    filters = []
    if warehouse:
        filters.append(["warehouse", "=", warehouse])
    if item_codes:
        filters.append(["item_code", "in", item_codes])
    rows = frappe.get_list(
        "Bin",
        filters=filters,
        fields=["item_code", "actual_qty"],
        limit_page_length=5000,
    )
    result: dict[str, float] = {}
    for row in rows:
        item_code = row.get("item_code")
        if item_code:
            result[item_code] = result.get(item_code, 0.0) + float(
                row.get("actual_qty") or 0,
            )
    return result

def _dead_items(warehouse: str | None, from_date: str, limit: int) -> list[dict]:
    moved = set(_movement_by_item(warehouse, from_date))
    filters = []
    if warehouse:
        filters.append(["warehouse", "=", warehouse])
    rows = frappe.get_list(
        "Bin",
        filters=filters,
        fields=["item_code", "actual_qty", "valuation_rate"],
        order_by="item_code asc",
        limit_page_length=5000,
    )
    dead = []
    for row in rows:
        item_code = row.get("item_code")
        actual_qty = float(row.get("actual_qty") or 0)
        if not item_code or item_code in moved or actual_qty <= 0:
            continue
        value = actual_qty * float(row.get("valuation_rate") or 0)
        dead.append({
            "item_code": item_code,
            "actual_qty": actual_qty,
            "stock_value": round(value, 2),
        })
    dead.sort(key=lambda row: (-row["stock_value"], row["item_code"]))
    return dead[:limit]

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
