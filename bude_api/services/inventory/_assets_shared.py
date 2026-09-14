"""Asset tracking endpoints (standard ERPNext Asset module — no custom DocTypes).

Reads:  list_assets, get_asset, get_asset_movements, list_locations,
        list_asset_categories
Writes: set_epc, create_asset_movement, create_asset_repair,
        create_maintenance_log

All persistence uses standard DocTypes: Asset, Asset Movement, Asset Repair,
Asset Maintenance Log, Location, Asset Category, Employee — plus the bude_epc
Custom Field.
"""

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success

from ..common.permissions import require_stock_execution_role

_EPC_DOCTYPES = {"Asset", "Item", "Serial No"}

_ASSET_LIST_FIELDS = [
    "name",
    "asset_name",
    "item_code",
    "asset_category",
    "location",
    "custodian",
    "status",
    "purchase_amount",
    "value_after_depreciation",
    "bude_epc",
]

def _whitelist(methods, allow_guest: bool = False):
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=methods)

def _erpnext_message(exc):
    msg = (str(exc) or "").strip() or "ERPNext rejected the document."
    try:
        from frappe.utils import strip_html_tags

        msg = strip_html_tags(msg).strip() or msg
    except Exception:
        pass
    return msg

def _mutate(action):
    try:
        return action()
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(_erpnext_message(exc), code="VALIDATION_ERPNEXT")
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")

_MOVE_PURPOSES = {"Issue", "Receipt", "Transfer"}

__all__ = [name for name in globals() if not name.startswith("__")]
