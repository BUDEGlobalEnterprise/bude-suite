"""Grouped mobile endpoints: profile."""

from datetime import date, datetime, timedelta

from ._mobile_shared import *  # noqa: F401,F403

_CAREER_PROPERTIES = {
    "designation": "Designation",
    "department": "Department",
    "branch": "Branch",
    "grade": "Grade",
    "reports_to": "Reports To",
    "employment_type": "Employment Type",
    "job_title": "Job Title",
    "company": "Company",
}


def profile() -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    fields = [
        "name",
        "employee_name",
        "company",
        "department",
        "designation",
        "date_of_joining",
        "reports_to",
        "cell_number",
        "personal_email",
        "company_email",
        "emergency_phone_number",
        "person_to_be_contacted",
        "relation",
        "user_id",
    ]
    fields.extend(
        _existing_fields(
            "Employee",
            [
                "status",
                "employee_number",
                "branch",
                "holiday_list",
                "prefered_email",
                "current_address",
                "permanent_address",
                "contract_end_date",
                "notice_number_of_days",
                "scheduled_confirmation_date",
                "final_confirmation_date",
                "date_of_retirement",
                "resignation_letter_date",
                "relieving_date",
            ],
        )
    )
    rows = frappe.get_list(
        "Employee",
        filters=[["name", "=", employee["name"]]],
        fields=list(dict.fromkeys(fields)),
        limit_page_length=1,
    )
    detail = dict(rows[0] if rows else employee)
    detail["education"] = _employee_child_rows(
        employee["name"],
        "Employee Education",
        [
            "school_univ",
            "qualification",
            "level",
            "year_of_passing",
            "class_per",
            "maj_opt_subj",
        ],
    )
    detail["internal_work_history"] = _employee_child_rows(
        employee["name"],
        "Employee Internal Work History",
        ["branch", "department", "designation", "from_date", "to_date"],
    )
    detail["external_work_history"] = _employee_child_rows(
        employee["name"],
        "Employee External Work History",
        ["company_name", "designation", "total_experience"],
    )
    detail["skills"] = _employee_skills(employee["name"])
    detail["trainings"] = _employee_trainings(employee["name"])
    detail["upcoming_training"] = _employee_upcoming_training(employee["name"])
    detail["current_appraisal"] = _employee_current_appraisal(employee["name"])
    detail["promotions"] = _employee_promotions(employee["name"])
    detail["transfers"] = _employee_transfers(employee["name"])
    detail["separations"] = _employee_separations(employee["name"])
    detail["employee_groups"] = _employee_groups(employee["name"])
    detail["leave_blocks"] = _employee_leave_blocks(detail)
    return success(detail)


def _employee_child_rows(
    employee: str,
    doctype: str,
    fields: list[str],
) -> list[dict]:
    """Read optional standard Employee child tables without exposing private fields."""
    try:
        exists = frappe.db.exists("DocType", doctype)
    except Exception:
        return []
    if not isinstance(exists, (bool, str)) or not exists:
        return []
    available_fields = _existing_fields(doctype, fields)
    if not available_fields:
        return []
    try:
        rows = frappe.get_list(
            doctype,
            filters=[
                ["parent", "=", employee],
                ["parenttype", "=", "Employee"],
            ],
            fields=available_fields,
            order_by="idx asc",
            limit_page_length=100,
        )
    except Exception:
        return []
    return [{field: row.get(field) for field in available_fields} for row in rows]


def _employee_skills(employee: str) -> list[dict]:
    """Read optional standard HRMS skill map records for this employee."""
    try:
        if not frappe.db.exists("DocType", "Employee Skill Map"):
            return []
        if not frappe.db.exists("DocType", "Employee Skill"):
            return []
        maps = frappe.get_list(
            "Employee Skill Map",
            filters=[["employee", "=", employee]],
            fields=["name"],
            limit_page_length=1,
        )
        if not maps:
            return []
        fields = _existing_fields(
            "Employee Skill",
            ["skill", "proficiency", "evaluation_date"],
        )
        rows = frappe.get_list(
            "Employee Skill",
            filters=[
                ["parent", "=", maps[0]["name"]],
                ["parenttype", "=", "Employee Skill Map"],
            ],
            fields=fields,
            order_by="idx asc",
            limit_page_length=100,
        )
    except Exception:
        return []
    return [{field: row.get(field) for field in fields} for row in rows]


