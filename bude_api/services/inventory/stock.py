"""Grouped service facade for `inventory.stock` endpoints."""

from . import material_requests as _material_requests
from .material_requests import create_material_request
from . import transfers as _transfers
from .transfers import create_transfer
from . import receipts as _receipts
from .receipts import create_receipt
from . import reconciliations as _reconciliations
from .reconciliations import create_reconciliation
from . import _stock_shared as _shared

for _name, _value in vars(_shared).items():
    if not _name.startswith("__"):
        globals().setdefault(_name, _value)

_GROUP_MODULES = [_material_requests, _transfers, _receipts, _reconciliations]

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
