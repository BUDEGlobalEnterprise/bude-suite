"""Grouped service facade for `sales.mobile` endpoints."""

from . import masters as _masters
from .masters import masters
from . import dashboard as _dashboard
from .dashboard import dashboard, team_summary
from . import customers as _customers
from .customers import customers, customer_detail, customer_buying_history, customer_fulfillment, customer_quotation_guidance, customer_item_pricing, customer_opportunities, customer_account_team, customer_returns, customer_receipts, customer_loyalty, customer_dunnings, customer_maintenance, customer_warranty_claims
from . import catalog as _catalog
from .catalog import items
from . import visits as _visits
from .visits import create_visit, visit_check_in, visit_check_out
from . import field_day as _field_day
from .field_day import field_day
from . import collections as _collections
from .collections import collections_queue
from . import documents as _documents
from .documents import commercial_preview, create_quotation, create_order, create_invoice, record_payment
from . import _mobile_shared as _shared

for _name, _value in vars(_shared).items():
    if not _name.startswith("__"):
        globals().setdefault(_name, _value)

_GROUP_MODULES = [_masters, _dashboard, _customers, _catalog, _visits, _field_day, _collections, _documents]

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
