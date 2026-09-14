"""Grouped stock endpoints: receipts."""

from ._stock_shared import *  # noqa: F401,F403

def create_receipt(
    items: list,
    target_warehouse: str,
    against_po: str | None = None,
    posting_date: str | None = None,
    company: str | None = None,
    target_location: str | None = None,
    unresolved_scans: list | None = None,
) -> dict:
    """Receive stock into [target_warehouse].

    If [against_po] is provided: creates a Purchase Receipt linked to the PO.
    The supplier is resolved from the PO. Each item must match a line on
    that PO (by item_code) — extras are rejected with
    VALIDATION_PO_LINE_MISMATCH. Each item may also carry `rejected_qty`
    and `rejected_warehouse` — standard Purchase Receipt Item fields for
    goods received but not accepted (damaged/short). `rejected_qty` is not
    supported without a PO (Stock Entry has no such field); use
    `damage_note` there instead, which folds into `remarks`.

    Otherwise: creates a Stock Entry of type Material Receipt.

    `unresolved_scans` is an optional list of raw barcodes the operator
    scanned but chose to proceed past without resolving to an item; noted
    in the document's `remarks` so they aren't silently lost.

    Returns {name, docstatus} on success.
    """
    error = _validate_receipt_inputs(items, target_warehouse, against_po)
    if error is not None:
        return error

    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_stock_execution_role(frappe)
    if permission_error is not None:
        return permission_error

    target_or_error = _resolve_effective_warehouse(
        target_warehouse,
        target_location,
        company,
        label="Target",
    )
    if isinstance(target_or_error, dict):
        return target_or_error
    effective_target, resolved_company = target_or_error

    missing = _missing_items([row["item_code"] for row in items])
    if missing:
        return failure(
            f"Unknown item(s): {', '.join(missing)}",
            code="VALIDATION_UNKNOWN_ITEM",
        )

    if against_po:
        rejected_warehouses = {
            (row.get("rejected_warehouse") or "").strip()
            for row in items
            if (row.get("rejected_warehouse") or "").strip()
        }
        for warehouse in rejected_warehouses:
            if not _warehouse_exists(warehouse):
                return failure(
                    f"Rejected warehouse '{warehouse}' does not exist.",
                    code="VALIDATION_UNKNOWN_WAREHOUSE",
                )
        return _create_purchase_receipt(
            items,
            effective_target,
            against_po,
            posting_date,
            resolved_company,
            unresolved_scans,
        )

    return _create_material_receipt(
        items, effective_target, posting_date, resolved_company, unresolved_scans
    )
