"""Stock write endpoints.

    POST /api/method/bude_api.api.stock.create_transfer        (auth required)
    POST /api/method/bude_api.api.stock.create_receipt         (auth required)
    POST /api/method/bude_api.api.stock.create_reconciliation  (auth required)
    POST /api/method/bude_api.api.stock.create_material_request (auth required)

All writes go through standard ERPNext DocTypes (Stock Entry, Purchase
Receipt, Stock Reconciliation, Warehouse, Item, Purchase Order) — no
custom DocTypes.
"""

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success

from ..common.permissions import permission_denied, require_stock_execution_role

from .stock_tracking import expand_stock_rows

def _whitelist(allow_guest: bool = False):
    if frappe is None:
        def decorator(fn):
            return fn
        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=["POST"])

def _insert_and_submit(doc_data: dict) -> dict:
    """Insert + submit a doc, turning ERPNext validation errors (which Frappe
    would otherwise surface as a raw HTTP 417 with no usable message) into a
    clean VALIDATION_ERPNEXT failure envelope. Rolls back so a rejected submit
    never leaves a stray draft behind.
    """
    doc = frappe.get_doc(doc_data)
    try:
        doc.insert(ignore_permissions=False)
        doc.submit()
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(_erpnext_message(exc), code="VALIDATION_ERPNEXT")
    except frappe.PermissionError:
        frappe.db.rollback()
        return permission_denied()
    return success({"name": doc.name, "docstatus": doc.docstatus})

def _insert_draft(doc_data: dict) -> dict:
    doc = frappe.get_doc(doc_data)
    try:
        doc.insert(ignore_permissions=False)
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(_erpnext_message(exc), code="VALIDATION_ERPNEXT")
    except frappe.PermissionError:
        frappe.db.rollback()
        return permission_denied()
    return success({"name": doc.name, "docstatus": doc.docstatus})

def _erpnext_message(exc: Exception) -> str:
    msg = (str(exc) or "").strip() or "ERPNext rejected the document."
    try:  # Frappe messages can carry HTML; strip it for a clean mobile string.
        from frappe.utils import strip_html_tags
        msg = strip_html_tags(msg).strip() or msg
    except Exception:
        pass
    return msg

def _build_remarks(notes: list) -> str | None:
    """Join per-line exception/variance notes and unresolved-scan flags into
    one `remarks` string. No custom fields — `remarks` is the standard
    ERPNext text field already used elsewhere in this app (see demo/seed.py).
    """
    cleaned = [n for n in notes if n]
    return "\n".join(cleaned) if cleaned else None

def _unresolved_scan_notes(unresolved_scans: list | None) -> list:
    return [f"Unresolved scan: {b}" for b in (unresolved_scans or []) if b]

def _validate_material_request_inputs(items) -> dict | None:
    if not items:
        return failure("At least one item is required.", code="VALIDATION_REQUIRED")
    for row in items:
        if not isinstance(row, dict):
            return failure("Each item must be an object.", code="VALIDATION_BAD_SHAPE")
        if "item_code" not in row or not row["item_code"]:
            return failure("Each item needs an item_code.", code="VALIDATION_REQUIRED")
        if "qty" not in row:
            return failure("Each item needs a qty.", code="VALIDATION_REQUIRED")
        try:
            qty = float(row["qty"])
        except (TypeError, ValueError):
            return failure(
                f"Invalid qty for {row.get('item_code')}.",
                code="VALIDATION_BAD_QTY",
            )
        if qty <= 0:
            return failure(
                f"qty must be greater than zero for {row['item_code']}.",
                code="VALIDATION_BAD_QTY",
            )
    return None

def _today() -> str | None:
    try:
        return frappe.utils.nowdate()
    except Exception:
        return None

_EXCEPTION_TYPES = {"shortage", "damage"}