def _employee_trainings(employee: str) -> list[dict]:
    """Read standard Employee Training rows linked through Employee Skill Map."""
    try:
        if not frappe.db.exists("DocType", "Employee Skill Map"):
            return []
        if not frappe.db.exists("DocType", "Employee Training"):
            return []
        maps = frappe.get_list(
            "Employee Skill Map",
            filters=[["employee", "=", employee]],
            fields=["name"],
            limit_page_length=1,
        )
        if not maps:
            return []
        fields = _existing_fields(
            "Employee Training",
            ["training", "training_date"],
        )
        if not fields:
            return []
        rows = frappe.get_list(
            "Employee Training",
            filters=[
                ["parent", "=", maps[0]["name"]],
                ["parenttype", "=", "Employee Skill Map"],
            ],
            fields=fields,
            order_by="training_date desc, idx asc",
            limit_page_length=100,
        )
    except Exception:
        return []
    return [{field: row.get(field) for field in fields} for row in rows]


def _employee_upcoming_training(employee: str) -> list[dict]:
    """Return scheduled standard Training Events assigned to this employee."""
    try:
        if not frappe.db.exists("DocType", "Training Event Employee"):
            return []
        if not frappe.db.exists("DocType", "Training Event"):
            return []
        attendee_fields = _existing_fields(
            "Training Event Employee",
            ["parent", "status", "attendance", "is_mandatory"],
        )
        if "parent" not in attendee_fields:
            return []
        attendees = frappe.get_list(
            "Training Event Employee",
            filters=[
                ["employee", "=", employee],
                ["parenttype", "=", "Training Event"],
            ],
            fields=attendee_fields,
            order_by="idx asc",
            limit_page_length=100,
            ignore_permissions=True,
        )
        event_names = [row.get("parent") for row in attendees if row.get("parent")]
        if not event_names:
            return []
        event_fields = _existing_fields(
            "Training Event",
            [
                "name",
                "event_name",
                "training_program",
                "event_status",
                "type",
                "level",
                "course",
                "location",
                "start_time",
                "end_time",
                "trainer_name",
                "has_certificate",
            ],
        )
        try:
            now_value = str(frappe.utils.now_datetime())
        except Exception:
            now_value = datetime.now().isoformat(sep=" ")
        events = frappe.get_list(
            "Training Event",
            filters=[
                ["name", "in", event_names],
                ["event_status", "=", "Scheduled"],
                ["start_time", ">=", now_value],
            ],
            fields=event_fields,
            order_by="start_time asc",
            limit_page_length=20,
            ignore_permissions=True,
        )
    except Exception:
        return []
    attendee_by_event = {row.get("parent"): row for row in attendees}
    result = []
    for event in events:
        attendee = attendee_by_event.get(event.get("name"), {})
        result.append(
            {
                "name": event.get("name") or "",
                "event_name": event.get("event_name") or event.get("name") or "",
                "training_program": event.get("training_program") or "",
                "event_status": event.get("event_status") or "",
                "type": event.get("type") or "",
                "level": event.get("level") or "",
                "course": event.get("course") or "",
                "location": event.get("location") or "",
                "start_time": str(event.get("start_time") or ""),
                "end_time": str(event.get("end_time") or ""),
                "trainer_name": event.get("trainer_name") or "",
                "has_certificate": bool(event.get("has_certificate")),
                "attendee_status": attendee.get("status") or "",
                "attendance": attendee.get("attendance") or "",
                "is_mandatory": bool(attendee.get("is_mandatory")),
            }
        )
    return result


