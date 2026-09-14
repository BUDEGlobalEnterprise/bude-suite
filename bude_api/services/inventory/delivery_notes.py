"""Grouped inventory.sales_orders endpoints: delivery_notes."""

from ._sales_orders_shared import *  # noqa: F401,F403

def create_delivery_note(
    sales_order: str,
    source_warehouse: str,
    items: list,
    posting_date: str | None = None,
    company: str | None = None,
    source_location: str | None = None,
    pod_attachments: list | None = None,
) -> dict:
    """Create and submit a Delivery Note for an exactly fulfilled Sales Order."""
    sales_order = (sales_order or "").strip()
    source_warehouse = (source_warehouse or "").strip()
    if not sales_order:
        return failure("sales_order is required.", code="VALIDATION_REQUIRED")
    if not source_warehouse:
        return failure("source_warehouse is required.", code="VALIDATION_REQUIRED")
    if not items:
        return failure("At least one item is required.", code="VALIDATION_REQUIRED")
    attachment_error = _validate_pod_attachments(pod_attachments)
    if attachment_error is not None:
        return attachment_error
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_stock_execution_role(frappe)
    if permission_error is not None:
        return permission_error

    so = _sales_order(sales_order, company=company)
    if isinstance(so, dict) and so.get("ok") is False:
        return so

    stock_api.frappe = frappe
    if hasattr(stock_api, "sync_frappe"):
        stock_api.sync_frappe(frappe)
    source_or_error = stock_api._resolve_effective_warehouse(
        source_warehouse,
        source_location,
        so.get("company") or company,
        label="Source",
    )
    if isinstance(source_or_error, dict):
        return source_or_error
    effective_source, resolved_company = source_or_error

    pending = _pending_lines(sales_order)
    exact_error = _validate_exact_items(items, pending)
    if exact_error is not None:
        return exact_error

    pending_by_name = {row["sales_order_item"]: row for row in pending}
    erp_items = stock_api.expand_stock_rows(
        frappe,
        items,
        warehouse=effective_source,
        flow="outbound",
        row_builder=lambda row, allocation: {
            "item_code": row["item_code"],
            "qty": (allocation or row)["qty"],
            "warehouse": effective_source,
            "against_sales_order": sales_order,
            "so_detail": row["sales_order_item"],
        },
    )
    if isinstance(erp_items, dict):
        return erp_items

    doc_data = {
        "doctype": "Delivery Note",
        "customer": so.get("customer"),
        "posting_date": posting_date,
        "items": erp_items,
    }
    if resolved_company:
        doc_data["company"] = resolved_company
    for row in doc_data["items"]:
        source_line = pending_by_name[row["so_detail"]]
        if source_line.get("stock_uom"):
            row["uom"] = source_line["stock_uom"]

    result = stock_api._insert_and_submit(doc_data)
    if result.get("ok") is not True:
        return result
    attachment_error = _attach_pod_files(result["data"]["name"], pod_attachments)
    if attachment_error is not None:
        return attachment_error
    if pod_attachments:
        result["data"]["pod_attachments"] = len(pod_attachments)
    return result