def _validate_inputs(
    items, source_warehouse, target_warehouse,
) -> dict | None:
    if not source_warehouse or not source_warehouse.strip():
        return failure("source_warehouse is required.", code="VALIDATION_REQUIRED")
    if not target_warehouse or not target_warehouse.strip():
        return failure("target_warehouse is required.", code="VALIDATION_REQUIRED")
    if not items:
        return failure("At least one item is required.", code="VALIDATION_REQUIRED")
    for row in items:
        if not isinstance(row, dict):
            return failure("Each item must be an object.", code="VALIDATION_BAD_SHAPE")
        if "item_code" not in row or not row["item_code"]:
            return failure("Each item needs an item_code.", code="VALIDATION_REQUIRED")
        if "qty" not in row:
            return failure("Each item needs a qty.", code="VALIDATION_REQUIRED")
        try:
            qty = float(row["qty"])
        except (TypeError, ValueError):
            return failure(
                f"Invalid qty for {row.get('item_code')}.",
                code="VALIDATION_BAD_QTY",
            )
        if qty <= 0:
            return failure(
                f"qty must be greater than zero for {row['item_code']}.",
                code="VALIDATION_BAD_QTY",
            )
        exception_type = row.get("exception_type")
        if exception_type is not None and exception_type not in _EXCEPTION_TYPES:
            return failure(
                f"exception_type must be one of {sorted(_EXCEPTION_TYPES)} "
                f"for {row['item_code']}.",
                code="VALIDATION_BAD_EXCEPTION_TYPE",
            )
    return None

def _warehouse_info(name: str) -> dict | None:
    rows = frappe.get_list(
        "Warehouse",
        filters=[["name", "=", name]],
        fields=["name", "company", "parent_warehouse"],
        limit=1,
    )
    return rows[0] if rows else None

def _warehouse_exists(name: str) -> bool:
    return _warehouse_info(name) is not None

def _clean_company(company: str | None) -> str | None:
    company = (company or "").strip()
    return company or None

def _warehouse_company_mismatch(message: str) -> dict:
    return failure(message, code="VALIDATION_WAREHOUSE_COMPANY_MISMATCH")

def _location_scope_mismatch(message: str) -> dict:
    return failure(message, code="VALIDATION_LOCATION_SCOPE")

def _resolve_effective_warehouse(
    warehouse: str,
    location: str | None,
    company: str | None,
    label: str = "Warehouse",
) -> tuple[str, str | None] | dict:
    parent = _warehouse_info(warehouse)
    if parent is None:
        return failure(
            f"{label} warehouse '{warehouse}' does not exist.",
            code="VALIDATION_UNKNOWN_WAREHOUSE",
        )

    resolved_company_or_error = _resolve_warehouse_company(
        warehouse,
        parent.get("company"),
        company,
        label=f"{label} warehouse",
    )
    if isinstance(resolved_company_or_error, dict):
        return resolved_company_or_error
    resolved_company = resolved_company_or_error

    location = (location or "").strip()
    if not location:
        return warehouse, resolved_company

    child = _warehouse_info(location)
    if child is None:
        return failure(
            f"{label} location '{location}' does not exist.",
            code="VALIDATION_UNKNOWN_WAREHOUSE",
        )
    if child.get("parent_warehouse") != warehouse:
        return _location_scope_mismatch(
            f"{label} location '{location}' is not under warehouse '{warehouse}'."
        )

    child_company_or_error = _resolve_warehouse_company(
        location,
        child.get("company"),
        resolved_company,
        label=f"{label} location",
    )
    if isinstance(child_company_or_error, dict):
        return child_company_or_error

    return location, child_company_or_error

def _resolve_transfer_company(
    source_warehouse: str,
    source_company: str | None,
    target_warehouse: str,
    target_company: str | None,
    company: str | None,
) -> str | dict | None:
    source_company = _clean_company(source_company)
    target_company = _clean_company(target_company)
    requested_company = _clean_company(company)

    if source_company and target_company and source_company != target_company:
        return _warehouse_company_mismatch(
            f"Source warehouse '{source_warehouse}' belongs to '{source_company}', "
            f"but target warehouse '{target_warehouse}' belongs to '{target_company}'."
        )

    inferred_company = source_company or target_company
    if requested_company:
        for label, warehouse, warehouse_company in (
            ("Source", source_warehouse, source_company),
            ("Target", target_warehouse, target_company),
        ):
            if warehouse_company and warehouse_company != requested_company:
                return _warehouse_company_mismatch(
                    f"{label} warehouse '{warehouse}' belongs to "
                    f"'{warehouse_company}', not '{requested_company}'."
                )
        return requested_company

    return inferred_company

