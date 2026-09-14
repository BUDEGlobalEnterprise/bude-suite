"""Field-service technician endpoints layered on the helpdesk module.

A field job is an HD Ticket assigned to a technician (an Agent). This module
adds the on-site execution pieces using only standard DocTypes:

- site/contact resolution:  HD Ticket -> Contact -> Address, with a
  best-effort fallback through HD Customer.erpnext_customer -> Address.
- geo check-in / check-out: HRMS ``Employee Checkin`` tagged with the ticket
  in ``device_id`` and ``skip_auto_attendance=1`` so site visits never
  disturb shift attendance.
- visit report:             ERPNext ``Maintenance Visit`` (submitted) when an
  ERPNext Customer is resolvable, always paired with an internal
  HD Ticket Comment carrying the work summary.

Writes are portal-style (``ignore_permissions=True``) behind our own agent
role gate, for the same reason documented in ``helpdesk.py``: the underlying
doctypes' role models (Maintenance User, HR) do not match helpdesk agents.
"""

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success

from .tickets import _require_helpdesk, _set_ticket_status

from ..common.permissions import require_helpdesk_agent_role

MAX_VISIT_ROWS = 50

COMPLETION_STATUSES = {"Partially Completed", "Fully Completed"}

MAINTENANCE_TYPES = {"Scheduled", "Unscheduled", "Breakdown"}

SERVICE_PERSON_GROUP = "Field Service"

def _whitelist(methods=None, allow_guest: bool = False):
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=methods or ["GET", "POST"])

def _current_user() -> str | None:
    return getattr(getattr(frappe, "session", None), "user", None)

def _require_doctype(doctype: str, code: str) -> dict | None:
    if not frappe.db.exists("DocType", doctype):
        return failure(
            f"The '{doctype}' DocType is not available on this site.",
            code=code,
            data={"doctype": doctype},
        )
    return None

def _guards(*doctypes_with_codes: tuple[str, str]) -> dict | None:
    denied = require_helpdesk_agent_role(frappe)
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    for doctype, code in doctypes_with_codes:
        missing = _require_doctype(doctype, code)
        if missing:
            return missing
    return None

def _current_employee() -> dict | None:
    rows = frappe.get_list(
        "Employee",
        filters=[["user_id", "=", _current_user()], ["status", "=", "Active"]],
        fields=["name", "employee_name", "company"],
        limit_page_length=1,
        ignore_permissions=True,
    )
    return rows[0] if rows else None

def _employee_or_failure() -> tuple[dict | None, dict | None]:
    employee = _current_employee()
    if not employee:
        return None, failure(
            "No active Employee record is linked to this user. Field-service "
            "check-in and visit reports require one.",
            code="FS_EMPLOYEE_REQUIRED",
        )
    return employee, None

def _job_ticket(ticket_name: str) -> tuple[dict | None, dict | None]:
    rows = frappe.get_list(
        "HD Ticket",
        filters=[["name", "=", ticket_name]],
        fields=["name", "subject", "status", "contact", "customer", "raised_by"],
        limit_page_length=1,
        ignore_permissions=True,
    )
    if not rows:
        return None, failure("Ticket not found.", code="TICKET_NOT_FOUND")
    return rows[0], None

def _device_tag(ticket_name: str) -> str:
    return f"HD Ticket {ticket_name}"

def _address_display(address_name: str) -> str:
    if not address_name:
        return ""
    try:
        render = frappe.get_attr("frappe.contacts.doctype.address.address.get_address_display")
        return render(address_name) or ""
    except Exception:
        return ""

def _resolve_site(ticket: dict) -> dict:
    """Best-effort contact + address for the job site."""
    contact_info: dict = {}
    address_name = ""
    contact_name = ticket.get("contact") or ""
    if contact_name and frappe.db.exists("Contact", contact_name):
        contact = frappe.get_list(
            "Contact",
            filters=[["name", "=", contact_name]],
            fields=["name", "full_name", "mobile_no", "phone", "email_id", "address"],
            limit_page_length=1,
            ignore_permissions=True,
        )
        if contact:
            row = contact[0]
            contact_info = {
                "name": str(row.get("name") or ""),
                "full_name": row.get("full_name") or "",
                "phone": row.get("mobile_no") or row.get("phone") or "",
                "email": row.get("email_id") or "",
            }
            address_name = row.get("address") or ""
    erpnext_customer = _erpnext_customer(ticket)
    if not address_name and erpnext_customer:
        # Dynamic Link is a child DocType. Frappe v16's get_list() strips the
        # requested parent field, so use the direct child-table reader after
        # constraining the query to this already-resolved customer.
        linked = frappe.get_all(
            "Dynamic Link",
            filters=[
                ["link_doctype", "=", "Customer"],
                ["link_name", "=", erpnext_customer],
                ["parenttype", "=", "Address"],
            ],
            fields=["parent"],
            limit_page_length=1,
        )
        if linked:
            address_name = linked[0].get("parent") or ""
    return {
        "contact": contact_info,
        "address": _address_display(address_name),
        "customer": ticket.get("customer") or "",
        "erpnext_customer": erpnext_customer,
    }

