"""Helpdesk (ITSM) endpoints for the Bude Helpdesk Flutter app.

All persistence uses the Frappe Helpdesk app's standard DocTypes (HD Ticket,
HD Ticket Comment, Communication, File) plus core DocTypes. No custom
DocTypes and no frappe/helpdesk core modifications.

Requester endpoints mirror Helpdesk's own customer portal: identity is the
session user, every query is scoped by ``raised_by``, and portal-style writes
use ``ignore_permissions=True`` exactly as upstream's portal API does — so a
requester does not need the "HD Customer" role pre-assigned. Agent endpoints
are gated by the Agent / Agent Manager roles and use standard permissions.

Ticket status transitions on reply are handled by Helpdesk itself: frappe
core invokes ``HDTicket.on_communication_update`` when a linked Communication
is inserted, which reopens on customer reply and marks "Replied" on agent
reply.
"""

import base64

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.pagination import parse_page

from ...utils.response import failure, success

from ..common.permissions import HELPDESK_AGENT_ROLES, has_any_role, require_helpdesk_agent_role

DEFAULT_PAGE_LIMIT = 20

MAX_PAGE_LIMIT = 100

MAX_CONVERSATION_ROWS = 200

SUPPORT_PULSE_SCAN_LIMIT = 500

MAX_ATTACHMENT_BASE64_LENGTH = 7_000_000

ATTACHMENT_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "heic", "pdf", "txt", "log"}

DEFAULT_OPEN_STATUS = "Open"

DEFAULT_CLOSED_STATUS = "Closed"

TICKET_LIST_FIELDS = [
    "name",
    "subject",
    "status",
    "priority",
    "ticket_type",
    "agent_group",
    "raised_by",
    "response_by",
    "resolution_by",
    "agreement_status",
    "customer",
    "contact",
    "via_customer_portal",
    "first_responded_on",
    "opening_date",
    "resolution_date",
    "creation",
    "modified",
]

ATTACHMENT_FIELDS = ["name", "file_name", "file_url", "is_private", "creation"]


def _whitelist(methods=None, allow_guest: bool = False):
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=methods or ["GET", "POST"])


def _current_user() -> str | None:
    return getattr(getattr(frappe, "session", None), "user", None)


def _require_login() -> dict | None:
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    user = _current_user()
    if not user or user == "Guest":
        return failure("Your session has expired. Please sign in again.", code="AUTH_EXPIRED")
    return None


def _require_helpdesk() -> dict | None:
    """Return a JSON failure when the Frappe Helpdesk app is not installed."""
    if not frappe.db.exists("DocType", "HD Ticket"):
        return failure(
            "The Frappe Helpdesk app is not installed on this site. Install it "
            "before using helpdesk features.",
            code="HELPDESK_NOT_INSTALLED",
            data={"doctype": "HD Ticket"},
        )
    return None


def _is_agent() -> bool:
    return has_any_role(frappe, HELPDESK_AGENT_ROLES)


def _ticket_fields(*extra: str) -> list[str]:
    """Return HD Ticket fields supported by the installed Helpdesk version."""
    fields = [*TICKET_LIST_FIELDS, *extra]
    try:
        meta = frappe.get_meta("HD Ticket")
        has_field = getattr(meta, "has_field", None)
        if callable(has_field):
            return [field for field in fields if field == "name" or has_field(field)]
    except Exception:
        pass
    # Description is part of every supported HD Ticket detail schema. Other
    # extras are optional and must not break the primary screen when metadata
    # cannot confirm that the installed version supports them.
    return [
        field
        for field in fields
        if field in TICKET_LIST_FIELDS or field == "description"
    ]


