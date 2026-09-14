"""Cycle counting schedule generation.

Uses standard Frappe `ToDo` rows only. Each task references an `Item`; the
warehouse/class metadata is stored in the ToDo description so no custom DocType
is needed.
"""

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success
from ..common.permissions import permission_denied, require_stock_execution_role

_TODO_OPEN_STATUSES = ["Open"]
_TODO_CLOSED_STATUSES = ["Closed", "Cancelled"]
_CLASS_DEFAULTS = {"A": 7, "B": 30, "C": 90}
_MAX_DAYS = 365
_MAX_ITEMS = 500
_MARKER = "Cycle count"


def _whitelist():
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=False, methods=["POST"])


@_whitelist()
def generate_schedule(
    warehouse: str,
    days: int = 90,
    item_limit: int = 200,
    a_frequency_days: int = 7,
    b_frequency_days: int = 30,
    c_frequency_days: int = 90,
    assigned_to: str | None = None,
) -> dict:
    warehouse = (warehouse or "").strip()
    if not warehouse:
        return failure("warehouse is required.", code="VALIDATION_REQUIRED")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_stock_execution_role(frappe)
    if permission_error:
        return permission_error

    try:
        days = max(1, min(int(days), _MAX_DAYS))
        item_limit = max(1, min(int(item_limit), _MAX_ITEMS))
        frequencies = {
            "A": max(1, int(a_frequency_days or _CLASS_DEFAULTS["A"])),
            "B": max(1, int(b_frequency_days or _CLASS_DEFAULTS["B"])),
            "C": max(1, int(c_frequency_days or _CLASS_DEFAULTS["C"])),
        }
    except (TypeError, ValueError):
        return failure("days, item_limit, and frequencies must be integers.", code="VALIDATION_BAD_NUMBER")

    today = frappe.utils.nowdate()
    from_date = frappe.utils.add_days(today, -days)
    velocities = _ledger_velocity(warehouse, from_date, item_limit)
    classified = _classify_abc(velocities)
    existing = _existing_cycle_todos(warehouse, [row["item_code"] for row in classified])

    created = []
    skipped = []
    for row in classified:
        item_code = row["item_code"]
        if item_code in existing:
            skipped.append({"item_code": item_code, "todo_name": existing[item_code]})
            continue
        result = _create_todo(
            item_code=item_code,
            warehouse=warehouse,
            abc_class=row["abc_class"],
            velocity=row["velocity"],
            frequency_days=frequencies[row["abc_class"]],
            assigned_to=(assigned_to or "").strip() or None,
        )
        if isinstance(result, dict) and result.get("ok") is False:
            return result
        created.append({**row, "todo_name": result})

    return success({
        "warehouse": warehouse,
        "from_date": from_date,
        "to_date": today,
        "created": created,
        "skipped": skipped,
        "total": len(classified),
    })


def _ledger_velocity(warehouse: str, from_date: str, item_limit: int) -> list[dict]:
    rows = frappe.get_list(
        "Stock Ledger Entry",
        filters=[
            ["warehouse", "=", warehouse],
            ["posting_date", ">=", from_date],
            ["is_cancelled", "=", 0],
        ],
        fields=["item_code", "actual_qty"],
        limit_page_length=5000,
    )
    velocity: dict[str, float] = {}
    for row in rows:
        item_code = row.get("item_code")
        if not item_code:
            continue
        velocity[item_code] = velocity.get(item_code, 0.0) + abs(float(row.get("actual_qty") or 0))
    result = [
        {"item_code": item_code, "velocity": qty}
        for item_code, qty in velocity.items()
        if qty > 0
    ]
    result.sort(key=lambda row: (-row["velocity"], row["item_code"]))
    return result[:item_limit]


def _classify_abc(rows: list[dict]) -> list[dict]:
    total = sum(row["velocity"] for row in rows)
    if total <= 0:
        return []
    cumulative = 0.0
    classified = []
    for row in rows:
        cumulative += row["velocity"]
        share = cumulative / total
        abc_class = "A" if share <= 0.80 else ("B" if share <= 0.95 else "C")
        classified.append({**row, "abc_class": abc_class})
    return classified


def _existing_cycle_todos(warehouse: str, item_codes: list[str]) -> dict[str, str]:
    if not item_codes:
        return {}
    rows = frappe.get_list(
        "ToDo",
        filters=[
            ["status", "not in", _TODO_CLOSED_STATUSES],
            ["reference_type", "=", "Item"],
            ["reference_name", "in", item_codes],
        ],
        fields=["name", "reference_name", "description"],
        limit_page_length=1000,
    )
    existing = {}
    marker = f"{_MARKER} warehouse: {warehouse}"
    for row in rows:
        if marker in (row.get("description") or ""):
            existing[row["reference_name"]] = row["name"]
    return existing


def _create_todo(
    *,
    item_code: str,
    warehouse: str,
    abc_class: str,
    velocity: float,
    frequency_days: int,
    assigned_to: str | None,
) -> str | dict:
    description = (
        f"{_MARKER} warehouse: {warehouse}\n"
        f"ABC class: {abc_class}\n"
        f"Velocity: {velocity}\n"
        f"Frequency days: {frequency_days}"
    )
    doc = frappe.get_doc({
        "doctype": "ToDo",
        "description": description,
        "reference_type": "Item",
        "reference_name": item_code,
        "allocated_to": assigned_to,
        "status": "Open",
        "priority": "High" if abc_class == "A" else ("Medium" if abc_class == "B" else "Low"),
        "date": frappe.utils.nowdate(),
    })
    try:
        doc.insert(ignore_permissions=False)
    except frappe.PermissionError:
        frappe.db.rollback()
        return permission_denied()
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(_erpnext_message(exc), code="VALIDATION_ERPNEXT")
    return doc.name


def _erpnext_message(exc: Exception) -> str:
    msg = (str(exc) or "").strip() or "ERPNext rejected the document."
    try:
        from frappe.utils import strip_html_tags

        msg = strip_html_tags(msg).strip() or msg
    except Exception:
        pass
    return msg
