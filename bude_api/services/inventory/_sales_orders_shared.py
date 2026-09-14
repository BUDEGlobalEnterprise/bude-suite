"""Sales Order fulfillment endpoints.

Reads open Sales Orders and creates submitted Delivery Notes from exact
mobile pick/pack dispatch payloads. Uses only standard ERPNext DocTypes.
"""

import base64

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success

from . import stock as stock_api

from ..common.permissions import require_stock_execution_role

_CLOSED_STATUSES = {"Closed", "Completed", "Cancelled"}

_QTY_EPSILON = 0.000001

def _whitelist(allow_guest: bool = False):
    if frappe is None:
        def decorator(fn):
            return fn
        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=["GET", "POST"])

def _sales_order(name: str, company: str | None = None) -> dict:
    rows = frappe.get_list(
        "Sales Order",
        filters=[["name", "=", name], ["docstatus", "=", 1]],
        fields=[
            "name",
            "customer",
            "transaction_date",
            "delivery_date",
            "status",
            "company",
        ],
        limit=1,
    )
    row = rows[0] if rows else None
    if not row:
        return failure(
            f"Sales Order '{name}' not found or not submitted.",
            code="VALIDATION_UNKNOWN_SALES_ORDER",
        )
    if row.get("status") in _CLOSED_STATUSES:
        return failure(
            f"Sales Order '{name}' is {row.get('status')}.",
            code="VALIDATION_SALES_ORDER_CLOSED",
        )
    requested_company = (company or "").strip()
    if requested_company and row.get("company") and row.get("company") != requested_company:
        return failure(
            f"Sales Order '{name}' belongs to '{row.get('company')}', not '{requested_company}'.",
            code="VALIDATION_SO_COMPANY_MISMATCH",
        )
    return row

def _pending_summary_by_order(names: list[str]) -> dict[str, dict]:
    if not names:
        return {}
    lines = frappe.get_list(
        "Sales Order Item",
        filters=[["parent", "in", names]],
        fields=["parent", "qty", "delivered_qty"],
        limit=5000,
    )
    summary: dict[str, dict] = {}
    for line in lines:
        pending = _pending_qty(line)
        if pending <= _QTY_EPSILON:
            continue
        bucket = summary.setdefault(line["parent"], {"item_count": 0, "pending_qty": 0.0})
        bucket["item_count"] += 1
        bucket["pending_qty"] += pending
    return summary

def _pending_lines(sales_order: str) -> list[dict]:
    rows = frappe.get_list(
        "Sales Order Item",
        filters=[["parent", "=", sales_order]],
        fields=[
            "name",
            "item_code",
            "item_name",
            "qty",
            "delivered_qty",
            "stock_uom",
            "warehouse",
        ],
        order_by="idx asc",
        limit=500,
    )
    result = []
    tracking_by_item = _tracking_by_item({row["item_code"] for row in rows})
    for row in rows:
        pending = _pending_qty(row)
        if pending <= _QTY_EPSILON:
            continue
        tracking = tracking_by_item.get(row["item_code"], {})
        result.append({
            "sales_order_item": row["name"],
            "item_code": row["item_code"],
            "item_name": row.get("item_name"),
            "pending_qty": pending,
            "stock_uom": row.get("stock_uom"),
            "warehouse": row.get("warehouse"),
            "has_batch_no": tracking.get("has_batch_no") or 0,
            "has_serial_no": tracking.get("has_serial_no") or 0,
            "create_new_batch": tracking.get("create_new_batch") or 0,
        })
    return result

def _tracking_by_item(item_codes: set[str]) -> dict[str, dict]:
    if not item_codes:
        return {}
    rows = frappe.get_list(
        "Item",
        filters=[["item_code", "in", list(item_codes)]],
        fields=["item_code", "has_batch_no", "has_serial_no", "create_new_batch"],
        limit=len(item_codes),
    )
    return {row["item_code"]: row for row in rows}

def _pending_qty(row: dict) -> float:
    return float(row.get("qty") or 0) - float(row.get("delivered_qty") or 0)

