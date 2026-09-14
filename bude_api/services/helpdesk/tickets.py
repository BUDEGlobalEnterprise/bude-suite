"""Grouped service facade for `helpdesk.tickets` endpoints."""

from . import ticket_records as _ticket_records
from .ticket_records import (
    support_pulse,
    my_tickets,
    agent_tickets,
    ticket_detail,
    suggest_articles,
    related_tickets,
    customer_ticket_context,
    ticket_assignments,
    saved_replies,
    ticket_sla_context,
    ticket_classification,
    ticket_team_context,
    ticket_organization_context,
    ticket_activity,
    create_ticket,
    close_ticket,
    reopen_ticket,
    set_status,
)
from . import comments as _comments
from .comments import reply, add_comment
from . import attachments as _attachments
from .attachments import upload_ticket_attachment
from . import agents as _agents
from .agents import assign_ticket, agents
from . import masters as _masters
from .masters import masters
from . import setup_health as _setup_health
from .setup_health import setup_health
from . import automation as _automation
from .automation import automation_status, evaluate_automation, retry_failed_automation
from . import channels as _channels
from .channels import (
    channel_health,
    ticket_delivery,
    forward_ticket,
    send_whatsapp_template,
    log_phone_activity,
)
from . import _tickets_shared as _shared

for _name, _value in vars(_shared).items():
    if not _name.startswith("__"):
        globals().setdefault(_name, _value)

_GROUP_MODULES = [
    _ticket_records,
    _comments,
    _attachments,
    _agents,
    _masters,
    _setup_health,
    _automation,
    _channels,
]


def sync_frappe(frappe_module):
    _shared.frappe = frappe_module
    _facade_globals = globals()
    _skip = {
        "_shared",
        "_GROUP_MODULES",
        "sync_frappe",
        "_facade_globals",
        "_skip",
        "_name",
        "_value",
        "module",
        "value",
    }
    for _name, _value in list(_facade_globals.items()):
        if _name.startswith("__") or _name in _skip:
            continue
        if hasattr(_shared, _name):
            setattr(_shared, _name, _value)
    for module in _GROUP_MODULES:
        if hasattr(module, "frappe"):
            module.frappe = frappe_module
        for _name, _value in list(_facade_globals.items()):
            if _name.startswith("__") or _name in _skip:
                continue
            if hasattr(module, _name):
                setattr(module, _name, _value)
        for value in vars(module).values():
            if callable(value) and hasattr(value, "__globals__") and "frappe" in value.__globals__:
                value.__globals__["frappe"] = frappe_module
