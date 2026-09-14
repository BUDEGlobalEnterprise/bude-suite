"""Grouped mobile endpoints: masters."""

from ._mobile_shared import *  # noqa: F401,F403

def masters() -> dict:
    denied = require_sales_role(frappe)
    if denied:
        return denied
    return success(
        {
            "companies": _names("Company"),
            "territories": _names("Territory"),
            "price_lists": _names("Price List", filters=[["selling", "=", 1]]),
            "warehouses": _names("Warehouse", filters=[["disabled", "=", 0]]),
            "item_groups": _names("Item Group"),
            "modes_of_payment": _names("Mode of Payment", filters=[["enabled", "=", 1]]),
            "sales_persons": _sales_persons(),
            "is_manager": _is_sales_manager(),
            "can_invoice": _has_accounts_role() or _is_sales_manager(),
        }
    )
