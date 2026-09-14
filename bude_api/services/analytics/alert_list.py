"""Grouped analytics.alerts endpoints: alert_list."""

from ._alerts_shared import *  # noqa: F401,F403

def list_alerts(limit: int | None = None, offset: int = 0) -> dict:
    """Aggregate operational alerts. Returns {alerts, counts, total}."""
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_stock_execution_role(frappe)
    if permission_error:
        return permission_error

    page = parse_page(limit, offset, default_limit=100, max_limit=500)
    if not isinstance(page, Page):
        return page

    alerts: list = []

    alerts += _maintenance_due()
    alerts += _assets_in_maintenance()
    alerts += _stock_alerts()

    total = len(alerts)
    alerts = alerts[page.offset : page.offset + page.limit]
    counts: dict = {}
    for a in alerts:
        counts[a["category"]] = counts.get(a["category"], 0) + 1

    return success(
        {
            "alerts": alerts,
            "counts": counts,
            "limit": page.limit,
            "offset": page.offset,
            "total": total,
        }
    )