def _erpnext_customer(ticket: dict) -> str:
    hd_customer = ticket.get("customer") or ""
    if not hd_customer:
        return ""
    value = frappe.db.get_value("HD Customer", hd_customer, "erpnext_customer") or ""
    # erpnext_customer is a plain Data field, so verify it still points at a Customer
    if value and frappe.db.exists("Customer", value):
        return str(value)
    return ""

def _my_visits(ticket_name: str, employee_name: str) -> list[dict]:
    rows = frappe.get_list(
        "Employee Checkin",
        filters=[
            ["employee", "=", employee_name],
            ["device_id", "=", _device_tag(ticket_name)],
        ],
        fields=["name", "log_type", "time", "latitude", "longitude"],
        order_by="time asc",
        limit_page_length=MAX_VISIT_ROWS,
        ignore_permissions=True,
    )
    return [
        {
            "name": str(row.get("name") or ""),
            "log_type": row.get("log_type") or "",
            "time": str(row.get("time") or ""),
            "latitude": float(row.get("latitude") or 0) or None,
            "longitude": float(row.get("longitude") or 0) or None,
        }
        for row in rows
    ]

def _insert_checkin(ticket_name: str, employee: dict, log_type: str, latitude, longitude) -> dict:
    record = {
        "doctype": "Employee Checkin",
        "employee": employee["name"],
        "log_type": log_type,
        "time": frappe.utils.now_datetime(),
        "device_id": _device_tag(ticket_name),
        "skip_auto_attendance": 1,
    }
    if latitude is not None and longitude is not None:
        try:
            record["latitude"] = float(latitude)
            record["longitude"] = float(longitude)
        except (TypeError, ValueError):
            pass
    doc = frappe.get_doc(record)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc

def _visit_toggle(ticket_name: str, log_type: str, latitude, longitude) -> dict:
    denied = _guards(("Employee Checkin", "FS_HRMS_NOT_INSTALLED"))
    if denied:
        return denied
    if not ticket_name:
        return failure("ticket_name is required.", code="VALIDATION_REQUIRED")
    ticket, error = _job_ticket(ticket_name)
    if error:
        return error
    employee, error = _employee_or_failure()
    if error:
        return error
    visits = _my_visits(ticket_name, employee["name"])
    on_site = bool(visits) and visits[-1]["log_type"] == "IN"
    if log_type == "IN" and on_site:
        return failure("Already checked in on this job site.", code="FS_ALREADY_CHECKED_IN")
    if log_type == "OUT" and not on_site:
        return failure("Not currently checked in on this job site.", code="FS_NOT_CHECKED_IN")
    try:
        doc = _insert_checkin(ticket_name, employee, log_type, latitude, longitude)
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(str(exc), code="VALIDATION_ERPNEXT")
    return success(
        {
            "name": doc.name,
            "ticket_name": str(ticket.get("name") or ""),
            "log_type": log_type,
            "time": str(doc.get("time") or ""),
        }
    )

def _ensure_service_person(employee: dict) -> str:
    """Get or create the Sales Person record Maintenance Visit rows require."""
    existing = frappe.get_list(
        "Sales Person",
        filters=[["employee", "=", employee["name"]]],
        fields=["name"],
        limit_page_length=1,
        ignore_permissions=True,
    )
    if existing:
        return str(existing[0]["name"])
    root = frappe.get_list(
        "Sales Person",
        filters=[["is_group", "=", 1], ["parent_sales_person", "is", "not set"]],
        fields=["name"],
        limit_page_length=1,
        ignore_permissions=True,
    )
    group_parent = str(root[0]["name"]) if root else ""
    group = frappe.get_list(
        "Sales Person",
        filters=[["sales_person_name", "=", SERVICE_PERSON_GROUP]],
        fields=["name"],
        limit_page_length=1,
        ignore_permissions=True,
    )
    if group:
        parent = str(group[0]["name"])
    elif group_parent:
        group_doc = frappe.get_doc(
            {
                "doctype": "Sales Person",
                "sales_person_name": SERVICE_PERSON_GROUP,
                "parent_sales_person": group_parent,
                "is_group": 1,
                # "" not None: blocks update_if_missing from stamping the
                # caller's Employee user-permission default onto the group,
                # which would trip Sales Person's employee-uniqueness check
                "employee": "",
            }
        )
        group_doc.insert(ignore_permissions=True)
        parent = group_doc.name
    else:
        parent = ""
    doc = frappe.get_doc(
        {
            "doctype": "Sales Person",
            "sales_person_name": employee.get("employee_name") or employee["name"],
            "parent_sales_person": parent or None,
            "is_group": 0,
            "employee": employee["name"],
        }
    )
    doc.insert(ignore_permissions=True)
    return str(doc.name)

def _default_company(employee: dict) -> str:
    if employee.get("company"):
        return str(employee["company"])
    rows = frappe.get_list(
        "Company", fields=["name"], limit_page_length=1, ignore_permissions=True
    )
    return str(rows[0]["name"]) if rows else ""

__all__ = [name for name in globals() if not name.startswith("__")]