def _employee_current_appraisal(employee: str) -> dict:
    """Return the latest standard appraisal and privacy-safe manual goals."""
    try:
        if not frappe.db.exists("DocType", "Appraisal"):
            return {}
        rows = frappe.get_list(
            "Appraisal",
            filters=[["employee", "=", employee], ["docstatus", "!=", 2]],
            fields=_existing_fields(
                "Appraisal",
                [
                    "name",
                    "appraisal_cycle",
                    "start_date",
                    "end_date",
                    "total_score",
                    "goal_score_percentage",
                    "self_score",
                    "final_score",
                    "rate_goals_manually",
                ],
            ),
            order_by="end_date desc, creation desc",
            limit_page_length=1,
            ignore_permissions=True,
        )
        if not rows:
            return {}
        appraisal = rows[0]
        goals = []
        if frappe.db.exists("DocType", "Appraisal Goal"):
            goals = frappe.get_list(
                "Appraisal Goal",
                filters=[
                    ["parent", "=", appraisal.get("name")],
                    ["parenttype", "=", "Appraisal"],
                ],
                fields=_existing_fields(
                    "Appraisal Goal",
                    ["kra", "per_weightage", "score", "score_earned"],
                ),
                order_by="idx asc",
                limit_page_length=100,
                ignore_permissions=True,
            )
    except Exception:
        return {}
    return {
        "name": appraisal.get("name") or "",
        "appraisal_cycle": appraisal.get("appraisal_cycle") or "",
        "start_date": str(appraisal.get("start_date") or ""),
        "end_date": str(appraisal.get("end_date") or ""),
        "total_score": float(appraisal.get("total_score") or 0),
        "goal_score_percentage": float(
            appraisal.get("goal_score_percentage") or 0
        ),
        "self_score": float(appraisal.get("self_score") or 0),
        "final_score": float(appraisal.get("final_score") or 0),
        "goals": [
            {
                "goal": row.get("kra") or "",
                "weightage": float(row.get("per_weightage") or 0),
                "score": float(row.get("score") or 0),
                "score_earned": float(row.get("score_earned") or 0),
            }
            for row in goals
        ],
    }


def _employee_promotions(employee: str) -> list[dict]:
    """Return submitted promotions with only privacy-safe career changes."""
    try:
        if not frappe.db.exists("DocType", "Employee Promotion"):
            return []
        promotions = frappe.get_list(
            "Employee Promotion",
            filters=[["employee", "=", employee], ["docstatus", "=", 1]],
            fields=_existing_fields(
                "Employee Promotion",
                ["name", "promotion_date", "company"],
            ),
            order_by="promotion_date desc, creation desc",
            limit_page_length=20,
            ignore_permissions=True,
        )
    except Exception:
        return []
    if not promotions:
        return []

    child_exists = False
    try:
        child_exists = bool(
            frappe.db.exists("DocType", "Employee Property History")
        )
    except Exception:
        child_exists = False
    result = []
    for promotion in promotions:
        changes = []
        if child_exists:
            try:
                rows = frappe.get_list(
                    "Employee Property History",
                    filters=[
                        ["parent", "=", promotion.get("name")],
                        ["parenttype", "=", "Employee Promotion"],
                    ],
                    fields=_existing_fields(
                        "Employee Property History",
                        ["property", "fieldname", "current", "new"],
                    ),
                    order_by="idx asc",
                    limit_page_length=100,
                    ignore_permissions=True,
                )
            except Exception:
                rows = []
            for row in rows:
                fieldname = str(row.get("fieldname") or "").strip()
                if fieldname not in _CAREER_PROPERTIES:
                    continue
                changes.append(
                    {
                        "field": fieldname,
                        "label": row.get("property")
                        or _CAREER_PROPERTIES[fieldname],
                        "from": row.get("current") or "",
                        "to": row.get("new") or "",
                    }
                )
        result.append(
            {
                "name": promotion.get("name") or "",
                "promotion_date": str(promotion.get("promotion_date") or ""),
                "company": promotion.get("company") or "",
                "changes": changes,
            }
        )
    return result