def _resolve_warehouse_company(
    warehouse: str,
    warehouse_company: str | None,
    company: str | None,
    label: str = "Warehouse",
) -> str | dict | None:
    warehouse_company = _clean_company(warehouse_company)
    requested_company = _clean_company(company)
    if requested_company and warehouse_company and requested_company != warehouse_company:
        return _warehouse_company_mismatch(
            f"{label} '{warehouse}' belongs to '{warehouse_company}', "
            f"not '{requested_company}'."
        )
    return requested_company or warehouse_company

def _missing_items(codes: list) -> list:
    if not codes:
        return []
    found = frappe.get_list(
        "Item",
        filters=[["item_code", "in", codes]],
        fields=["item_code"],
        limit=len(codes),
    )
    found_set = {row["item_code"] for row in found}
    return [code for code in codes if code not in found_set]

def _validate_receipt_inputs(items, target_warehouse, against_po=None) -> dict | None:
    if not target_warehouse or not target_warehouse.strip():
        return failure("target_warehouse is required.", code="VALIDATION_REQUIRED")
    if not items:
        return failure("At least one item is required.", code="VALIDATION_REQUIRED")
    for row in items:
        if not isinstance(row, dict):
            return failure("Each item must be an object.", code="VALIDATION_BAD_SHAPE")
        if "item_code" not in row or not row["item_code"]:
            return failure("Each item needs an item_code.", code="VALIDATION_REQUIRED")
        if "qty" not in row:
            return failure("Each item needs a qty.", code="VALIDATION_REQUIRED")
        try:
            qty = float(row["qty"])
        except (TypeError, ValueError):
            return failure(
                f"Invalid qty for {row.get('item_code')}.",
                code="VALIDATION_BAD_QTY",
            )
        if qty <= 0:
            return failure(
                f"qty must be greater than zero for {row['item_code']}.",
                code="VALIDATION_BAD_QTY",
            )
        rejected_qty_error = _validate_rejected_qty(row, against_po)
        if rejected_qty_error is not None:
            return rejected_qty_error
    return None

def _validate_rejected_qty(row: dict, against_po: str | None) -> dict | None:
    if "rejected_qty" not in row or row["rejected_qty"] in (None, ""):
        return None
    try:
        rejected_qty = float(row["rejected_qty"])
    except (TypeError, ValueError):
        return failure(
            f"Invalid rejected_qty for {row.get('item_code')}.",
            code="VALIDATION_BAD_QTY",
        )
    if rejected_qty < 0:
        return failure(
            f"rejected_qty cannot be negative for {row['item_code']}.",
            code="VALIDATION_BAD_QTY",
        )
    if rejected_qty <= 0:
        return None
    if not against_po:
        return failure(
            f"rejected_qty for {row['item_code']} requires against_po "
            "(Stock Entry has no rejected-qty field); use damage_note instead.",
            code="VALIDATION_REJECTED_QTY_REQUIRES_PO",
        )
    if not (row.get("rejected_warehouse") or "").strip():
        return failure(
            f"rejected_warehouse is required when rejected_qty is set "
            f"for {row['item_code']}.",
            code="VALIDATION_REJECTED_WAREHOUSE_REQUIRED",
        )
    return None

def _create_material_receipt(
    items, target_warehouse, posting_date, company=None, unresolved_scans=None
) -> dict:
    erp_items = expand_stock_rows(
        frappe,
        items,
        warehouse=target_warehouse,
        flow="inbound",
        allow_new_batches=True,
        allow_new_serials=True,
        row_builder=lambda row, allocation: {
            "item_code": row["item_code"],
            "qty": (allocation or row)["qty"],
            "t_warehouse": target_warehouse,
        },
    )
    if isinstance(erp_items, dict):
        return erp_items

    doc_data = {
        "doctype": "Stock Entry",
        "stock_entry_type": "Material Receipt",
        "purpose": "Material Receipt",
        "posting_date": posting_date,
        "items": erp_items,
    }
    if company:
        doc_data["company"] = company
    remarks = _build_remarks(
        [
            f"{row['item_code']}: {(row.get('damage_note') or '').strip()}"
            for row in items
            if (row.get("damage_note") or "").strip()
        ]
        + _unresolved_scan_notes(unresolved_scans)
    )
    if remarks:
        doc_data["remarks"] = remarks
    return _insert_and_submit(doc_data)

