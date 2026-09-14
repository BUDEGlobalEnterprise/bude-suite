"""Grouped sales.legacy endpoints: orders_legacy."""

from ._legacy_shared import *  # noqa: F401,F403

def create_order(
    customer: str,
    items: list,
    delivery_date: str | None = None,
    company: str | None = None,
    price_list: str | None = None,
) -> dict:
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    item_error = _validate_items(items)
    if item_error:
        return item_error
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_sales_role(frappe)
    if permission_error:
        return permission_error

    if not _exists("Customer", customer):
        return failure(f"Customer '{customer}' does not exist.", code="VALIDATION_UNKNOWN_CUSTOMER")
    missing = _missing_items([row["item_code"] for row in items])
    if missing:
        return failure(f"Unknown item(s): {', '.join(missing)}", code="VALIDATION_UNKNOWN_ITEM")

    doc_data = {
        "doctype": "Sales Order",
        "customer": customer,
        "delivery_date": delivery_date,
        "items": [
            {
                "item_code": row["item_code"],
                "qty": float(row["qty"]),
                **({"rate": float(row["rate"])} if row.get("rate") not in (None, "") else {}),
                **({"warehouse": row["warehouse"].strip()} if (row.get("warehouse") or "").strip() else {}),
            }
            for row in items
        ],
    }
    if company:
        doc_data["company"] = company
    if price_list:
        doc_data["selling_price_list"] = price_list
    return _insert_doc(doc_data)

def my_orders(limit: int | None = None, offset: int = 0) -> dict:
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_sales_role(frappe)
    if permission_error:
        return permission_error

    page = parse_page(limit, offset, default_limit=50, max_limit=200)
    if not isinstance(page, Page):
        return page

    owner = getattr(getattr(frappe, "session", None), "user", None)
    filters = [
        ["owner", "=", owner],
        ["status", "not in", list(_CLOSED_STATUSES)],
    ]
    rows = frappe.get_list(
        "Sales Order",
        filters=filters,
        fields=["name", "customer", "transaction_date", "delivery_date", "status", "per_delivered", "per_billed"],
        order_by="modified desc",
        limit_start=page.offset,
        limit_page_length=page.limit,
    )
    return success({
        "orders": rows,
        "limit": page.limit,
        "offset": page.offset,
        "total": _count_rows("Sales Order", filters),
    })
