"""Grouped service facade for `admin.notifications` endpoints."""

from . import notification_devices as _notification_devices
from .notification_devices import register_device, unregister_device, list_registered_devices, revoke_registered_device
from . import notification_preferences as _notification_preferences
from .notification_preferences import preferences, update_preferences
from . import notification_payloads as _notification_payloads
from .notification_payloads import payloads, route_for_category
from . import notification_fanout as _notification_fanout
from .notification_fanout import fan_out_notification_logs
from . import _notifications_shared as _shared

for _name, _value in vars(_shared).items():
    if not _name.startswith("__"):
        globals().setdefault(_name, _value)

_GROUP_MODULES = [_notification_devices, _notification_preferences, _notification_payloads, _notification_fanout]

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
