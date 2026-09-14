"""Safe omnichannel operations built on standard Frappe communication records."""

import hashlib
import json
import re
from email.utils import getaddresses
from html import escape
from urllib import request
from urllib.parse import urlparse

from ...utils.response import failure, success
from ..common.permissions import (
    HELPDESK_MANAGER_ROLES,
    require_any_role,
    require_helpdesk_agent_role,
)
from ._tickets_shared import (
    MAX_CONVERSATION_ROWS,
    _current_user,
    _require_helpdesk,
    _visible_ticket,
    frappe,
)

CHANNEL_AUDIT_SERVICE = "bude_helpdesk_channel"
DELIVERY_SCAN_LIMIT = 500
MAX_FORWARD_RECIPIENTS = 20
MAX_FORWARD_ATTACHMENTS = 10
MAX_CHANNEL_ATTEMPTS = 3
MAX_MESSAGE_LENGTH = 100_000
MAX_SUMMARY_LENGTH = 2_000
PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")
VARIABLE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def channel_health() -> dict:
    denied = require_any_role(
        frappe,
        HELPDESK_MANAGER_ROLES,
        "Agent Manager access is required for channel health.",
    )
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    queues = _safe_list(
        "Email Queue",
        fields=["name", "status", "retry", "creation", "modified"],
        order_by="modified desc",
        limit_page_length=DELIVERY_SCAN_LIMIT,
        ignore_permissions=True,
    )
    counts = {status: 0 for status in ("Not Sent", "Sending", "Sent", "Partially Sent", "Error")}
    for row in queues:
        status = str(row.get("status") or "")
        if status in counts:
            counts[status] += 1
    attempted = counts["Sent"] + counts["Partially Sent"] + counts["Error"]
    accepted = counts["Sent"] + counts["Partially Sent"]
    email_accounts = _safe_list(
        "Email Account",
        filters=[["enable_outgoing", "=", 1]],
        fields=["name"],
        limit_page_length=100,
        ignore_permissions=True,
    )
    templates = _whatsapp_templates()
    whatsapp_enabled = _conf_bool("bude_helpdesk_whatsapp_enabled")
    whatsapp_endpoint = str(_conf("bude_helpdesk_whatsapp_endpoint") or "").strip()
    whatsapp_token = str(_conf("bude_helpdesk_whatsapp_token") or "").strip()
    return success(
        {
            "email": {
                "available": bool(email_accounts),
                "outgoing_accounts": len(email_accounts),
                "queue": {
                    "not_sent": counts["Not Sent"],
                    "sending": counts["Sending"],
                    "sent": counts["Sent"],
                    "partially_sent": counts["Partially Sent"],
                    "error": counts["Error"],
                    "accepted_rate": round(accepted * 100 / attempted) if attempted else 100,
                    "sample_limit": DELIVERY_SCAN_LIMIT,
                    "sample_truncated": len(queues) >= DELIVERY_SCAN_LIMIT,
                },
            },
            "whatsapp": {
                "enabled": whatsapp_enabled,
                "configured": bool(whatsapp_endpoint and whatsapp_token and templates),
                "template_count": len(templates),
                "consent_required": True,
                "identity_source": "Ticket contact",
            },
            "telephony": {
                "native_available": _exists("DocType", "TP Call Log"),
                "activity_bridge": True,
                "identity_source": "Ticket contact",
            },
            "audit": _channel_audit_counts(),
            "checked_at": _now_string(),
        }
    )


