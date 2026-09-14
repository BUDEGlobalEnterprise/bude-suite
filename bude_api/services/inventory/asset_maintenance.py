"""Grouped inventory.assets endpoints: asset_maintenance."""

from ._assets_shared import *  # noqa: F401,F403

def create_asset_repair(
    asset: str,
    failure_date: str | None = None,
    description: str | None = None,
    repair_cost: float | None = None,
) -> dict:
    """Create a standard Asset Repair record (status Pending)."""
    asset = (asset or "").strip()
    if not asset:
        return failure("asset is required.", code="VALIDATION_REQUIRED")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    permission_error = require_stock_execution_role(frappe)
    if permission_error is not None:
        return permission_error
    existing = frappe.get_list(
        "Asset",
        filters=[["name", "=", asset]],
        fields=["name"],
        limit=1,
    )
    if not existing:
        return failure(f"Asset '{asset}' not found.", code="VALIDATION_NOT_FOUND")

    data = {
        "doctype": "Asset Repair",
        "asset": asset,
        "failure_date": failure_date or frappe.utils.now_datetime(),
        "repair_status": "Pending",
    }
    if description:
        data["description"] = description
    if repair_cost is not None:
        data["repair_cost"] = repair_cost

    def _do():
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=False)
        return success({"name": doc.name, "docstatus": doc.docstatus})

    return _mutate(_do)

def list_maintenance_logs(
    asset: str | None = None,
    status: str = "Planned",
    limit: int = 50,
) -> dict:
    """Scheduled maintenance tasks (standard Asset Maintenance Log)."""
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    limit = max(1, min(int(limit), 200))
    filters: list = []
    if status:
        filters.append(["maintenance_status", "=", status])
    if asset:
        filters.append(["asset_name", "=", asset])
    rows = frappe.get_all(
        "Asset Maintenance Log",
        filters=filters,
        fields=[
            "name",
            "asset_name",
            "item_code",
            "task",
            "maintenance_status",
            "due_date",
            "completion_date",
        ],
        order_by="due_date asc",
        limit_page_length=limit,
    )
    for r in rows:
        r["due_date"] = str(r.get("due_date") or "")
        r["completion_date"] = str(r.get("completion_date") or "")
    return success(rows)

def complete_maintenance_log(log: str, completion_date: str | None = None) -> dict:
    """Mark a scheduled Asset Maintenance Log as completed."""
    log = (log or "").strip()
    if not log:
        return failure("log is required.", code="VALIDATION_REQUIRED")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    permission_error = require_stock_execution_role(frappe)
    if permission_error is not None:
        return permission_error
    existing = frappe.get_list(
        "Asset Maintenance Log",
        filters=[["name", "=", log]],
        fields=["name"],
        limit=1,
    )
    if not existing:
        return failure(f"Maintenance log '{log}' not found.", code="VALIDATION_NOT_FOUND")

    doc = frappe.get_doc("Asset Maintenance Log", log)
    doc.maintenance_status = "Completed"
    doc.completion_date = completion_date or frappe.utils.nowdate()

    def _do():
        doc.save(ignore_permissions=False)
        return success({"name": doc.name, "maintenance_status": "Completed"})

    return _mutate(_do)