def _create_purchase_receipt(
    items,
    target_warehouse,
    against_po,
    posting_date,
    company=None,
    unresolved_scans=None,
) -> dict:
    po_rows = frappe.get_list(
        "Purchase Order",
        filters=[["name", "=", against_po], ["docstatus", "=", 1]],
        fields=["name", "supplier", "company"],
        limit=1,
    )
    po_doc = po_rows[0] if po_rows else None
    if not po_doc:
        return failure(
            f"Purchase Order '{against_po}' not found or not submitted.",
            code="VALIDATION_UNKNOWN_PO",
        )
    po_company = _clean_company(po_doc.get("company"))
    company = _clean_company(company)
    if company and po_company and company != po_company:
        return failure(
            f"Purchase Order '{against_po}' belongs to '{po_company}', not '{company}'.",
            code="VALIDATION_PO_COMPANY_MISMATCH",
        )
    company = company or po_company

    # Build a lookup of {item_code: po_detail_name, po_qty} from the PO lines.
    po_lines = frappe.get_list(
        "Purchase Order Item",
        filters=[["parent", "=", against_po]],
        fields=["name", "item_code", "qty"],
        limit=500,
    )
    po_line_by_code = {row["item_code"]: row for row in po_lines}

    rejected = [
        row["item_code"] for row in items if row["item_code"] not in po_line_by_code
    ]
    if rejected:
        return failure(
            f"Item(s) not on PO {against_po}: {', '.join(rejected)}",
            code="VALIDATION_PO_LINE_MISMATCH",
        )

    erp_items = expand_stock_rows(
        frappe,
        items,
        warehouse=target_warehouse,
        flow="inbound",
        allow_new_batches=True,
        allow_new_serials=True,
        row_builder=lambda row, allocation: {
            "item_code": row["item_code"],
            "qty": (allocation or row)["qty"],
            "warehouse": target_warehouse,
            "purchase_order": against_po,
            "purchase_order_item": po_line_by_code[row["item_code"]]["name"],
            **(
                {"rejected_qty": row["rejected_qty"]}
                if row.get("rejected_qty")
                else {}
            ),
            **(
                {"rejected_warehouse": row["rejected_warehouse"]}
                if row.get("rejected_warehouse")
                else {}
            ),
        },
    )
    if isinstance(erp_items, dict):
        return erp_items

    pr_data = {
        "doctype": "Purchase Receipt",
        "supplier": po_doc["supplier"],
        "posting_date": posting_date,
        "items": erp_items,
    }
    if company:
        pr_data["company"] = company
    remarks = _build_remarks(
        [
            f"{row['item_code']}: {(row.get('damage_note') or '').strip()}"
            for row in items
            if (row.get("damage_note") or "").strip()
        ]
        + _unresolved_scan_notes(unresolved_scans)
    )
    if remarks:
        pr_data["remarks"] = remarks
    return _insert_and_submit(pr_data)

def _validate_reconciliation_inputs(counts, warehouse) -> dict | None:
    if not warehouse or not warehouse.strip():
        return failure("warehouse is required.", code="VALIDATION_REQUIRED")
    if not counts:
        return failure("At least one count is required.", code="VALIDATION_REQUIRED")
    for row in counts:
        if not isinstance(row, dict):
            return failure("Each count must be an object.", code="VALIDATION_BAD_SHAPE")
        if "item_code" not in row or not row["item_code"]:
            return failure("Each count needs an item_code.", code="VALIDATION_REQUIRED")
        if "qty" not in row:
            return failure("Each count needs a qty.", code="VALIDATION_REQUIRED")
        try:
            qty = float(row["qty"])
        except (TypeError, ValueError):
            return failure(
                f"Invalid qty for {row.get('item_code')}.",
                code="VALIDATION_BAD_QTY",
            )
        if qty < 0:
            return failure(
                f"qty cannot be negative for {row['item_code']}.",
                code="VALIDATION_BAD_QTY",
            )
    return None

__all__ = [name for name in globals() if not name.startswith("__")]
