"""Public API wrappers for `sales_mobile.py`.

Business logic lives in `bude_api.services.sales.mobile`.
Endpoint names stay here for Frappe/mobile compatibility.
"""
import builtins
import inspect
try:
    import frappe
except ImportError:
    frappe = None
_PUBLIC_NAMES = {'masters', 'dashboard', 'customers', 'customer_detail', 'customer_buying_history', 'customer_fulfillment', 'customer_quotation_guidance', 'customer_item_pricing', 'customer_opportunities', 'customer_account_team', 'customer_returns', 'customer_receipts', 'customer_loyalty', 'customer_dunnings', 'customer_maintenance', 'customer_warranty_claims', 'items', 'field_day', 'collections_queue', 'create_visit', 'visit_check_in', 'visit_check_out', 'commercial_preview', 'create_quotation', 'create_order', 'create_invoice', 'record_payment', 'team_summary'}
from ..services.sales import mobile as _service
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
def masters():
    return _call("masters")

@_whitelist()
def dashboard(scope: str | None=None, from_date: str | None=None, to_date: str | None=None, sales_person: str | None=None, territory: str | None=None):
    return _call("dashboard", scope, from_date, to_date, sales_person, territory)

@_whitelist()
def customers(search: str | None=None, territory: str | None=None, assigned_to_me: bool=False, limit: int | None=None, offset: int=0):
    return _call("customers", search, territory, assigned_to_me, limit, offset)

@_whitelist()
def customer_detail(customer: str):
    return _call("customer_detail", customer)

@_whitelist()
def customer_buying_history(customer: str, limit: int=5):
    return _call("customer_buying_history", customer, limit)

@_whitelist()
def customer_fulfillment(customer: str, limit: int=10):
    return _call("customer_fulfillment", customer, limit)

@_whitelist()
def customer_quotation_guidance(customer: str, limit: int=10):
    return _call("customer_quotation_guidance", customer, limit)

@_whitelist()
def customer_item_pricing(customer: str, limit: int=10):
    return _call("customer_item_pricing", customer, limit)

@_whitelist()
def customer_opportunities(customer: str, limit: int=10):
    return _call("customer_opportunities", customer, limit)

@_whitelist()
def customer_account_team(customer: str):
    return _call("customer_account_team", customer)

@_whitelist()
def customer_returns(customer: str, limit: int=10):
    return _call("customer_returns", customer, limit)

@_whitelist()
def customer_receipts(customer: str, limit: int=10):
    return _call("customer_receipts", customer, limit)

@_whitelist()
def customer_loyalty(customer: str, limit: int=20):
    return _call("customer_loyalty", customer, limit)

@_whitelist()
def customer_dunnings(customer: str, limit: int=10):
    return _call("customer_dunnings", customer, limit)

@_whitelist()
def customer_maintenance(customer: str, limit: int=10):
    return _call("customer_maintenance", customer, limit)

@_whitelist()
def customer_warranty_claims(customer: str, limit: int=10):
    return _call("customer_warranty_claims", customer, limit)

@_whitelist()
def items(search: str | None=None, item_group: str | None=None, price_list: str | None=None, warehouse: str | None=None, limit: int | None=None, offset: int=0):
    return _call("items", search, item_group, price_list, warehouse, limit, offset)

@_whitelist(["GET"])
def field_day(day: str | None=None, territory: str | None=None):
    return _call("field_day", day, territory)

@_whitelist(["GET"])
def collections_queue(search: str | None=None, overdue_only: bool=False, company: str | None=None, limit: int | None=None, offset: int=0):
    return _call("collections_queue", search, overdue_only, company, limit, offset)

@_whitelist(["POST"])
def create_visit(customer: str, contact: str | None=None, notes: str | None=None, next_follow_up: str | None=None, latitude=None, longitude=None):
    return _call("create_visit", customer, contact, notes, next_follow_up, latitude, longitude)

@_whitelist(["POST"])
def visit_check_in(customer: str, latitude, longitude, accuracy=None, client_request_id: str | None=None):
    return _call("visit_check_in", customer, latitude, longitude, accuracy, client_request_id)

@_whitelist(["POST"])
def visit_check_out(event: str, latitude, longitude, accuracy=None, notes: str | None=None, client_request_id: str | None=None):
    return _call("visit_check_out", event, latitude, longitude, accuracy, notes, client_request_id)

@_whitelist(["POST"])
def create_quotation(customer: str, items: list, valid_till: str | None=None, price_list: str | None=None, company: str | None=None, client_request_id: str | None=None):
    return _call("create_quotation", customer, items, valid_till, price_list, company, client_request_id)

@_whitelist(["POST"])
def create_order(customer: str, items: list, delivery_date: str | None=None, price_list: str | None=None, company: str | None=None, submit: bool=False, client_request_id: str | None=None):
    return _call("create_order", customer, items, delivery_date, price_list, company, submit, client_request_id)

@_whitelist(["POST"])
def create_invoice(customer: str, items: list, sales_order: str | None=None, company: str | None=None, submit: bool=True, client_request_id: str | None=None):
    return _call("create_invoice", customer, items, sales_order, company, submit, client_request_id)

@_whitelist(["POST"])
def record_payment(customer: str, amount, mode_of_payment: str, reference_no: str | None=None, reference_date: str | None=None, invoice: str | None=None, company: str | None=None, client_request_id: str | None=None):
    return _call("record_payment", customer, amount, mode_of_payment, reference_no, reference_date, invoice, company, client_request_id)

@_whitelist(["POST"])
def commercial_preview(customer: str, items: list, price_list: str | None=None, company: str | None=None):
    return _call("commercial_preview", customer, items, price_list, company)

@_whitelist()
def team_summary(from_date: str | None=None, to_date: str | None=None, territory: str | None=None, sales_person: str | None=None):
    return _call("team_summary", from_date, to_date, territory, sales_person)