def _employee_transfers(employee: str) -> list[dict]:
    """Return submitted transfers with only privacy-safe career changes."""
    try:
        if not frappe.db.exists("DocType", "Employee Transfer"):
            return []
        transfers = frappe.get_list(
            "Employee Transfer",
            filters=[["employee", "=", employee], ["docstatus", "=", 1]],
            fields=_existing_fields(
                "Employee Transfer",
                [
                    "name",
                    "transfer_date",
                    "company",
                    "new_company",
                    "new_employee_id",
                ],
            ),
            order_by="transfer_date desc, creation desc",
            limit_page_length=20,
            ignore_permissions=True,
        )
    except Exception:
        return []
    if not transfers:
        return []

    try:
        child_exists = bool(
            frappe.db.exists("DocType", "Employee Property History")
        )
    except Exception:
        child_exists = False
    result = []
    for transfer in transfers:
        changes = []
        if child_exists:
            try:
                rows = frappe.get_list(
                    "Employee Property History",
                    filters=[
                        ["parent", "=", transfer.get("name")],
                        ["parenttype", "=", "Employee Transfer"],
                    ],
                    fields=_existing_fields(
                        "Employee Property History",
                        ["property", "fieldname", "current", "new"],
                    ),
                    order_by="idx asc",
                    limit_page_length=100,
                    ignore_permissions=True,
                )
            except Exception:
                rows = []
            for row in rows:
                fieldname = str(row.get("fieldname") or "").strip()
                if fieldname not in _CAREER_PROPERTIES:
                    continue
                changes.append(
                    {
                        "field": fieldname,
                        "label": row.get("property")
                        or _CAREER_PROPERTIES[fieldname],
                        "from": row.get("current") or "",
                        "to": row.get("new") or "",
                    }
                )
        result.append(
            {
                "name": transfer.get("name") or "",
                "transfer_date": str(transfer.get("transfer_date") or ""),
                "company": transfer.get("company") or "",
                "new_company": transfer.get("new_company") or "",
                "new_employee_id": transfer.get("new_employee_id") or "",
                "changes": changes,
            }
        )
    return result


