"""Batch and serial lookup endpoints.

Uses standard ERPNext Batch and Serial No DocTypes only. Lots are represented
as Batch records.
"""

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success


def _whitelist(allow_guest: bool = False):
    if frappe is None:
        def decorator(fn):
            return fn
        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=["GET", "POST"])


@_whitelist()
def batches(
    item_code: str,
    warehouse: str | None = None,
    include_expired: bool | str = False,
    limit: int = 100,
) -> dict:
    """Return Batch rows for an item, optionally filtered to batches in stock."""
    item_code = (item_code or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    try:
        limit = max(1, min(int(limit), 500))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")

    filters: list = [["item", "=", item_code], ["disabled", "=", 0]]

    rows = frappe.get_list(
        "Batch",
        filters=filters,
        fields=["name", "batch_id", "item", "expiry_date", "disabled"],
        order_by="expiry_date asc, name asc",
        limit_page_length=limit,
    )
    if not _truthy(include_expired):
        today = _today()
        rows = [
            row for row in rows
            if not row.get("expiry_date") or str(row.get("expiry_date")) >= today
        ]

    if warehouse:
        available = set(frappe.get_list(
            "Stock Ledger Entry",
            filters=[
                ["item_code", "=", item_code],
                ["warehouse", "=", warehouse],
                ["batch_no", "is", "set"],
                ["is_cancelled", "=", 0],
            ],
            pluck="batch_no",
            limit=5000,
        ))
        rows = [row for row in rows if _batch_no(row) in available]

    return success([_batch_payload(row) for row in rows])


@_whitelist()
def serials(
    item_code: str,
    warehouse: str | None = None,
    batch_no: str | None = None,
    limit: int = 100,
) -> dict:
    """Return available Serial No rows for an item."""
    item_code = (item_code or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    try:
        limit = max(1, min(int(limit), 500))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")

    filters: list = [["item_code", "=", item_code]]
    if warehouse:
        filters.append(["warehouse", "=", warehouse])
    if batch_no:
        filters.append(["batch_no", "=", batch_no])

    rows = frappe.get_list(
        "Serial No",
        filters=filters,
        fields=["name", "item_code", "warehouse", "status", "batch_no"],
        order_by="name asc",
        limit_page_length=limit,
    )
    return success(rows)


def _batch_payload(row: dict) -> dict:
    return {
        "batch_no": _batch_no(row),
        "batch_id": row.get("batch_id"),
        "item_code": row.get("item"),
        "expiry_date": row.get("expiry_date"),
        "disabled": row.get("disabled"),
    }


def _batch_no(row: dict) -> str:
    return row.get("name") or row.get("batch_id")


def _today() -> str:
    try:
        return frappe.utils.nowdate()
    except Exception:
        from datetime import date
        return date.today().isoformat()


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}
