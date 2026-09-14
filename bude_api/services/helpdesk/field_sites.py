"""Grouped helpdesk.field_service endpoints: field_sites."""

from ._field_service_shared import *  # noqa: F401,F403

def job_site(ticket_name: str) -> dict:
    """Site contact/address plus the caller's visit log for one job."""
    denied = _guards()
    if denied:
        return denied
    if not ticket_name:
        return failure("ticket_name is required.", code="VALIDATION_REQUIRED")
    ticket, error = _job_ticket(ticket_name)
    if error:
        return error
    payload = _resolve_site(ticket)
    payload["ticket_name"] = str(ticket.get("name") or "")
    payload["visits"] = []
    payload["checked_in"] = False
    employee = None
    if frappe.db.exists("DocType", "Employee Checkin"):
        employee = _current_employee()
        if employee:
            visits = _my_visits(ticket_name, employee["name"])
            payload["visits"] = visits
            payload["checked_in"] = bool(visits) and visits[-1]["log_type"] == "IN"
    payload["has_employee"] = bool(employee)
    return success(payload)