def _employee_separations(employee: str) -> list[dict]:
    """Return offboarding progress without interviews or assignee details."""
    try:
        if not frappe.db.exists("DocType", "Employee Separation"):
            return []
        separations = frappe.get_list(
            "Employee Separation",
            filters=[["employee", "=", employee], ["docstatus", "!=", 2]],
            fields=_existing_fields(
                "Employee Separation",
                [
                    "name",
                    "resignation_letter_date",
                    "boarding_begins_on",
                    "boarding_status",
                    "employee_separation_template",
                    "company",
                ],
            ),
            order_by="boarding_begins_on desc, creation desc",
            limit_page_length=10,
            ignore_permissions=True,
        )
    except Exception:
        return []
    if not separations:
        return []

    activity_exists = False
    task_exists = False
    try:
        activity_exists = bool(
            frappe.db.exists("DocType", "Employee Boarding Activity")
        )
        task_exists = bool(frappe.db.exists("DocType", "Task"))
    except Exception:
        pass
    result = []
    for separation in separations:
        activities = []
        if activity_exists:
            try:
                rows = frappe.get_list(
                    "Employee Boarding Activity",
                    filters=[
                        ["parent", "=", separation.get("name")],
                        ["parenttype", "=", "Employee Separation"],
                    ],
                    fields=_existing_fields(
                        "Employee Boarding Activity",
                        [
                            "activity_name",
                            "task",
                            "task_weight",
                            "begin_on",
                            "duration",
                        ],
                    ),
                    order_by="idx asc",
                    limit_page_length=100,
                    ignore_permissions=True,
                )
            except Exception:
                rows = []
            task_names = [row.get("task") for row in rows if row.get("task")]
            task_by_name = {}
            if task_exists and task_names:
                try:
                    task_rows = frappe.get_list(
                        "Task",
                        filters=[["name", "in", task_names]],
                        fields=_existing_fields(
                            "Task",
                            ["name", "status", "progress", "exp_end_date"],
                        ),
                        limit_page_length=len(task_names),
                        ignore_permissions=True,
                    )
                except Exception:
                    task_rows = []
                task_by_name = {
                    str(row.get("name") or ""): row for row in task_rows
                }
            for row in rows:
                task = task_by_name.get(str(row.get("task") or ""), {})
                activities.append(
                    {
                        "activity": row.get("activity_name") or "",
                        "task": row.get("task") or "",
                        "status": task.get("status") or "",
                        "progress": float(task.get("progress") or 0),
                        "due_date": str(task.get("exp_end_date") or ""),
                        "weight": float(row.get("task_weight") or 0),
                        "begin_on": int(row.get("begin_on") or 0),
                        "duration": int(row.get("duration") or 0),
                    }
                )
        completed = sum(
            row["status"] in {"Completed", "Cancelled"}
            or row["progress"] >= 100
            for row in activities
        )
        result.append(
            {
                "name": separation.get("name") or "",
                "resignation_date": str(
                    separation.get("resignation_letter_date") or ""
                ),
                "begins_on": str(
                    separation.get("boarding_begins_on") or ""
                ),
                "status": separation.get("boarding_status") or "",
                "template": separation.get(
                    "employee_separation_template"
                )
                or "",
                "company": separation.get("company") or "",
                "activities": activities,
                "completed_activities": completed,
                "total_activities": len(activities),
            }
        )
    return result


def _employee_groups(employee: str) -> list[dict]:
    """Return Employee Group memberships without exposing coworker identities."""
    try:
        if not frappe.db.exists("DocType", "Employee Group"):
            return []
        if not frappe.db.exists("DocType", "Employee Group Table"):
            return []
        link_fields = _existing_fields(
            "Employee Group Table",
            ["parent", "employee"],
        )
        if "parent" not in link_fields:
            return []
        links = frappe.get_list(
            "Employee Group Table",
            filters=[
                ["employee", "=", employee],
                ["parenttype", "=", "Employee Group"],
            ],
            fields=link_fields,
            order_by="idx asc",
            limit_page_length=100,
            ignore_permissions=True,
        )
        group_names = list(
            dict.fromkeys(
                str(row.get("parent") or "")
                for row in links
                if row.get("parent")
            )
        )
        if not group_names:
            return []
        groups = frappe.get_list(
            "Employee Group",
            filters=[["name", "in", group_names]],
            fields=_existing_fields(
                "Employee Group",
                ["name", "employee_group_name"],
            ),
            limit_page_length=len(group_names),
            ignore_permissions=True,
        )
        membership_rows = frappe.get_list(
            "Employee Group Table",
            filters=[
                ["parent", "in", group_names],
                ["parenttype", "=", "Employee Group"],
            ],
            fields=["parent"],
            limit_page_length=5000,
            ignore_permissions=True,
        )
    except Exception:
        return []
    member_counts: dict[str, int] = {}
    for row in membership_rows:
        parent = str(row.get("parent") or "")
        member_counts[parent] = member_counts.get(parent, 0) + 1
    by_name = {str(row.get("name") or ""): row for row in groups}
    return [
        {
            "name": name,
            "group_name": by_name.get(name, {}).get("employee_group_name")
            or name,
            "member_count": member_counts.get(name, 0),
        }
        for name in group_names
    ]