def ticket_delivery(ticket_name: str, limit: int = 50) -> dict:
    denied = require_helpdesk_agent_role(frappe)
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    ticket, error = _visible_ticket(ticket_name)
    if error:
        return error
    parsed_limit = _limit(limit, 1, 100)
    if isinstance(parsed_limit, dict):
        return parsed_limit
    rows = _safe_list(
        "Communication",
        filters=[
            ["reference_doctype", "=", "HD Ticket"],
            ["reference_name", "=", ticket["name"]],
            ["communication_type", "=", "Communication"],
        ],
        fields=[
            "name",
            "subject",
            "communication_medium",
            "sent_or_received",
            "delivery_status",
            "has_attachment",
            "creation",
        ],
        order_by="creation desc",
        limit_page_length=parsed_limit,
        ignore_permissions=True,
    )
    names = [str(row.get("name") or "") for row in rows if row.get("name")]
    queue_by_communication = _email_queue_by_communication(names)
    attachment_counts = _communication_attachment_counts(names)
    records = []
    for row in rows:
        name = str(row.get("name") or "")
        queue = queue_by_communication.get(name, {})
        medium = str(row.get("communication_medium") or "Email")
        records.append(
            {
                "name": name,
                "subject": str(row.get("subject") or ""),
                "channel": _channel_label(medium),
                "direction": str(row.get("sent_or_received") or ""),
                "delivery_status": str(row.get("delivery_status") or ""),
                "queue_status": str(queue.get("status") or ""),
                "queue_retry": _int(queue.get("retry")),
                "queue_has_error": bool(queue.get("error")),
                "attachment_count": attachment_counts.get(name, 0),
                "creation": str(row.get("creation") or ""),
            }
        )
    templates = _whatsapp_templates()
    whatsapp_configured = bool(
        _secure_endpoint(str(_conf("bude_helpdesk_whatsapp_endpoint") or "").strip())
        and str(_conf("bude_helpdesk_whatsapp_token") or "").strip()
        and templates
    )
    return success(
        {
            "ticket": ticket["name"],
            "records": records,
            "limit": parsed_limit,
            "capabilities": {
                "email": _outgoing_email_available(),
                "whatsapp": _conf_bool("bude_helpdesk_whatsapp_enabled") and whatsapp_configured,
                "whatsapp_templates": templates,
                "phone": bool(_ticket_phone(ticket)),
                "consent_required": True,
            },
        }
    )


def forward_ticket(
    ticket_name: str,
    recipients,
    subject: str,
    content: str,
    attachment_names=None,
    cc=None,
) -> dict:
    denied = require_helpdesk_agent_role(frappe)
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    ticket, error = _visible_ticket(ticket_name)
    if error:
        return error
    recipients_value, recipients_valid = _emails(recipients)
    cc_value, cc_valid = _emails(cc)
    if not recipients_value or not recipients_valid or not cc_valid:
        return failure("At least one valid recipient is required.", code="VALIDATION_RECIPIENTS")
    if len(recipients_value) + len(cc_value) > MAX_FORWARD_RECIPIENTS:
        return failure(
            f"A maximum of {MAX_FORWARD_RECIPIENTS} recipients is allowed.",
            code="VALIDATION_RECIPIENTS",
        )
    subject = str(subject or "").strip()
    content = str(content or "").strip()
    if not subject or len(subject) > 300 or not content or len(content) > MAX_MESSAGE_LENGTH:
        return failure(
            "A subject and message are required within the allowed limits.",
            code="VALIDATION_REQUIRED",
        )
    requested_files = _string_list(attachment_names)
    if len(requested_files) > MAX_FORWARD_ATTACHMENTS:
        return failure(
            f"A maximum of {MAX_FORWARD_ATTACHMENTS} attachments is allowed.",
            code="VALIDATION_ATTACHMENTS",
        )
    if requested_files and not _attachments_belong_to_ticket(ticket["name"], requested_files):
        return failure(
            "Every attachment must belong to this ticket conversation.",
            code="VALIDATION_ATTACHMENTS",
        )
    try:
        make = frappe.get_attr("frappe.core.doctype.communication.email.make")
        result = make(
            doctype="HD Ticket",
            name=ticket["name"],
            content=content,
            subject=subject,
            recipients=recipients_value,
            cc=cc_value or None,
            communication_medium="Email",
            sent_or_received="Sent",
            send_email=True,
            attachments=requested_files,
        )
        frappe.db.commit()
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    except Exception as exc:
        frappe.db.rollback()
        return failure(
            "The forwarded email could not be queued.",
            code="CHANNEL_DELIVERY_FAILED",
            data={"reason": type(exc).__name__},
        )
    name = str((result or {}).get("name") or "") if isinstance(result, dict) else ""
    return success(
        {
            "communication": name,
            "status": "Queued",
            "recipient_count": len(recipients_value) + len(cc_value),
            "attachment_count": len(requested_files),
        }
    )


