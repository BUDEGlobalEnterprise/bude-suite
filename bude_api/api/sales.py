"""Public API wrappers for `sales.py`.

Business logic lives in `bude_api.services.sales.legacy`.
Endpoint names stay here for Frappe/mobile compatibility.
"""
import builtins
import inspect
try:
    import frappe
except ImportError:
    frappe = None
_PUBLIC_NAMES = {'item_price', 'list_customers', 'create_order', 'my_orders', 'create_invoice', 'record_payment'}
from ..services.sales import legacy as _service
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
def item_price(item_code: str, price_list: str | None=None, warehouse: str | None=None):
    return _call("item_price", item_code, price_list, warehouse)

@_whitelist()
def list_customers(search: str | None=None, limit: int | None=None, offset: int=0):
    return _call("list_customers", search, limit, offset)

@_whitelist()
def create_order(customer: str, items: list, delivery_date: str | None=None, company: str | None=None, price_list: str | None=None):
    return _call("create_order", customer, items, delivery_date, company, price_list)

@_whitelist()
def my_orders(limit: int | None=None, offset: int=0):
    return _call("my_orders", limit, offset)

@_whitelist()
def create_invoice(customer: str, items: list, sales_order: str | None=None, posting_date: str | None=None, company: str | None=None):
    return _call("create_invoice", customer, items, sales_order, posting_date, company)

@_whitelist()
def record_payment(party: str, paid_amount, mode_of_payment: str, reference_no: str | None=None, reference_date: str | None=None, sales_invoice: str | None=None, company: str | None=None):
    return _call("record_payment", party, paid_amount, mode_of_payment, reference_no, reference_date, sales_invoice, company)
