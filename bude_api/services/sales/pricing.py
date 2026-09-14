"""Grouped sales.legacy endpoints: pricing."""

from ._legacy_shared import *  # noqa: F401,F403

def item_price(
    item_code: str,
    price_list: str | None = None,
    warehouse: str | None = None,
) -> dict:
    item_code = (item_code or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_sales_role(frappe)
    if permission_error:
        return permission_error

    price_list = (price_list or "Standard Selling").strip()
    warehouse = (warehouse or "").strip() or None
    price_rows = frappe.get_list(
        "Item Price",
        filters=[
            ["item_code", "=", item_code],
            ["price_list", "=", price_list],
            ["selling", "=", 1],
        ],
        fields=["price_list", "price_list_rate", "currency", "uom"],
        order_by="valid_from desc",
        limit_page_length=1,
    )
    bin_filters = [["item_code", "=", item_code]]
    if warehouse:
        bin_filters.append(["warehouse", "=", warehouse])
    bins = frappe.get_list(
        "Bin",
        filters=bin_filters,
        fields=["warehouse", "actual_qty", "projected_qty"],
        limit_page_length=200,
    )
    available_qty = sum(float(row.get("actual_qty") or 0) for row in bins)
    projected_qty = sum(float(row.get("projected_qty") or 0) for row in bins)
    price = price_rows[0] if price_rows else {}
    return success({
        "item_code": item_code,
        "price_list": price_list,
        "rate": float(price.get("price_list_rate") or 0),
        "currency": price.get("currency"),
        "uom": price.get("uom"),
        "warehouse": warehouse,
        "available_qty": available_qty,
        "projected_qty": projected_qty,
    })
