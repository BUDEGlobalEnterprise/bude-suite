"""Public API wrappers for `masters.py`.

Business logic lives in `bude_api.services.admin.masters`.
Endpoint names stay here for Frappe/mobile compatibility.
"""
import builtins
import inspect
try:
    import frappe
except ImportError:
    frappe = None
_PUBLIC_NAMES = {'list_masters', 'list_records', 'get_record', 'list_link_options', 'create_record', 'update_record', 'set_disabled'}
from ..services.admin import masters as _service
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
@_whitelist(methods=["GET"], allow_guest=False)
def list_masters():
    return _call("list_masters")

@_whitelist(methods=["GET"], allow_guest=False)
def list_records(master, search=None, limit=50, offset=0):
    return _call("list_records", master, search, limit, offset)

@_whitelist(methods=["GET"], allow_guest=False)
def get_record(master, name):
    return _call("get_record", master, name)

@_whitelist(methods=["GET"], allow_guest=False)
def list_link_options(doctype, search=None, limit=20):
    return _call("list_link_options", doctype, search, limit)

@_whitelist(methods=["POST"], allow_guest=False)
def create_record(master, values):
    return _call("create_record", master, values)

@_whitelist(methods=["POST"], allow_guest=False)
def update_record(master, name, values):
    return _call("update_record", master, name, values)

@_whitelist(methods=["POST"], allow_guest=False)
def set_disabled(master, name, disabled=True):
    return _call("set_disabled", master, name, disabled)
