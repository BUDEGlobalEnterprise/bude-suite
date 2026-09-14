"""Employee self-service endpoints for the Bude HR Flutter app.

All persistence uses standard ERPNext/HRMS DocTypes. These endpoints are a
clean-room implementation inspired by common ESS flows, not copied from the
reference HR apps in the repository.
"""

import base64

import math

from datetime import date, datetime, timedelta

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success

HR_ROLES = {"Employee", "HR User", "HR Manager", "System Manager"}

MANAGER_ROLES = {"HR User", "HR Manager", "System Manager", "Leave Approver", "Expense Approver"}

DEFAULT_PAGE_LIMIT = 50

MAX_PAGE_LIMIT = 100

MAX_WIDE_PAGE_LIMIT = 500

MANAGER_CACHE_TTL_SECONDS = 60

def _whitelist(methods=None, allow_guest: bool = False):
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=methods or ["GET", "POST"])

def _require_hr_role() -> dict | None:
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    user = getattr(getattr(frappe, "session", None), "user", None)
    if not user or user == "Guest":
        return failure("Your session has expired. Please sign in again.", code="AUTH_EXPIRED")
    if user == "Administrator":
        return None
    roles = set(frappe.get_roles(user) or [])
    if roles.intersection(HR_ROLES):
        return None
    return failure("An HR role is required for this action.", code="PERMISSION_DENIED")

def _require_manager() -> dict | None:
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    user = getattr(getattr(frappe, "session", None), "user", None)
    if not user or user == "Guest":
        return failure("Your session has expired. Please sign in again.", code="AUTH_EXPIRED")
    if user == "Administrator":
        return None
    roles = set(frappe.get_roles(user) or [])
    if roles.intersection(MANAGER_ROLES):
        return None
    return failure("A manager role is required for this action.", code="PERMISSION_DENIED")

def _current_employee() -> dict | None:
    user = getattr(getattr(frappe, "session", None), "user", None)
    rows = frappe.get_list(
        "Employee",
        filters=[["user_id", "=", user], ["status", "=", "Active"]],
        fields=[
            "name",
            "employee_name",
            "company",
            "department",
            "designation",
            "user_id",
        ],
        limit_page_length=1,
    )
    return rows[0] if rows else None

def _employee_or_failure() -> tuple[dict | None, dict | None]:
    denied = _require_hr_role()
    if denied:
        return None, denied
    employee = _current_employee()
    if not employee:
        return None, failure(
            "No active Employee record is linked to this user.",
            code="HR_EMPLOYEE_NOT_FOUND",
        )
    return employee, None

def _require_doctypes(*doctypes: str) -> dict | None:
    """Return a JSON failure when an optional HRMS DocType is not installed."""
    for doctype in doctypes:
        exists = frappe.db.exists("DocType", doctype)
        if not exists:
            return failure(
                f"{doctype} is not available on this ERPNext site. Install the HRMS app "
                "or enable this DocType before using this HR feature.",
                code="HR_DOCTYPE_UNAVAILABLE",
                data={"doctype": doctype},
            )
    return None

def _page(
    limit: int | str | None = DEFAULT_PAGE_LIMIT,
    offset: int | str | None = 0,
    cap: int = MAX_PAGE_LIMIT,
) -> tuple[int, int]:
    """Bound every list endpoint so clients cannot ask for unbounded rows."""
    try:
        parsed_limit = int(limit if limit is not None else DEFAULT_PAGE_LIMIT)
    except Exception:
        parsed_limit = DEFAULT_PAGE_LIMIT
    try:
        parsed_offset = int(offset if offset is not None else 0)
    except Exception:
        parsed_offset = 0
    return max(1, min(parsed_limit, cap)), max(0, parsed_offset)

def _month_window(month: str | None = None) -> tuple[date | None, date | None, dict | None]:
    today = date.today()
    if month:
        try:
            year, month_no = [int(part) for part in str(month).split("-", 1)]
            start = date(year, month_no, 1)
        except Exception:
            return (
                None,
                None,
                failure("month must use YYYY-MM format.", code="VALIDATION_BAD_MONTH"),
            )
    else:
        start = date(today.year, today.month, 1)
    next_month = date(
        start.year + (1 if start.month == 12 else 0), 1 if start.month == 12 else start.month + 1, 1
    )
    return start, next_month - timedelta(days=1), None

