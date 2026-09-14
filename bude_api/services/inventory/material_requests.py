"""Grouped stock endpoints: material_requests."""

from ._stock_shared import *  # noqa: F401,F403

def create_material_request(
    items: list,
    schedule_date: str | None = None,
    company: str | None = None,
) -> dict:
    """Create a draft Purchase Material Request for replenishment."""
    error = _validate_material_request_inputs(items)
    if error is not None:
        return error

    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_stock_execution_role(frappe)
    if permission_error is not None:
        return permission_error

    missing = _missing_items([row["item_code"] for row in items])
    if missing:
        return failure(
            f"Unknown item(s): {', '.join(missing)}",
            code="VALIDATION_UNKNOWN_ITEM",
        )

    warehouses = {
        (row.get("warehouse") or "").strip()
        for row in items
        if (row.get("warehouse") or "").strip()
    }
    for warehouse in warehouses:
        if not _warehouse_exists(warehouse):
            return failure(
                f"Warehouse '{warehouse}' does not exist.",
                code="VALIDATION_UNKNOWN_WAREHOUSE",
            )

    doc_data = {
        "doctype": "Material Request",
        "material_request_type": "Purchase",
        "schedule_date": schedule_date or _today(),
        "items": [
            {
                "item_code": row["item_code"],
                "qty": float(row["qty"]),
                **(
                    {"warehouse": row["warehouse"].strip()}
                    if (row.get("warehouse") or "").strip()
                    else {}
                ),
            }
            for row in items
        ],
    }
    if company:
        doc_data["company"] = company
    return _insert_draft(doc_data)
