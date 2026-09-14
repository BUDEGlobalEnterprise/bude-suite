"""Shared batch/serial allocation validation for stock write endpoints."""

from __future__ import annotations

from collections.abc import Callable
from math import isclose

from ...utils.response import failure

_QTY_EPSILON = 0.000001


def expand_stock_rows(
    frappe,
    lines: list,
    *,
    warehouse: str,
    flow: str,
    row_builder: Callable[[dict, dict | None], dict],
    allow_new_batches: bool = False,
    allow_new_serials: bool = False,
) -> list[dict] | dict:
    """Validate tracking allocations and return ERPNext child rows.

    `flow` is one of inbound, outbound, or count. Existing untracked payloads
    with no allocations are returned as one row per mobile line.
    """
    expanded: list[dict] = []
    for line in lines:
        item_code = (line.get("item_code") or "").strip()
        item = _item_tracking_info(frappe, item_code)
        allocations = line.get("allocations") or []
        if item is None and not allocations:
            expanded.append(row_builder(line, None))
            continue
        if item is None:
            return failure(
                f"Unknown item(s): {item_code}",
                code="VALIDATION_UNKNOWN_ITEM",
            )

        if not isinstance(allocations, list):
            return failure(
                f"allocations must be a list for {item_code}.",
                code="VALIDATION_BAD_SHAPE",
            )

        has_batch = _truthy(item.get("has_batch_no"))
        has_serial = _truthy(item.get("has_serial_no"))
        if not allocations:
            if has_batch:
                return failure(
                    f"Batch is required for {item_code}.",
                    code="VALIDATION_MISSING_BATCH",
                )
            if has_serial:
                return failure(
                    f"Serial numbers are required for {item_code}.",
                    code="VALIDATION_MISSING_SERIAL",
                )
            expanded.append(row_builder(line, None))
            continue

        if not has_batch and any((a or {}).get("batch_no") for a in allocations):
            return failure(
                f"{item_code} is not batch tracked.",
                code="VALIDATION_UNTRACKED_ALLOCATION",
            )
        if not has_serial and any((a or {}).get("serial_nos") for a in allocations):
            return failure(
                f"{item_code} is not serial tracked.",
                code="VALIDATION_UNTRACKED_ALLOCATION",
            )

        qty_error = _validate_allocation_total(item_code, line, allocations)
        if qty_error is not None:
            return qty_error

        for allocation in allocations:
            if not isinstance(allocation, dict):
                return failure(
                    f"Each allocation for {item_code} must be an object.",
                    code="VALIDATION_BAD_SHAPE",
                )
            alloc = dict(allocation)
            batch_no = (alloc.get("batch_no") or "").strip()
            serial_nos = _serial_list(alloc.get("serial_nos"))
            qty = _qty(alloc.get("qty"))

            if has_batch:
                if not batch_no:
                    return failure(
                        f"Batch is required for {item_code}.",
                        code="VALIDATION_MISSING_BATCH",
                    )
                batch_error = _validate_batch(
                    frappe,
                    item_code,
                    batch_no,
                    alloc.get("expiry_date"),
                    flow=flow,
                    allow_new=allow_new_batches,
                )
                if batch_error is not None:
                    return batch_error
            elif batch_no:
                return failure(
                    f"{item_code} is not batch tracked.",
                    code="VALIDATION_UNTRACKED_ALLOCATION",
                )

            if has_serial:
                if not serial_nos:
                    return failure(
                        f"Serial numbers are required for {item_code}.",
                        code="VALIDATION_MISSING_SERIAL",
                    )
                if not _serial_qty_matches(qty, serial_nos):
                    return failure(
                        f"Serial count must match qty for {item_code}.",
                        code="VALIDATION_SERIAL_COUNT_MISMATCH",
                    )
                serial_error = _validate_serials(
                    frappe,
                    item_code,
                    serial_nos,
                    warehouse,
                    batch_no or None,
                    flow=flow,
                    allow_new=allow_new_serials,
                )
                if serial_error is not None:
                    return serial_error
            elif serial_nos:
                return failure(
                    f"{item_code} is not serial tracked.",
                    code="VALIDATION_UNTRACKED_ALLOCATION",
                )

            erp_row = row_builder(line, alloc)
            if batch_no:
                erp_row["batch_no"] = batch_no
            if serial_nos:
                erp_row["serial_no"] = "\n".join(serial_nos)
            erp_row["qty"] = qty
            expanded.append(erp_row)

    return expanded


def _item_tracking_info(frappe, item_code: str) -> dict | None:
    rows = frappe.get_list(
        "Item",
        filters=[["item_code", "=", item_code]],
        fields=[
            "item_code",
            "has_batch_no",
            "has_serial_no",
            "create_new_batch",
            "stock_uom",
        ],
        limit=1,
    )
    return rows[0] if rows else None


