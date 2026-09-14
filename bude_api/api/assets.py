"""Public API wrappers for `assets.py`.

Business logic lives in `bude_api.services.inventory.assets`.
Endpoint names stay here for Frappe/mobile compatibility.
"""
import builtins
import inspect
try:
    import frappe
except ImportError:
    frappe = None
_PUBLIC_NAMES = {'list_assets', 'get_asset', 'get_asset_movements', 'list_locations', 'list_asset_categories', 'set_epc', 'create_asset_movement', 'create_asset_repair', 'list_maintenance_logs', 'complete_maintenance_log'}
from ..services.inventory import assets as _service
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
@_whitelist(methods=["GET", "POST"])
def list_assets(search: str | None=None, location: str | None=None, custodian: str | None=None, status: str | None=None, category: str | None=None, limit: int=50):
    return _call("list_assets", search, location, custodian, status, category, limit)

@_whitelist(methods=["GET", "POST"])
def get_asset(name: str):
    return _call("get_asset", name)

@_whitelist(methods=["GET", "POST"])
def get_asset_movements(asset: str, limit: int=20):
    return _call("get_asset_movements", asset, limit)

@_whitelist(methods=["GET", "POST"])
def list_locations(limit: int=200):
    return _call("list_locations", limit)

@_whitelist(methods=["GET", "POST"])
def list_asset_categories(limit: int=200):
    return _call("list_asset_categories", limit)

@_whitelist(methods=["POST"])
def set_epc(doctype: str, name: str, epc: str):
    return _call("set_epc", doctype, name, epc)

@_whitelist(methods=["POST"])
def create_asset_movement(assets: list, purpose: str, target_location: str | None=None, to_employee: str | None=None, transaction_date: str | None=None):
    return _call("create_asset_movement", assets, purpose, target_location, to_employee, transaction_date)

@_whitelist(methods=["POST"])
def create_asset_repair(asset: str, failure_date: str | None=None, description: str | None=None, repair_cost: float | None=None):
    return _call("create_asset_repair", asset, failure_date, description, repair_cost)

@_whitelist(methods=["GET", "POST"])
def list_maintenance_logs(asset: str | None=None, status: str='Planned', limit: int=50):
    return _call("list_maintenance_logs", asset, status, limit)

@_whitelist(methods=["POST"])
def complete_maintenance_log(log: str, completion_date: str | None=None):
    return _call("complete_maintenance_log", log, completion_date)
