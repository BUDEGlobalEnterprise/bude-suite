"""Guided warehouse task aggregation.

Builds a mobile task queue from standard ERPNext/Frappe documents only:
Purchase Orders, Sales Orders, Asset Maintenance Logs, and Frappe ToDo rows.
No custom DocTypes are introduced.
"""

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success

from ..common.permissions import permission_denied

_CLOSED_STATUSES = {"Closed", "Completed", "Cancelled"}

_TODO_CLOSED_STATUSES = {"Closed", "Cancelled"}

_SUPPORTED_DOCTYPES = {
    "Purchase Order": "receivePurchaseOrder",
    "Sales Order": "fulfillSalesOrder",
    "Asset Maintenance Log": "assetMaintenance",
    "Item": "cycleCount",
}

_PRIORITY_RANK = {"Urgent": 0, "High": 0, "Medium": 1, "Low": 2}

def _whitelist(methods=None, allow_guest: bool = False):
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=methods or ["GET", "POST"])

def _purchase_order_tasks(todos: dict[tuple[str, str], dict], *, company: str | None) -> list[dict]:
    filters = [
        ["docstatus", "=", 1],
        ["status", "not in", list(_CLOSED_STATUSES)],
    ]
    if company:
        filters.append(["company", "=", company])
    rows = frappe.get_list(
        "Purchase Order",
        filters=filters,
        fields=["name", "supplier", "transaction_date", "schedule_date", "status", "company"],
        order_by="transaction_date desc",
        limit_page_length=500,
    )
    item_counts = _child_counts("Purchase Order Item", [row["name"] for row in rows])
    tasks = []
    for row in rows:
        todo = todos.get(("Purchase Order", row["name"]))
        tasks.append(
            _task(
                kind="receivePurchaseOrder",
                title=f"Receive {row['name']}",
                subtitle=row.get("supplier") or row.get("status") or "Purchase Order",
                priority=_priority(todo, fallback="Medium"),
                due_date=_first(row.get("schedule_date"), row.get("transaction_date")),
                assigned_to=(todo or {}).get("allocated_to"),
                company=row.get("company"),
                source_doctype="Purchase Order",
                source_name=row["name"],
                todo_name=(todo or {}).get("name"),
                item_count=item_counts.get(row["name"], 0),
            )
        )
    return tasks

def _sales_order_tasks(todos: dict[tuple[str, str], dict], *, company: str | None) -> list[dict]:
    filters = [
        ["docstatus", "=", 1],
        ["status", "not in", list(_CLOSED_STATUSES)],
    ]
    if company:
        filters.append(["company", "=", company])
    rows = frappe.get_list(
        "Sales Order",
        filters=filters,
        fields=["name", "customer", "transaction_date", "delivery_date", "status", "company"],
        order_by="delivery_date asc",
        limit_page_length=500,
    )
    pending = _sales_order_pending([row["name"] for row in rows])
    tasks = []
    for row in rows:
        summary = pending.get(row["name"], {"item_count": 0, "pending_qty": 0.0})
        if summary["item_count"] <= 0:
            continue
        todo = todos.get(("Sales Order", row["name"]))
        tasks.append(
            _task(
                kind="fulfillSalesOrder",
                title=f"Fulfill {row['name']}",
                subtitle=row.get("customer") or row.get("status") or "Sales Order",
                priority=_priority(todo, fallback="Medium"),
                due_date=_first(row.get("delivery_date"), row.get("transaction_date")),
                assigned_to=(todo or {}).get("allocated_to"),
                company=row.get("company"),
                source_doctype="Sales Order",
                source_name=row["name"],
                todo_name=(todo or {}).get("name"),
                item_count=summary["item_count"],
                pending_qty=summary["pending_qty"],
            )
        )
    return tasks

def _asset_maintenance_tasks(
    todos: dict[tuple[str, str], dict], *, company: str | None
) -> list[dict]:
    filters = [["maintenance_status", "=", "Planned"]]
    if company:
        asset_rows = frappe.get_list(
            "Asset",
            filters=[["company", "=", company]],
            fields=["name"],
            limit_page_length=1000,
        )
        asset_names = [row["name"] for row in asset_rows]
        if not asset_names:
            return []
        filters.append(["asset_name", "in", asset_names])
    rows = frappe.get_list(
        "Asset Maintenance Log",
        filters=filters,
        fields=["name", "asset_name", "item_code", "task", "due_date", "maintenance_status"],
        order_by="due_date asc",
        limit_page_length=500,
    )
    tasks = []
    for row in rows:
        todo = todos.get(("Asset Maintenance Log", row["name"]))
        tasks.append(
            _task(
                kind="assetMaintenance",
                title=row.get("task") or f"Maintenance {row['name']}",
                subtitle=row.get("asset_name") or row.get("item_code") or "Asset maintenance",
                priority=_priority(todo, fallback="Low"),
                due_date=row.get("due_date"),
                assigned_to=(todo or {}).get("allocated_to"),
                company=company,
                source_doctype="Asset Maintenance Log",
                source_name=row["name"],
                todo_name=(todo or {}).get("name"),
                item_count=1,
                asset_name=row.get("asset_name"),
            )
        )
    return tasks

