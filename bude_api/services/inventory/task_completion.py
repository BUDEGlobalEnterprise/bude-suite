"""Grouped inventory.warehouse_tasks endpoints: task_completion."""

from ._warehouse_tasks_shared import *  # noqa: F401,F403

def complete(
    todo_name: str, result_doctype: str | None = None, result_name: str | None = None
) -> dict:
    todo_name = (todo_name or "").strip()
    if not todo_name:
        return failure("todo_name is required.", code="VALIDATION_REQUIRED")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    try:
        visible = frappe.get_list(
            "ToDo",
            filters=[["name", "=", todo_name]],
            fields=["name"],
            limit=1,
        )
    except frappe.PermissionError:
        return permission_denied()
    if not visible:
        return failure(f"ToDo '{todo_name}' not found.", code="NOT_FOUND")

    try:
        doc = frappe.get_doc("ToDo", todo_name)
        doc.status = "Closed"
        note = _completion_note(result_doctype, result_name)
        if note:
            current = (doc.get("description") or "").strip()
            doc.description = f"{current}\n{note}".strip() if current else note
        doc.save(ignore_permissions=False)
    except frappe.PermissionError:
        frappe.db.rollback()
        return permission_denied()
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(_erpnext_message(exc), code="VALIDATION_ERPNEXT")

    return success({"name": todo_name, "status": "Closed"})
