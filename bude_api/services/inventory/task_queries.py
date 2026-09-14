"""Grouped inventory.warehouse_tasks endpoints: task_queries."""

from ._warehouse_tasks_shared import *  # noqa: F401,F403

def list_open(limit: int = 100, company: str | None = None) -> dict:
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    try:
        limit = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")

    company = (company or "").strip() or None
    try:
        todos = _todos_by_reference()
        tasks = [
            *_purchase_order_tasks(todos, company=company),
            *_sales_order_tasks(todos, company=company),
            *_asset_maintenance_tasks(todos, company=company),
            *_cycle_count_tasks(todos),
        ]
    except frappe.PermissionError:
        return permission_denied()
    tasks.sort(key=_task_sort_key)
    return success(tasks[:limit])
