"""Public API wrappers for `counts.py`.

Business logic lives in `bude_api.services.analytics.counts`.
Endpoint names stay here for Frappe/mobile compatibility.
"""
import builtins
import inspect
try:
    import frappe
except ImportError:
    frappe = None
_PUBLIC_NAMES = {'generate_schedule'}
from ..services.analytics import counts as _service
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

def _call(name, *args, **kwargs):
    _sync_service_globals()
    return getattr(_service, name)(*args, **kwargs)
@_whitelist()
def generate_schedule(warehouse: str, days: int=90, item_limit: int=200, a_frequency_days: int=7, b_frequency_days: int=30, c_frequency_days: int=90, assigned_to: str | None=None):
    return _call("generate_schedule", warehouse, days, item_limit, a_frequency_days, b_frequency_days, c_frequency_days, assigned_to)