def _serialize_ticket(row: dict) -> dict:
    return {
        "name": str(row.get("name") or ""),
        "subject": row.get("subject") or "",
        "status": row.get("status") or "",
        "priority": row.get("priority") or "",
        "ticket_type": row.get("ticket_type") or "",
        "team": row.get("agent_group") or "",
        "raised_by": row.get("raised_by") or "",
        "response_by": str(row.get("response_by") or ""),
        "resolution_by": str(row.get("resolution_by") or ""),
        "agreement_status": row.get("agreement_status") or "",
        "customer": row.get("customer") or "",
        "contact": row.get("contact") or "",
        "via_customer_portal": bool(row.get("via_customer_portal")),
        "first_responded_on": str(row.get("first_responded_on") or ""),
        "opening_date": str(row.get("opening_date") or ""),
        "resolution_date": str(row.get("resolution_date") or ""),
        "resolution_details": row.get("resolution_details") or "",
        "feedback": row.get("feedback") or "",
        "feedback_rating": float(row.get("feedback_rating") or 0),
        "creation": str(row.get("creation") or ""),
        "modified": str(row.get("modified") or ""),
    }


def _add_optional_ticket_filters(
    filters: list,
    *,
    priority: str | None = None,
    ticket_type: str | None = None,
    team: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    unassigned: bool = False,
) -> None:
    if priority:
        filters.append(["priority", "=", priority])
    if ticket_type:
        filters.append(["ticket_type", "=", ticket_type])
    if team:
        filters.append(["agent_group", "=", team])
    if from_date:
        filters.append(["creation", ">=", from_date])
    if to_date:
        filters.append(["creation", "<=", to_date])
    if unassigned in (True, 1, "1", "true", "True"):
        filters.append(["_assign", "in", ["", "[]"]])


def _ticket_search_or_filters(
    search: str | None, *, include_requester: bool = False
) -> list | None:
    if not search:
        return None
    needle = f"%{search}%"
    fields = ["name", "subject"]
    if include_requester:
        fields.append("raised_by")
    return [[field, "like", needle] for field in fields]


def _ticket_attachments(ticket_name: str) -> list[dict]:
    rows = frappe.get_list(
        "File",
        filters=[
            ["attached_to_doctype", "=", "HD Ticket"],
            ["attached_to_name", "=", ticket_name],
        ],
        fields=ATTACHMENT_FIELDS,
        order_by="creation asc",
        limit_page_length=MAX_CONVERSATION_ROWS,
        ignore_permissions=True,
    )
    return [
        {
            "name": str(row.get("name") or ""),
            "file_name": row.get("file_name") or "",
            "file_url": row.get("file_url") or "",
            "is_private": bool(row.get("is_private")),
            "creation": str(row.get("creation") or ""),
        }
        for row in rows
    ]


def _visible_ticket(ticket_name: str) -> tuple[dict | None, dict | None]:
    """Fetch a ticket the caller may see: their own, or any if agent.

    Foreign tickets return TICKET_NOT_FOUND (not PERMISSION_DENIED) so
    requesters cannot probe other users' ticket names.
    """
    filters = [["name", "=", ticket_name]]
    if not _is_agent():
        filters.append(["raised_by", "=", _current_user()])
    rows = frappe.get_list(
        "HD Ticket",
        filters=filters,
        fields=_ticket_fields(
            "description",
            "resolution_details",
            "feedback",
            "feedback_rating",
            "sla",
            "raised_outside_working_hours",
            "on_hold_since",
            "total_hold_time",
            "template",
        ),
        limit_page_length=1,
        ignore_permissions=True,
    )
    if not rows:
        return None, failure("Ticket not found.", code="TICKET_NOT_FOUND")
    return rows[0], None


def _set_ticket_status(ticket_name: str, status: str) -> dict:
    ticket, error = _visible_ticket(ticket_name)
    if error:
        return error
    try:
        doc = frappe.get_doc("HD Ticket", ticket["name"])
        doc.status = status
        # save (not db.set_value) so helpdesk's SLA/activity controller runs
        doc.save(ignore_permissions=True)
        frappe.db.commit()
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(str(exc), code="VALIDATION_ERPNEXT")
    return success({"name": ticket["name"], "status": status})


__all__ = [name for name in globals() if not name.startswith("__")]