def send_whatsapp_template(
    ticket_name: str,
    template: str,
    variables=None,
    consent_reference: str | None = None,
    request_key: str | None = None,
) -> dict:
    denied = require_helpdesk_agent_role(frappe)
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not _conf_bool("bude_helpdesk_whatsapp_enabled"):
        return failure("WhatsApp delivery is disabled.", code="CHANNEL_DISABLED")
    ticket, error = _visible_ticket(ticket_name)
    if error:
        return error
    template = str(template or "").strip()
    if template not in _whatsapp_templates():
        return failure("Select an approved configured template.", code="VALIDATION_TEMPLATE")
    consent_reference = str(consent_reference or "").strip()
    if len(consent_reference) < 3 or len(consent_reference) > 200:
        return failure("A consent reference is required.", code="VALIDATION_CONSENT")
    request_key = str(request_key or "").strip()
    if len(request_key) < 8 or len(request_key) > 100:
        return failure("A valid request key is required.", code="VALIDATION_REQUEST_KEY")
    variable_map = _variables(variables)
    if isinstance(variable_map, dict) and variable_map.get("ok") is False:
        return variable_map
    phone = _ticket_phone(ticket)
    if not phone:
        return failure(
            "The ticket contact does not have one unambiguous E.164 phone number.",
            code="CHANNEL_IDENTITY_UNAVAILABLE",
        )
    endpoint = str(_conf("bude_helpdesk_whatsapp_endpoint") or "").strip()
    token = str(_conf("bude_helpdesk_whatsapp_token") or "").strip()
    if not _secure_endpoint(endpoint) or not token:
        return failure("WhatsApp delivery is not fully configured.", code="CHANNEL_NOT_CONFIGURED")
    audit_id = hashlib.sha256(f"whatsapp:{ticket['name']}:{request_key}".encode()).hexdigest()
    audit = _audit_by_request(audit_id)
    attempts = _audit_attempts(audit) + 1
    if audit and audit.get("status") == "Completed":
        return success({"status": "Accepted", "duplicate": True, "attempts": attempts - 1})
    if attempts > MAX_CHANNEL_ATTEMPTS:
        return failure("The delivery retry limit was reached.", code="CHANNEL_RETRY_EXHAUSTED")
    payload = {
        "event": "helpdesk.message.send",
        "channel": "whatsapp",
        "ticket": ticket["name"],
        "to": phone,
        "template": template,
        "variables": variable_map,
        "consent_reference": consent_reference,
        "idempotency_key": audit_id,
    }
    try:
        provider = _post_json(endpoint, token, payload)
        communication = frappe.get_doc(
            {
                "doctype": "Communication",
                "communication_type": "Communication",
                "communication_medium": "Chat",
                "reference_doctype": "HD Ticket",
                "reference_name": ticket["name"],
                "subject": f"WhatsApp template: {template}",
                "content": f"WhatsApp template {escape(template)} accepted by the configured provider.",
                "sent_or_received": "Sent",
                "status": "Linked",
                "delivery_status": "Sent",
            }
        )
        communication.insert(ignore_permissions=True)
        _write_audit(
            audit,
            audit_id,
            ticket["name"],
            request_key,
            template,
            phone,
            consent_reference,
            attempts,
            "Completed",
            output=json.dumps(provider, separators=(",", ":")),
        )
        frappe.db.commit()
    except Exception as exc:
        frappe.db.rollback()
        try:
            _write_audit(
                audit,
                audit_id,
                ticket["name"],
                request_key,
                template,
                phone,
                consent_reference,
                attempts,
                "Failed",
                error=type(exc).__name__,
            )
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
        return failure(
            "The WhatsApp provider did not accept the message.",
            code="CHANNEL_DELIVERY_FAILED",
            data={"attempts": attempts},
        )
    return success({"status": "Accepted", "duplicate": False, "attempts": attempts})


