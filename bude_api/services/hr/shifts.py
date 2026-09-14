"""Grouped mobile endpoints: shifts."""

from ._mobile_shared import *  # noqa: F401,F403

def shift_status() -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Shift Assignment", "Shift Type")
    if missing:
        return missing
    today = frappe.utils.today()
    assignments = frappe.get_list(
        "Shift Assignment",
        filters=[
            ["employee", "=", employee["name"]],
            ["status", "=", "Active"],
            ["start_date", "<=", today],
        ],
        fields=["name", "shift_type", "start_date", "end_date", "shift_location"],
        order_by="start_date desc",
        limit_page_length=20,
    )
    assignment = next(
        (
            row
            for row in assignments
            if not row.get("end_date") or str(row.get("end_date")) >= today
        ),
        None,
    )
    shift = {}
    if assignment and assignment.get("shift_type"):
        rows = frappe.get_list(
            "Shift Type",
            filters=[["name", "=", assignment["shift_type"]]],
            fields=["name", "start_time", "end_time", "holiday_list", "color"],
            limit_page_length=1,
        )
        shift = rows[0] if rows else {}
    return success(
        {
            "assignment": assignment,
            "shift": {
                "name": shift.get("name"),
                "start_time": str(shift.get("start_time") or ""),
                "end_time": str(shift.get("end_time") or ""),
                "holiday_list": shift.get("holiday_list"),
                "color": shift.get("color"),
            }
            if shift
            else None,
        }
    )

def shift_roster(month: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Shift Assignment", "Shift Type")
    if missing:
        return missing
    page_limit, page_offset = _page(limit, offset)
    start, end, month_error = _month_window(month)
    if month_error:
        return month_error
    rows = frappe.get_list(
        "Shift Assignment",
        filters=[
            ["employee", "=", employee["name"]],
            ["start_date", "<=", end.isoformat()],
            ["end_date", ">=", start.isoformat()],
        ],
        fields=["name", "shift_type", "start_date", "end_date", "status", "shift_location"],
        order_by="start_date asc",
        limit_start=page_offset,
        limit_page_length=page_limit,
    )
    return success(
        [
            {
                "name": row.get("name"),
                "shift_type": row.get("shift_type") or "",
                "start_date": str(row.get("start_date") or ""),
                "end_date": str(row.get("end_date") or ""),
                "status": row.get("status") or "",
                "shift_location": row.get("shift_location") or "",
            }
            for row in rows
        ]
    )

def shift_requests(limit: int = 50, offset: int = 0) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Shift Request")
    if missing:
        return missing
    page_limit, page_offset = _page(limit, offset)
    rows = frappe.get_list(
        "Shift Request",
        filters=[["employee", "=", employee["name"]]],
        fields=[
            "name",
            "employee",
            "shift_type",
            "from_date",
            "to_date",
            "status",
            "reason",
            "docstatus",
        ],
        order_by="from_date desc",
        limit_start=page_offset,
        limit_page_length=page_limit,
    )
    return success([_shift_request_row(row) for row in rows])

def apply_shift_request(
    shift_type: str, from_date: str, to_date: str, reason: str | None = None
) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Shift Request")
    if missing:
        return missing
    if not shift_type or not from_date or not to_date:
        return failure(
            "shift_type, from_date, and to_date are required.", code="VALIDATION_REQUIRED"
        )
    try:
        doc = frappe.get_doc(
            {
                "doctype": "Shift Request",
                "employee": employee["name"],
                "employee_name": employee.get("employee_name"),
                "company": employee.get("company"),
                "shift_type": shift_type,
                "from_date": from_date,
                "to_date": to_date,
                "reason": reason,
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

def manager_pending_shift_requests(limit: int = 50, offset: int = 0) -> dict:
    report_names, error = _direct_report_names()
    if error:
        return error
    missing = _require_doctypes("Shift Request")
    if missing:
        return missing
    if not report_names:
        return success([])
    page_limit, page_offset = _page(limit, offset)
    rows = frappe.get_list(
        "Shift Request",
        filters=[["employee", "in", report_names], ["docstatus", "=", 0]],
        fields=[
            "name",
            "employee",
            "employee_name",
            "shift_type",
            "from_date",
            "to_date",
            "status",
            "reason",
            "docstatus",
        ],
        order_by="from_date asc",
        limit_start=page_offset,
        limit_page_length=page_limit,
    )
    return success([_shift_request_row(row) for row in rows])

def decide_shift_request(name: str, approved: bool, comment: str | None = None) -> dict:
    report_names, error = _direct_report_names()
    if error:
        return error
    missing = _require_doctypes("Shift Request")
    if missing:
        return missing
    rows = frappe.get_list(
        "Shift Request",
        filters=[["name", "=", name], ["employee", "in", report_names]],
        fields=["name"],
        limit_page_length=1,
    )
    if not rows:
        return failure("Shift request not found.", code="HR_SHIFT_REQUEST_NOT_FOUND")
    try:
        doc = frappe.get_doc("Shift Request", name)
        doc.status = "Approved" if _as_bool(approved) else "Rejected"
        _apply_decision(doc, comment)
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(str(exc), code="VALIDATION_ERPNEXT")
    return success({"name": name, "status": doc.get("status")})
