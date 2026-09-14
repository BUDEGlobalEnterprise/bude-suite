"""Grouped helpdesk.field_service endpoints: field_completion."""

from ._field_service_shared import *  # noqa: F401,F403

def complete_visit(
    ticket_name: str,
    work_done: str,
    completion_status: str = "Fully Completed",
    maintenance_type: str = "Unscheduled",
    resolve_ticket: bool = False,
) -> dict:
    """Record the visit outcome: internal note always, Maintenance Visit when
    the ticket resolves to an ERPNext Customer, optional ticket resolution."""
    denied = _guards(("Maintenance Visit", "FS_MAINTENANCE_NOT_INSTALLED"))
    if denied:
        return denied
    if not ticket_name or not work_done:
        return failure("ticket_name and work_done are required.", code="VALIDATION_REQUIRED")
    if completion_status not in COMPLETION_STATUSES:
        return failure(
            f"completion_status must be one of: {', '.join(sorted(COMPLETION_STATUSES))}",
            code="FS_COMPLETION_STATUS_INVALID",
        )
    if maintenance_type not in MAINTENANCE_TYPES:
        return failure(
            f"maintenance_type must be one of: {', '.join(sorted(MAINTENANCE_TYPES))}",
            code="FS_MAINTENANCE_TYPE_INVALID",
        )
    ticket, error = _job_ticket(ticket_name)
    if error:
        return error
    employee, error = _employee_or_failure()
    if error:
        return error

    visit_name = None
    visit_skipped_reason = None
    erpnext_customer = _erpnext_customer(ticket)
    try:
        comment = frappe.get_doc(
            {
                "doctype": "HD Ticket Comment",
                "reference_ticket": ticket_name,
                "content": f"Field visit ({completion_status}): {work_done}",
                "commented_by": _current_user(),
            }
        )
        comment.insert(ignore_permissions=True)

        if erpnext_customer:
            visit = frappe.get_doc(
                {
                    "doctype": "Maintenance Visit",
                    "customer": erpnext_customer,
                    "company": _default_company(employee),
                    "mntc_date": frappe.utils.today(),
                    "completion_status": completion_status,
                    "maintenance_type": maintenance_type,
                    "purposes": [
                        {
                            "service_person": _ensure_service_person(employee),
                            "work_done": work_done,
                            "description": ticket.get("subject") or ticket_name,
                        }
                    ],
                }
            )
            visit.insert(ignore_permissions=True)
            visit.flags.ignore_permissions = True
            visit.submit()
            visit_name = visit.name
        else:
            visit_skipped_reason = "NO_ERPNEXT_CUSTOMER"
        frappe.db.commit()
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(str(exc), code="VALIDATION_ERPNEXT")

    ticket_status = ticket.get("status") or ""
    if resolve_ticket in (True, 1, "1", "true", "True"):
        resolved = _set_ticket_status(ticket_name, "Resolved")
        if resolved.get("ok"):
            ticket_status = "Resolved"
    return success(
        {
            "comment": comment.name,
            "maintenance_visit": visit_name,
            "visit_skipped_reason": visit_skipped_reason,
            "ticket_status": ticket_status,
        }
    )
