"""RFID EPC custom fields on standard ERPNext doctypes.

No custom DocTypes — these are plain Custom Field records created idempotently
after every migrate via ERPNext's own helper. Storing an EPC on Asset / Serial
No / Item lets a handheld RFID read resolve to the right record (see
`bude_api.api.scan.resolve_epc`).
"""

try:
    import frappe  # noqa: F401
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
except ImportError:  # pragma: no cover - allows import without Frappe installed
    frappe = None
    create_custom_fields = None

CUSTOM_FIELDS = {
    "Asset": [
        {
            "fieldname": "bude_epc",
            "label": "RFID EPC",
            "fieldtype": "Data",
            "unique": 1,
            "insert_after": "asset_name",
            "description": "RFID tag EPC for handheld scanning (bude_api).",
            "translatable": 0,
        }
    ],
    "Serial No": [
        {
            "fieldname": "bude_epc",
            "label": "RFID EPC",
            "fieldtype": "Data",
            "insert_after": "serial_no",
            "description": "RFID tag EPC for handheld scanning (bude_api).",
            "translatable": 0,
        }
    ],
    "Item": [
        {
            "fieldname": "bude_epc",
            "label": "RFID EPC",
            "fieldtype": "Data",
            "insert_after": "item_code",
            "description": "RFID tag EPC for bulk item-level scanning (bude_api).",
            "translatable": 0,
        }
    ],
}


def ensure_custom_fields() -> None:
    """Create/update the bude_epc Custom Fields. Idempotent — safe to re-run."""
    if create_custom_fields is None:
        return
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
