"""Grouped mobile endpoints: leave."""

from ._mobile_shared import *  # noqa: F401,F403

def leave_balances() -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Leave Allocation", "Leave Application")
    if missing:
        return missing
    today = date.today().isoformat()
    allocation_fields = _existing_fields(
        "Leave Allocation",
        [
            "leave_type",
            "from_date",
            "to_date",
            "new_leaves_allocated",
            "total_leaves_allocated",
            "carry_forwarded_leaves_count",
            "total_leaves_encashed",
        ],
    )
    allocation_filters = [
        ["employee", "=", employee["name"]],
        ["docstatus", "=", 1],
        ["from_date", "<=", today],
        ["to_date", ">=", today],
    ]
    if "expired" in _existing_fields("Leave Allocation", ["expired"]):
        allocation_filters.append(["expired", "=", 0])
    allocations = frappe.get_list(
        "Leave Allocation",
        filters=allocation_filters,
        fields=allocation_fields,
        limit_page_length=200,
    )
    applications = frappe.get_list(
        "Leave Application",
        filters=[
            ["employee", "=", employee["name"]],
            ["docstatus", "=", 1],
            ["status", "in", ["Approved", "Open"]],
        ],
        fields=["leave_type", "total_leave_days"],
        limit_page_length=500,
    )
    used_by_type: dict[str, float] = {}
    for row in applications:
        used_by_type[row["leave_type"]] = used_by_type.get(row["leave_type"], 0) + float(
            row.get("total_leave_days") or 0
        )
    allocation_by_type: dict[str, dict] = {}
    for row in allocations:
        leave_type = row["leave_type"]
        current = allocation_by_type.setdefault(
            leave_type,
            {
                "leave_type": leave_type,
                "allocated": 0.0,
                "new_allocated": 0.0,
                "carried_forward": 0.0,
                "encashed": 0.0,
                "from_date": "",
                "to_date": "",
            },
        )
        current["allocated"] += float(row.get("total_leaves_allocated") or 0)
        current["new_allocated"] += float(row.get("new_leaves_allocated") or 0)
        current["carried_forward"] += float(
            row.get("carry_forwarded_leaves_count") or 0
        )
        current["encashed"] += float(row.get("total_leaves_encashed") or 0)
        from_date = str(row.get("from_date") or "")
        to_date = str(row.get("to_date") or "")
        if from_date and (
            not current["from_date"] or from_date < current["from_date"]
        ):
            current["from_date"] = from_date
        if to_date and (not current["to_date"] or to_date > current["to_date"]):
            current["to_date"] = to_date

    rows = []
    for leave_type, row in allocation_by_type.items():
        allocated = row["allocated"]
        used = used_by_type.get(leave_type, 0)
        rows.append(
            {
                **row,
                "used": used,
                "available": allocated - used,
                "usage_percent": 0 if allocated <= 0 else min(100, used / allocated * 100),
            }
        )
    return success(sorted(rows, key=lambda row: row["leave_type"]))