def _date_or_none(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except Exception:
        return None

def _validate_geofence(employee_name: str, latitude, longitude) -> dict | None:
    """Validate against optional custom fields on Shift Type when configured.

    Expected custom fieldnames on Shift Type:
    - bude_geofence_enabled
    - bude_geofence_latitude
    - bude_geofence_longitude
    - bude_geofence_radius_meters
    - bude_geofence_mode: Reject or Flag (Reject default)
    """
    if latitude is None or longitude is None:
        return None
    missing = _require_doctypes("Shift Assignment", "Shift Type")
    if missing:
        return None
    today = frappe.utils.today()
    assignments = frappe.get_list(
        "Shift Assignment",
        filters=[
            ["employee", "=", employee_name],
            ["status", "=", "Active"],
            ["start_date", "<=", today],
        ],
        fields=["shift_type", "end_date"],
        order_by="start_date desc",
        limit_page_length=10,
    )
    assignment = next(
        (
            row
            for row in assignments
            if not row.get("end_date") or str(row.get("end_date")) >= today
        ),
        None,
    )
    if not assignment or not assignment.get("shift_type"):
        return None
    optional_fields = _existing_fields(
        "Shift Type",
        [
            "bude_geofence_enabled",
            "bude_geofence_latitude",
            "bude_geofence_longitude",
            "bude_geofence_radius_meters",
            "bude_geofence_mode",
        ],
    )
    if len(optional_fields) < 4:
        return None
    shift = frappe.get_list(
        "Shift Type",
        filters=[["name", "=", assignment["shift_type"]]],
        fields=["name", *optional_fields],
        limit_page_length=1,
    )
    if not shift or not _as_bool(shift[0].get("bude_geofence_enabled")):
        return None
    center_lat = shift[0].get("bude_geofence_latitude")
    center_lng = shift[0].get("bude_geofence_longitude")
    radius = float(shift[0].get("bude_geofence_radius_meters") or 0)
    if center_lat in (None, "") or center_lng in (None, "") or radius <= 0:
        return None
    distance = _distance_meters(
        float(latitude), float(longitude), float(center_lat), float(center_lng)
    )
    if distance <= radius:
        return None
    if str(shift[0].get("bude_geofence_mode") or "Reject").lower() == "flag":
        return None
    return failure(
        "Attendance location is outside the assigned shift geofence.",
        code="HR_GEOFENCE_VIOLATION",
        data={"distance_meters": round(distance, 1), "radius_meters": radius},
    )

def _existing_fields(doctype: str, fields: list[str]) -> list[str]:
    # Frappe's ``Meta.has_field`` only checks DocFields on some framework
    # versions. Standard document columns are valid query fields too; dropping
    # them made notification payloads lose their identifier and timestamp.
    standard_fields = {
        "name",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "idx",
        "parent",
        "parentfield",
        "parenttype",
    }
    get_meta = getattr(frappe, "get_meta", None)
    if not callable(get_meta):
        return fields
    meta = get_meta(doctype)
    has_field = getattr(meta, "has_field", None)
    if not callable(has_field):
        return fields
    return [field for field in fields if field in standard_fields or has_field(field)]

def _distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lam = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lam / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

CHECKIN_SELFIE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

MAX_SELFIE_BASE64_LENGTH = 7_000_000

def _owned_checkin(name: str) -> tuple[dict | None, dict | None]:
    employee, error = _employee_or_failure()
    if error:
        return None, error
    missing = _require_doctypes("Employee Checkin")
    if missing:
        return None, missing
    rows = frappe.get_list(
        "Employee Checkin",
        filters=[["name", "=", name], ["employee", "=", employee["name"]]],
        fields=["name"],
        limit_page_length=1,
    )
    if not rows:
        return None, failure("Employee check-in not found.", code="HR_CHECKIN_NOT_FOUND")
    return rows[0], None

def _shift_request_row(row: dict) -> dict:
    return {
        "name": row.get("name"),
        "employee": row.get("employee") or "",
        "employee_name": row.get("employee_name") or "",
        "shift_type": row.get("shift_type") or "",
        "from_date": str(row.get("from_date") or ""),
        "to_date": str(row.get("to_date") or ""),
        "status": row.get("status") or "",
        "reason": row.get("reason") or "",
        "docstatus": int(row.get("docstatus") or 0),
    }

def _leave_is_cancellable(row: dict) -> bool:
    # ERPNext only allows cancelling a submitted application that is not
    # already cancelled/rejected.
    return int(row.get("docstatus") or 0) == 1 and row.get("status") not in {
        "Cancelled",
        "Rejected",
    }

def _leave_row(row: dict) -> dict:
    return {
        "name": row.get("name"),
        "leave_type": row.get("leave_type"),
        "from_date": str(row.get("from_date") or ""),
        "to_date": str(row.get("to_date") or ""),
        "status": row.get("status"),
        "total_leave_days": float(row.get("total_leave_days") or 0),
        "description": row.get("description") or "",
        "cancellable": _leave_is_cancellable(row),
    }

def _owned_leave(name: str) -> tuple[dict | None, dict | None]:
    """Fetch a leave application only if it belongs to the current employee.

    Returns (row, error). A missing/foreign record yields HR_LEAVE_NOT_FOUND
    so we never leak the existence of another employee's application.
    """
    employee, error = _employee_or_failure()
    if error:
        return None, error
    missing = _require_doctypes("Leave Application")
    if missing:
        return None, missing
    rows = frappe.get_list(
        "Leave Application",
        filters=[["name", "=", name], ["employee", "=", employee["name"]]],
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
        limit_page_length=1,
    )
    if not rows:
        return None, failure("Leave application not found.", code="HR_LEAVE_NOT_FOUND")
    return rows[0], None

ATTACHMENT_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "heic", "pdf"}

