"""Public API wrappers for `helpdesk.py`.

Business logic lives in `bude_api.services.helpdesk.tickets`.
Endpoint names stay here for Frappe/mobile compatibility.
"""

import builtins
import inspect

try:
    import frappe
except ImportError:
    frappe = None
_PUBLIC_NAMES = {
    "my_tickets",
    "support_pulse",
    "setup_health",
    "automation_status",
    "evaluate_automation",
    "retry_failed_automation",
    "channel_health",
    "ticket_delivery",
    "forward_ticket",
    "send_whatsapp_template",
    "log_phone_activity",
    "agent_tickets",
    "ticket_detail",
    "suggest_articles",
    "related_tickets",
    "customer_ticket_context",
    "ticket_assignments",
    "saved_replies",
    "ticket_sla_context",
    "ticket_classification",
    "ticket_team_context",
    "ticket_organization_context",
    "ticket_activity",
    "create_ticket",
    "reply",
    "close_ticket",
    "reopen_ticket",
    "set_status",
    "assign_ticket",
    "add_comment",
    "upload_ticket_attachment",
    "agents",
    "masters",
}
from ..services.helpdesk import tickets as _service


def _whitelist(methods=None, allow_guest: bool = False):
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=methods or ["GET", "POST"])


def _export_service_helpers():
    for name, value in vars(_service).items():
        if name == "frappe" or name.startswith("__"):
            continue
        globals().setdefault(name, value)


_export_service_helpers()


def _sync_service_globals():
    if hasattr(_service, "frappe"):
        _service.frappe = frappe
    if hasattr(_service, "sync_frappe"):
        _service.sync_frappe(frappe)
    reserved = {
        "builtins",
        "inspect",
        "frappe",
        "_service",
        "_whitelist",
        "_export_service_helpers",
        "_sync_service_globals",
        "_call",
        "_PUBLIC_NAMES",
    } | _PUBLIC_NAMES
    for name, value in builtins.list(globals().items()):
        if name in reserved or name.startswith("__"):
            continue
        if hasattr(_service, name):
            setattr(_service, name, value)
    for value in builtins.list(vars(_service).values()):
        if (
            inspect.ismodule(value)
            and getattr(value, "__name__", "").startswith("bude_api.services")
            and hasattr(value, "frappe")
        ):
            value.frappe = frappe
        if (
            callable(value)
            and hasattr(value, "__globals__")
            and value.__globals__.get("__name__") == getattr(_service, "__name__", None)
            and "frappe" in value.__globals__
        ):
            value.__globals__["frappe"] = frappe
    if hasattr(_service, "sync_frappe"):
        _service.sync_frappe(frappe)


def _call(name, *args, **kwargs):
    _sync_service_globals()
    return getattr(_service, name)(*args, **kwargs)


@_whitelist(["GET", "POST"])
def my_tickets(
    status: str | None = None,
    priority: str | None = None,
    ticket_type: str | None = None,
    team: str | None = None,
    search: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
):
    return _call(
        "my_tickets", status, priority, ticket_type, team, search, from_date, to_date, limit, offset
    )


@_whitelist(["GET", "POST"])
def support_pulse(limit: int = 5, due_soon_hours: int = 4):
    return _call("support_pulse", limit, due_soon_hours)


@_whitelist(["GET", "POST"])
def setup_health():
    return _call("setup_health")


@_whitelist(["GET", "POST"])
def automation_status():
    return _call("automation_status")


@_whitelist(["POST"])
def evaluate_automation(dry_run=True):
    return _call("evaluate_automation", dry_run)


@_whitelist(["POST"])
def retry_failed_automation(limit=20):
    return _call("retry_failed_automation", limit)


@_whitelist(["GET", "POST"])
def channel_health():
    return _call("channel_health")


@_whitelist(["GET", "POST"])
def ticket_delivery(ticket_name: str, limit: int = 50):
    return _call("ticket_delivery", ticket_name, limit)


@_whitelist(["POST"])
def forward_ticket(
    ticket_name: str,
    recipients,
    subject: str,
    content: str,
    attachment_names=None,
    cc=None,
):
    return _call(
        "forward_ticket",
        ticket_name,
        recipients,
        subject,
        content,
        attachment_names,
        cc,
    )


