"""Grouped analytics.alerts endpoints: alert_summary."""

from ._alerts_shared import *  # noqa: F401,F403

def summary(warehouse: str | None = None) -> dict:
    """Alert counts for dashboard badges, cached for a short TTL."""
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_stock_execution_role(frappe)
    if permission_error:
        return permission_error

    cache_key = f"bude_api:alerts:summary:{(warehouse or '').strip() or '*'}"
    cached = _cache_get(cache_key)
    if isinstance(cached, dict):
        return success(cached)

    data = {"low_stock_count": len(_low_stock_rows(warehouse))}
    _cache_set(cache_key, data, expires_in_sec=_SUMMARY_CACHE_TTL_SEC)
    return success(data)
