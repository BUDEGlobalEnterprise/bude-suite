"""Grouped mobile endpoints: manager."""

from ._mobile_shared import *  # noqa: F401,F403

def manager_summary() -> dict:
    denied = _require_manager()
    if denied:
        return denied
    missing = _require_doctypes("Leave Application", "Expense Claim")
    if missing:
        return missing
    user = _current_user()
    pending_leaves = frappe.db.count(
        "Leave Application",
        filters={
            "leave_approver": user,
            "docstatus": 1,
            "status": "Open",
        },
    )
    pending_expenses = frappe.db.count(
        "Expense Claim",
        filters={"expense_approver": user, "approval_status": "Draft"},
    )
    return success(
        {
            "pending_leaves": pending_leaves,
            "pending_expenses": pending_expenses,
        }
    )

def manager_direct_reports(limit: int = 100) -> dict:
    denied = _require_manager()
    if denied:
        return denied
    manager = _current_employee()
    if not manager:
        return failure(
            "No active Employee record is linked to this user.",
            code="HR_EMPLOYEE_NOT_FOUND",
        )
    rows = frappe.get_list(
        "Employee",
        filters=[
            ["reports_to", "=", manager["name"]],
            ["status", "=", "Active"],
        ],
        fields=[
            "name",
            "employee_name",
            "department",
            "designation",
            "company_email",
            "cell_number",
        ],
        order_by="employee_name asc",
        limit_page_length=max(1, min(int(limit), 200)),
    )
    return success(
        [
            {
                "employee": row.get("name"),
                "employee_name": row.get("employee_name") or "",
                "department": row.get("department") or "",
                "designation": row.get("designation") or "",
                "company_email": row.get("company_email") or "",
                "cell_number": row.get("cell_number") or "",
            }
            for row in rows
        ]
    )

def manager_team_attendance_exceptions(days: int = 7, limit: int = 100) -> dict:
    """Absent / half-day / on-leave attendance for direct reports."""
    denied = _require_manager()
    if denied:
        return denied
    manager = _current_employee()
    if not manager:
        return failure(
            "No active Employee record is linked to this user.",
            code="HR_EMPLOYEE_NOT_FOUND",
        )
    missing = _require_doctypes("Attendance")
    if missing:
        return missing
    reports = frappe.get_list(
        "Employee",
        filters=[
            ["reports_to", "=", manager["name"]],
            ["status", "=", "Active"],
        ],
        fields=["name"],
        limit_page_length=200,
    )
    if not reports:
        return success([])
    window_days = max(1, min(int(days), 60))
    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    rows = frappe.get_list(
        "Attendance",
        filters=[
            ["employee", "in", [row["name"] for row in reports]],
            ["status", "in", ["Absent", "Half Day", "On Leave"]],
            ["attendance_date", ">=", cutoff],
            ["docstatus", "=", 1],
        ],
        fields=["name", "employee", "employee_name", "attendance_date", "status"],
        order_by="attendance_date desc",
        limit_page_length=max(1, min(int(limit), 200)),
    )
    return success(
        [
            {
                "name": row.get("name"),
                "employee": row.get("employee"),
                "employee_name": row.get("employee_name") or "",
                "attendance_date": str(row.get("attendance_date") or ""),
                "status": row.get("status") or "",
            }
            for row in rows
        ]
    )

def manager_report_profile(employee: str) -> dict:
    report_names, error = _direct_report_names()
    if error:
        return error
    if employee not in report_names:
        return failure("Direct report not found.", code="HR_DIRECT_REPORT_NOT_FOUND")
    rows = frappe.get_list(
        "Employee",
        filters=[["name", "=", employee]],
        fields=[
            "name",
            "employee_name",
            "company",
            "department",
            "designation",
            "date_of_joining",
            "reports_to",
            "cell_number",
            "company_email",
            "user_id",
        ],
        limit_page_length=1,
    )
    return success(rows[0] if rows else None)

def manager_team_calendar(month: str | None = None, limit: int = 500) -> dict:
    report_names, error = _direct_report_names()
    if error:
        return error
    missing = _require_doctypes("Attendance", "Leave Application")
    if missing:
        return missing
    if not report_names:
        return success({"attendance": [], "leave": []})
    today = date.today()
    if month:
        try:
            year, month_no = [int(part) for part in str(month).split("-", 1)]
            start = date(year, month_no, 1)
        except Exception:
            return failure("month must use YYYY-MM format.", code="VALIDATION_BAD_MONTH")
    else:
        start = date(today.year, today.month, 1)
    next_month = date(
        start.year + (1 if start.month == 12 else 0), 1 if start.month == 12 else start.month + 1, 1
    )
    end = next_month - timedelta(days=1)
    attendance = frappe.get_list(
        "Attendance",
        filters=[
            ["employee", "in", report_names],
            ["attendance_date", ">=", start.isoformat()],
            ["attendance_date", "<=", end.isoformat()],
        ],
        fields=["name", "employee", "employee_name", "attendance_date", "status"],
        order_by="attendance_date asc",
        limit_page_length=max(1, min(int(limit), 1000)),
    )
    leave = frappe.get_list(
        "Leave Application",
        filters=[
            ["employee", "in", report_names],
            ["from_date", "<=", end.isoformat()],
            ["to_date", ">=", start.isoformat()],
        ],
        fields=[
            "name",
            "employee",
            "employee_name",
            "leave_type",
            "from_date",
            "to_date",
            "status",
        ],
        order_by="from_date asc",
        limit_page_length=max(1, min(int(limit), 1000)),
    )
    return success(
        {
            "attendance": [
                {
                    "name": row.get("name"),
                    "employee": row.get("employee"),
                    "employee_name": row.get("employee_name") or "",
                    "date": str(row.get("attendance_date") or ""),
                    "status": row.get("status") or "",
                }
                for row in attendance
            ],
            "leave": [
                {
                    "name": row.get("name"),
                    "employee": row.get("employee"),
                    "employee_name": row.get("employee_name") or "",
                    "leave_type": row.get("leave_type") or "",
                    "from_date": str(row.get("from_date") or ""),
                    "to_date": str(row.get("to_date") or ""),
                    "status": row.get("status") or "",
                }
                for row in leave
            ],
        }
    )