def holidays(from_date: str | None = None, to_date: str | None = None, limit: int = 100) -> dict:
    """Holidays (incl. weekly-offs) from the employee's assigned Holiday List,
    falling back to the company default. Powers leave planning hints."""
    employee, error = _employee_or_failure()
    if error:
        return error
    emp_rows = frappe.get_list(
        "Employee",
        filters=[["name", "=", employee["name"]]],
        fields=["holiday_list", "company"],
        limit_page_length=1,
    )
    holiday_list = None
    # Current HRMS resolves the effective calendar through Holiday List
    # Assignment. Prefer the assignment covering the requested window, while
    # retaining the legacy Employee/company fallbacks for older ERPNext sites.
    assignment_date = from_date or date.today().isoformat()
    try:
        assignments = frappe.get_list(
            "Holiday List Assignment",
            filters=[
                ["employee", "=", employee["name"]],
                ["docstatus", "=", 1],
                ["from_date", "<=", assignment_date],
                ["to_date", ">=", assignment_date],
            ],
            fields=["holiday_list"],
            order_by="from_date desc",
            limit_page_length=1,
        )
        holiday_list = assignments[0].get("holiday_list") if assignments else None
    except Exception:
        # Holiday List Assignment does not exist on older HRMS releases.
        holiday_list = None
    if not holiday_list:
        holiday_list = emp_rows[0].get("holiday_list") if emp_rows else None
    if not holiday_list:
        company = emp_rows[0].get("company") if emp_rows else employee.get("company")
        company_rows = frappe.get_list(
            "Company",
            filters=[["name", "=", company]],
            fields=["default_holiday_list"],
            limit_page_length=1,
        )
        holiday_list = company_rows[0].get("default_holiday_list") if company_rows else None
    if not holiday_list:
        return success([])
    filters = [["parent", "=", holiday_list], ["parenttype", "=", "Holiday List"]]
    if from_date:
        filters.append(["holiday_date", ">=", from_date])
    if to_date:
        filters.append(["holiday_date", "<=", to_date])
    # Holiday is a child table. On current Frappe, permission-aware get_list
    # can return matching child rows with only `name`, leaving every requested
    # value blank. The parent has already been resolved from the signed-in
    # employee, so get_all remains safely scoped and returns the actual fields.
    rows = frappe.get_all(
        "Holiday",
        filters=filters,
        fields=["holiday_date", "description", "weekly_off"],
        order_by="holiday_date asc",
        limit_page_length=max(1, min(int(limit), 366)),
    )
    return success(
        [
            {
                "date": str(row.get("holiday_date") or ""),
                "description": row.get("description") or "",
                "weekly_off": bool(row.get("weekly_off")),
            }
            for row in rows
        ]
    )

