"""Grouped mobile endpoints: requests."""

from ._mobile_shared import *  # noqa: F401,F403

def travel_requests(limit: int = 50) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Travel Request")
    if missing:
        return missing
    rows = frappe.get_list(
        "Travel Request",
        filters=[["employee", "=", employee["name"]]],
        fields=[
            "name",
            "travel_type",
            "travel_funding",
            "purpose_of_travel",
            "description",
            "docstatus",
            "creation",
        ],
        order_by="creation desc",
        limit_page_length=max(1, min(int(limit), 100)),
    )
    return success(
        [
            {
                "name": row.get("name"),
                "travel_type": row.get("travel_type") or "",
                "travel_funding": row.get("travel_funding") or "",
                "purpose": row.get("purpose_of_travel") or "",
                "description": row.get("description") or "",
                "docstatus": int(row.get("docstatus") or 0),
                "creation": str(row.get("creation") or ""),
            }
            for row in rows
        ]
    )

def apply_travel_request(
    travel_type: str,
    purpose: str,
    description: str | None = None,
    travel_funding: str | None = None,
) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Travel Request")
    if missing:
        return missing
    if not travel_type or not purpose:
        return failure("travel_type and purpose are required.", code="VALIDATION_REQUIRED")
    try:
        doc = frappe.get_doc(
            {
                "doctype": "Travel Request",
                "employee": employee["name"],
                "employee_name": employee.get("employee_name"),
                "company": employee.get("company"),
                "travel_type": travel_type,
                "travel_funding": travel_funding,
                "purpose_of_travel": purpose,
                "description": description,
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

def todo_requests(limit: int = 50, offset: int = 0) -> dict:
    denied = _require_hr_role()
    if denied:
        return denied
    page_limit, page_offset = _page(limit, offset)
    user = _current_user()
    rows = frappe.get_list(
        "ToDo",
        filters=[["allocated_to", "=", user], ["reference_type", "=", "Employee"]],
        fields=["name", "description", "status", "priority", "date", "creation"],
        order_by="creation desc",
        limit_start=page_offset,
        limit_page_length=page_limit,
    )
    return success(
        [
            {
                "name": row.get("name"),
                "subject": row.get("description") or "",
                "status": row.get("status") or "",
                "priority": row.get("priority") or "",
                "date": str(row.get("date") or ""),
                "creation": str(row.get("creation") or ""),
            }
            for row in rows
        ]
    )

def submit_todo_request(
    subject: str, description: str | None = None, priority: str = "Medium"
) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    if not subject:
        return failure("subject is required.", code="VALIDATION_REQUIRED")
    user = _current_user()
    try:
        doc = frappe.get_doc(
            {
                "doctype": "ToDo",
                "allocated_to": user,
                "reference_type": "Employee",
                "reference_name": employee["name"],
                "description": "\n".join([subject, description or ""]).strip(),
                "priority": priority or "Medium",
                "status": "Open",
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
    return success({"name": doc.name, "status": doc.get("status")})

def grievances(limit: int = 50) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Employee Grievance")
    if missing:
        return missing
    rows = frappe.get_list(
        "Employee Grievance",
        filters=[["raised_by", "=", employee["name"]]],
        fields=["name", "subject", "date", "status", "grievance_type", "description"],
        order_by="date desc",
        limit_page_length=max(1, min(int(limit), 100)),
    )
    return success(
        [
            {
                "name": row.get("name"),
                "subject": row.get("subject") or "",
                "date": str(row.get("date") or ""),
                "status": row.get("status") or "",
                "grievance_type": row.get("grievance_type") or "",
                "description": row.get("description") or "",
            }
            for row in rows
        ]
    )

def submit_grievance(
    subject: str,
    description: str,
    grievance_type: str | None = None,
    grievance_against_party: str | None = None,
    grievance_against: str | None = None,
) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Employee Grievance")
    if missing:
        return missing
    if not subject or not description:
        return failure("subject and description are required.", code="VALIDATION_REQUIRED")
    try:
        resolved_type = grievance_type or _default_grievance_type()
        against_party = grievance_against_party or "Company"
        against = grievance_against or employee.get("company")
        doc = frappe.get_doc(
            {
                "doctype": "Employee Grievance",
                "subject": subject,
                "raised_by": employee["name"],
                "employee_name": employee.get("employee_name"),
                "designation": employee.get("designation"),
                "date": frappe.utils.today(),
                "status": "Open",
                "grievance_against_party": against_party,
                "grievance_against": against,
                "grievance_type": resolved_type,
                "description": description,
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
    return success({"name": doc.name, "status": doc.get("status")})
