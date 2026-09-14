"""Daily operations cockpit summary.

GET /api/method/bude_api.api.cockpit.today

Aggregates standard ERPNext/Frappe DocTypes only. The endpoint is intentionally
small and cached so the dashboard can refresh often without hammering MariaDB.
"""

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success
from . import alerts as alerts_api
from ..common.permissions import require_stock_execution_role

_CACHE_TTL_SEC = 60
_COUNT_CAP = 1000
_CLOSED_STATUSES = ["Closed", "Completed", "Cancelled"]
_TODO_CLOSED_STATUSES = ["Closed", "Cancelled"]


def _whitelist():
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=False, methods=["GET", "POST"])


@_whitelist()
def today(company: str | None = None) -> dict:
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_stock_execution_role(frappe)
    if permission_error:
        return permission_error

    company = (company or "").strip() or None
    user = getattr(getattr(frappe, "session", None), "user", None) or ""
    cache_key = f"bude_api:cockpit:today:{user}:{company or '*'}"
    cached = _cache_get(cache_key)
    if isinstance(cached, dict):
        return success(cached)

    today_date = frappe.utils.nowdate()
    data = {
        "date": today_date,
        "po_due_today": _purchase_orders_due_today(today_date, company),
        "open_sales_orders": _open_sales_orders(company),
        "open_pick_lists": _open_pick_lists(company),
        "assigned_count_tasks": _assigned_count_tasks(user, company),
        "low_stock_count": _low_stock_count(company),
        "pending_approvals": _pending_approvals(user),
    }
    _cache_set(cache_key, data, expires_in_sec=_CACHE_TTL_SEC)
    return success(data)


def _purchase_orders_due_today(today_date: str, company: str | None) -> int:
    filters = [
        ["docstatus", "=", 1],
        ["status", "not in", _CLOSED_STATUSES],
        ["schedule_date", "<=", today_date],
    ]
    if company:
        filters.append(["company", "=", company])
    return _bounded_count("Purchase Order", filters)


def _open_sales_orders(company: str | None) -> int:
    filters = [
        ["docstatus", "=", 1],
        ["status", "not in", _CLOSED_STATUSES],
    ]
    if company:
        filters.append(["company", "=", company])
    return _bounded_count("Sales Order", filters)


def _open_pick_lists(company: str | None) -> int:
    filters = [["docstatus", "<", 2], ["status", "not in", _CLOSED_STATUSES]]
    if company:
        filters.append(["company", "=", company])
    return _bounded_count("Pick List", filters)


def _assigned_count_tasks(user: str, company: str | None) -> int:
    filters = [
        ["status", "not in", _TODO_CLOSED_STATUSES],
        ["reference_type", "=", "Stock Reconciliation"],
    ]
    if user and user != "Administrator":
        filters.append(["allocated_to", "=", user])
    return _bounded_count("ToDo", filters)


def _low_stock_count(company: str | None) -> int:
    alerts_api.frappe = frappe
    # Low-stock is warehouse based. Company filtering is intentionally omitted
    # unless warehouses are supplied by a later V2 caller.
    return len(alerts_api._low_stock_rows())


def _pending_approvals(user: str) -> int:
    filters = [["status", "=", "Open"]]
    if user and user != "Administrator":
        filters.append(["user", "=", user])
    return _bounded_count("Workflow Action", filters)


def _bounded_count(doctype: str, filters: list) -> int:
    rows = frappe.get_list(
        doctype,
        filters=filters,
        fields=["name"],
        limit_page_length=_COUNT_CAP,
    )
    return len(rows)


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
