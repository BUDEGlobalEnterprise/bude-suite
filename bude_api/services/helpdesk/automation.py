"""Idempotent Helpdesk escalation policies using standard Frappe records."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success
from ..admin.notification_fanout import fan_out_notification_logs
from ..common.permissions import HELPDESK_MANAGER_ROLES, require_any_role

AUTOMATION_SERVICE = "bude_helpdesk_automation"
TICKET_SCAN_LIMIT = 500
AUDIT_SCAN_LIMIT = 500
MAX_RETRY_ATTEMPTS = 3
CLOSED_CATEGORIES = {"Resolved"}


def automation_status() -> dict:
    denied = _require_manager()
    if denied:
        return denied
    audits = _audit_rows(limit=AUDIT_SCAN_LIMIT)
    counts = _audit_counts(audits)
    return success(
        {
            "enabled": _enabled(),
            "policies": _policy_payloads(),
            "delivery": counts,
            "recent_events": [_serialize_audit(row) for row in audits[:20]],
            "schedule": "Every 15 minutes",
            "scan_limit": TICKET_SCAN_LIMIT,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def evaluate_automation(dry_run=True) -> dict:
    denied = _require_manager()
    if denied:
        return denied
    dry_run = _as_bool(dry_run)
    if not dry_run and not _enabled():
        return failure(
            "Helpdesk automation is disabled in site configuration.",
            code="AUTOMATION_DISABLED",
        )
    return success(_evaluate(dry_run=dry_run, retry_failed=False))


def retry_failed_automation(limit=20) -> dict:
    denied = _require_manager()
    if denied:
        return denied
    if not _enabled():
        return failure(
            "Helpdesk automation is disabled in site configuration.",
            code="AUTOMATION_DISABLED",
        )
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if limit < 1 or limit > 100:
        return failure("limit must be between 1 and 100.", code="VALIDATION_BAD_LIMIT")
    result = _retry_failed(limit)
    result["delivery"] = _fanout()
    return success(result)


def run_helpdesk_automation() -> dict:
    """Bench scheduler entry point. Disabled unless explicitly configured."""
    if frappe is None or not _enabled():
        return {"enabled": False, "matched": 0, "delivered": 0, "failed": 0}
    return _evaluate(dry_run=False, retry_failed=True)


def _evaluate(*, dry_run: bool, retry_failed: bool) -> dict:
    now = _now()
    rows = _open_tickets()
    truncated = len(rows) > TICKET_SCAN_LIMIT
    rows = rows[:TICKET_SCAN_LIMIT]
    managers = _manager_users()
    reopen_counts = _reopen_counts([str(row.get("name") or "") for row in rows])
    events = _events(rows, managers, reopen_counts, now)
    result = {
        "enabled": _enabled(),
        "dry_run": dry_run,
        "scanned": len(rows),
        "scan_limit": TICKET_SCAN_LIMIT,
        "scan_truncated": truncated,
        "matched": len(events),
        "delivered": 0,
        "failed": 0,
        "skipped": 0,
        "matches": [_event_preview(event) for event in events[:100]],
        "retry": None,
        "delivery": None,
    }
    if dry_run:
        return result
    if retry_failed:
        result["retry"] = _retry_failed(100)
    for event in events:
        outcome = _deliver_event(event)
        result[outcome] += 1
    result["delivery"] = _fanout()
    return result


def _events(
    rows: list[dict], managers: list[str], reopen_counts: dict[str, int], now: datetime
) -> list[dict]:
    settings = _settings()
    events = []
    policy_counts: dict[str, int] = {}
    for row in rows:
        ticket = str(row.get("name") or "")
        if not ticket:
            continue
        recipients = _assignees(row.get("_assign")) or managers
        matched = _matched_policies(row, reopen_counts.get(ticket, 0), now, settings)
        for policy in matched:
            policy_counts[policy] = policy_counts.get(policy, 0) + 1
            target_users = managers if policy == "unassigned" else recipients
            for recipient in target_users:
                events.append(_event(row, policy, recipient, now, settings))
    if policy_counts:
        summary = ", ".join(
            f"{_policy_label(key)}: {count}" for key, count in sorted(policy_counts.items())
        )
        for manager in managers:
            events.append(
                {
                    "policy": "manager_digest",
                    "ticket": "",
                    "recipient": manager,
                    "subject": "Bude Helpdesk escalation digest",
                    "content": f"Current automation matches — {summary}.",
                    "event_key": f"manager_digest:{now.date().isoformat()}:{manager}",
                }
            )
    return events


def _matched_policies(row: dict, reopen_count: int, now: datetime, settings: dict) -> list[str]:
    matched = []
    created = _datetime(row.get("creation")) or now
    modified = _datetime(row.get("modified")) or created
    deadline = _deadline(row)
    unassigned_age = now - created
    latest_activity = max(
        [
            value
            for value in (
                modified,
                _datetime(row.get("last_agent_response")),
                _datetime(row.get("last_customer_response")),
            )
            if value is not None
        ]
    )
    if _unassigned(row.get("_assign")) and unassigned_age >= timedelta(
        minutes=settings["unassigned_minutes"]
    ):
        matched.append("unassigned")
    if deadline and now <= deadline <= now + timedelta(hours=settings["due_soon_hours"]):
        matched.append("due_soon")
    if (deadline and deadline < now) or str(row.get("agreement_status") or "").lower() == "failed":
        matched.append("breach")
    if now - latest_activity >= timedelta(hours=settings["inactivity_hours"]):
        matched.append("inactivity")
    customer = str(row.get("customer") or "").strip().lower()
    priority = str(row.get("priority") or "").strip().lower()
    if customer in settings["vip_customers"] or priority in settings["vip_priorities"]:
        matched.append("vip")
    if reopen_count >= settings["reopen_count"]:
        matched.append("repeated_reopen")
    return matched


def _event(row: dict, policy: str, recipient: str, now: datetime, settings: dict) -> dict:
    ticket = str(row.get("name") or "")
    label = _policy_label(policy)
    bucket = _event_bucket(policy, row, now, settings)
    return {
        "policy": policy,
        "ticket": ticket,
        "recipient": recipient,
        "subject": f"Helpdesk {label}: {ticket}",
        "content": f"Ticket {ticket} matched the {label.lower()} policy. Open Support Pulse to respond.",
        "event_key": f"{policy}:{ticket}:{recipient}:{bucket}",
    }


def _event_bucket(policy: str, row: dict, now: datetime, settings: dict) -> str:
    if policy == "due_soon":
        return str(_deadline(row) or "")
    if policy == "repeated_reopen":
        return str(settings["reopen_count"])
    hours = {
        "unassigned": 4,
        "breach": 4,
        "inactivity": 24,
        "vip": 24,
    }.get(policy, 24)
    return str(int(now.timestamp()) // (hours * 3600))


def _deliver_event(event: dict) -> str:
    request_id = hashlib.sha256(event["event_key"].encode("utf-8")).hexdigest()
    existing = _audit_by_request(request_id)
    attempts = _audit_attempts(existing) + 1
    if existing and existing.get("status") == "Completed":
        return "skipped"
    if attempts > MAX_RETRY_ATTEMPTS:
        return "skipped"
    notification_name = _existing_notification(event)
    try:
        if not notification_name:
            payload = {
                "doctype": "Notification Log",
                "type": "Alert",
                "title": event["subject"],
                "description": event["content"],
                "subject": event["subject"],
                "email_content": event["content"],
                "for_user": event["recipient"],
                "link": "/agent/pulse" if event.get("ticket") else "/admin/automation",
            }
            if event.get("ticket"):
                payload["document_type"] = "HD Ticket"
                payload["document_name"] = event["ticket"]
            notification = frappe.get_doc(payload)
            notification.insert(ignore_permissions=True)
            notification_name = str(getattr(notification, "name", "") or "")
        _write_audit(
            existing,
            request_id,
            event,
            attempts,
            "Completed",
            output=json.dumps({"notification_log": notification_name}),
        )
        return "delivered"
    except Exception as exc:
        try:
            _write_audit(
                existing,
                request_id,
                event,
                attempts,
                "Failed",
                error=type(exc).__name__,
            )
        except Exception:
            pass
        return "failed"


def _write_audit(
    existing: dict | None,
    request_id: str,
    event: dict,
    attempts: int,
    status: str,
    *,
    output: str = "",
    error: str = "",
) -> None:
    data = json.dumps(
        {
            "policy": event["policy"],
            "ticket": event.get("ticket") or "",
            "recipient": event["recipient"],
            "event_key": event["event_key"],
            "attempts": attempts,
        },
        separators=(",", ":"),
    )
    values = {"status": status, "data": data, "output": output, "error": error}
    if existing and existing.get("name"):
        frappe.db.set_value("Integration Request", existing["name"], values)
        return
    payload = {
        "doctype": "Integration Request",
        "request_id": request_id,
        "integration_request_service": AUTOMATION_SERVICE,
        "request_description": f'{event["policy"]}:{event.get("ticket") or "digest"}',
        **values,
    }
    if event.get("ticket"):
        payload["reference_doctype"] = "HD Ticket"
        payload["reference_docname"] = event["ticket"]
    doc = frappe.get_doc(payload)
    doc.insert(ignore_permissions=True)


def _retry_failed(limit: int) -> dict:
    rows = _safe_list(
        "Integration Request",
        filters=[
            ["integration_request_service", "=", AUTOMATION_SERVICE],
            ["status", "=", "Failed"],
        ],
        fields=["name", "request_id", "status", "data"],
        order_by="modified asc",
        limit_page_length=limit,
        ignore_permissions=True,
    )
    result = {"found": len(rows), "delivered": 0, "failed": 0, "skipped": 0}
    for row in rows:
        data = _json(row.get("data"))
        ticket = str(data.get("ticket") or "")
        policy = str(data.get("policy") or "")
        recipient = str(data.get("recipient") or "")
        if not policy or not recipient or _audit_attempts(row) >= MAX_RETRY_ATTEMPTS:
            result["skipped"] += 1
            continue
        if ticket and not _ticket_is_open(ticket):
            result["skipped"] += 1
            continue
        event = {
            "policy": policy,
            "ticket": ticket,
            "recipient": recipient,
            "subject": "Bude Helpdesk escalation digest"
            if not ticket
            else f"Helpdesk {_policy_label(policy)}: {ticket}",
            "content": "A previous Helpdesk automation delivery is being retried.",
            "event_key": str(data.get("event_key") or row.get("request_id") or ""),
        }
        outcome = _deliver_event(event)
        result[outcome] += 1
    return result


def _policy_payloads() -> list[dict]:
    settings = _settings()
    return [
        _policy("unassigned", f'After {settings["unassigned_minutes"]} minutes', "Managers"),
        _policy(
            "due_soon",
            f'Within {settings["due_soon_hours"]} hours',
            "Assigned agent, then managers",
        ),
        _policy("breach", "After the next SLA deadline", "Assigned agent, then managers"),
        _policy(
            "inactivity",
            f'After {settings["inactivity_hours"]} hours',
            "Assigned agent, then managers",
        ),
        _policy(
            "vip", "Configured customers or critical priorities", "Assigned agent, then managers"
        ),
        _policy(
            "repeated_reopen",
            f'After {settings["reopen_count"]} reopenings',
            "Assigned agent, then managers",
            available=_doctype_exists("HD Ticket Activity"),
        ),
        _policy("manager_digest", "Daily when policies match", "Managers"),
    ]


def _policy(key: str, threshold: str, recipients: str, *, available: bool = True) -> dict:
    return {
        "key": key,
        "label": _policy_label(key),
        "enabled": available,
        "available": available,
        "threshold": threshold,
        "recipients": recipients,
    }


def _settings() -> dict:
    return {
        "unassigned_minutes": _conf_int("bude_helpdesk_unassigned_minutes", 30, 5, 1440),
        "due_soon_hours": _conf_int("bude_helpdesk_due_soon_hours", 4, 1, 24),
        "inactivity_hours": _conf_int("bude_helpdesk_inactivity_hours", 24, 1, 720),
        "reopen_count": _conf_int("bude_helpdesk_reopen_count", 2, 1, 20),
        "vip_customers": _conf_set("bude_helpdesk_vip_customers"),
        "vip_priorities": _conf_set("bude_helpdesk_vip_priorities") or {"urgent"},
    }


def _open_tickets() -> list[dict]:
    fields = [
        "name",
        "subject",
        "status",
        "status_category",
        "priority",
        "customer",
        "agreement_status",
        "response_by",
        "resolution_by",
        "first_responded_on",
        "last_agent_response",
        "last_customer_response",
        "creation",
        "modified",
        "_assign",
    ]
    fields = _existing_fields("HD Ticket", fields)
    return _safe_list(
        "HD Ticket",
        filters=[["status_category", "not in", sorted(CLOSED_CATEGORIES)]],
        fields=fields,
        order_by="creation asc",
        limit_page_length=TICKET_SCAN_LIMIT + 1,
        ignore_permissions=True,
    )


def _reopen_counts(ticket_names: list[str]) -> dict[str, int]:
    if not ticket_names or not _doctype_exists("HD Ticket Activity"):
        return {}
    statuses = _safe_list(
        "HD Ticket Status",
        filters=[["category", "in", ["Open", "Resolved"]]],
        fields=["name", "category"],
        limit_page_length=100,
        ignore_permissions=True,
    )
    categories = {str(row.get("name") or ""): str(row.get("category") or "") for row in statuses}
    activities = _safe_list(
        "HD Ticket Activity",
        filters=[["ticket", "in", ticket_names], ["action", "like", "set status to %"]],
        fields=["ticket", "action", "creation"],
        order_by="creation asc",
        limit_page_length=5000,
        ignore_permissions=True,
    )
    previous: dict[str, str] = {}
    counts: dict[str, int] = {}
    for row in activities:
        ticket = str(row.get("ticket") or "")
        status = str(row.get("action") or "").removeprefix("set status to ")
        category = categories.get(status, "")
        if category == "Open" and previous.get(ticket) == "Resolved":
            counts[ticket] = counts.get(ticket, 0) + 1
        if category:
            previous[ticket] = category
    return counts


def _manager_users() -> list[str]:
    roles = _safe_list(
        "Has Role",
        filters=[["role", "in", sorted(HELPDESK_MANAGER_ROLES)], ["parenttype", "=", "User"]],
        fields=["parent"],
        limit_page_length=500,
        ignore_permissions=True,
    )
    names = sorted({str(row.get("parent") or "") for row in roles if row.get("parent")})
    if not names:
        return ["Administrator"] if _exists("User", "Administrator") else []
    users = _safe_list(
        "User",
        filters=[["name", "in", names], ["enabled", "=", 1]],
        fields=["name"],
        limit_page_length=len(names),
        ignore_permissions=True,
    )
    return sorted({str(row.get("name") or "") for row in users if row.get("name")})


def _audit_rows(limit: int) -> list[dict]:
    return _safe_list(
        "Integration Request",
        filters=[["integration_request_service", "=", AUTOMATION_SERVICE]],
        fields=[
            "name",
            "request_id",
            "request_description",
            "status",
            "data",
            "reference_docname",
            "creation",
            "modified",
        ],
        order_by="modified desc",
        limit_page_length=min(limit, AUDIT_SCAN_LIMIT),
        ignore_permissions=True,
    )


def _audit_counts(rows: list[dict]) -> dict:
    completed = sum(row.get("status") == "Completed" for row in rows)
    failed = sum(row.get("status") == "Failed" for row in rows)
    attempted = completed + failed
    return {
        "attempted": attempted,
        "completed": completed,
        "failed": failed,
        "rate": round(completed * 100 / attempted) if attempted else 100,
        "sample_limit": AUDIT_SCAN_LIMIT,
        "sample_truncated": len(rows) >= AUDIT_SCAN_LIMIT,
    }


def _serialize_audit(row: dict) -> dict:
    data = _json(row.get("data"))
    return {
        "name": str(row.get("name") or ""),
        "policy": str(data.get("policy") or ""),
        "ticket": str(data.get("ticket") or row.get("reference_docname") or ""),
        "status": str(row.get("status") or ""),
        "attempts": int(data.get("attempts") or 0),
        "modified": str(row.get("modified") or row.get("creation") or ""),
    }


def _audit_by_request(request_id: str) -> dict | None:
    rows = _safe_list(
        "Integration Request",
        filters=[
            ["integration_request_service", "=", AUTOMATION_SERVICE],
            ["request_id", "=", request_id],
        ],
        fields=["name", "request_id", "status", "data"],
        limit_page_length=1,
        ignore_permissions=True,
    )
    return rows[0] if rows else None


def _existing_notification(event: dict) -> str:
    try:
        value = frappe.db.exists(
            "Notification Log",
            {
                "for_user": event["recipient"],
                "subject": event["subject"],
                "document_type": "HD Ticket" if event.get("ticket") else "",
                "document_name": event.get("ticket") or "",
            },
        )
    except Exception:
        return ""
    return str(value) if isinstance(value, str) else ""


def _ticket_is_open(ticket: str) -> bool:
    rows = _safe_list(
        "HD Ticket",
        filters=[["name", "=", ticket], ["status_category", "not in", sorted(CLOSED_CATEGORIES)]],
        fields=["name"],
        limit_page_length=1,
    )
    return bool(rows)


def _event_preview(event: dict) -> dict:
    return {
        "policy": event["policy"],
        "ticket": event.get("ticket") or "",
        "recipient_count": 1,
        "subject": event["subject"],
    }


def _fanout():
    try:
        return fan_out_notification_logs(limit=200)
    except Exception:
        return failure("Push fan-out failed and will retry.", code="PUSH_FANOUT_FAILED")


def _deadline(row: dict) -> datetime | None:
    if not row.get("first_responded_on"):
        response = _datetime(row.get("response_by"))
        if response:
            return response
    return _datetime(row.get("resolution_by"))


def _datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _now() -> datetime:
    try:
        return _datetime(frappe.utils.now_datetime()) or datetime.now()
    except Exception:
        return datetime.now()


def _assignees(value) -> list[str]:
    if isinstance(value, list):
        return sorted({str(item) for item in value if item})
    try:
        decoded = json.loads(str(value or "[]"))
    except (TypeError, ValueError):
        return []
    return sorted({str(item) for item in decoded if item}) if isinstance(decoded, list) else []


def _unassigned(value) -> bool:
    return not _assignees(value)


def _audit_attempts(row: dict | None) -> int:
    try:
        return int(_json((row or {}).get("data")).get("attempts") or 0)
    except (TypeError, ValueError):
        return 0


def _json(value) -> dict:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _policy_label(key: str) -> str:
    return {
        "unassigned": "Unassigned ticket",
        "due_soon": "SLA due soon",
        "breach": "SLA breach",
        "inactivity": "Ticket inactivity",
        "vip": "VIP / critical ticket",
        "repeated_reopen": "Repeated reopening",
        "manager_digest": "Manager digest",
    }.get(key, key.replace("_", " ").title())


def _enabled() -> bool:
    value = _conf("bude_helpdesk_automation_enabled")
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _conf(key: str):
    conf = getattr(frappe, "conf", {})
    try:
        return conf.get(key)
    except Exception:
        return getattr(conf, key, None)


def _conf_int(key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(_conf(key))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


def _conf_set(key: str) -> set[str]:
    value = _conf(key)
    if isinstance(value, list | tuple | set):
        values = value
    else:
        values = str(value or "").split(",")
    return {str(item).strip().lower() for item in values if str(item).strip()}


def _existing_fields(doctype: str, fields: list[str]) -> list[str]:
    try:
        meta = frappe.get_meta(doctype)
        return [field for field in fields if field == "name" or meta.has_field(field)]
    except Exception:
        return fields


def _safe_list(doctype: str, **kwargs) -> list[dict]:
    try:
        rows = frappe.get_list(doctype, **kwargs)
    except Exception:
        return []
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _doctype_exists(doctype: str) -> bool:
    return _exists("DocType", doctype)


def _exists(doctype: str, name_or_filters) -> bool:
    try:
        value = frappe.db.exists(doctype, name_or_filters)
    except Exception:
        return False
    return bool(value) if isinstance(value, bool | int | str) else False


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return value is True or value == 1


def _require_manager() -> dict | None:
    return require_any_role(
        frappe,
        HELPDESK_MANAGER_ROLES,
        "Agent Manager access is required for Helpdesk automation.",
    )