@_whitelist(["POST"])
def send_whatsapp_template(
    ticket_name: str,
    template: str,
    variables=None,
    consent_reference: str | None = None,
    request_key: str | None = None,
):
    return _call(
        "send_whatsapp_template",
        ticket_name,
        template,
        variables,
        consent_reference,
        request_key,
    )


@_whitelist(["POST"])
def log_phone_activity(
    ticket_name: str,
    direction: str,
    duration_seconds=0,
    summary: str | None = None,
    external_call_id: str | None = None,
):
    return _call(
        "log_phone_activity",
        ticket_name,
        direction,
        duration_seconds,
        summary,
        external_call_id,
    )


@_whitelist(["GET", "POST"])
def agent_tickets(
    status: str | None = None,
    priority: str | None = None,
    ticket_type: str | None = None,
    team: str | None = None,
    search: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    assigned_to_me: bool = False,
    unassigned: bool = False,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
):
    return _call(
        "agent_tickets",
        status,
        priority,
        ticket_type,
        team,
        search,
        from_date,
        to_date,
        assigned_to_me,
        unassigned,
        limit,
        offset,
    )


@_whitelist(["GET", "POST"])
def ticket_detail(ticket_name: str):
    return _call("ticket_detail", ticket_name)


@_whitelist(["GET", "POST"])
def suggest_articles(ticket_name: str, limit: int = 3):
    return _call("suggest_articles", ticket_name, limit)


@_whitelist(["GET", "POST"])
def related_tickets(ticket_name: str, limit: int = 5):
    return _call("related_tickets", ticket_name, limit)


@_whitelist(["GET", "POST"])
def customer_ticket_context(ticket_name: str, limit: int = 5):
    return _call("customer_ticket_context", ticket_name, limit)


@_whitelist(["GET", "POST"])
def ticket_assignments(ticket_name: str):
    return _call("ticket_assignments", ticket_name)


@_whitelist(["GET", "POST"])
def saved_replies(ticket_name: str, limit: int = 5):
    return _call("saved_replies", ticket_name, limit)


@_whitelist(["GET", "POST"])
def ticket_sla_context(ticket_name: str):
    return _call("ticket_sla_context", ticket_name)


@_whitelist(["GET", "POST"])
def ticket_classification(ticket_name: str):
    return _call("ticket_classification", ticket_name)


@_whitelist(["GET", "POST"])
def ticket_team_context(ticket_name: str):
    return _call("ticket_team_context", ticket_name)


@_whitelist(["GET", "POST"])
def ticket_organization_context(ticket_name: str):
    return _call("ticket_organization_context", ticket_name)


@_whitelist(["GET", "POST"])
def ticket_activity(ticket_name: str, limit: int = 30):
    return _call("ticket_activity", ticket_name, limit)


@_whitelist(["POST"])
def create_ticket(
    subject: str, description: str, priority: str | None = None, ticket_type: str | None = None
):
    return _call("create_ticket", subject, description, priority, ticket_type)


@_whitelist(["POST"])
def reply(ticket_name: str, content: str):
    return _call("reply", ticket_name, content)


@_whitelist(["POST"])
def close_ticket(ticket_name: str):
    return _call("close_ticket", ticket_name)


@_whitelist(["POST"])
def reopen_ticket(ticket_name: str):
    return _call("reopen_ticket", ticket_name)


@_whitelist(["POST"])
def set_status(ticket_name: str, status: str):
    return _call("set_status", ticket_name, status)


@_whitelist(["POST"])
def assign_ticket(ticket_name: str, agent_email: str):
    return _call("assign_ticket", ticket_name, agent_email)


@_whitelist(["POST"])
def add_comment(ticket_name: str, content: str):
    return _call("add_comment", ticket_name, content)


@_whitelist(["POST"])
def upload_ticket_attachment(ticket_name: str, file_name: str, content_base64: str):
    return _call("upload_ticket_attachment", ticket_name, file_name, content_base64)


@_whitelist(["GET", "POST"])
def agents(team: str | None = None, search: str | None = None):
    return _call("agents", team, search)


@_whitelist(["GET", "POST"])
def masters():
    return _call("masters")
