"""Grouped stock endpoints: reconciliations."""

from ._stock_shared import *  # noqa: F401,F403

def create_reconciliation(
    counts: list,
    warehouse: str,
    posting_date: str | None = None,
    company: str | None = None,
    location: str | None = None,
    unresolved_scans: list | None = None,
) -> dict:
    """Submit a Stock Reconciliation that snapshots actual counted quantities.

    [counts] is a list of {item_code: str, qty: number} representing what the
    operator physically counted. Each row becomes a Stock Reconciliation item
    that sets the actual on-hand to that qty (positive or zero — negatives
    are rejected because counting cannot legitimately produce a negative).
    Each row may also carry a free-text `variance_reason` — the variance
    itself is already computed by ERPNext (counted vs. Bin balance); this
    only supplies the *why*, folded into the document's `remarks`.

    `unresolved_scans` is an optional list of raw barcodes the operator
    scanned but chose to proceed past without resolving to an item; noted
    in `remarks` so they aren't silently lost.

    Per ERPNext convention, current_qty is left for the server to compute at
    submit time from the latest Bin balance.

    Returns {name, docstatus} on success.
    """
    error = _validate_reconciliation_inputs(counts, warehouse)
    if error is not None:
        return error

    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_stock_execution_role(frappe)
    if permission_error is not None:
        return permission_error

    warehouse_or_error = _resolve_effective_warehouse(
        warehouse,
        location,
        company,
        label="Count",
    )
    if isinstance(warehouse_or_error, dict):
        return warehouse_or_error
    effective_warehouse, resolved_company = warehouse_or_error

    missing = _missing_items([row["item_code"] for row in counts])
    if missing:
        return failure(
            f"Unknown item(s): {', '.join(missing)}",
            code="VALIDATION_UNKNOWN_ITEM",
        )

    erp_items = expand_stock_rows(
        frappe,
        counts,
        warehouse=effective_warehouse,
        flow="count",
        row_builder=lambda row, allocation: {
            "item_code": row["item_code"],
            "warehouse": effective_warehouse,
            "qty": (allocation or row)["qty"],
        },
    )
    if isinstance(erp_items, dict):
        return erp_items

    doc_data = {
        "doctype": "Stock Reconciliation",
        "purpose": "Stock Reconciliation",
        "posting_date": posting_date,
        "items": erp_items,
    }
    if resolved_company:
        doc_data["company"] = resolved_company
    remarks = _build_remarks(
        [
            f"{row['item_code']}: {(row.get('variance_reason') or '').strip()}"
            for row in counts
            if (row.get("variance_reason") or "").strip()
        ]
        + _unresolved_scan_notes(unresolved_scans)
    )
    if remarks:
        doc_data["remarks"] = remarks
    return _insert_and_submit(doc_data)