def _employee_leave_blocks(employee: dict) -> list[dict]:
    """Return upcoming applicable leave blocks, honoring user allow lists."""
    required = [
        "Leave Block List",
        "Leave Block List Date",
        "Leave Block List Allow",
    ]
    try:
        if any(not frappe.db.exists("DocType", row) for row in required):
            return []
        company = str(employee.get("company") or "")
        department = str(employee.get("department") or "")
        user = str(employee.get("user_id") or "")
        list_names: list[str] = []
        if company:
            global_lists = frappe.get_list(
                "Leave Block List",
                filters=[
                    ["company", "=", company],
                    ["applies_to_all_departments", "=", 1],
                ],
                fields=_existing_fields(
                    "Leave Block List",
                    [
                        "name",
                        "leave_block_list_name",
                        "company",
                        "leave_type",
                    ],
                ),
                limit_page_length=100,
                ignore_permissions=True,
            )
        else:
            global_lists = []
        list_by_name = {
            str(row.get("name") or ""): row
            for row in global_lists
            if row.get("name")
        }
        list_names.extend(list_by_name)
        if department and frappe.db.exists("DocType", "Department"):
            department_rows = frappe.get_list(
                "Department",
                filters=[["name", "=", department]],
                fields=_existing_fields(
                    "Department",
                    ["name", "leave_block_list"],
                ),
                limit_page_length=1,
                ignore_permissions=True,
            )
            department_list = (
                str(department_rows[0].get("leave_block_list") or "")
                if department_rows
                else ""
            )
            if department_list and department_list not in list_names:
                department_lists = frappe.get_list(
                    "Leave Block List",
                    filters=[["name", "=", department_list]],
                    fields=_existing_fields(
                        "Leave Block List",
                        [
                            "name",
                            "leave_block_list_name",
                            "company",
                            "leave_type",
                        ],
                    ),
                    limit_page_length=1,
                    ignore_permissions=True,
                )
                if department_lists:
                    list_by_name[department_list] = department_lists[0]
                    list_names.append(department_list)
        if not list_names:
            return []
        if user:
            allowed_rows = frappe.get_list(
                "Leave Block List Allow",
                filters=[
                    ["parent", "in", list_names],
                    ["parenttype", "=", "Leave Block List"],
                    ["allow_user", "=", user],
                ],
                fields=_existing_fields(
                    "Leave Block List Allow",
                    ["parent", "allow_user"],
                ),
                limit_page_length=100,
                ignore_permissions=True,
            )
            allowed = {
                str(row.get("parent") or "")
                for row in allowed_rows
                if row.get("parent")
            }
            list_names = [name for name in list_names if name not in allowed]
        if not list_names:
            return []
        start = date.today()
        end = start + timedelta(days=90)
        rows = frappe.get_list(
            "Leave Block List Date",
            filters=[
                ["parent", "in", list_names],
                ["parenttype", "=", "Leave Block List"],
                ["block_date", "between", [start.isoformat(), end.isoformat()]],
            ],
            fields=_existing_fields(
                "Leave Block List Date",
                ["parent", "block_date", "reason"],
            ),
            order_by="block_date asc, idx asc",
            limit_page_length=500,
            ignore_permissions=True,
        )
    except Exception:
        return []
    return [
        {
            "date": str(row.get("block_date") or ""),
            "reason": row.get("reason") or "",
            "list": list_by_name.get(str(row.get("parent") or ""), {}).get(
                "leave_block_list_name"
            )
            or row.get("parent")
            or "",
            "leave_type": list_by_name.get(
                str(row.get("parent") or ""), {}
            ).get("leave_type")
            or "",
        }
        for row in rows
        if row.get("block_date")
    ]


def employee_documents(limit: int = 50) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    rows = frappe.get_list(
        "File",
        filters=[
            ["attached_to_doctype", "=", "Employee"],
            ["attached_to_name", "=", employee["name"]],
        ],
        fields=["name", "file_name", "file_url", "is_private"],
        order_by="creation desc",
        limit_page_length=max(1, min(int(limit), 100)),
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
