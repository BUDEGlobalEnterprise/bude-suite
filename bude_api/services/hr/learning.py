"""Grouped mobile endpoints: learning."""

from ._mobile_shared import *  # noqa: F401,F403

def appraisals(limit: int = 20) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Appraisal")
    if missing:
        return missing
    rows = frappe.get_list(
        "Appraisal",
        filters=[["employee", "=", employee["name"]]],
        fields=[
            "name",
            "appraisal_cycle",
            "start_date",
            "end_date",
            "final_score",
            "total_score",
            "self_score",
            "remarks",
            "docstatus",
        ],
        order_by="start_date desc",
        limit_page_length=max(1, min(int(limit), 100)),
    )
    return success(
        [
            {
                "name": row.get("name"),
                "cycle": row.get("appraisal_cycle") or "",
                "start_date": str(row.get("start_date") or ""),
                "end_date": str(row.get("end_date") or ""),
                "final_score": float(row.get("final_score") or 0),
                "total_score": float(row.get("total_score") or 0),
                "self_score": float(row.get("self_score") or 0),
                "remarks": row.get("remarks") or "",
                "docstatus": int(row.get("docstatus") or 0),
            }
            for row in rows
        ]
    )

def training_events(limit: int = 50) -> dict:
    denied = _require_hr_role()
    if denied:
        return denied
    missing = _require_doctypes("Training Event")
    if missing:
        return missing
    rows = frappe.get_list(
        "Training Event",
        fields=[
            "name",
            "event_name",
            "training_program",
            "event_status",
            "type",
            "level",
            "location",
            "start_time",
            "end_time",
        ],
        order_by="start_time desc",
        limit_page_length=max(1, min(int(limit), 100)),
    )
    return success(
        [
            {
                "name": row.get("name"),
                "event_name": row.get("event_name") or row.get("name"),
                "program": row.get("training_program") or "",
                "status": row.get("event_status") or "",
                "type": row.get("type") or "",
                "level": row.get("level") or "",
                "location": row.get("location") or "",
                "start_time": str(row.get("start_time") or ""),
                "end_time": str(row.get("end_time") or ""),
            }
            for row in rows
        ]
    )

def onboarding_checklists(limit: int = 50, offset: int = 0) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    page_limit, page_offset = _page(limit, offset)
    data = []
    for doctype in ("Employee Onboarding", "Employee Separation"):
        missing = _require_doctypes(doctype)
        if missing:
            continue
        rows = frappe.get_list(
            doctype,
            filters=[["employee", "=", employee["name"]]],
            fields=["name", "employee", "employee_name", "boarding_status", "docstatus"],
            order_by="modified desc",
            limit_start=page_offset,
            limit_page_length=page_limit,
        )
        for row in rows:
            activities = frappe.get_list(
                "Employee Boarding Activity",
                filters=[["parent", "=", row["name"]]],
                fields=[
                    "name",
                    "activity_name",
                    "role",
                    "user",
                    "required_for_employee_creation",
                    "status",
                ],
                limit_page_length=100,
            )
            data.append(
                {
                    "doctype": doctype,
                    "name": row.get("name"),
                    "status": row.get("boarding_status") or "",
                    "docstatus": int(row.get("docstatus") or 0),
                    "activities": [
                        {
                            "name": item.get("name") or "",
                            "activity_name": item.get("activity_name") or "",
                            "role": item.get("role") or "",
                            "user": item.get("user") or "",
                            "status": item.get("status") or "",
                        }
                        for item in activities
                    ],
                }
            )
    return success(data)

def complete_onboarding_activity(parent_doctype: str, parent_name: str, activity_name: str) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    if parent_doctype not in {"Employee Onboarding", "Employee Separation"}:
        return failure("Unsupported checklist type.", code="VALIDATION_BAD_DOCTYPE")
    missing = _require_doctypes(parent_doctype, "Employee Boarding Activity")
    if missing:
        return missing
    rows = frappe.get_list(
        parent_doctype,
        filters=[["name", "=", parent_name], ["employee", "=", employee["name"]]],
        fields=["name"],
        limit_page_length=1,
    )
    if not rows:
        return failure("Checklist not found.", code="HR_CHECKLIST_NOT_FOUND")
    doc = frappe.get_doc(parent_doctype, parent_name)
    activity = None
    for row in doc.get("activities") or []:
        if row.get("name") == activity_name or row.get("activity_name") == activity_name:
            activity = row
            break
    if not activity:
        return failure("Checklist activity not found.", code="HR_CHECKLIST_ACTIVITY_NOT_FOUND")
    if isinstance(activity, dict):
        activity["status"] = "Completed"
    else:
        activity.status = "Completed"
    doc.save(ignore_permissions=False)
    frappe.db.commit()
    return success(
        {
            "doctype": parent_doctype,
            "name": parent_name,
            "activity_name": activity.get("activity_name") or activity_name,
            "status": activity.get("status") or "Completed",
        }
    )