MAX_ATTACHMENT_BASE64_LENGTH = 7_000_000

def _owned_expense_claim(name: str) -> tuple[dict | None, dict | None]:
    employee, error = _employee_or_failure()
    if error:
        return None, error
    missing = _require_doctypes("Expense Claim")
    if missing:
        return None, missing
    rows = frappe.get_list(
        "Expense Claim",
        filters=[["name", "=", name], ["employee", "=", employee["name"]]],
        fields=["name"],
        limit_page_length=1,
    )
    if not rows:
        return None, failure("Expense claim not found.", code="HR_EXPENSE_NOT_FOUND")
    return rows[0], None

def _default_grievance_type() -> str:
    existing = frappe.get_list("Grievance Type", fields=["name"], limit_page_length=1)
    if existing:
        return existing[0]["name"]
    doc = frappe.get_doc(
        {
            "doctype": "Grievance Type",
            "name": "General",
            "description": "General grievance",
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name

def _owned_salary_slip(name: str) -> tuple[dict | None, dict | None]:
    employee, error = _employee_or_failure()
    if error:
        return None, error
    missing = _require_doctypes("Salary Slip")
    if missing:
        return None, missing
    rows = frappe.get_list(
        "Salary Slip",
        filters=[
            ["name", "=", name],
            ["employee", "=", employee["name"]],
            ["docstatus", "=", 1],
        ],
        fields=["name"],
        limit_page_length=1,
    )
    if not rows:
        return None, failure("Salary slip not found.", code="HR_SALARY_NOT_FOUND")
    return rows[0], None

def _owned_notification(name: str) -> tuple[dict | None, dict | None]:
    denied = _require_hr_role()
    if denied:
        return None, denied
    user = getattr(getattr(frappe, "session", None), "user", None)
    rows = frappe.get_list(
        "Notification Log",
        filters=[["name", "=", name], ["for_user", "=", user]],
        fields=_notification_fields(),
        limit_page_length=1,
    )
    if not rows:
        return None, failure("Notification not found.", code="HR_NOTIFICATION_NOT_FOUND")
    return rows[0], None

def _notification_fields() -> list[str]:
    return _existing_fields(
        "Notification Log",
        [
            "name",
            "subject",
            "email_content",
            "read",
            "creation",
            "document_type",
            "document_name",
            "type",
        ],
    )

def _notification_payload(row: dict) -> dict:
    title = row.get("subject") or "Notification"
    message = row.get("email_content") or ""
    reference_type = row.get("document_type") or ""
    reference_name = row.get("document_name") or ""
    category, route = _notification_category_route(reference_type, reference_name, title, message)
    return {
        "name": row.get("name"),
        "title": title,
        "message": message,
        "read": bool(row.get("read")),
        "date": str(row.get("creation") or ""),
        "reference_type": reference_type,
        "reference_name": reference_name,
        "category": category,
        "route": route,
    }

def _notification_category_route(
    reference_type: str, reference_name: str, title: str, message: str
) -> tuple[str, str]:
    reference = (reference_type or "").lower()
    reference_id = (reference_name or "").strip()
    text = f"{title or ''} {message or ''}".lower()
    approval_pending = (
        "approval pending" in text
        or "pending approval" in text
        or "requires approval" in text
        or "please approve" in text
    )
    if approval_pending:
        tab = {
            "leave application": "leave",
            "expense claim": "expenses",
            "shift request": "shift",
        }.get(reference, "today")
        focus = f"&focus={reference_id}" if reference_id else ""
        return "approvals", f"/manager?tab={tab}{focus}"
    if reference in {"salary slip", "payroll entry"} or "payslip" in text or "salary" in text:
        return "salary", "/salary"
    if (
        reference in {"employee checkin", "attendance"}
        or "check-in" in text
        or "check out" in text
        or "attendance" in text
    ):
        return "attendance", "/attendance"
    if reference in {
        "attendance request",
        "leave application",
        "compensatory leave request",
        "employee advance",
        "travel request",
        "shift request",
        "employee grievance",
        "timesheet",
    }:
        return "requests", "/requests"
    if reference == "expense claim":
        return "expenses", "/expenses"
    return "general", "/notifications"

def _current_user() -> str | None:
    return getattr(getattr(frappe, "session", None), "user", None)

def _direct_report_names() -> tuple[list[str], dict | None]:
    denied = _require_manager()
    if denied:
        return [], denied
    manager = _current_employee()
    if not manager:
        return [], failure(
            "No active Employee record is linked to this user.",
            code="HR_EMPLOYEE_NOT_FOUND",
        )
    reports = frappe.get_list(
        "Employee",
        filters=[["reports_to", "=", manager["name"]], ["status", "=", "Active"]],
        fields=["name"],
        limit_page_length=500,
    )
    return [row["name"] for row in reports], None

def _approval_aging() -> list[dict]:
    rows = frappe.get_list(
        "Leave Application",
        filters=[
            ["leave_approver", "=", _current_user()],
            ["docstatus", "=", 1],
            ["status", "=", "Open"],
        ],
        fields=["name", "employee_name", "from_date", "creation"],
        order_by="creation asc",
        limit_page_length=50,
    )
    return [
        {
            "doctype": "Leave Application",
            "name": row.get("name"),
            "employee_name": row.get("employee_name") or "",
            "date": str(row.get("from_date") or ""),
            "creation": str(row.get("creation") or ""),
        }
        for row in rows
    ]

def _assigned_approval(
    doctype: str,
    name: str,
    approver_field: str,
) -> tuple[dict | None, dict | None]:
    denied = _require_manager()
    if denied:
        return None, denied
    missing = _require_doctypes(doctype)
    if missing:
        return None, missing
    rows = frappe.get_list(
        doctype,
        filters=[["name", "=", name], [approver_field, "=", _current_user()]],
        fields=["name"],
        limit_page_length=1,
    )
    if not rows:
        return None, failure("Approval request not found.", code="HR_APPROVAL_NOT_FOUND")
    return rows[0], None

def _as_bool(value) -> bool:
    # Whitelisted args arrive as strings over HTTP, so "false"/"0" must be
    # treated as False rather than truthy non-empty strings.
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)

def _apply_decision(doc, comment: str | None) -> None:
    if comment:
        doc.add_comment("Comment", comment)
    doc.save(ignore_permissions=False)
    frappe.db.commit()

__all__ = [name for name in globals() if not name.startswith("__")]
