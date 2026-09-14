"""Public API wrappers for `stock.py`.

Business logic lives in `bude_api.services.inventory.stock`.
Endpoint names stay here for Frappe/mobile compatibility.
"""
import builtins
import inspect
try:
    import frappe
except ImportError:
    frappe = None
_PUBLIC_NAMES = {'create_material_request', 'create_transfer', 'create_receipt', 'create_reconciliation'}
from ..services.inventory import stock as _service
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
def create_material_request(items: list, schedule_date: str | None=None, company: str | None=None):
    return _call("create_material_request", items, schedule_date, company)

@_whitelist()
def create_transfer(items: list, source_warehouse: str, target_warehouse: str, posting_date: str | None=None, company: str | None=None, source_location: str | None=None, target_location: str | None=None, unresolved_scans: list | None=None):
    return _call("create_transfer", items, source_warehouse, target_warehouse, posting_date, company, source_location, target_location, unresolved_scans)

@_whitelist()
def create_receipt(items: list, target_warehouse: str, against_po: str | None=None, posting_date: str | None=None, company: str | None=None, target_location: str | None=None, unresolved_scans: list | None=None):
    return _call("create_receipt", items, target_warehouse, against_po, posting_date, company, target_location, unresolved_scans)

@_whitelist()
def create_reconciliation(counts: list, warehouse: str, posting_date: str | None=None, company: str | None=None, location: str | None=None, unresolved_scans: list | None=None):
    return _call("create_reconciliation", counts, warehouse, posting_date, company, location, unresolved_scans)
