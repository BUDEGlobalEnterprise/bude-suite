"""Grouped service facade for `sales.legacy` endpoints."""

from . import pricing as _pricing
from .pricing import item_price
from . import customers_legacy as _customers_legacy
from .customers_legacy import list_customers
from . import orders_legacy as _orders_legacy
from .orders_legacy import create_order, my_orders
from . import invoice_payment as _invoice_payment
from .invoice_payment import create_invoice, record_payment
from . import _legacy_shared as _shared

for _name, _value in vars(_shared).items():
    if not _name.startswith("__"):
        globals().setdefault(_name, _value)

_GROUP_MODULES = [_pricing, _customers_legacy, _orders_legacy, _invoice_payment]

def sync_frappe(frappe_module):
    _shared.frappe = frappe_module
    _facade_globals = globals()
    _skip = {"_shared", "_GROUP_MODULES", "sync_frappe", "_facade_globals", "_skip", "_name", "_value", "module", "value"}
    for _name, _value in list(_facade_globals.items()):
        if _name.startswith("__") or _name in _skip:
            continue
        if hasattr(_shared, _name):
            setattr(_shared, _name, _value)
    for module in _GROUP_MODULES:
        if hasattr(module, "frappe"):
            module.frappe = frappe_module
        for _name, _value in list(_facade_globals.items()):
            if _name.startswith("__") or _name in _skip:
                continue
            if hasattr(module, _name):
                setattr(module, _name, _value)
        for value in vars(module).values():
            if callable(value) and hasattr(value, "__globals__") and "frappe" in value.__globals__:
                value.__globals__["frappe"] = frappe_module
