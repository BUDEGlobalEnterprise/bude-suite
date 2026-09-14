"""Grouped analytics.alerts endpoints: low_stock_alerts."""

from ._alerts_shared import *  # noqa: F401,F403

def low_stock(
    warehouse: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict:
    """Items below their per-warehouse reorder level.

    Derived from standard ERPNext `Item Reorder` rows joined to `Bin` balances.
    """
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_stock_execution_role(frappe)
    if permission_error:
        return permission_error

    page = parse_page(limit, offset, default_limit=50, max_limit=200)
    if not isinstance(page, Page):
        return page

    rows = _low_stock_rows(warehouse)
    total = len(rows)
    return success(
        {
            "items": rows[page.offset : page.offset + page.limit],
            "limit": page.limit,
            "offset": page.offset,
            "total": total,
        }
    )
