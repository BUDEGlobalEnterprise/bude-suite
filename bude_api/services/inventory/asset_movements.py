"""Grouped inventory.assets endpoints: asset_movements."""

from ._assets_shared import *  # noqa: F401,F403

def get_asset_movements(asset: str, limit: int = 20) -> dict:
    """Movement history for an asset (standard Asset Movement child rows)."""
    asset = (asset or "").strip()
    if not asset:
        return failure("asset is required.", code="VALIDATION_REQUIRED")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    limit = max(1, min(int(limit), 100))
    # Asset Movement Item child rows carry the per-asset source/target.
    rows = frappe.get_all(
        "Asset Movement Item",
        filters=[["asset", "=", asset]],
        fields=[
            "parent",
            "source_location",
            "target_location",
            "from_employee",
            "to_employee",
        ],
        order_by="creation desc",
        limit_page_length=limit,
    )
    # Decorate with the parent movement's date + purpose.
    parents = {r["parent"] for r in rows}
    meta = {}
    if parents:
        for m in frappe.get_all(
            "Asset Movement",
            filters=[["name", "in", list(parents)]],
            fields=["name", "transaction_date", "purpose"],
            limit_page_length=len(parents),
        ):
            meta[m["name"]] = m
    for r in rows:
        parent = meta.get(r["parent"], {})
        r["transaction_date"] = str(parent.get("transaction_date") or "")
        r["purpose"] = parent.get("purpose")
    return success(rows)

def create_asset_movement(
    assets: list,
    purpose: str,
    target_location: str | None = None,
    to_employee: str | None = None,
    transaction_date: str | None = None,
) -> dict:
    """Create + submit a standard Asset Movement.

    `purpose` is Issue (check-out to employee), Receipt (check-in), or
    Transfer (relocate). `assets` is a list of asset names. Each row's current
    location/custodian becomes the source; target_location/to_employee the
    destination.
    """
    purpose = (purpose or "").strip()
    if purpose not in _MOVE_PURPOSES:
        return failure(
            f"purpose must be one of {sorted(_MOVE_PURPOSES)}.",
            code="VALIDATION_BAD_PURPOSE",
        )
    if not assets:
        return failure("At least one asset is required.", code="VALIDATION_REQUIRED")
    if purpose in ("Transfer", "Receipt") and not target_location:
        return failure(
            "target_location is required for Transfer/Receipt.",
            code="VALIDATION_REQUIRED",
        )
    if purpose == "Issue" and not (to_employee or target_location):
        return failure(
            "to_employee or target_location is required for Issue.",
            code="VALIDATION_REQUIRED",
        )
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    permission_error = require_stock_execution_role(frappe)
    if permission_error is not None:
        return permission_error

    asset_names = [str(a).strip() for a in assets if str(a).strip()]
    company = None
    rows = []
    for asset in asset_names:
        current_rows = frappe.get_list(
            "Asset",
            filters=[["name", "=", asset]],
            fields=["location", "custodian", "company"],
            limit=1,
        )
        current = current_rows[0] if current_rows else None
        if not current:
            return failure(f"Asset '{asset}' not found.", code="VALIDATION_NOT_FOUND")
        company = company or current.get("company")
        rows.append(
            {
                "asset": asset,
                "source_location": current.get("location"),
                "from_employee": current.get("custodian"),
                "target_location": target_location,
                "to_employee": to_employee,
            }
        )

    def _do():
        doc = frappe.get_doc(
            {
                "doctype": "Asset Movement",
                "company": company,
                "purpose": purpose,
                "transaction_date": transaction_date or frappe.utils.now_datetime(),
                "assets": rows,
            }
        )
        doc.insert(ignore_permissions=False)
        doc.submit()
        return success({"name": doc.name, "docstatus": doc.docstatus})

    return _mutate(_do)
