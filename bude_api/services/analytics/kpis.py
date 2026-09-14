"""Grouped analytics.stock endpoints: kpis."""

from ._stock_analytics_shared import *  # noqa: F401,F403

def kpi_summary(
    warehouse: str | None = None,
    days: int = 90,
) -> dict:
    """Manager KPI rollup for inventory value, movement, and accuracy."""
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_stock_execution_role(frappe)
    if permission_error:
        return permission_error

    days = _bounded_int(days, default=90, minimum=1, maximum=_MAX_RANGE_DAYS)
    warehouse = (warehouse or "").strip() or None
    cache_key = f"bude_api:analytics:kpi:{warehouse or '*'}:{days}"
    cached = _cache_get(cache_key)
    if isinstance(cached, dict):
        return success(cached)

    today = _today()
    from_date = frappe.utils.add_days(today, -days)
    data = {
        "from_date": from_date,
        "to_date": today,
        "warehouse": warehouse,
        "stock_value": _stock_value(warehouse),
        "turnover_qty": _turnover_qty(warehouse, from_date),
        "dead_stock_value": _dead_stock_value(warehouse, from_date),
        "sales_velocity_qty": _sales_velocity_qty(warehouse, from_date),
        "pick_accuracy": _pick_accuracy(from_date),
        "variance_trend": _variance_trend(warehouse, from_date),
    }
    _cache_set(cache_key, data, expires_in_sec=_CACHE_TTL_SEC)
    return success(data)
