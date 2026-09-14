"""Signed customer quotation responses and standard Payment Requests."""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

from ...utils.response import failure, success
from ..common.permissions import has_any_role, permission_denied, require_sales_role

FINANCIAL_ROLES = {"Accounts User", "Accounts Manager", "Sales Manager", "System Manager"}


def create_response_link(frappe_module, quotation: str, valid_days=14) -> dict:
    denied = require_sales_role(frappe_module)
    if denied:
        return denied
    quotation = str(quotation or "").strip()
    if not quotation or not _permitted(frappe_module, "Quotation", quotation, "read"):
        return failure("Quotation not found or not permitted.", code="NOT_FOUND")
    secret = _secret(frappe_module)
    if not secret:
        return failure(
            "Configure bude_sales_quote_response_secret before sharing response links.",
            code="QUOTE_RESPONSE_NOT_CONFIGURED",
        )
    try:
        days = min(max(int(valid_days), 1), 30)
    except (TypeError, ValueError):
        return failure("valid_days must be between 1 and 30.", code="VALIDATION_DAYS")
    expires = int(time.time()) + days * 86400
    signature = _signature(secret, quotation, expires)
    base = str(frappe_module.utils.get_url()).rstrip("/")
    query = urlencode({"quotation": quotation, "expires": expires, "signature": signature})
    return success(
        {
            "quotation": quotation,
            "expires": expires,
            "url": f"{base}/bude-quotation-response?{query}",
        }
    )


def response_context(frappe_module, quotation, expires, signature) -> dict:
    error = _verify(frappe_module, quotation, expires, signature)
    if error:
        return error
    try:
        row = frappe_module.db.get_value(
            "Quotation",
            quotation,
            ["name", "customer_name", "party_name", "currency", "grand_total", "valid_till", "status"],
            as_dict=True,
        ) or {}
    except Exception:
        row = {}
    if not row:
        return failure("Quotation not found.", code="NOT_FOUND")
    return success(
        {
            "quotation": row.get("name") or quotation,
            "customer": row.get("customer_name") or row.get("party_name") or "",
            "currency": row.get("currency") or "",
            "grand_total": float(row.get("grand_total") or 0),
            "valid_till": str(row.get("valid_till") or ""),
            "status": row.get("status") or "Open",
        }
    )


def submit_response(frappe_module, quotation, action, expires, signature, notes=None) -> dict:
    error = _verify(frappe_module, quotation, expires, signature)
    if error:
        return error
    action = str(action or "").strip().lower()
    if action not in {"accept", "reject"}:
        return failure("action must be accept or reject.", code="VALIDATION_ACTION")
    marker = "ACCEPTED" if action == "accept" else "REJECTED"
    prefix = f"[BUDE QUOTATION RESPONSE] {marker}"
    try:
        existing = frappe_module.get_list(
            "Comment",
            filters=[
                ["reference_doctype", "=", "Quotation"],
                ["reference_name", "=", quotation],
                ["content", "like", f"{prefix}%"],
            ],
            fields=["name", "creation"],
            order_by="creation desc",
            limit_page_length=1,
        )
    except Exception:
        existing = []
    if existing:
        return success({"quotation": quotation, "response": marker.lower(), "duplicate": True})
    content = prefix
    clean_notes = str(notes or "").strip()[:1000]
    if clean_notes:
        content = f"{content}\n{clean_notes}"
    try:
        comment = frappe_module.get_doc(
            {
                "doctype": "Comment",
                "comment_type": "Comment",
                "reference_doctype": "Quotation",
                "reference_name": quotation,
                "content": content,
                "comment_email": "customer-response@bude.local",
                "comment_by": "Customer response link",
            }
        )
        comment.insert(ignore_permissions=True)
        _notify_owner(frappe_module, quotation, marker)
        frappe_module.db.commit()
    except Exception:
        try:
            frappe_module.db.rollback()
        except Exception:
            pass
        return failure("Response could not be saved. Please contact the sales representative.", code="QUOTE_RESPONSE_FAILED")
    return success({"quotation": quotation, "response": marker.lower()})


