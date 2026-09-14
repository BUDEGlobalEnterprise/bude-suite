"""Grouped stock endpoints: transfers."""

from ._stock_shared import *  # noqa: F401,F403

def create_transfer(
    items: list,
    source_warehouse: str,
    target_warehouse: str,
    posting_date: str | None = None,
    company: str | None = None,
    source_location: str | None = None,
    target_location: str | None = None,
    unresolved_scans: list | None = None,
) -> dict:
    """Create + submit a Stock Entry of type Material Transfer.

    `items` is a list of {item_code: str, qty: number}. Each item may also
    carry `exception_type` ("shortage" | "damage") and `exception_note` —
    Stock Entry has no rejected-qty equivalent, so these fold into the
    document's standard `remarks` field rather than a new ERP field.
    `unresolved_scans` is an optional list of raw barcodes the operator
    scanned but chose to proceed past without resolving to an item; these
    are also noted in `remarks` so they aren't silently lost.

    Returns {name, docstatus} on success. Validation errors are 4xx
    (VALIDATION_*); server / DB errors propagate as 5xx via Frappe's default
    handling.
    """
    error = _validate_inputs(items, source_warehouse, target_warehouse)
    if error is not None:
        return error

    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_stock_execution_role(frappe)
    if permission_error is not None:
        return permission_error

    source_or_error = _resolve_effective_warehouse(
        source_warehouse,
        source_location,
        company,
        label="Source",
    )
    if isinstance(source_or_error, dict):
        return source_or_error
    effective_source, source_company = source_or_error

    target_or_error = _resolve_effective_warehouse(
        target_warehouse,
        target_location,
        company,
        label="Target",
    )
    if isinstance(target_or_error, dict):
        return target_or_error
    effective_target, target_company = target_or_error

    if effective_source == effective_target:
        return failure(
            "Source and target warehouses must differ.",
            code="VALIDATION_SAME_WAREHOUSE",
        )
    resolved_company_or_error = _resolve_transfer_company(
        source_warehouse,
        source_company,
        target_warehouse,
        target_company,
        company,
    )
    if isinstance(resolved_company_or_error, dict):
        return resolved_company_or_error
    resolved_company = resolved_company_or_error

    missing = _missing_items([row["item_code"] for row in items])
    if missing:
        return failure(
            f"Unknown item(s): {', '.join(missing)}",
            code="VALIDATION_UNKNOWN_ITEM",
        )

    erp_items = expand_stock_rows(
        frappe,
        items,
        warehouse=effective_source,
        flow="outbound",
        row_builder=lambda row, allocation: {
            "item_code": row["item_code"],
            "qty": (allocation or row)["qty"],
            "s_warehouse": effective_source,
            "t_warehouse": effective_target,
        },
    )
    if isinstance(erp_items, dict):
        return erp_items

    doc_data = {
        "doctype": "Stock Entry",
        "stock_entry_type": "Material Transfer",
        "purpose": "Material Transfer",
        "posting_date": posting_date,
        "items": erp_items,
    }
    if resolved_company:
        doc_data["company"] = resolved_company
    remarks = _build_remarks(
        [
            f"{row['item_code']}: {row.get('exception_type', '')} — "
            f"{(row.get('exception_note') or '').strip()}"
            for row in items
            if row.get("exception_type") or (row.get("exception_note") or "").strip()
        ]
        + _unresolved_scan_notes(unresolved_scans)
    )
    if remarks:
        doc_data["remarks"] = remarks
    return _insert_and_submit(doc_data)