def log_phone_activity(
    ticket_name: str,
    direction: str,
    duration_seconds=0,
    summary: str | None = None,
    external_call_id: str | None = None,
) -> dict:
    denied = require_helpdesk_agent_role(frappe)
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    ticket, error = _visible_ticket(ticket_name)
    if error:
        return error
    direction = str(direction or "").strip().lower()
    if direction not in {"inbound", "outbound"}:
        return failure("direction must be inbound or outbound.", code="VALIDATION_DIRECTION")
    try:
        duration = int(duration_seconds)
    except (TypeError, ValueError):
        return failure("duration_seconds must be an integer.", code="VALIDATION_DURATION")
    if duration < 0 or duration > 86_400:
        return failure("duration_seconds is outside the allowed range.", code="VALIDATION_DURATION")
    summary = str(summary or "").strip()
    if not summary or len(summary) > MAX_SUMMARY_LENGTH:
        return failure(
            "A call summary is required within the allowed limit.", code="VALIDATION_REQUIRED"
        )
    external_call_id = str(external_call_id or "").strip()
    if external_call_id and len(external_call_id) > 120:
        return failure("external_call_id is too long.", code="VALIDATION_REQUEST_KEY")
    phone = _ticket_phone(ticket)
    if not phone:
        return failure(
            "The ticket contact does not have one unambiguous E.164 phone number.",
            code="CHANNEL_IDENTITY_UNAVAILABLE",
        )
    audit_id = ""
    if external_call_id:
        audit_id = hashlib.sha256(f"phone:{ticket['name']}:{external_call_id}".encode()).hexdigest()
        existing = _audit_by_request(audit_id)
        if existing and existing.get("status") == "Completed":
            return success({"name": "", "duplicate": True})
    try:
        doc = frappe.get_doc(
            {
                "doctype": "Communication",
                "communication_type": "Communication",
                "communication_medium": "Phone",
                "reference_doctype": "HD Ticket",
                "reference_name": ticket["name"],
                "subject": f"{direction.title()} phone call - {ticket['name']}",
                "content": f"<p>{escape(summary)}</p><p>Duration: {duration} seconds</p>",
                "phone_no": phone,
                "sent_or_received": "Received" if direction == "inbound" else "Sent",
                "status": "Linked",
            }
        )
        doc.insert(ignore_permissions=True)
        if audit_id:
            _write_phone_audit(audit_id, ticket["name"], external_call_id, direction, duration)
        frappe.db.commit()
    except Exception as exc:
        frappe.db.rollback()
        return failure(
            "The phone activity could not be recorded.",
            code="CHANNEL_ACTIVITY_FAILED",
            data={"reason": type(exc).__name__},
        )
    return success({"name": str(getattr(doc, "name", "") or ""), "duplicate": False})


def _ticket_phone(ticket: dict) -> str:
    contact = str(ticket.get("contact") or "").strip()
    if not contact:
        return ""
    rows = _safe_list(
        "Contact",
        filters=[["name", "=", contact]],
        fields=["name", "mobile_no", "phone"],
        limit_page_length=1,
        ignore_permissions=True,
    )
    if len(rows) != 1 or str(rows[0].get("name") or "") != contact:
        return ""
    candidates = {_normalize_phone(rows[0].get(field)) for field in ("mobile_no", "phone")}
    candidates.discard("")
    return candidates.pop() if len(candidates) == 1 else ""


def _normalize_phone(value) -> str:
    normalized = re.sub(r"[\s().-]", "", str(value or "").strip())
    return normalized if PHONE_PATTERN.fullmatch(normalized) else ""


def _emails(value) -> tuple[list[str], bool]:
    raw = _string_list(value, split_commas=True)
    parsed = [address.strip().lower() for _, address in getaddresses(raw)]
    valid = []
    for address in parsed:
        if address.count("@") != 1 or any(char.isspace() for char in address):
            continue
        local, domain = address.rsplit("@", 1)
        if local and "." in domain and not domain.startswith(".") and not domain.endswith("."):
            valid.append(address)
    return list(dict.fromkeys(valid)), len(valid) == len(raw)


def _string_list(value, *, split_commas: bool = False) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError):
            decoded = raw.split(",") if split_commas else [raw]
    else:
        decoded = value
    if not isinstance(decoded, list | tuple | set):
        return []
    values = [str(item).strip() for item in decoded if str(item).strip()]
    return list(dict.fromkeys(values))


