"""Public API wrappers for `field_service.py`.

Business logic lives in `bude_api.services.helpdesk.field_service`.
Endpoint names stay here for Frappe/mobile compatibility.
"""
import builtins
import inspect
try:
    import frappe
except ImportError:
    frappe = None
_PUBLIC_NAMES = {'job_site', 'job_check_in', 'job_check_out', 'complete_visit'}
from ..services.helpdesk import field_service as _service
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
    reserved = {"builtins", "inspect", "frappe", "_service", "_whitelist", "_export_service_helpers", "_sync_service_globals", "_call", "_PUBLIC_NAMES"} | _PUBLIC_NAMES
    for name, value in builtins.list(globals().items()):
        if name in reserved or name.startswith("__"):
            continue
        if hasattr(_service, name):
            setattr(_service, name, value)
    for value in builtins.list(vars(_service).values()):
        if inspect.ismodule(value) and getattr(value, "__name__", "").startswith("bude_api.services") and hasattr(value, "frappe"):
            value.frappe = frappe
        if callable(value) and hasattr(value, "__globals__") and value.__globals__.get("__name__") == getattr(_service, "__name__", None) and "frappe" in value.__globals__:
            value.__globals__["frappe"] = frappe
    if hasattr(_service, "sync_frappe"):
        _service.sync_frappe(frappe)
    from . import helpdesk as _helpdesk_api

    for helper_name in ("_require_helpdesk", "_set_ticket_status"):
        helper = getattr(_service, helper_name, None)
        if callable(helper) and hasattr(helper, "__globals__") and "frappe" in helper.__globals__:
            helper.__globals__["frappe"] = _helpdesk_api.frappe

def _call(name, *args, **kwargs):
    _sync_service_globals()
    return getattr(_service, name)(*args, **kwargs)
@_whitelist(["GET", "POST"])
def job_site(ticket_name: str):
    return _call("job_site", ticket_name)

@_whitelist(["POST"])
def job_check_in(ticket_name: str, latitude=None, longitude=None):
    return _call("job_check_in", ticket_name, latitude, longitude)

@_whitelist(["POST"])
def job_check_out(ticket_name: str, latitude=None, longitude=None):
    return _call("job_check_out", ticket_name, latitude, longitude)

@_whitelist(["POST"])
def complete_visit(ticket_name: str, work_done: str, completion_status: str='Fully Completed', maintenance_type: str='Unscheduled', resolve_ticket: bool=False):
    return _call("complete_visit", ticket_name, work_done, completion_status, maintenance_type, resolve_ticket)
