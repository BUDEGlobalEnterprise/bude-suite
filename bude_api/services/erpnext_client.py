"""Thin wrapper around Frappe ORM for ERPNext standard DocTypes.

Rules:
- Only standard DocTypes (Item, Item Barcode, Stock Entry, Warehouse, Serial No, Batch, ...).
- No custom DocType creation.
- Read-only helpers here in Phase 1; write paths via dedicated services in Phase 2.
"""

from typing import Any

try:
    import frappe
except ImportError:
    frappe = None


_SUPPORTED_DOCTYPES = {
    "Item",
    "Item Barcode",
    "Bin",
    "Stock Entry",
    "Stock Ledger Entry",
    "Serial No",
    "Batch",
    "Warehouse",
    "Sales Order",
    "Purchase Receipt",
    "Delivery Note",
    "Stock Reconciliation",
    "Asset",
}


class ERPNextClient:
    def _guard(self) -> None:
        if frappe is None:
            raise RuntimeError("Frappe is not available — run inside a Frappe bench.")

    def get(self, doctype: str, name: str) -> dict[str, Any]:
        self._guard()
        if doctype not in _SUPPORTED_DOCTYPES:
            raise ValueError(f"DocType '{doctype}' is not in the supported standard set.")
        return frappe.get_doc(doctype, name).as_dict()

    def list(
        self,
        doctype: str,
        filters: list | None = None,
        fields: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self._guard()
        if doctype not in _SUPPORTED_DOCTYPES:
            raise ValueError(f"DocType '{doctype}' is not in the supported standard set.")
        return frappe.get_list(
            doctype,
            filters=filters or [],
            fields=fields or ["name"],
            limit=limit,
        )