def _variables(value):
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return failure("variables must be a JSON object.", code="VALIDATION_VARIABLES")
    if not isinstance(value, dict) or len(value) > 20:
        return failure("variables must contain at most 20 entries.", code="VALIDATION_VARIABLES")
    result = {}
    for key, item in value.items():
        key = str(key)
        item = str(item)
        if not VARIABLE_KEY_PATTERN.fullmatch(key) or len(item) > 500:
            return failure("A template variable is invalid.", code="VALIDATION_VARIABLES")
        result[key] = item
    return result


def _attachments_belong_to_ticket(ticket: str, names: list[str]) -> bool:
    communications = _safe_list(
        "Communication",
        filters=[["reference_doctype", "=", "HD Ticket"], ["reference_name", "=", ticket]],
        fields=["name"],
        limit_page_length=MAX_CONVERSATION_ROWS,
        ignore_permissions=True,
    )
    communication_names = {str(row.get("name") or "") for row in communications}
    files = _safe_list(
        "File",
        filters=[["name", "in", names]],
        fields=["name", "attached_to_doctype", "attached_to_name"],
        limit_page_length=len(names),
        ignore_permissions=True,
    )
    if {str(row.get("name") or "") for row in files} != set(names):
        return False
    return all(
        (row.get("attached_to_doctype") == "HD Ticket" and row.get("attached_to_name") == ticket)
        or (
            row.get("attached_to_doctype") == "Communication"
            and row.get("attached_to_name") in communication_names
        )
        for row in files
    )


def _email_queue_by_communication(names: list[str]) -> dict[str, dict]:
    if not names:
        return {}
    rows = _safe_list(
        "Email Queue",
        filters=[["communication", "in", names]],
        fields=["name", "communication", "status", "retry", "error", "modified"],
        order_by="modified desc",
        limit_page_length=min(len(names) * 3, DELIVERY_SCAN_LIMIT),
        ignore_permissions=True,
    )
    result = {}
    for row in rows:
        communication = str(row.get("communication") or "")
        result.setdefault(communication, row)
    return result


def _communication_attachment_counts(names: list[str]) -> dict[str, int]:
    if not names:
        return {}
    rows = _safe_list(
        "File",
        filters=[
            ["attached_to_doctype", "=", "Communication"],
            ["attached_to_name", "in", names],
        ],
        fields=["attached_to_name"],
        limit_page_length=min(len(names) * MAX_FORWARD_ATTACHMENTS, DELIVERY_SCAN_LIMIT),
        ignore_permissions=True,
    )
    result = {}
    for row in rows:
        name = str(row.get("attached_to_name") or "")
        result[name] = result.get(name, 0) + 1
    return result


def _post_json(endpoint: str, token: str, payload: dict) -> dict:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = request.Request(
        endpoint,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=10) as response:
        status = int(getattr(response, "status", 0) or response.getcode())
        raw = response.read(4096)
    if status < 200 or status >= 300:
        raise RuntimeError("provider rejected request")
    try:
        decoded = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, ValueError):
        decoded = {}
    if not isinstance(decoded, dict):
        decoded = {}
    return {
        key: str(decoded.get(key) or "")[:200]
        for key in ("message_id", "id", "status")
        if decoded.get(key)
    }


def _write_audit(
    existing,
    request_id: str,
    ticket: str,
    request_key: str,
    template: str,
    phone: str,
    consent_reference: str,
    attempts: int,
    status: str,
    *,
    output: str = "",
    error: str = "",
) -> None:
    data = json.dumps(
        {
            "channel": "whatsapp",
            "ticket": ticket,
            "request_key": request_key,
            "template": template,
            "recipient": _mask_phone(phone),
            "consent_reference": consent_reference,
            "attempts": attempts,
            "agent": _current_user(),
        },
        separators=(",", ":"),
    )
    values = {"status": status, "data": data, "output": output, "error": error}
    if existing and existing.get("name"):
        frappe.db.set_value("Integration Request", existing["name"], values)
        return
    doc = frappe.get_doc(
        {
            "doctype": "Integration Request",
            "request_id": request_id,
            "integration_request_service": CHANNEL_AUDIT_SERVICE,
            "request_description": f"whatsapp:{ticket}",
            "reference_doctype": "HD Ticket",
            "reference_docname": ticket,
            **values,
        }
    )
    doc.insert(ignore_permissions=True)


