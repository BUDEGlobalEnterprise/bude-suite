"""Grouped sales.legacy endpoints: invoice_payment."""

from ._legacy_shared import *  # noqa: F401,F403

def create_invoice(
    customer: str,
    items: list,
    sales_order: str | None = None,
    posting_date: str | None = None,
    company: str | None = None,
) -> dict:
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    item_error = _validate_items(items)
    if item_error:
        return item_error
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_sales_role(frappe)
    if permission_error:
        return permission_error

    sales_order = (sales_order or "").strip() or None
    doc_data = {
        "doctype": "Sales Invoice",
        "customer": customer,
        "posting_date": posting_date,
        "items": [
            {
                "item_code": row["item_code"],
                "qty": float(row["qty"]),
                **({"rate": float(row["rate"])} if row.get("rate") not in (None, "") else {}),
                **({"sales_order": sales_order} if sales_order else {}),
            }
            for row in items
        ],
    }
    if company:
        doc_data["company"] = company
    return _insert_and_submit(doc_data)

def record_payment(
    party: str,
    paid_amount,
    mode_of_payment: str,
    reference_no: str | None = None,
    reference_date: str | None = None,
    sales_invoice: str | None = None,
    company: str | None = None,
) -> dict:
    party = (party or "").strip()
    mode_of_payment = (mode_of_payment or "").strip()
    if not party:
        return failure("party is required.", code="VALIDATION_REQUIRED")
    if not mode_of_payment:
        return failure("mode_of_payment is required.", code="VALIDATION_REQUIRED")
    try:
        amount = float(paid_amount)
    except (TypeError, ValueError):
        return failure("paid_amount must be numeric.", code="VALIDATION_BAD_AMOUNT")
    if amount <= 0:
        return failure("paid_amount must be greater than zero.", code="VALIDATION_BAD_AMOUNT")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_sales_role(frappe)
    if permission_error:
        return permission_error

    invoice = (sales_invoice or "").strip()
    doc_data = {
        "doctype": "Payment Entry",
        "payment_type": "Receive",
        "party_type": "Customer",
        "party": party,
        "paid_amount": amount,
        "received_amount": amount,
        "mode_of_payment": mode_of_payment,
        "reference_no": reference_no,
        "reference_date": reference_date,
        "references": [
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": invoice,
                "allocated_amount": amount,
            }
        ] if invoice else [],
    }
    if company:
        doc_data["company"] = company
    return _insert_and_submit(doc_data)
