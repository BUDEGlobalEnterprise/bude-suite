"""Grouped helpdesk ticket endpoints: comments."""

from ._tickets_shared import *  # noqa: F401,F403

def reply(ticket_name: str, content: str) -> dict:
    denied = _require_login()
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name or not content:
        return failure("ticket_name and content are required.", code="VALIDATION_REQUIRED")
    ticket, error = _visible_ticket(ticket_name)
    if error:
        return error
    user = _current_user()
    is_requester = (ticket.get("raised_by") or "") == user
    try:
        doc = frappe.get_doc(
            {
                "doctype": "Communication",
                "communication_type": "Communication",
                "reference_doctype": "HD Ticket",
                "reference_name": ticket_name,
                "subject": f"Re: {ticket.get('subject') or ticket_name}",
                "content": content,
                "sender": user,
                "sent_or_received": "Received" if is_requester else "Sent",
                "status": "Linked",
            }
        )
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(str(exc), code="VALIDATION_ERPNEXT")
    return success({"name": doc.name})

def add_comment(ticket_name: str, content: str) -> dict:
    """Internal agent note (HD Ticket Comment) — never visible to requesters."""
    denied = require_helpdesk_agent_role(frappe)
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name or not content:
        return failure("ticket_name and content are required.", code="VALIDATION_REQUIRED")
    if not frappe.db.exists("HD Ticket", ticket_name):
        return failure("Ticket not found.", code="TICKET_NOT_FOUND")
    try:
        doc = frappe.get_doc(
            {
                "doctype": "HD Ticket Comment",
                "reference_ticket": ticket_name,
                "content": content,
                "commented_by": _current_user(),
            }
        )
        doc.insert(ignore_permissions=False)
        frappe.db.commit()
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(str(exc), code="VALIDATION_ERPNEXT")
    return success({"name": doc.name})