def response_status(frappe_module, quotation) -> dict:
    denied = require_sales_role(frappe_module)
    if denied:
        return denied
    try:
        rows = frappe_module.get_list(
            "Comment",
            filters=[
                ["reference_doctype", "=", "Quotation"],
                ["reference_name", "=", quotation],
                ["content", "like", "[BUDE QUOTATION RESPONSE]%"],
            ],
            fields=["content", "creation"],
            order_by="creation desc",
            limit_page_length=1,
        )
    except Exception:
        rows = []
    content = str(rows[0].get("content") or "") if rows else ""
    status = "accepted" if "ACCEPTED" in content else "rejected" if "REJECTED" in content else "pending"
    return success({"quotation": quotation, "response": status, "responded_at": str(rows[0].get("creation") or "") if rows else ""})


def create_payment_request(frappe_module, reference_doctype, reference_name) -> dict:
    denied = require_sales_role(frappe_module)
    if denied:
        return denied
    if not has_any_role(frappe_module, FINANCIAL_ROLES):
        return permission_denied("Accounts or Sales Manager access is required.")
    if reference_doctype not in {"Sales Order", "Sales Invoice"}:
        return failure("Payment Requests support Sales Orders and Sales Invoices.", code="VALIDATION_REFERENCE")
    if not _permitted(frappe_module, reference_doctype, reference_name, "read"):
        return failure("Document not found or not permitted.", code="NOT_FOUND")
    try:
        maker = frappe_module.get_attr(
            "erpnext.accounts.doctype.payment_request.payment_request.make_payment_request"
        )
        result = maker(
            dt=reference_doctype,
            dn=reference_name,
            submit_doc=1,
            return_doc=1,
        )
        name = getattr(result, "name", None) or (result.get("name") if isinstance(result, dict) else "")
        url = getattr(result, "payment_url", None) or (result.get("payment_url") if isinstance(result, dict) else "")
    except Exception as exc:
        return failure(str(exc) or "Payment Request could not be created.", code="PAYMENT_REQUEST_FAILED")
    return success({"name": name or "", "payment_url": url or "", "reference": reference_name})


def _verify(frappe_module, quotation, expires, signature):
    secret = _secret(frappe_module)
    try:
        expires_value = int(expires)
    except (TypeError, ValueError):
        return failure("Invalid response link.", code="INVALID_SIGNATURE")
    expected = _signature(secret, str(quotation or ""), expires_value) if secret else ""
    if not expected or not hmac.compare_digest(expected, str(signature or "")):
        return failure("Invalid response link.", code="INVALID_SIGNATURE")
    if expires_value < int(time.time()):
        return failure("This response link has expired.", code="LINK_EXPIRED")
    return None


def _signature(secret, quotation, expires):
    return hmac.new(secret.encode(), f"{quotation}:{expires}".encode(), hashlib.sha256).hexdigest()


def _secret(frappe_module):
    try:
        value = frappe_module.conf.get("bude_sales_quote_response_secret")
        return value.strip() if isinstance(value, str) else ""
    except Exception:
        return ""


def _permitted(frappe_module, doctype, name, permission):
    try:
        return bool(frappe_module.has_permission(doctype, ptype=permission, doc=name))
    except Exception:
        return False


def _notify_owner(frappe_module, quotation, response):
    owner = frappe_module.db.get_value("Quotation", quotation, "owner")
    if not owner:
        return
    log = frappe_module.get_doc(
        {
            "doctype": "Notification Log",
            "for_user": owner,
            "type": "Alert",
            "document_type": "Quotation",
            "document_name": quotation,
            "subject": f"Customer {response.lower()} quotation {quotation}",
            "email_content": f"Customer response recorded: {response}.",
        }
    )
    log.insert(ignore_permissions=True)