def _validate_exact_items(items: list, pending: list[dict]) -> dict | None:
    pending_by_name = {row["sales_order_item"]: row for row in pending}
    seen: set[str] = set()

    for row in items:
        if not isinstance(row, dict):
            return failure("Each item must be an object.", code="VALIDATION_BAD_SHAPE")
        line_name = (row.get("sales_order_item") or "").strip()
        if not line_name:
            return failure("Each item needs a sales_order_item.", code="VALIDATION_REQUIRED")
        if line_name in seen:
            return failure(
                f"Duplicate Sales Order line '{line_name}'.",
                code="VALIDATION_DUPLICATE_SO_LINE",
            )
        seen.add(line_name)
        if line_name not in pending_by_name:
            return failure(
                f"Sales Order line '{line_name}' is not pending on this order.",
                code="VALIDATION_SO_LINE_MISMATCH",
            )
        pending_row = pending_by_name[line_name]
        if row.get("item_code") != pending_row["item_code"]:
            return failure(
                f"Item mismatch for Sales Order line '{line_name}'.",
                code="VALIDATION_SO_LINE_MISMATCH",
            )
        try:
            qty = float(row.get("qty"))
        except (TypeError, ValueError):
            return failure(
                f"Invalid qty for {row.get('item_code')}.",
                code="VALIDATION_BAD_QTY",
            )
        expected = float(pending_row["pending_qty"])
        if abs(qty - expected) > _QTY_EPSILON:
            return failure(
                f"Line '{line_name}' requires exactly {expected:g}.",
                code="VALIDATION_EXACT_QTY_REQUIRED",
            )

    missing = [row["sales_order_item"] for row in pending if row["sales_order_item"] not in seen]
    if missing:
        return failure(
            f"Missing Sales Order line(s): {', '.join(missing)}",
            code="VALIDATION_MISSING_SO_LINES",
        )
    return None

def _validate_pod_attachments(attachments: list | None) -> dict | None:
    if not attachments:
        return None
    if not isinstance(attachments, list):
        return failure("pod_attachments must be a list.", code="VALIDATION_BAD_SHAPE")
    if len(attachments) > 2:
        return failure("Only photo and signature POD files are supported.", code="VALIDATION_BAD_SHAPE")
    seen = set()
    for attachment in attachments:
        if not isinstance(attachment, dict):
            return failure("Each POD attachment must be an object.", code="VALIDATION_BAD_SHAPE")
        kind = (attachment.get("type") or "").strip()
        file_name = (attachment.get("file_name") or "").strip()
        content = (attachment.get("content_base64") or "").strip()
        if kind not in {"photo", "signature"}:
            return failure("POD attachment type must be photo or signature.", code="VALIDATION_BAD_SHAPE")
        if kind in seen:
            return failure(f"Duplicate POD attachment type: {kind}.", code="VALIDATION_BAD_SHAPE")
        seen.add(kind)
        if not file_name or not content:
            return failure("POD file_name and content_base64 are required.", code="VALIDATION_REQUIRED")
        if len(content) > 7_000_000:
            return failure("POD attachment is too large.", code="VALIDATION_FILE_TOO_LARGE")
        if base64 is not None:
            try:
                base64.b64decode(content, validate=True)
            except Exception:
                return failure("POD attachment content must be valid base64.", code="VALIDATION_BAD_FILE")
    return None

def _attach_pod_files(delivery_note: str, attachments: list | None) -> dict | None:
    if not attachments:
        return None
    try:
        for attachment in attachments:
            file_doc = frappe.get_doc({
                "doctype": "File",
                "attached_to_doctype": "Delivery Note",
                "attached_to_name": delivery_note,
                "file_name": attachment["file_name"],
                "content": attachment["content_base64"],
                "decode": True,
                "is_private": 1,
            })
            file_doc.insert(ignore_permissions=False)
        frappe.db.commit()
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(stock_api._erpnext_message(exc), code="VALIDATION_ERPNEXT")
    return None

__all__ = [name for name in globals() if not name.startswith("__")]
