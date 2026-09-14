"""Grouped mobile endpoints: documents."""

import json

from ._mobile_shared import *  # noqa: F401,F403

def create_quotation(
    customer: str,
    items: list,
    valid_till: str | None = None,
    price_list: str | None = None,
    company: str | None = None,
    client_request_id: str | None = None,
) -> dict:
    denied = require_sales_role(frappe)
    if denied:
        return denied
    error = _validate_customer_items(customer, items)
    if error:
        return error
    return _idempotent_sales(
        "quotation",
        client_request_id,
        lambda: _insert_doc(_selling_doc("Quotation", customer, items, company=company, price_list=price_list, valid_till=valid_till)),
    )

def create_order(
    customer: str,
    items: list,
    delivery_date: str | None = None,
    price_list: str | None = None,
    company: str | None = None,
    submit: bool = False,
    client_request_id: str | None = None,
) -> dict:
    denied = require_sales_role(frappe)
    if denied:
        return denied
    error = _validate_customer_items(customer, items)
    if error:
        return error
    doc_data = _selling_doc("Sales Order", customer, items, company=company, price_list=price_list, delivery_date=delivery_date)
    return _idempotent_sales(
        "sales_order",
        client_request_id,
        lambda: _insert_and_maybe_submit(doc_data, submit),
    )

def create_invoice(
    customer: str,
    items: list,
    sales_order: str | None = None,
    company: str | None = None,
    submit: bool = True,
    client_request_id: str | None = None,
) -> dict:
    denied = _require_accounts_or_manager()
    if denied:
        return denied
    error = _validate_customer_items(customer, items)
    if error:
        return error
    doc_data = _selling_doc("Sales Invoice", customer, items, company=company, sales_order=sales_order)
    return _idempotent_sales(
        "sales_invoice",
        client_request_id,
        lambda: _insert_and_maybe_submit(doc_data, submit in (True, 1, "1", "true", "True")),
    )

def record_payment(
    customer: str,
    amount,
    mode_of_payment: str,
    reference_no: str | None = None,
    reference_date: str | None = None,
    invoice: str | None = None,
    company: str | None = None,
    client_request_id: str | None = None,
) -> dict:
    denied = _require_accounts_or_manager()
    if denied:
        return denied
    try:
        paid_amount = float(amount)
    except (TypeError, ValueError):
        return failure("amount must be numeric.", code="VALIDATION_BAD_AMOUNT")
    if paid_amount <= 0:
        return failure("amount must be greater than zero.", code="VALIDATION_BAD_AMOUNT")
    customer = (customer or "").strip()
    mode_of_payment = (mode_of_payment or "").strip()
    if not customer or not mode_of_payment:
        return failure("customer and mode_of_payment are required.", code="VALIDATION_REQUIRED")
    doc_data = {
        "doctype": "Payment Entry",
        "payment_type": "Receive",
        "party_type": "Customer",
        "party": customer,
        "paid_amount": paid_amount,
        "received_amount": paid_amount,
        "mode_of_payment": mode_of_payment,
        "reference_no": reference_no,
        "reference_date": reference_date,
        "references": [
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": invoice,
                "allocated_amount": paid_amount,
            }
        ]
        if invoice
        else [],
    }
    if company:
        doc_data["company"] = company
    return _idempotent_sales(
        "payment",
        client_request_id,
        lambda: _insert_and_maybe_submit(doc_data, True),
    )


def commercial_preview(
    customer: str,
    items: list,
    price_list: str | None = None,
    company: str | None = None,
) -> dict:
    denied = require_sales_role(frappe)
    if denied:
        return denied
    error = _validate_customer_items(customer, items)
    if error:
        return error
    values = _selling_doc(
        "Sales Order",
        customer,
        items,
        company=company,
        price_list=price_list,
    )
    try:
        doc = frappe.get_doc(values)
        for method in ("set_missing_values", "calculate_taxes_and_totals"):
            try:
                doc.run_method(method)
            except Exception:
                callable_method = getattr(doc, method, None)
                if callable(callable_method):
                    callable_method()
        raw = doc.as_dict() if callable(getattr(doc, "as_dict", None)) else values
    except Exception as exc:
        return failure(_erpnext_message(exc), code="VALIDATION_ERPNEXT")
    net_total = float(raw.get("net_total") or raw.get("total") or 0)
    grand_total = float(raw.get("grand_total") or net_total)
    outstanding = float(_outstanding(customer) or 0)
    credit_limits = _customer_credit_limits(customer)
    company_limit = next(
        (
            float(row.get("credit_limit") or 0)
            for row in credit_limits
            if not company or row.get("company") == company
        ),
        0,
    )
    bypass = any(
        bool(row.get("bypass_credit_limit_check"))
        for row in credit_limits
        if not company or row.get("company") == company
    )
    projected = outstanding + grand_total
    return success(
        {
            "currency": raw.get("currency") or "",
            "net_total": net_total,
            "tax_total": float(raw.get("total_taxes_and_charges") or (grand_total - net_total)),
            "grand_total": grand_total,
            "items": [
                {
                    "item_code": row.get("item_code") or "",
                    "item_name": row.get("item_name") or "",
                    "qty": float(row.get("qty") or 0),
                    "uom": row.get("uom") or row.get("stock_uom") or "",
                    "conversion_factor": float(row.get("conversion_factor") or 1),
                    "rate": float(row.get("rate") or 0),
                    "amount": float(row.get("amount") or 0),
                }
                for row in (raw.get("items") or [])
            ],
            "taxes": [
                {
                    "description": row.get("description") or row.get("account_head") or "Tax",
                    "rate": float(row.get("rate") or 0),
                    "amount": float(row.get("tax_amount") or 0),
                }
                for row in (raw.get("taxes") or [])
            ],
            "credit": {
                "outstanding": outstanding,
                "credit_limit": company_limit,
                "projected_outstanding": projected,
                "bypass": bypass,
                "within_limit": bypass or company_limit <= 0 or projected <= company_limit,
            },
        }
    )


def _idempotent_sales(action_name, request_id, action):
    request_id = str(request_id or "").strip()
    if request_id:
        try:
            rows = frappe.get_list(
                "Integration Request",
                filters=[
                    ["integration_request_service", "=", f"bude_sales:{action_name}"],
                    ["request_id", "=", request_id],
                ],
                fields=["output"],
                limit_page_length=1,
            )
        except Exception:
            rows = []
        if rows:
            try:
                return success(json.loads(rows[0].get("output") or "{}"))
            except (TypeError, ValueError):
                pass
    result = action()
    if not isinstance(result, dict) or result.get("ok") is not True:
        return result
    if request_id:
        try:
            log = frappe.get_doc(
                {
                    "doctype": "Integration Request",
                    "integration_request_service": f"bude_sales:{action_name}",
                    "status": "Completed",
                    "request_id": request_id,
                    "request_description": action_name,
                    "output": json.dumps(result.get("data") or {}, default=str),
                }
            )
            log.insert(ignore_permissions=True)
        except Exception:
            pass
    return result
