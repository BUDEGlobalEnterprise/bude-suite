"""Grouped helpdesk ticket endpoints: attachments."""

from ._tickets_shared import *  # noqa: F401,F403

def upload_ticket_attachment(ticket_name: str, file_name: str, content_base64: str) -> dict:
    denied = _require_login()
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    extension = (file_name or "").rsplit(".", 1)[-1].lower()
    if not file_name or "." not in file_name or extension not in ATTACHMENT_EXTENSIONS:
        return failure(
            "A file name ending in jpg, jpeg, png, webp, heic, pdf, txt, or log is required.",
            code="VALIDATION_REQUIRED",
        )
    if not content_base64 or len(content_base64) > MAX_ATTACHMENT_BASE64_LENGTH:
        return failure(
            "Attachment content is missing or larger than 5MB.",
            code="VALIDATION_REQUIRED",
        )
    try:
        base64.b64decode(content_base64, validate=True)
    except Exception:
        return failure("Attachment content must be valid base64.", code="VALIDATION_REQUIRED")
    ticket, error = _visible_ticket(ticket_name)
    if error:
        return error
    try:
        doc = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": file_name,
                "attached_to_doctype": "HD Ticket",
                "attached_to_name": ticket["name"],
                "is_private": 1,
                "content": content_base64,
                "decode": True,
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
    return success({"name": doc.name, "file_url": doc.get("file_url") or ""})
