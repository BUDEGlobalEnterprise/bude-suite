"""Grouped inventory.assets endpoints: asset_records."""

from ._assets_shared import *  # noqa: F401,F403

def list_assets(
    search: str | None = None,
    location: str | None = None,
    custodian: str | None = None,
    status: str | None = None,
    category: str | None = None,
    limit: int = 50,
) -> dict:
    """List assets with optional filters. Standard Asset DocType only."""
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    limit = max(1, min(int(limit), 200))
    filters: list = []
    if location:
        filters.append(["location", "=", location])
    if custodian:
        filters.append(["custodian", "=", custodian])
    if status:
        filters.append(["status", "=", status])
    if category:
        filters.append(["asset_category", "=", category])

    or_filters = None
    search = (search or "").strip()
    if search:
        or_filters = [
            ["asset_name", "like", f"%{search}%"],
            ["name", "like", f"%{search}%"],
            ["item_code", "like", f"%{search}%"],
        ]

    rows = frappe.get_all(
        "Asset",
        filters=filters,
        or_filters=or_filters,
        fields=_ASSET_LIST_FIELDS,
        order_by="modified desc",
        limit_page_length=limit,
    )
    for row in rows:
        row["gross_purchase_amount"] = row.pop("purchase_amount", None)
    return success(rows)

def get_asset(name: str) -> dict:
    """Full asset detail incl. depreciation schedule + custodian name."""
    name = (name or "").strip()
    if not name:
        return failure("name is required.", code="VALIDATION_REQUIRED")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    asset_rows = frappe.get_all(
        "Asset",
        filters=[["name", "=", name]],
        fields=["name"],
        limit=1,
    )
    if not asset_rows:
        return failure(f"Asset '{name}' not found.", code="VALIDATION_NOT_FOUND")

    doc = frappe.get_doc("Asset", name)
    custodian_name = None
    if doc.get("custodian"):
        employee_rows = frappe.get_all(
            "Employee",
            filters=[["name", "=", doc.custodian]],
            fields=["employee_name"],
            limit=1,
        )
        custodian_name = employee_rows[0]["employee_name"] if employee_rows else None

    # Depreciation schedule lives in the `schedules` child table when the asset
    # has calculate_depreciation enabled. Read it defensively across versions.
    schedule = []
    for row in doc.get("schedules") or []:
        schedule.append(
            {
                "schedule_date": str(row.get("schedule_date") or ""),
                "depreciation_amount": row.get("depreciation_amount"),
                "accumulated_depreciation_amount": row.get("accumulated_depreciation_amount"),
                "journal_entry": row.get("journal_entry"),
            }
        )

    data = {
        "name": doc.name,
        "asset_name": doc.get("asset_name"),
        "item_code": doc.get("item_code"),
        "asset_category": doc.get("asset_category"),
        "company": doc.get("company"),
        "status": doc.get("status"),
        "location": doc.get("location"),
        "custodian": doc.get("custodian"),
        "custodian_name": custodian_name,
        "purchase_date": str(doc.get("purchase_date") or ""),
        "available_for_use_date": str(doc.get("available_for_use_date") or ""),
        "gross_purchase_amount": doc.get("gross_purchase_amount"),
        "value_after_depreciation": doc.get("value_after_depreciation"),
        "maintenance_required": doc.get("maintenance_required"),
        "bude_epc": doc.get("bude_epc"),
        "depreciation_schedule": schedule,
    }
    return success(data)

def list_locations(limit: int = 200) -> dict:
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    limit = max(1, min(int(limit), 500))
    rows = frappe.get_all(
        "Location",
        fields=[
            "name",
            "location_name",
            "parent_location",
            "latitude",
            "longitude",
            "is_group",
        ],
        order_by="name asc",
        limit_page_length=limit,
    )
    return success(rows)

def list_asset_categories(limit: int = 200) -> dict:
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    limit = max(1, min(int(limit), 500))
    rows = frappe.get_all(
        "Asset Category",
        fields=["name"],
        order_by="name asc",
        limit_page_length=limit,
    )
    return success([r["name"] for r in rows])

def set_epc(doctype: str, name: str, epc: str) -> dict:
    """Write `bude_epc` on a standard record so future scans resolve to it."""
    doctype = (doctype or "").strip()
    name = (name or "").strip()
    epc = (epc or "").strip()

    if doctype not in _EPC_DOCTYPES:
        return failure(
            f"doctype must be one of {sorted(_EPC_DOCTYPES)}.",
            code="VALIDATION_BAD_DOCTYPE",
        )
    if not name:
        return failure("name is required.", code="VALIDATION_REQUIRED")
    if not epc:
        return failure("epc is required.", code="VALIDATION_REQUIRED")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    permission_error = require_stock_execution_role(frappe)
    if permission_error is not None:
        return permission_error

    existing = frappe.get_list(
        doctype,
        filters=[["name", "=", name]],
        fields=["name"],
        limit=1,
    )
    if not existing:
        return failure(f"{doctype} '{name}' not found.", code="VALIDATION_NOT_FOUND")

    taken = frappe.get_list(
        doctype,
        filters=[["bude_epc", "=", epc], ["name", "!=", name]],
        fields=["name"],
        limit=1,
    )
    if taken:
        return failure(
            f"EPC already bound to {doctype} '{taken[0]['name']}'.",
            code="VALIDATION_EPC_TAKEN",
        )

    def _do():
        doc = frappe.get_doc(doctype, name)
        doc.set("bude_epc", epc)
        doc.save(ignore_permissions=False)
        return success({"doctype": doctype, "name": name, "bude_epc": epc})

    return _mutate(_do)