def apply_leave(
    leave_type: str,
    from_date: str,
    to_date: str,
    reason: str | None = None,
    half_day: bool = False,
    half_day_date: str | None = None,
) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Leave Application")
    if missing:
        return missing
    if not leave_type or not from_date or not to_date:
        return failure(
            "leave_type, from_date, and to_date are required.",
            code="VALIDATION_REQUIRED",
        )
    try:
        is_half_day = _as_bool(half_day)
        leave_approver = (
            frappe.db.get_value("Employee", employee["name"], "leave_approver")
            or frappe.db.get_value("Employee", employee["name"], "expense_approver")
            or "Administrator"
        )
        doc = frappe.get_doc(
            {
                "doctype": "Leave Application",
                "employee": employee["name"],
                "company": employee.get("company"),
                "leave_type": leave_type,
                "from_date": from_date,
                "to_date": to_date,
                "description": reason,
                "leave_approver": leave_approver,
                "half_day": 1 if is_half_day else 0,
                "half_day_date": half_day_date or from_date if is_half_day else None,
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

def leave_requests(limit: int = 50) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Leave Application")
    if missing:
        return missing
    rows = frappe.get_list(
        "Leave Application",
        filters=[["employee", "=", employee["name"]]],
        fields=[
            "name",
            "leave_type",
            "from_date",
            "to_date",
            "status",
            "total_leave_days",
            "description",
            "docstatus",
        ],
        order_by="from_date desc",
        limit_page_length=max(1, min(int(limit), 100)),
    )
    return success([_leave_row(row) for row in rows])

def leave_request_detail(name: str) -> dict:
    row, error = _owned_leave(name)
    if error:
        return error
    return success(_leave_row(row))


def upload_leave_attachment(
    leave_name: str,
    file_name: str,
    content_base64: str,
) -> dict:
    extension = (file_name or "").rsplit(".", 1)[-1].lower()
    if not file_name or "." not in file_name or extension not in ATTACHMENT_EXTENSIONS:
        return failure(
            "A supporting document ending in jpg, jpeg, png, webp, heic, or pdf is required.",
            code="VALIDATION_REQUIRED",
        )
    if not content_base64 or len(content_base64) > MAX_ATTACHMENT_BASE64_LENGTH:
        return failure(
            "Attachment content is missing or larger than 5MB.",
            code="VALIDATION_REQUIRED",
        )
    leave, error = _owned_leave(leave_name)
    if error:
        return error
    try:
        doc = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": file_name,
                "attached_to_doctype": "Leave Application",
                "attached_to_name": leave["name"],
                "is_private": 1,
                "content": content_base64,
                "decode": True,
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
    return success({"name": doc.name, "file_url": doc.get("file_url") or ""})


def leave_attachments(leave_name: str, limit: int = 20) -> dict:
    leave, error = _owned_leave(leave_name)
    if error:
        return error
    rows = frappe.get_list(
        "File",
        filters=[
            ["attached_to_doctype", "=", "Leave Application"],
            ["attached_to_name", "=", leave["name"]],
        ],
        fields=["name", "file_name", "file_url", "is_private"],
        order_by="creation desc",
        limit_page_length=max(1, min(int(limit), 50)),
    )
    return success(
        [
            {
                "name": row.get("name"),
                "file_name": row.get("file_name") or "",
                "file_url": row.get("file_url") or "",
                "is_private": bool(row.get("is_private")),
            }
            for row in rows
        ]
    )


def cancel_leave(name: str) -> dict:
    row, error = _owned_leave(name)
    if error:
        return error
    if not _leave_is_cancellable(row):
        return failure(
            "This leave application cannot be cancelled.",
            code="HR_LEAVE_NOT_CANCELLABLE",
        )
    try:
        doc = frappe.get_doc("Leave Application", name)
        doc.cancel()
        frappe.db.commit()
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(str(exc), code="VALIDATION_ERPNEXT")
    return success({"name": name, "status": "Cancelled"})

def comp_off_requests(limit: int = 50) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Compensatory Leave Request")
    if missing:
        return missing
    rows = frappe.get_list(
        "Compensatory Leave Request",
        filters=[["employee", "=", employee["name"]]],
        fields=["name", "leave_type", "work_from_date", "work_end_date", "reason", "docstatus"],
        order_by="work_from_date desc",
        limit_page_length=max(1, min(int(limit), 100)),
    )
    return success(
        [
            {
                "name": row.get("name"),
                "leave_type": row.get("leave_type") or "",
                "from_date": str(row.get("work_from_date") or ""),
                "to_date": str(row.get("work_end_date") or ""),
                "reason": row.get("reason") or "",
                "docstatus": int(row.get("docstatus") or 0),
            }
            for row in rows
        ]
    )

def apply_comp_off(
    leave_type: str,
    work_from_date: str,
    work_end_date: str,
    reason: str | None = None,
    half_day: bool = False,
    half_day_date: str | None = None,
) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Compensatory Leave Request")
    if missing:
        return missing
    if not leave_type or not work_from_date or not work_end_date:
        return failure(
            "leave_type, work_from_date, and work_end_date are required.",
            code="VALIDATION_REQUIRED",
        )
    try:
        is_half_day = _as_bool(half_day)
        doc = frappe.get_doc(
            {
                "doctype": "Compensatory Leave Request",
                "employee": employee["name"],
                "leave_type": leave_type,
                "work_from_date": work_from_date,
                "work_end_date": work_end_date,
                "reason": reason,
                "half_day": 1 if is_half_day else 0,
                "half_day_date": half_day_date or work_from_date if is_half_day else None,
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

def manager_pending_leaves(limit: int = 50) -> dict:
    denied = _require_manager()
    if denied:
        return denied
    missing = _require_doctypes("Leave Application")
    if missing:
        return missing
    rows = frappe.get_list(
        "Leave Application",
        filters=[
            ["leave_approver", "=", _current_user()],
            ["docstatus", "=", 1],
            ["status", "=", "Open"],
        ],
        fields=[
            "name",
            "employee",
            "employee_name",
            "leave_type",
            "from_date",
            "to_date",
            "total_leave_days",
        ],
        order_by="from_date asc",
        limit_page_length=max(1, min(int(limit), 100)),
    )
    return success(
        [
            {
                "name": row.get("name"),
                "employee": row.get("employee"),
                "employee_name": row.get("employee_name"),
                "leave_type": row.get("leave_type"),
                "from_date": str(row.get("from_date") or ""),
                "to_date": str(row.get("to_date") or ""),
                "total_leave_days": float(row.get("total_leave_days") or 0),
            }
            for row in rows
        ]
    )

def decide_leave(name: str, approved: bool, comment: str | None = None) -> dict:
    _, error = _assigned_approval("Leave Application", name, "leave_approver")
    if error:
        return error
    status = "Approved" if _as_bool(approved) else "Rejected"
    try:
        doc = frappe.get_doc("Leave Application", name)
        doc.status = status
        _apply_decision(doc, comment)
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(str(exc), code="VALIDATION_ERPNEXT")
    return success({"name": name, "status": status})
