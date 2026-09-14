"""Grouped mobile endpoints: expenses."""

from ._mobile_shared import *  # noqa: F401,F403

def expense_claims(limit: int = 50) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Expense Claim")
    if missing:
        return missing
    page_limit, _ = _page(limit, 0, cap=100)
    rows = frappe.get_list(
        "Expense Claim",
        filters=[["employee", "=", employee["name"]]],
        fields=["name", "status", "total_claimed_amount", "posting_date"],
        order_by="modified desc",
        limit_page_length=page_limit,
    )
    return success(
        [
            {
                "name": str(row.get("name") or ""),
                "status": str(row.get("status") or ""),
                "total_claimed_amount": float(row.get("total_claimed_amount") or 0),
                "posting_date": str(row.get("posting_date") or ""),
            }
            for row in rows
        ]
    )

def submit_expense_claim(
    expense_type: str,
    amount: float,
    description: str | None = None,
    posting_date: str | None = None,
) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Expense Claim")
    if missing:
        return missing
    if not expense_type or float(amount or 0) <= 0:
        return failure("expense_type and positive amount are required.", code="VALIDATION_REQUIRED")
    try:
        doc = frappe.get_doc(
            {
                "doctype": "Expense Claim",
                "employee": employee["name"],
                "company": employee.get("company"),
                "posting_date": posting_date,
                "expenses": [
                    {
                        "expense_type": expense_type,
                        "amount": amount,
                        "sanctioned_amount": amount,
                        "description": description,
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

def expense_types() -> dict:
    denied = _require_hr_role()
    if denied:
        return denied
    missing = _require_doctypes("Expense Claim Type")
    if missing:
        return missing
    rows = frappe.get_list(
        "Expense Claim Type",
        fields=["name"],
        order_by="name asc",
        limit_page_length=200,
    )
    return success([row.get("name") for row in rows])

def expense_claim_detail(name: str) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Expense Claim", "Expense Claim Detail")
    if missing:
        return missing
    rows = frappe.get_list(
        "Expense Claim",
        filters=[["name", "=", name], ["employee", "=", employee["name"]]],
        fields=[
            "name",
            "status",
            "approval_status",
            "posting_date",
            "total_claimed_amount",
            "total_sanctioned_amount",
        ],
        limit_page_length=1,
    )
    if not rows:
        return failure("Expense claim not found.", code="HR_EXPENSE_NOT_FOUND")
    claim = rows[0]
    lines = frappe.get_list(
        "Expense Claim Detail",
        filters=[["parent", "=", name]],
        fields=["expense_type", "amount", "sanctioned_amount", "description"],
        limit_page_length=100,
    )
    return success(
        {
            "name": claim.get("name"),
            "status": claim.get("status"),
            "approval_status": claim.get("approval_status"),
            "posting_date": str(claim.get("posting_date") or ""),
            "total_claimed_amount": float(claim.get("total_claimed_amount") or 0),
            "total_sanctioned_amount": float(claim.get("total_sanctioned_amount") or 0),
            "expenses": [
                {
                    "expense_type": line.get("expense_type"),
                    "amount": float(line.get("amount") or 0),
                    "sanctioned_amount": float(line.get("sanctioned_amount") or 0),
                    "description": line.get("description") or "",
                }
                for line in lines
            ],
        }
    )

def upload_expense_attachment(
    claim_name: str,
    file_name: str,
    content_base64: str,
) -> dict:
    extension = (file_name or "").rsplit(".", 1)[-1].lower()
    if not file_name or "." not in file_name or extension not in ATTACHMENT_EXTENSIONS:
        return failure(
            "A receipt file name ending in jpg, jpeg, png, webp, heic, or pdf is required.",
            code="VALIDATION_REQUIRED",
        )
    if not content_base64 or len(content_base64) > MAX_ATTACHMENT_BASE64_LENGTH:
        return failure(
            "Attachment content is missing or larger than 5MB.",
            code="VALIDATION_REQUIRED",
        )
    claim, error = _owned_expense_claim(claim_name)
    if error:
        return error
    try:
        doc = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": file_name,
                "attached_to_doctype": "Expense Claim",
                "attached_to_name": claim["name"],
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

def expense_attachments(claim_name: str, limit: int = 20) -> dict:
    claim, error = _owned_expense_claim(claim_name)
    if error:
        return error
    rows = frappe.get_list(
        "File",
        filters=[
            ["attached_to_doctype", "=", "Expense Claim"],
            ["attached_to_name", "=", claim["name"]],
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

def employee_advances(limit: int = 50) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Employee Advance")
    if missing:
        return missing
    rows = frappe.get_list(
        "Employee Advance",
        filters=[["employee", "=", employee["name"]]],
        fields=[
            "name",
            "posting_date",
            "purpose",
            "advance_amount",
            "paid_amount",
            "claimed_amount",
            "status",
            "docstatus",
        ],
        order_by="posting_date desc",
        limit_page_length=max(1, min(int(limit), 100)),
    )
    return success(
        [
            {
                "name": row.get("name"),
                "posting_date": str(row.get("posting_date") or ""),
                "purpose": row.get("purpose") or "",
                "advance_amount": float(row.get("advance_amount") or 0),
                "paid_amount": float(row.get("paid_amount") or 0),
                "claimed_amount": float(row.get("claimed_amount") or 0),
                "status": row.get("status") or "",
                "docstatus": int(row.get("docstatus") or 0),
            }
            for row in rows
        ]
    )

def apply_employee_advance(
    amount: float,
    purpose: str,
    posting_date: str | None = None,
) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Employee Advance")
    if missing:
        return missing
    if float(amount or 0) <= 0 or not purpose:
        return failure("amount and purpose are required.", code="VALIDATION_REQUIRED")
    try:
        doc = frappe.get_doc(
            {
                "doctype": "Employee Advance",
                "employee": employee["name"],
                "company": employee.get("company"),
                "posting_date": posting_date or frappe.utils.today(),
                "advance_amount": amount,
                "purpose": purpose,
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

def manager_pending_expenses(limit: int = 50) -> dict:
    denied = _require_manager()
    if denied:
        return denied
    missing = _require_doctypes("Expense Claim")
    if missing:
        return missing
    rows = frappe.get_list(
        "Expense Claim",
        filters=[
            ["expense_approver", "=", _current_user()],
            ["approval_status", "=", "Draft"],
        ],
        fields=[
            "name",
            "employee",
            "employee_name",
            "total_claimed_amount",
            "posting_date",
        ],
        order_by="posting_date asc",
        limit_page_length=max(1, min(int(limit), 100)),
    )
    return success(
        [
            {
                "name": row.get("name"),
                "employee": row.get("employee"),
                "employee_name": row.get("employee_name"),
                "total_claimed_amount": float(row.get("total_claimed_amount") or 0),
                "posting_date": str(row.get("posting_date") or ""),
            }
            for row in rows
        ]
    )

def decide_expense(name: str, approved: bool, comment: str | None = None) -> dict:
    _, error = _assigned_approval("Expense Claim", name, "expense_approver")
    if error:
        return error
    status = "Approved" if _as_bool(approved) else "Rejected"
    try:
        doc = frappe.get_doc("Expense Claim", name)
        doc.approval_status = status
        _apply_decision(doc, comment)
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(str(exc), code="VALIDATION_ERPNEXT")
    return success({"name": name, "approval_status": status})
