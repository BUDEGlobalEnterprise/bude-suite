"""Grouped mobile endpoints: attendance."""

from ._mobile_shared import *  # noqa: F401,F403

def attendance_status() -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Employee Checkin")
    if missing:
        return missing
    latest = frappe.get_list(
        "Employee Checkin",
        filters=[["employee", "=", employee["name"]]],
        fields=["name", "time", "log_type"],
        order_by="time desc",
        limit_page_length=1,
    )
    latest_in = frappe.get_list(
        "Employee Checkin",
        filters=[["employee", "=", employee["name"]], ["log_type", "=", "IN"]],
        fields=["time"],
        order_by="time desc",
        limit_page_length=1,
    )
    latest_out = frappe.get_list(
        "Employee Checkin",
        filters=[["employee", "=", employee["name"]], ["log_type", "=", "OUT"]],
        fields=["time"],
        order_by="time desc",
        limit_page_length=1,
    )
    last = latest[0] if latest else {}
    return success(
        {
            "checked_in": last.get("log_type") == "IN",
            "last_check_in": str(latest_in[0].get("time")) if latest_in else None,
            "last_check_out": str(latest_out[0].get("time")) if latest_out else None,
            "latest_checkin_id": last.get("name"),
            "last_log_type": last.get("log_type"),
            "server_time": str(frappe.utils.now_datetime()),
        }
    )

def attendance_history(limit: int = 30) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Employee Checkin")
    if missing:
        return missing
    page_limit, _ = _page(limit, 0, cap=100)
    rows = frappe.get_list(
        "Employee Checkin",
        filters=[["employee", "=", employee["name"]]],
        fields=["name", "time", "log_type"],
        order_by="time desc",
        limit_page_length=page_limit,
    )
    return success(
        [
            {
                "name": row.get("name"),
                "time": str(row.get("time") or ""),
                "log_type": row.get("log_type"),
            }
            for row in rows
        ]
    )


