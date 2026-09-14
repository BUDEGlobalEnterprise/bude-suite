"""Public API wrappers for `admin_onboarding.py`.

Business logic lives in `bude_api.services.admin.onboarding`.
Endpoint names stay here for Frappe/mobile compatibility.
"""
import builtins
import inspect
try:
    import frappe
except ImportError:
    frappe = None
_PUBLIC_NAMES = {'role_profiles', 'users', 'assign_role_profile', 'devices', 'revoke_device', 'seed_pilot_workflow'}
from ..services.admin import onboarding as _service
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
def role_profiles(limit: int=50):
    return _call("role_profiles", limit)

@_whitelist(methods=["GET"], allow_guest=False)
def users(limit: int=50, search: str | None=None):
    return _call("users", limit, search)

@_whitelist(methods=["POST"], allow_guest=False)
def assign_role_profile(user: str, role_profile: str):
    return _call("assign_role_profile", user, role_profile)

@_whitelist(methods=["GET"], allow_guest=False)
def devices():
    return _call("devices")

@_whitelist(methods=["POST"], allow_guest=False)
def revoke_device(user: str, device_id: str):
    return _call("revoke_device", user, device_id)

@_whitelist(methods=["POST"], allow_guest=False)
def seed_pilot_workflow(confirm: bool=False, profile: str='preview', base_url: str | None=None, dry_run: bool=False):
    return _call("seed_pilot_workflow", confirm, profile, base_url, dry_run)
