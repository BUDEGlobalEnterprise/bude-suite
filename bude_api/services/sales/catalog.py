"""Grouped mobile endpoints: catalog."""

from ._mobile_shared import *  # noqa: F401,F403

def items(
    search: str | None = None,
    item_group: str | None = None,
    price_list: str | None = None,
    warehouse: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict:
    denied = require_sales_role(frappe)
    if denied:
        return denied
    page = _page(limit, offset)
    if not isinstance(page, Page):
        return page
    filters = [["disabled", "=", 0], ["is_sales_item", "=", 1]]
    if search:
        filters.append(["item_name", "like", f"%{search.strip()}%"])
    if item_group:
        filters.append(["item_group", "=", item_group])
    rows = frappe.get_list(
        "Item",
        filters=filters,
        fields=["item_code", "item_name", "item_group", "stock_uom"],
        order_by="item_name asc",
        limit_start=page.offset,
        limit_page_length=page.limit,
    )
    price_by_item = _price_by_item([row["item_code"] for row in rows], price_list or "Standard Selling")
    stock_by_item = _stock_by_item([row["item_code"] for row in rows], warehouse)
    uoms_by_item = _uoms_by_item([row["item_code"] for row in rows])
    return success(
        {
            "items": [
                {
                    **row,
                    "rate": price_by_item.get(row["item_code"], {}).get("rate", 0),
                    "currency": price_by_item.get(row["item_code"], {}).get("currency"),
                    "available_qty": stock_by_item.get(row["item_code"], 0),
                    "uoms": uoms_by_item.get(row["item_code"], [
                        {"uom": row.get("stock_uom") or "", "conversion_factor": 1}
                    ]),
                }
                for row in rows
            ],
            "limit": page.limit,
            "offset": page.offset,
            "total": _count("Item", filters),
        }
    )


def _uoms_by_item(item_codes: list[str]) -> dict[str, list[dict]]:
    if not item_codes:
        return {}
    try:
        rows = frappe.get_list(
            "UOM Conversion Detail",
            filters=[["parent", "in", item_codes]],
            fields=["parent", "uom", "conversion_factor"],
            order_by="idx asc",
            limit_page_length=1000,
        )
    except Exception:
        return {}
    result = {}
    for row in rows:
        result.setdefault(row.get("parent"), []).append(
            {
                "uom": row.get("uom") or "",
                "conversion_factor": float(row.get("conversion_factor") or 1),
            }
        )
    return result
