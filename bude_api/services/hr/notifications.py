"""Grouped mobile endpoints: notifications."""

from ._mobile_shared import *  # noqa: F401,F403

def notifications(limit: int = 50) -> dict:
    denied = _require_hr_role()
    if denied:
        return denied
    user = getattr(getattr(frappe, "session", None), "user", None)
    fields = _notification_fields()
    rows = frappe.get_list(
        "Notification Log",
        filters=[["for_user", "=", user]],
        fields=fields,
        order_by="creation desc",
        limit_page_length=max(1, min(int(limit), 100)),
    )
    return success([_notification_payload(row) for row in rows])

def notification_detail(name: str) -> dict:
    row, error = _owned_notification(name)
    if error:
        return error
    return success(_notification_payload(row))

def mark_notification_read(name: str) -> dict:
    row, error = _owned_notification(name)
    if error:
        return error
    try:
        frappe.db.set_value("Notification Log", name, "read", 1)
        frappe.db.commit()
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    return success({"name": name, "read": True})

def register_push_token(token: str, platform: str = "", device_id: str = "") -> dict:
    denied = _require_hr_role()
    if denied:
        return denied
    missing = _require_doctypes("Bude HR Push Token")
    if missing:
        return missing
    token = (token or "").strip()
    platform = (platform or "").strip()[:40]
    device_id = (device_id or "").strip()[:140]
    if not token:
        return failure("Push token is required.", code="HR_PUSH_TOKEN_REQUIRED")
    user = _current_user()
    employee = _current_employee()
    if not employee:
        return failure(
            "No active Employee record is linked to this user.", code="HR_EMPLOYEE_NOT_FOUND"
        )
    existing = frappe.get_list(
        "Bude HR Push Token",
        filters=[["user", "=", user], ["token", "=", token]],
        fields=["name"],
        limit_page_length=1,
    )
    try:
        if existing:
            doc = frappe.get_doc("Bude HR Push Token", existing[0]["name"])
            doc.employee = employee.get("name")
            doc.platform = platform
            doc.device_id = device_id
            doc.enabled = 1
            doc.save(ignore_permissions=False)
            name = doc.name
        else:
            doc = frappe.get_doc(
                {
                    "doctype": "Bude HR Push Token",
                    "user": user,
                    "employee": employee.get("name"),
                    "token": token,
                    "platform": platform,
                    "device_id": device_id,
                    "enabled": 1,
                }
            )
            doc.insert(ignore_permissions=False)
            name = doc.name
        frappe.db.commit()
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(str(exc), code="VALIDATION_ERROR")
    return success({"name": name, "registered": True})

def clear_push_token(token: str = "", device_id: str = "") -> dict:
    denied = _require_hr_role()
    if denied:
        return denied
    missing = _require_doctypes("Bude HR Push Token")
    if missing:
        return missing
    user = _current_user()
    filters = [["user", "=", user]]
    token = (token or "").strip()
    device_id = (device_id or "").strip()[:140]
    if token:
        filters.append(["token", "=", token])
    elif device_id:
        filters.append(["device_id", "=", device_id])
    else:
        return failure("Push token or device id is required.", code="HR_PUSH_TOKEN_REQUIRED")
    rows = frappe.get_list(
        "Bude HR Push Token",
        filters=filters,
        fields=["name"],
        limit_page_length=20,
    )
    cleared = 0
    try:
        for row in rows:
            frappe.db.set_value("Bude HR Push Token", row["name"], "enabled", 0)
            cleared += 1
        frappe.db.commit()
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    return success({"cleared": cleared})