def attendance_summary(days: int = 30) -> dict:
    """Summarize the employee's recent submitted Attendance records."""
    employee, error = _employee_or_failure()
    if error:
        return error
    try:
        days = int(days)
    except (TypeError, ValueError):
        return failure("days must be an integer.", code="VALIDATION_BAD_DAYS")
    if days < 7 or days > 90:
        return failure("days must be between 7 and 90.", code="VALIDATION_BAD_DAYS")
    empty = {
        "days": days,
        "recorded_days": 0,
        "status_counts": {},
        "average_working_hours": 0.0,
        "late_entries": 0,
        "early_exits": 0,
    }
    try:
        if not frappe.db.exists("DocType", "Attendance"):
            return success(empty)
        fields = _existing_fields(
            "Attendance",
            [
                "attendance_date",
                "status",
                "working_hours",
                "late_entry",
                "early_exit",
            ],
        )
        if not {"attendance_date", "status"}.issubset(fields):
            return success(empty)
        end = date.today()
        start = end - timedelta(days=days - 1)
        rows = frappe.get_list(
            "Attendance",
            filters=[
                ["employee", "=", employee["name"]],
                ["docstatus", "=", 1],
                ["attendance_date", ">=", start.isoformat()],
                ["attendance_date", "<=", end.isoformat()],
            ],
            fields=fields,
            order_by="attendance_date desc",
            limit_page_length=days + 10,
        )
    except Exception:
        return success(empty)
    status_counts: dict[str, int] = {}
    working_hours = []
    late_entries = 0
    early_exits = 0
    for row in rows:
        status = str(row.get("status") or "Unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        hours = float(row.get("working_hours") or 0)
        if hours > 0:
            working_hours.append(hours)
        late_entries += int(bool(row.get("late_entry")))
        early_exits += int(bool(row.get("early_exit")))
    return success(
        {
            "days": days,
            "recorded_days": len(rows),
            "status_counts": status_counts,
            "average_working_hours": (
                round(sum(working_hours) / len(working_hours), 2)
                if working_hours
                else 0.0
            ),
            "late_entries": late_entries,
            "early_exits": early_exits,
        }
    )


def check_in(
    type: str = "IN",
    latitude: float | None = None,
    longitude: float | None = None,
    accuracy: float | None = None,
) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Employee Checkin")
    if missing:
        return missing
    log_type = str(type or "").upper()
    if log_type not in {"IN", "OUT"}:
        return failure("type must be IN or OUT.", code="VALIDATION_BAD_TYPE")
    geofence_error = _validate_geofence(employee["name"], latitude, longitude)
    if geofence_error:
        return geofence_error
    try:
        payload = {
            "doctype": "Employee Checkin",
            "employee": employee["name"],
            "log_type": log_type,
            "time": frappe.utils.now_datetime(),
        }
        if latitude is not None and longitude is not None:
            payload["latitude"] = latitude
            payload["longitude"] = longitude
        if accuracy is not None:
            payload["accuracy"] = accuracy
        doc = frappe.get_doc(payload)
        doc.insert(ignore_permissions=False)
        frappe.db.commit()
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(str(exc), code="VALIDATION_ERPNEXT")
    return success({"name": doc.name, "log_type": log_type})

def upload_checkin_selfie(checkin_name: str, file_name: str, content_base64: str) -> dict:
    extension = (file_name or "").rsplit(".", 1)[-1].lower()
    if not file_name or "." not in file_name or extension not in CHECKIN_SELFIE_EXTENSIONS:
        return failure(
            "A selfie image ending in jpg, jpeg, png, or webp is required.",
            code="VALIDATION_REQUIRED",
        )
    if not content_base64 or len(content_base64) > MAX_SELFIE_BASE64_LENGTH:
        return failure("Selfie content is missing or larger than 5MB.", code="VALIDATION_REQUIRED")
    try:
        base64.b64decode(content_base64, validate=True)
    except Exception:
        return failure("Selfie content must be valid base64.", code="VALIDATION_REQUIRED")
    checkin, error = _owned_checkin(checkin_name)
    if error:
        return error
    try:
        doc = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": file_name,
                "attached_to_doctype": "Employee Checkin",
                "attached_to_name": checkin["name"],
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

def attendance_calendar(month: str | None = None) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Attendance")
    if missing:
        return missing
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
    rows = frappe.get_list(
        "Attendance",
        filters=[
            ["employee", "=", employee["name"]],
            ["attendance_date", ">=", start.isoformat()],
            ["attendance_date", "<=", end.isoformat()],
        ],
        fields=[
            "name",
            "attendance_date",
            "status",
            "working_hours",
            "in_time",
            "out_time",
            "late_entry",
            "early_exit",
            "shift",
        ],
        order_by="attendance_date asc",
        limit_page_length=100,
    )
    return success(
        [
            {
                "name": row.get("name"),
                "date": str(row.get("attendance_date") or ""),
                "status": row.get("status") or "",
                "working_hours": float(row.get("working_hours") or 0),
                "in_time": str(row.get("in_time") or ""),
                "out_time": str(row.get("out_time") or ""),
                "late_entry": bool(row.get("late_entry")),
                "early_exit": bool(row.get("early_exit")),
                "shift": row.get("shift") or "",
            }
            for row in rows
        ]
    )

def attendance_requests(limit: int = 50) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Attendance Request")
    if missing:
        return missing
    page_limit, _ = _page(limit, 0, cap=100)
    rows = frappe.get_list(
        "Attendance Request",
        filters=[["employee", "=", employee["name"]]],
        fields=["name", "from_date", "to_date", "reason", "explanation", "docstatus"],
        order_by="from_date desc",
        limit_page_length=page_limit,
    )
    return success(
        [
            {
                "name": row.get("name"),
                "from_date": str(row.get("from_date") or ""),
                "to_date": str(row.get("to_date") or ""),
                "reason": row.get("reason") or "",
                "explanation": row.get("explanation") or "",
                "docstatus": int(row.get("docstatus") or 0),
            }
            for row in rows
        ]
    )

def apply_attendance_request(
    from_date: str,
    to_date: str,
    reason: str,
    explanation: str | None = None,
    half_day: bool = False,
    half_day_date: str | None = None,
) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Attendance Request")
    if missing:
        return missing
    if not from_date or not to_date or not reason:
        return failure("from_date, to_date, and reason are required.", code="VALIDATION_REQUIRED")
    try:
        is_half_day = _as_bool(half_day)
        doc = frappe.get_doc(
            {
                "doctype": "Attendance Request",
                "employee": employee["name"],
                "company": employee.get("company"),
                "from_date": from_date,
                "to_date": to_date,
                "reason": reason,
                "explanation": explanation,
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
    return success({"name": doc.name})

def attendance_anomalies(
    from_date: str | None = None,
    to_date: str | None = None,
    type: str | None = None,
    late_minutes: int = 15,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    report_names, error = _direct_report_names()
    if error:
        return error
    missing = _require_doctypes("Attendance", "Employee Checkin")
    if missing:
        return missing
    if not report_names:
        return success([])
    page_limit, page_offset = _page(limit, offset)
    end = _date_or_none(to_date) or date.today()
    start = _date_or_none(from_date) or (end - timedelta(days=7))
    if (end - start).days > 60:
        return failure("Date range is capped at 60 days.", code="VALIDATION_RANGE_TOO_WIDE")
    wanted = str(type or "all").lower()
    rows = frappe.get_list(
        "Attendance",
        filters=[
            ["employee", "in", report_names],
            ["attendance_date", ">=", start.isoformat()],
            ["attendance_date", "<=", end.isoformat()],
        ],
        fields=[
            "name",
            "employee",
            "employee_name",
            "attendance_date",
            "status",
            "late_entry",
            "in_time",
            "out_time",
            "working_hours",
        ],
        order_by="attendance_date desc",
        limit_page_length=MAX_WIDE_PAGE_LIMIT,
    )
    anomalies = []
    for row in rows:
        reason = None
        anomaly_type = None
        if row.get("status") == "Absent":
            anomaly_type = "absent"
            reason = "Absent without a submitted attendance record."
        elif row.get("late_entry"):
            anomaly_type = "late"
            reason = f"Marked late by Attendance. Threshold: {int(late_minutes)} minutes."
        elif row.get("in_time") and not row.get("out_time"):
            anomaly_type = "missing_checkout"
            reason = "Attendance has an in-time but no out-time."
        if anomaly_type and wanted in {"all", anomaly_type}:
            anomalies.append(
                {
                    "type": anomaly_type,
                    "name": row.get("name"),
                    "employee": row.get("employee"),
                    "employee_name": row.get("employee_name") or "",
                    "date": str(row.get("attendance_date") or ""),
                    "status": row.get("status") or "",
                    "reason": reason,
                }
            )
    return success(anomalies[page_offset : page_offset + page_limit])