def _cycle_count_tasks(todos: dict[tuple[str, str], dict]) -> list[dict]:
    tasks = []
    for (reference_type, item_code), todo in todos.items():
        if reference_type != "Item":
            continue
        description = todo.get("description") or ""
        if "Cycle count warehouse:" not in description:
            continue
        warehouse = _cycle_count_value(description, "Cycle count warehouse")
        abc_class = _cycle_count_value(description, "ABC class") or "C"
        tasks.append(
            _task(
                kind="cycleCount",
                title=f"Count {item_code}",
                subtitle=warehouse or "Cycle count",
                priority=_priority(todo, fallback="Medium"),
                due_date=todo.get("date"),
                assigned_to=todo.get("allocated_to"),
                company=None,
                source_doctype="Item",
                source_name=item_code,
                todo_name=todo.get("name"),
                item_count=1,
                abc_class=abc_class,
                warehouse=warehouse,
            )
        )
    return tasks

def _todos_by_reference() -> dict[tuple[str, str], dict]:
    rows = frappe.get_list(
        "ToDo",
        filters=[
            ["status", "not in", list(_TODO_CLOSED_STATUSES)],
            ["reference_type", "in", list(_SUPPORTED_DOCTYPES.keys())],
        ],
        fields=[
            "name",
            "allocated_to",
            "reference_type",
            "reference_name",
            "description",
            "priority",
            "date",
        ],
        order_by="date asc",
        limit_page_length=1000,
    )
    result: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row.get("reference_type"), row.get("reference_name"))
        if key[0] not in _SUPPORTED_DOCTYPES or not key[1]:
            continue
        result.setdefault(key, row)
    return result

def _child_counts(doctype: str, parents: list[str]) -> dict[str, int]:
    if not parents:
        return {}
    rows = frappe.get_all(
        doctype,
        filters=[["parent", "in", parents]],
        fields=["parent"],
        limit_page_length=5000,
    )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["parent"]] = counts.get(row["parent"], 0) + 1
    return counts

def _sales_order_pending(names: list[str]) -> dict[str, dict]:
    if not names:
        return {}
    rows = frappe.get_all(
        "Sales Order Item",
        filters=[["parent", "in", names]],
        fields=["parent", "qty", "delivered_qty"],
        limit_page_length=5000,
    )
    result: dict[str, dict] = {}
    for row in rows:
        pending = float(row.get("qty") or 0) - float(row.get("delivered_qty") or 0)
        if pending <= 0.000001:
            continue
        bucket = result.setdefault(row["parent"], {"item_count": 0, "pending_qty": 0.0})
        bucket["item_count"] += 1
        bucket["pending_qty"] += pending
    return result

def _task(
    *,
    kind: str,
    title: str,
    subtitle: str,
    priority: str,
    due_date,
    assigned_to,
    company,
    source_doctype: str,
    source_name: str,
    todo_name=None,
    item_count=0,
    pending_qty=0.0,
    asset_name=None,
    abc_class=None,
    warehouse=None,
) -> dict:
    task_id = todo_name or f"{kind}:{source_name}"
    return {
        "id": task_id,
        "kind": kind,
        "title": title,
        "subtitle": subtitle,
        "priority": priority,
        "due_date": str(due_date) if due_date else None,
        "assigned_to": assigned_to,
        "company": company,
        "source_doctype": source_doctype,
        "source_name": source_name,
        "todo_name": todo_name,
        "item_count": item_count,
        "pending_qty": pending_qty,
        "asset_name": asset_name,
        "abc_class": abc_class,
        "warehouse": warehouse,
    }

def _cycle_count_value(description: str, label: str) -> str | None:
    prefix = f"{label}:"
    for line in description.splitlines():
        if line.startswith(prefix):
            value = line[len(prefix) :].strip()
            return value or None
    return None

def _priority(todo: dict | None, *, fallback: str) -> str:
    raw = (todo or {}).get("priority")
    if raw in _PRIORITY_RANK:
        return raw
    return fallback

def _task_sort_key(task: dict) -> tuple:
    due = task.get("due_date") or "9999-12-31"
    return (
        _PRIORITY_RANK.get(task.get("priority"), 1),
        due,
        task.get("title") or "",
    )

def _first(*values):
    for value in values:
        if value:
            return value
    return None

def _completion_note(result_doctype: str | None, result_name: str | None) -> str | None:
    result_doctype = (result_doctype or "").strip()
    result_name = (result_name or "").strip()
    if not result_doctype or not result_name:
        return None
    return f"Completed from mobile: {result_doctype} {result_name}"

def _erpnext_message(exc: Exception) -> str:
    msg = (str(exc) or "").strip() or "ERPNext rejected the document."
    try:
        from frappe.utils import strip_html_tags

        msg = strip_html_tags(msg).strip() or msg
    except Exception:
        pass
    return msg

__all__ = [name for name in globals() if not name.startswith("__")]
