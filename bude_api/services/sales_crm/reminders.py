"""Scheduled and event-driven CRM reminders using standard Frappe records."""

from __future__ import annotations

from datetime import date, datetime, timedelta

try:
    import frappe
except ImportError:  # pragma: no cover - bench runtime dependency
    frappe = None

from ..admin.notification_fanout import fan_out_notification_logs

FALSE_VALUES = {False, 0, "0", "false", "False", "no", "off"}
OPEN_TASK_STATUSES = ["Open", "Todo", "To Do", "Pending"]


def run_crm_reminders() -> dict:
    """Create each due reminder once and immediately attempt push fan-out."""
    if frappe is None or not _enabled():
        return {"created": 0, "skipped": 0, "delivery": None}

    now = _now()
    created = 0
    skipped = 0
    for reminder in [*_task_reminders(now), *_sla_reminders(), *_quotation_reminders(now.date())]:
        if _insert_once(reminder):
            created += 1
        else:
            skipped += 1

    delivery = fan_out_notification_logs(limit=200)
    return {"created": created, "skipped": skipped, "delivery": delivery}


def on_crm_record_update(doc, method=None) -> None:
    """Notify a newly assigned owner and record stage changes without dual-write."""
    if frappe is None or not _enabled() or not _active_doctype(doc.doctype):
        return
    before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
    if before is None:
        return

    owner_field, stage_field = _event_fields(doc.doctype)
    current_owner = _value(doc, owner_field)
    previous_owner = _value(before, owner_field)
    if current_owner and current_owner != previous_owner:
        _insert_once(
            {
                "for_user": current_owner,
                "subject": f"{_label(doc.doctype)} assigned: {doc.name}",
                "email_content": "A sales record was assigned to you.",
                "document_type": doc.doctype,
                "document_name": doc.name,
                "event_key": f"assignment:{doc.doctype}:{doc.name}:{current_owner}",
            }
        )

    current_stage = _value(doc, stage_field)
    previous_stage = _value(before, stage_field)
    if current_owner and current_stage and current_stage != previous_stage:
        _insert_once(
            {
                "for_user": current_owner,
                "subject": f"{_label(doc.doctype)} stage changed: {current_stage}",
                "email_content": f"{doc.name} moved from {previous_stage or 'Unspecified'} to {current_stage}.",
                "document_type": doc.doctype,
                "document_name": doc.name,
                "event_key": f"stage:{doc.doctype}:{doc.name}:{current_stage}",
            }
        )


def _task_reminders(now: datetime) -> list[dict]:
    provider = _provider()
    if provider == "frappe_crm" and _doctype_exists("CRM Task"):
        fields = ["name", "title", "assigned_to", "due_date", "status", "reference_doctype", "reference_docname"]
        rows = _safe_list(
            "CRM Task",
            fields,
            filters=[["status", "in", OPEN_TASK_STATUSES], ["due_date", "<=", now.date()]],
        )
        return [
            _reminder(
                row.get("assigned_to"),
                f"CRM task overdue: {row.get('title') or row.get('name')}",
                "A CRM task is due. Open Bude Sales to complete or reschedule it.",
                row.get("reference_doctype") or "CRM Task",
                row.get("reference_docname") or row.get("name"),
                f"task:{row.get('name')}:{_date_key(row.get('due_date'))}",
            )
            for row in rows
            if row.get("assigned_to")
        ]

    rows = _safe_list(
        "ToDo",
        ["name", "description", "allocated_to", "date", "status", "reference_type", "reference_name"],
        filters=[["status", "in", OPEN_TASK_STATUSES], ["date", "<=", now.date()]],
    )
    return [
        _reminder(
            row.get("allocated_to"),
            f"CRM task overdue: {row.get('description') or row.get('name')}",
            "A CRM task is due. Open Bude Sales to complete or reschedule it.",
            row.get("reference_type") or "ToDo",
            row.get("reference_name") or row.get("name"),
            f"task:{row.get('name')}:{_date_key(row.get('date'))}",
        )
        for row in rows
        if row.get("allocated_to")
    ]