def manager_today() -> dict:
    report_names, error = _direct_report_names()
    if error:
        return error
    missing = _require_doctypes("Employee Checkin", "Attendance", "Leave Application")
    if missing:
        return missing
    cache_key = f"bude_hr_manager_today:{_current_user()}:{frappe.utils.today()}"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return success(cached)
    if not report_names:
        data = {"present": [], "late": [], "absent": [], "on_leave": [], "approval_aging": []}
        frappe.cache().set_value(cache_key, data, expires_in_sec=MANAGER_CACHE_TTL_SECONDS)
        return success(data)
    today = frappe.utils.today()
    employees = frappe.get_list(
        "Employee",
        filters=[["name", "in", report_names]],
        fields=["name", "employee_name"],
        limit_page_length=MAX_WIDE_PAGE_LIMIT,
    )
    names = {row["name"]: row.get("employee_name") or row["name"] for row in employees}
    checkins = frappe.get_list(
        "Employee Checkin",
        filters=[
            ["employee", "in", report_names],
            ["time", ">=", f"{today} 00:00:00"],
            ["time", "<=", f"{today} 23:59:59"],
        ],
        fields=["employee", "time", "log_type"],
        order_by="time asc",
        limit_page_length=MAX_WIDE_PAGE_LIMIT,
    )
    present_employees = {row.get("employee") for row in checkins}
    attendance = frappe.get_list(
        "Attendance",
        filters=[["employee", "in", report_names], ["attendance_date", "=", today]],
        fields=["employee", "status", "late_entry"],
        limit_page_length=MAX_WIDE_PAGE_LIMIT,
    )
    on_leave = [row.get("employee") for row in attendance if row.get("status") == "On Leave"]
    late = [row.get("employee") for row in attendance if row.get("late_entry")]
    absent = [
        name for name in report_names if name not in present_employees and name not in on_leave
    ]
    data = {
        "present": [
            {"employee": emp, "employee_name": names.get(emp, emp)}
            for emp in sorted(present_employees)
        ],
        "late": [
            {"employee": emp, "employee_name": names.get(emp, emp)} for emp in sorted(set(late))
        ],
        "absent": [
            {"employee": emp, "employee_name": names.get(emp, emp)} for emp in sorted(absent)
        ],
        "on_leave": [
            {"employee": emp, "employee_name": names.get(emp, emp)} for emp in sorted(set(on_leave))
        ],
        "approval_aging": _approval_aging(),
    }
    frappe.cache().set_value(cache_key, data, expires_in_sec=MANAGER_CACHE_TTL_SECONDS)
    return success(data)

def timesheets(limit: int = 50, offset: int = 0) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Timesheet")
    if missing:
        return missing
    page_limit, page_offset = _page(limit, offset)
    rows = frappe.get_list(
        "Timesheet",
        filters=[["employee", "=", employee["name"]]],
        fields=["name", "start_date", "end_date", "total_hours", "status", "docstatus"],
        order_by="modified desc",
        limit_start=page_offset,
        limit_page_length=page_limit,
    )
    return success(
        [
            {
                "name": row.get("name"),
                "start_date": str(row.get("start_date") or ""),
                "end_date": str(row.get("end_date") or ""),
                "total_hours": float(row.get("total_hours") or 0),
                "status": row.get("status") or "",
                "docstatus": int(row.get("docstatus") or 0),
            }
            for row in rows
        ]
    )

def submit_timesheet(
    activity_type: str,
    from_time: str,
    to_time: str,
    hours: float,
    project: str | None = None,
    task: str | None = None,
    note: str | None = None,
) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Timesheet")
    if missing:
        return missing
    if (
        not activity_type
        or not from_time
        or not to_time
        or float(hours or 0) <= 0
        or float(hours or 0) > 24
    ):
        return failure(
            "activity_type, from_time, to_time, and 0-24 hours are required.",
            code="VALIDATION_REQUIRED",
        )
    try:
        doc = frappe.get_doc(
            {
                "doctype": "Timesheet",
                "employee": employee["name"],
                "company": employee.get("company"),
                "time_logs": [
                    {
                        "activity_type": activity_type,
                        "from_time": from_time,
                        "to_time": to_time,
                        "hours": hours,
                        "project": project,
                        "task": task,
                        "description": note,
                    }
                ],
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