def _write_phone_audit(
    request_id: str, ticket: str, external_call_id: str, direction: str, duration: int
) -> None:
    data = json.dumps(
        {
            "channel": "phone",
            "ticket": ticket,
            "external_call_id": external_call_id,
            "direction": direction,
            "duration_seconds": duration,
            "agent": _current_user(),
            "attempts": 1,
        },
        separators=(",", ":"),
    )
    doc = frappe.get_doc(
        {
            "doctype": "Integration Request",
            "request_id": request_id,
            "integration_request_service": CHANNEL_AUDIT_SERVICE,
            "request_description": f"phone:{ticket}",
            "reference_doctype": "HD Ticket",
            "reference_docname": ticket,
            "status": "Completed",
            "data": data,
        }
    )
    doc.insert(ignore_permissions=True)


def _audit_by_request(request_id: str):
    rows = _safe_list(
        "Integration Request",
        filters=[
            ["integration_request_service", "=", CHANNEL_AUDIT_SERVICE],
            ["request_id", "=", request_id],
        ],
        fields=["name", "request_id", "status", "data"],
        limit_page_length=1,
        ignore_permissions=True,
    )
    return rows[0] if rows else None


def _audit_attempts(row) -> int:
    try:
        data = json.loads(str((row or {}).get("data") or "{}"))
        return int(data.get("attempts") or 0) if isinstance(data, dict) else 0
    except (TypeError, ValueError):
        return 0


def _channel_audit_counts() -> dict:
    rows = _safe_list(
        "Integration Request",
        filters=[["integration_request_service", "=", CHANNEL_AUDIT_SERVICE]],
        fields=["status"],
        order_by="modified desc",
        limit_page_length=DELIVERY_SCAN_LIMIT,
        ignore_permissions=True,
    )
    completed = sum(row.get("status") == "Completed" for row in rows)
    failed = sum(row.get("status") == "Failed" for row in rows)
    return {
        "completed": completed,
        "failed": failed,
        "sample_limit": DELIVERY_SCAN_LIMIT,
        "sample_truncated": len(rows) >= DELIVERY_SCAN_LIMIT,
    }


def _whatsapp_templates() -> list[str]:
    return sorted(_string_list(_conf("bude_helpdesk_whatsapp_templates"), split_commas=True))


def _outgoing_email_available() -> bool:
    rows = _safe_list(
        "Email Account",
        filters=[["enable_outgoing", "=", 1]],
        fields=["name"],
        limit_page_length=1,
        ignore_permissions=True,
    )
    return bool(rows)


def _secure_endpoint(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.netloc)
        and not parsed.username
        and not parsed.password
    )


def _conf(name: str):
    conf = getattr(frappe, "conf", {})
    try:
        return conf.get(name)
    except Exception:
        return getattr(conf, name, None)


def _conf_bool(name: str) -> bool:
    value = _conf(name)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return value is True or value == 1


def _safe_list(doctype: str, **kwargs) -> list[dict]:
    try:
        rows = frappe.get_list(doctype, **kwargs)
    except Exception:
        return []
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _exists(doctype: str, name_or_filters) -> bool:
    try:
        value = frappe.db.exists(doctype, name_or_filters)
    except Exception:
        return False
    return bool(value) if isinstance(value, bool | int | str) else False


def _limit(value, minimum: int, maximum: int):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if parsed < minimum or parsed > maximum:
        return failure(
            f"limit must be between {minimum} and {maximum}.",
            code="VALIDATION_BAD_LIMIT",
        )
    return parsed


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _mask_phone(phone: str) -> str:
    return f"***{phone[-4:]}" if len(phone) >= 4 else "***"


def _channel_label(medium: str) -> str:
    return "WhatsApp" if medium == "Chat" else medium or "Other"


def _now_string() -> str:
    try:
        return str(frappe.utils.now_datetime())
    except Exception:
        return ""
