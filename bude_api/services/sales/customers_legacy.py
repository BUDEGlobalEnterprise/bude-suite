"""Grouped sales.legacy endpoints: customers_legacy."""

from ._legacy_shared import *  # noqa: F401,F403

def list_customers(
    search: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict:
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_sales_role(frappe)
    if permission_error:
        return permission_error

    page = parse_page(limit, offset, default_limit=50, max_limit=200)
    if not isinstance(page, Page):
        return page

    filters = []
    search = (search or "").strip()
    if search:
        filters.append(["customer_name", "like", f"%{search}%"])

    rows = frappe.get_list(
        "Customer",
        filters=filters,
        fields=["name", "customer_name", "customer_group", "territory"],
        order_by="customer_name asc",
        limit_start=page.offset,
        limit_page_length=page.limit,
    )
    return success({
        "customers": rows,
        "limit": page.limit,
        "offset": page.offset,
        "total": _count_rows("Customer", filters),
    })
