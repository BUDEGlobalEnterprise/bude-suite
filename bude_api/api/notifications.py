"""Public API wrappers for `notifications.py`.

Business logic lives in `bude_api.services.admin.notifications`.
Endpoint names stay here for Frappe/mobile compatibility.
"""
import builtins
import inspect
try:
    import frappe
except ImportError:
    frappe = None
_PUBLIC_NAMES = {'register_device', 'unregister_device', 'preferences', 'update_preferences', 'payloads', 'fan_out_notification_logs', 'route_for_category', 'list_registered_devices', 'revoke_registered_device'}
from ..services.admin import notifications as _service
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
def register_device(token: str, device_id: str, platform: str | None=None):
    return _call("register_device", token, device_id, platform)

@_whitelist()
def unregister_device(device_id: str | None=None):
    return _call("unregister_device", device_id)

@_whitelist()
def preferences():
    return _call("preferences")

@_whitelist()
def update_preferences(preferences: dict):
    return _call("update_preferences", preferences)

@_whitelist()
def payloads(limit: int | None=None, offset: int=0):
    return _call("payloads", limit, offset)

@_whitelist()
def fan_out_notification_logs(limit: int | None=None, dry_run: bool=False):
    return _call("fan_out_notification_logs", limit, dry_run)

def route_for_category(category: str):
    return _call("route_for_category", category)

def list_registered_devices():
    return _call("list_registered_devices")

def revoke_registered_device(user: str, device_id: str):
    return _call("revoke_registered_device", user, device_id)
