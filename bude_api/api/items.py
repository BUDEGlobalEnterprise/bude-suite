"""Public API wrappers for `items.py`.

Business logic lives in `bude_api.services.inventory.items`.
Endpoint names stay here for Frappe/mobile compatibility.
"""

import builtins
import inspect

try:
    import frappe
except ImportError:
    frappe = None
_PUBLIC_NAMES = {
    "search",
    "list_groups",
    "get_by_barcode",
    "get_ledger",
    "get_stock",
    "get_storage_locations",
    "get_movement_insight",
    "get_supply_demand",
    "get_quality_inspections",
    "get_reservations",
    "get_alternatives",
    "get_batches",
    "get_manufacturing_readiness",
    "get_production_status",
    "get_planning",
    "get_buying_insight",
    "get_serial_warranty",
}
from ..services.inventory import items as _service


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
    reserved = {
        "builtins",
        "inspect",
        "frappe",
        "_service",
        "_whitelist",
        "_export_service_helpers",
        "_sync_service_globals",
        "_call",
        "_PUBLIC_NAMES",
    } | _PUBLIC_NAMES
    for name, value in builtins.list(globals().items()):
        if name in reserved or name.startswith("__"):
            continue
        if hasattr(_service, name):
            setattr(_service, name, value)
    for value in builtins.list(vars(_service).values()):
        if (
            inspect.ismodule(value)
            and getattr(value, "__name__", "").startswith("bude_api.services")
            and hasattr(value, "frappe")
        ):
            value.frappe = frappe
        if (
            callable(value)
            and hasattr(value, "__globals__")
            and value.__globals__.get("__name__") == getattr(_service, "__name__", None)
            and "frappe" in value.__globals__
        ):
            value.__globals__["frappe"] = frappe
    if hasattr(_service, "sync_frappe"):
        _service.sync_frappe(frappe)


def _call(name, *args, **kwargs):
    _sync_service_globals()
    return getattr(_service, name)(*args, **kwargs)


@_whitelist()
def search(
    query: str = "",
    limit: int = 20,
    page: int = 0,
    warehouse: str | None = None,
    item_group: str | None = None,
    in_stock: str | None = None,
):
    return _call("search", query, limit, page, warehouse, item_group, in_stock)


@_whitelist()
def list_groups():
    return _call("list_groups")


@_whitelist()
def get_by_barcode(barcode: str):
    return _call("get_by_barcode", barcode)


@_whitelist()
def get_ledger(item_code: str, warehouse: str | None = None, limit: int = 50):
    return _call("get_ledger", item_code, warehouse, limit)


@_whitelist()
def get_stock(item_code: str, warehouse: str | None = None):
    return _call("get_stock", item_code, warehouse)


@_whitelist()
def get_storage_locations(item_code: str, limit: int = 20):
    return _call("get_storage_locations", item_code, limit)


@_whitelist()
def get_movement_insight(
    item_code: str,
    warehouse: str | None = None,
    days: int = 90,
):
    return _call("get_movement_insight", item_code, warehouse, days)


@_whitelist()
def get_supply_demand(
    item_code: str,
    warehouse: str | None = None,
    limit: int = 10,
):
    return _call("get_supply_demand", item_code, warehouse, limit)


@_whitelist()
def get_quality_inspections(item_code: str, limit: int = 10):
    return _call("get_quality_inspections", item_code, limit)


@_whitelist()
def get_reservations(
    item_code: str,
    warehouse: str | None = None,
    limit: int = 10,
):
    return _call("get_reservations", item_code, warehouse, limit)


@_whitelist()
def get_alternatives(
    item_code: str,
    warehouse: str | None = None,
    limit: int = 20,
):
    return _call("get_alternatives", item_code, warehouse, limit)


@_whitelist()
def get_batches(
    item_code: str,
    warehouse: str | None = None,
    limit: int = 20,
):
    return _call("get_batches", item_code, warehouse, limit)


@_whitelist()
def get_manufacturing_readiness(
    item_code: str,
    warehouse: str | None = None,
    quantity: float = 1,
    limit: int = 20,
):
    return _call(
        "get_manufacturing_readiness",
        item_code,
        warehouse,
        quantity,
        limit,
    )


@_whitelist()
def get_production_status(item_code: str, limit: int = 10):
    return _call("get_production_status", item_code, limit)


@_whitelist()
def get_planning(item_code: str, warehouse: str | None = None, horizon_days: int = 90):
    return _call("get_planning", item_code, warehouse, horizon_days)


@_whitelist()
def get_buying_insight(item_code: str, limit: int = 5):
    return _call("get_buying_insight", item_code, limit)


@_whitelist()
def get_serial_warranty(item_code: str, limit: int = 20):
    return _call("get_serial_warranty", item_code, limit)
