"""Grouped helpdesk ticket endpoints: agents."""

from ._tickets_shared import *  # noqa: F401,F403

def assign_ticket(ticket_name: str, agent_email: str) -> dict:
    denied = require_helpdesk_agent_role(frappe)
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name or not agent_email:
        return failure("ticket_name and agent_email are required.", code="VALIDATION_REQUIRED")
    if not frappe.db.exists("HD Ticket", ticket_name):
        return failure("Ticket not found.", code="TICKET_NOT_FOUND")
    if not frappe.db.exists("User", agent_email):
        return failure("Agent user not found.", code="USER_NOT_FOUND")
    try:
        assign_add = frappe.get_attr("frappe.desk.form.assign_to.add")
        assign_add(
            {
                "doctype": "HD Ticket",
                "name": ticket_name,
                "assign_to": [agent_email],
            }
        )
        frappe.db.commit()
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(str(exc), code="VALIDATION_ERPNEXT")
    return success({"name": ticket_name, "assigned_to": agent_email})

def agents(team: str | None = None, search: str | None = None) -> dict:
    denied = require_helpdesk_agent_role(frappe)
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    role_rows = frappe.get_list(
        "Has Role",
        filters=[
            ["role", "in", list(HELPDESK_AGENT_ROLES)],
            ["parenttype", "=", "User"],
        ],
        fields=["parent"],
        limit_page_length=MAX_PAGE_LIMIT,
        ignore_permissions=True,
    )
    emails = sorted({row.get("parent") for row in role_rows if row.get("parent")})
    if not emails:
        return success([])
    filters = [["name", "in", emails], ["enabled", "=", 1]]
    if search:
        filters.append(["name", "like", f"%{search}%"])
    users = frappe.get_list(
        "User",
        filters=filters,
        fields=["name", "full_name", "email"],
        order_by="full_name asc",
        limit_page_length=MAX_PAGE_LIMIT,
        ignore_permissions=True,
    )
    result = []
    for user in users:
        email = user.get("email") or user.get("name") or ""
        teams = []
        if team:
            teams = [team]
        result.append(
            {
                "email": email,
                "full_name": user.get("full_name") or email,
                "teams": teams,
            }
        )
    return success(result)