def _validate_allocation_total(item_code: str, line: dict, allocations: list) -> dict | None:
    try:
        line_qty = _qty(line.get("qty"))
        total = sum(_qty((allocation or {}).get("qty")) for allocation in allocations)
    except (TypeError, ValueError):
        return failure(
            f"Invalid allocation qty for {item_code}.",
            code="VALIDATION_BAD_QTY",
        )
    if not isclose(line_qty, total, abs_tol=_QTY_EPSILON):
        return failure(
            f"Allocation qty must equal line qty for {item_code}.",
            code="VALIDATION_ALLOCATION_QTY_MISMATCH",
        )
    return None


def _validate_batch(
    frappe,
    item_code: str,
    batch_no: str,
    expiry_date,
    *,
    flow: str,
    allow_new: bool,
) -> dict | None:
    batch = _batch(frappe, batch_no)
    if batch is None:
        if not allow_new:
            return failure(
                f"Batch '{batch_no}' does not exist.",
                code="VALIDATION_UNKNOWN_BATCH",
            )
        _create_batch(frappe, item_code, batch_no, expiry_date)
        return None

    if batch.get("item") != item_code:
        return failure(
            f"Batch '{batch_no}' does not belong to {item_code}.",
            code="VALIDATION_BATCH_ITEM_MISMATCH",
        )
    if _truthy(batch.get("disabled")):
        return failure(
            f"Batch '{batch_no}' is disabled.",
            code="VALIDATION_BATCH_DISABLED",
        )
    if flow == "outbound" and _is_expired(frappe, batch.get("expiry_date")):
        return failure(
            f"Batch '{batch_no}' is expired.",
            code="VALIDATION_EXPIRED_BATCH",
        )
    return None


def _batch(frappe, batch_no: str) -> dict | None:
    rows = frappe.get_list(
        "Batch",
        filters=[["name", "=", batch_no]],
        fields=["name", "batch_id", "item", "expiry_date", "disabled"],
        limit=1,
    )
    return rows[0] if rows else None


def _create_batch(frappe, item_code: str, batch_no: str, expiry_date) -> None:
    doc = frappe.get_doc({
        "doctype": "Batch",
        "batch_id": batch_no,
        "item": item_code,
        **({"expiry_date": expiry_date} if expiry_date else {}),
    })
    doc.insert(ignore_permissions=False)


def _validate_serials(
    frappe,
    item_code: str,
    serial_nos: list[str],
    warehouse: str,
    batch_no: str | None,
    *,
    flow: str,
    allow_new: bool,
) -> dict | None:
    seen: set[str] = set()
    for serial_no in serial_nos:
        if serial_no in seen:
            return failure(
                f"Duplicate serial '{serial_no}'.",
                code="VALIDATION_DUPLICATE_SERIAL",
            )
        seen.add(serial_no)
        serial = _serial(frappe, serial_no)
        if serial is None:
            if not allow_new:
                return failure(
                    f"Serial '{serial_no}' is not available.",
                    code="VALIDATION_UNAVAILABLE_SERIAL",
                )
            _create_serial(frappe, item_code, serial_no, batch_no)
            continue
        if serial.get("item_code") != item_code:
            return failure(
                f"Serial '{serial_no}' does not belong to {item_code}.",
                code="VALIDATION_SERIAL_ITEM_MISMATCH",
            )
        if batch_no and serial.get("batch_no") and serial.get("batch_no") != batch_no:
            return failure(
                f"Serial '{serial_no}' is not in batch '{batch_no}'.",
                code="VALIDATION_SERIAL_BATCH_MISMATCH",
            )
        if flow == "outbound":
            if serial.get("warehouse") != warehouse:
                return failure(
                    f"Serial '{serial_no}' is not available in {warehouse}.",
                    code="VALIDATION_UNAVAILABLE_SERIAL",
                )
            status = (serial.get("status") or "").strip()
            if status and status not in {"Active", "Available"}:
                return failure(
                    f"Serial '{serial_no}' is {status}.",
                    code="VALIDATION_UNAVAILABLE_SERIAL",
                )
    return None


def _serial(frappe, serial_no: str) -> dict | None:
    rows = frappe.get_list(
        "Serial No",
        filters=[["name", "=", serial_no]],
        fields=["name", "item_code", "warehouse", "status", "batch_no"],
        limit=1,
    )
    return rows[0] if rows else None


def _create_serial(frappe, item_code: str, serial_no: str, batch_no: str | None) -> None:
    doc = frappe.get_doc({
        "doctype": "Serial No",
        "serial_no": serial_no,
        "item_code": item_code,
        **({"batch_no": batch_no} if batch_no else {}),
    })
    doc.insert(ignore_permissions=False)


def _serial_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        return [str(raw).strip() for raw in value if str(raw).strip()]
    return []


def _serial_qty_matches(qty: float, serial_nos: list[str]) -> bool:
    rounded = round(qty)
    return isclose(qty, rounded, abs_tol=_QTY_EPSILON) and rounded == len(serial_nos)


def _qty(value) -> float:
    qty = float(value)
    if qty < 0:
        raise ValueError("qty cannot be negative")
    return qty


def _is_expired(frappe, expiry_date) -> bool:
    if not expiry_date:
        return False
    today = _today(frappe)
    return str(expiry_date) < today


def _today(frappe) -> str:
    try:
        return frappe.utils.nowdate()
    except Exception:
        from datetime import date
        return date.today().isoformat()


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}
