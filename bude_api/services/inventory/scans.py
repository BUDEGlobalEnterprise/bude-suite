"""RFID/barcode resolution endpoint.

    GET/POST /api/method/bude_api.api.scan.resolve_epc   (auth required)

Resolves a scanned EPC (or barcode) to a record, trying in order:
Asset.bude_epc → Serial No.bude_epc → Item.bude_epc → Item Barcode.
All reads use standard ERPNext DocTypes + the bude_epc Custom Field.
"""

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success

_ITEM_FIELDS = [
    "name",
    "item_code",
    "item_name",
    "description",
    "stock_uom",
    "has_batch_no",
    "has_serial_no",
    "create_new_batch",
    "image",
    "disabled",
]

_ASSET_FIELDS = [
    "name",
    "asset_name",
    "item_code",
    "asset_category",
    "location",
    "custodian",
    "status",
    "bude_epc",
]

_SERIAL_FIELDS = [
    "name",
    "item_code",
    "item_name",
    "warehouse",
    "status",
    "batch_no",
    "bude_epc",
]


def _whitelist(allow_guest: bool = False):
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=["GET", "POST"])


@_whitelist()
def resolve_epc(epc: str) -> dict:
    """Resolve a scanned EPC to an asset, serial, or item.

    Returns {match_type, asset?|serial?|item?}. match_type is null when the
    tag isn't registered anywhere — the client can then offer to bind it.
    """
    epc = (epc or "").strip()
    if not epc:
        return failure("epc is required.", code="VALIDATION_REQUIRED")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    asset = frappe.get_all("Asset", filters=[["bude_epc", "=", epc]], fields=_ASSET_FIELDS, limit=1)
    if asset:
        return success({"match_type": "asset", "asset": asset[0]})

    serial = frappe.get_all(
        "Serial No", filters=[["bude_epc", "=", epc]], fields=_SERIAL_FIELDS, limit=1
    )
    if serial:
        return success({"match_type": "serial", "serial": serial[0]})

    item = frappe.get_all("Item", filters=[["bude_epc", "=", epc]], fields=_ITEM_FIELDS, limit=1)
    if item:
        return success({"match_type": "item", "item": item[0]})

    # Fallback: a plain barcode stored on the Item Barcode child table.
    barcode_rows = frappe.get_all(
        "Item Barcode", filters=[["barcode", "=", epc]], fields=["parent"], limit=1
    )
    if barcode_rows:
        item = frappe.get_all(
            "Item",
            filters=[["item_code", "=", barcode_rows[0]["parent"]]],
            fields=_ITEM_FIELDS,
            limit=1,
        )
        if item:
            return success({"match_type": "item", "item": item[0]})

    return success({"match_type": None})
