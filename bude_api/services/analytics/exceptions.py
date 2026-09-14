"""Exception handling workflows using standard ERPNext/Frappe DocTypes."""

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success
from ..common.permissions import permission_denied, require_stock_execution_role

EXCEPTION_TYPES = {"shortage", "damage", "unknown_scan", "blocked_stock"}


def _whitelist():
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=False, methods=["POST", "GET"])


@_whitelist()
def report(
    exception_type: str,
    item_code: str | None = None,
    qty=1,
    warehouse: str | None = None,
    damage_warehouse: str | None = None,
    counted_qty=None,
    barcode: str | None = None,
    note: str | None = None,
    allocated_to: str | None = None,
) -> dict:
    """Map an operator exception to a standard DocType record."""
    exception_type = (exception_type or "").strip()
    if exception_type not in EXCEPTION_TYPES:
        return failure(
            f"exception_type must be one of {sorted(EXCEPTION_TYPES)}.",
            code="VALIDATION_UNKNOWN_EXCEPTION",
        )
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_stock_execution_role(frappe)
    if permission_error:
        return permission_error

    if exception_type == "damage":
        return _damage_transfer(item_code, qty, warehouse, damage_warehouse, note)
    if exception_type == "shortage":
        return _shortage_reconciliation(item_code, counted_qty, warehouse, note)
    if exception_type == "unknown_scan":
        return _todo_exception(
            title=f"Unknown scan: {(barcode or '').strip()}",
            description=(
                f"Exception: unknown_scan\n"
                f"Barcode: {(barcode or '').strip()}\n"
                f"Warehouse: {(warehouse or '').strip()}\n"
                f"Note: {(note or '').strip()}"
            ),
            allocated_to=allocated_to,
        )
    return _todo_exception(
        title=f"Blocked stock: {(item_code or '').strip() or (barcode or '').strip()}",
        description=(
            "Exception: blocked_stock\n"
            f"Item: {(item_code or '').strip()}\n"
            f"Barcode: {(barcode or '').strip()}\n"
            f"Warehouse: {(warehouse or '').strip()}\n"
            f"Note: {(note or '').strip()}"
        ),
        item_code=item_code,
        allocated_to=allocated_to,
    )


@_whitelist()
def list_open(limit: int = 100, offset: int = 0) -> dict:
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    permission_error = require_stock_execution_role(frappe)
    if permission_error:
        return permission_error
    try:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset or 0))
        rows = frappe.get_list(
            "ToDo",
            filters=[
                ["status", "not in", ["Closed", "Cancelled"]],
                ["description", "like", "Exception:%"],
            ],
            fields=[
                "name",
                "description",
                "reference_type",
                "reference_name",
                "allocated_to",
                "priority",
                "date",
            ],
            order_by="creation desc",
            limit_start=offset,
            limit_page_length=limit,
        )
    except frappe.PermissionError:
        return permission_denied()
    return success({
        "exceptions": [_parse_todo(row) for row in rows],
        "total": len(rows),
        "limit": limit,
        "offset": offset,
    })


def _damage_transfer(item_code, qty, warehouse, damage_warehouse, note):
    item_code = (item_code or "").strip()
    warehouse = (warehouse or "").strip()
    damage_warehouse = (damage_warehouse or "").strip()
    if not item_code or not warehouse or not damage_warehouse:
        return failure(
            "item_code, warehouse, and damage_warehouse are required.",
            code="VALIDATION_REQUIRED",
        )
    try:
        qty = float(qty)
    except (TypeError, ValueError):
        return failure("qty must be numeric.", code="VALIDATION_BAD_QTY")
    if qty <= 0:
        return failure("qty must be greater than zero.", code="VALIDATION_BAD_QTY")

    return _insert_and_submit({
        "doctype": "Stock Entry",
        "stock_entry_type": "Material Transfer",
        "purpose": "Material Transfer",
        "remarks": f"Exception: damage\n{(note or '').strip()}".strip(),
        "items": [
            {
                "item_code": item_code,
                "qty": qty,
                "s_warehouse": warehouse,
                "t_warehouse": damage_warehouse,
            }
        ],
    })


def _shortage_reconciliation(item_code, counted_qty, warehouse, note):
    item_code = (item_code or "").strip()
    warehouse = (warehouse or "").strip()
    if not item_code or not warehouse or counted_qty is None:
        return failure(
            "item_code, warehouse, and counted_qty are required.",
            code="VALIDATION_REQUIRED",
        )
    try:
        counted_qty = float(counted_qty)
    except (TypeError, ValueError):
        return failure("counted_qty must be numeric.", code="VALIDATION_BAD_QTY")
    if counted_qty < 0:
        return failure("counted_qty cannot be negative.", code="VALIDATION_BAD_QTY")
    return _insert_and_submit({
        "doctype": "Stock Reconciliation",
        "purpose": "Stock Reconciliation",
        "remarks": f"Exception: shortage\n{(note or '').strip()}".strip(),
        "items": [
            {
                "item_code": item_code,
                "warehouse": warehouse,
                "qty": counted_qty,
            }
        ],
    })


def _todo_exception(title, description, item_code=None, allocated_to=None):
    item_code = (item_code or "").strip()
    payload = {
        "doctype": "ToDo",
        "description": description,
        "status": "Open",
        "priority": "High",
        "allocated_to": (allocated_to or "").strip() or None,
        "date": frappe.utils.nowdate(),
    }
    if item_code:
        payload["reference_type"] = "Item"
        payload["reference_name"] = item_code
    doc = frappe.get_doc(payload)
    try:
        doc.insert(ignore_permissions=False)
    except frappe.PermissionError:
        frappe.db.rollback()
        return permission_denied()
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(_erpnext_message(exc), code="VALIDATION_ERPNEXT")
    return success({"doctype": "ToDo", "name": doc.name, "title": title})


def _insert_and_submit(doc_data: dict) -> dict:
    doc = frappe.get_doc(doc_data)
    try:
        doc.insert(ignore_permissions=False)
        doc.submit()
    except frappe.PermissionError:
        frappe.db.rollback()
        return permission_denied()
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(_erpnext_message(exc), code="VALIDATION_ERPNEXT")
    return success({"doctype": doc_data["doctype"], "name": doc.name, "docstatus": doc.docstatus})


def _parse_todo(row: dict) -> dict:
    description = row.get("description") or ""
    first = description.splitlines()[0] if description else "Exception"
    return {
        "name": row.get("name"),
        "title": first,
        "description": description,
        "reference_type": row.get("reference_type"),
        "reference_name": row.get("reference_name"),
        "allocated_to": row.get("allocated_to"),
        "priority": row.get("priority"),
        "date": str(row.get("date")) if row.get("date") else None,
    }


def _erpnext_message(exc: Exception) -> str:
    msg = (str(exc) or "").strip() or "ERPNext rejected the document."
    try:
        from frappe.utils import strip_html_tags

        msg = strip_html_tags(msg).strip() or msg
    except Exception:
        pass
    return msg
