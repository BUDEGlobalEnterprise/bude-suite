"""Grouped helpdesk ticket endpoints: masters."""

from ._tickets_shared import *  # noqa: F401,F403

def masters() -> dict:
    """Pickers for the ticket form: types, priorities, statuses, teams."""
    denied = _require_login()
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    ticket_types = frappe.get_list(
        "HD Ticket Type",
        filters=[["disabled", "=", 0]],
        fields=["name"],
        limit_page_length=MAX_PAGE_LIMIT,
        ignore_permissions=True,
    )
    priorities = frappe.get_list(
        "HD Ticket Priority",
        filters=[["disabled", "=", 0]],
        fields=["name", "integer_value"],
        order_by="integer_value desc",
        limit_page_length=MAX_PAGE_LIMIT,
        ignore_permissions=True,
    )
    statuses = frappe.get_list(
        "HD Ticket Status",
        filters=[["enabled", "=", 1]],
        fields=["name", "label_agent", "category"],
        limit_page_length=MAX_PAGE_LIMIT,
        ignore_permissions=True,
    )
    teams = frappe.get_list(
        "HD Team",
        filters=[["disabled", "=", 0]],
        fields=["name"],
        limit_page_length=MAX_PAGE_LIMIT,
        ignore_permissions=True,
    )
    return success(
        {
            "ticket_types": [row.get("name") for row in ticket_types],
            "priorities": [
                {"name": row.get("name"), "level": row.get("integer_value") or 0}
                for row in priorities
            ],
            "statuses": [
                {
                    "name": row.get("name"),
                    "label": row.get("label_agent") or row.get("name"),
                    "category": row.get("category") or "",
                }
                for row in statuses
            ],
            "teams": [row.get("name") for row in teams],
            "is_agent": _is_agent(),
        }
    )