def _sla_reminders() -> list[dict]:
    if _provider() != "frappe_crm" or not _doctype_exists("CRM Lead"):
        return []
    rows = _safe_list(
        "CRM Lead",
        ["name", "lead_name", "lead_owner", "owner", "sla_status"],
        filters=[["sla_status", "in", ["Failed", "Breached", "At Risk"]]],
    )
    today = _now().date().isoformat()
    return [
        _reminder(
            row.get("lead_owner") or row.get("owner"),
            f"Lead SLA breach: {row.get('lead_name') or row.get('name')}",
            "This lead needs attention to recover its response SLA.",
            "CRM Lead",
            row.get("name"),
            f"sla:{row.get('name')}:{today}",
        )
        for row in rows
        if row.get("lead_owner") or row.get("owner")
    ]


def _quotation_reminders(today: date) -> list[dict]:
    if not _doctype_exists("Quotation"):
        return []
    rows = _safe_list(
        "Quotation",
        ["name", "owner", "valid_till", "status", "party_name"],
        filters=[
            ["docstatus", "=", 1],
            ["status", "not in", ["Ordered", "Lost", "Cancelled"]],
            ["valid_till", "between", [today, today + timedelta(days=1)]],
        ],
    )
    return [
        _reminder(
            row.get("owner"),
            f"Quotation expiring: {row.get('name')}",
            f"Quotation for {row.get('party_name') or 'the customer'} expires by {row.get('valid_till')}.",
            "Quotation",
            row.get("name"),
            f"quotation:{row.get('name')}:{_date_key(row.get('valid_till'))}",
        )
        for row in rows
        if row.get("owner")
    ]


def _insert_once(reminder: dict) -> bool:
    if not reminder.get("for_user") or not reminder.get("document_name"):
        return False
    event_key = reminder.pop("event_key")
    cache_key = f"bude_api:crm:reminder:{event_key}"
    cache = frappe.cache()
    if cache.get_value(cache_key):
        return False
    existing = frappe.db.exists(
        "Notification Log",
        {
            "for_user": reminder["for_user"],
            "subject": reminder["subject"],
            "document_type": reminder["document_type"],
            "document_name": reminder["document_name"],
        },
    )
    if existing:
        cache.set_value(cache_key, 1, expires_in_sec=172800)
        return False
    doc = frappe.get_doc({"doctype": "Notification Log", "type": "Alert", **reminder})
    doc.insert(ignore_permissions=True)
    cache.set_value(cache_key, 1, expires_in_sec=172800)
    return True


def _reminder(user, subject, content, doctype, name, event_key) -> dict:
    return {
        "for_user": user,
        "subject": subject,
        "email_content": content,
        "document_type": doctype,
        "document_name": name,
        "event_key": event_key,
    }


def _safe_list(doctype, fields, filters) -> list[dict]:
    try:
        existing = _existing_fields(doctype, fields)
        return frappe.get_list(
            doctype,
            fields=existing,
            filters=filters,
            limit_page_length=500,
        )
    except Exception:
        return []


def _existing_fields(doctype, fields):
    try:
        meta = frappe.get_meta(doctype)
        return [field for field in fields if field == "name" or meta.has_field(field)]
    except Exception:
        return fields


def _enabled() -> bool:
    try:
        value = frappe.conf.get("bude_sales_crm_enabled")
    except Exception:
        return False
    return value is not None and value not in FALSE_VALUES


def _provider() -> str:
    try:
        return frappe.conf.get("bude_sales_crm_provider") or "erpnext"
    except Exception:
        return "erpnext"


def _active_doctype(doctype: str) -> bool:
    active = {"CRM Lead", "CRM Deal"} if _provider() == "frappe_crm" else {"Lead", "Opportunity"}
    return doctype in active


def _event_fields(doctype: str) -> tuple[str, str]:
    return {
        "Lead": ("lead_owner", "status"),
        "Opportunity": ("opportunity_owner", "sales_stage"),
        "CRM Lead": ("lead_owner", "status"),
        "CRM Deal": ("deal_owner", "status"),
    }[doctype]


def _doctype_exists(doctype: str) -> bool:
    try:
        return bool(frappe.db.exists("DocType", doctype))
    except Exception:
        return False


def _value(doc, field):
    if hasattr(doc, "get"):
        return doc.get(field)
    return getattr(doc, field, None)


def _label(doctype: str) -> str:
    return "Lead" if "Lead" in doctype else "Deal"


def _date_key(value) -> str:
    if isinstance(value, date | datetime):
        return value.isoformat()
    return str(value or "")


def _now() -> datetime:
    try:
        return frappe.utils.now_datetime()
    except Exception:
        return datetime.now()
