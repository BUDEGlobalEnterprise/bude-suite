"""Public API wrappers for `permissions.py`.

Business logic lives in `bude_api.services.common.permissions`.
Endpoint names stay here for Frappe/mobile compatibility.
"""
import builtins
import inspect
try:
    import frappe
except ImportError:
    frappe = None
_PUBLIC_NAMES = {'auth_expired', 'permission_denied', 'has_any_role', 'require_any_role', 'require_stock_execution_role', 'require_sales_role', 'require_helpdesk_agent_role'}
from ..services.common import permissions as _service
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
def auth_expired(message: str='Your session has expired. Please sign in again.'):
    return _call("auth_expired", message)

def permission_denied(message: str='You do not have permission for this action.'):
    return _call("permission_denied", message)

def has_any_role(frappe_module, allowed_roles: set[str]):
    return _call("has_any_role", frappe_module, allowed_roles)

def require_any_role(frappe_module, allowed_roles: set[str], message: str='You do not have permission for this action.'):
    return _call("require_any_role", frappe_module, allowed_roles, message)

def require_stock_execution_role(frappe_module):
    return _call("require_stock_execution_role", frappe_module)

def require_sales_role(frappe_module):
    return _call("require_sales_role", frappe_module)

def require_helpdesk_agent_role(frappe_module):
    return _call("require_helpdesk_agent_role", frappe_module)
