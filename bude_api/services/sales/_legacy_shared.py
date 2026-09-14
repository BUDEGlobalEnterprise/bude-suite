"""Sales execution endpoints for mobile users.

All writes use standard ERPNext DocTypes only: Sales Order, Sales Invoice,
Payment Entry, Customer, Item Price, and Bin.
"""

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.pagination import Page, parse_page

from ...utils.response import failure, success

from ..common.permissions import permission_denied, require_sales_role

_CLOSED_STATUSES = {"Closed", "Completed", "Cancelled"}

def _whitelist():
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=False, methods=["GET", "POST"])

def _validate_items(items) -> dict | None:
    if not items:
        return failure("At least one item is required.", code="VALIDATION_REQUIRED")
    for row in items:
        if not isinstance(row, dict):
            return failure("Each item must be an object.", code="VALIDATION_BAD_SHAPE")
        if not row.get("item_code"):
            return failure("Each item needs an item_code.", code="VALIDATION_REQUIRED")
        if "qty" not in row:
            return failure("Each item needs a qty.", code="VALIDATION_REQUIRED")
        try:
            qty = float(row["qty"])
        except (TypeError, ValueError):
            return failure(f"Invalid qty for {row.get('item_code')}.", code="VALIDATION_BAD_QTY")
        if qty <= 0:
            return failure(f"qty must be greater than zero for {row['item_code']}.", code="VALIDATION_BAD_QTY")
    return None

def _exists(doctype: str, name: str) -> bool:
    return bool(frappe.get_list(doctype, filters=[["name", "=", name]], fields=["name"], limit=1))

def _missing_items(codes: list[str]) -> list[str]:
    rows = frappe.get_list(
        "Item",
        filters=[["item_code", "in", codes]],
        fields=["item_code"],
        limit=len(codes),
    )
    found = {row["item_code"] for row in rows}
    return [code for code in codes if code not in found]

def _count_rows(doctype: str, filters: list) -> int:
    try:
        return int(frappe.db.count(doctype, filters=filters))
    except Exception:
        rows = frappe.get_list(
            doctype,
            filters=filters,
            fields=["name"],
            limit_page_length=1000,
        )
        return len(rows)

def _insert_doc(doc_data: dict) -> dict:
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

def _insert_and_submit(doc_data: dict) -> dict:
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

def _erpnext_message(exc: Exception) -> str:
    msg = (str(exc) or "").strip() or "ERPNext rejected the document."
    try:
        from frappe.utils import strip_html_tags

        msg = strip_html_tags(msg).strip() or msg
    except Exception:
        pass
    return msg

__all__ = [name for name in globals() if not name.startswith("__")]
