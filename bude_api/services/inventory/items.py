"""Item lookup endpoints.

    POST /api/method/bude_api.api.items.search           (auth required)
    POST /api/method/bude_api.api.items.get_by_barcode   (auth required)
    POST /api/method/bude_api.api.items.get_stock        (auth required)

All three use standard ERPNext DocTypes: Item, Item Barcode, Bin.
No custom DocTypes, no writes — read-only Phase 2 lookups.
"""

from datetime import date, datetime, timedelta

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
    "item_group",
    "brand",
    "is_stock_item",
    "is_sales_item",
    "is_purchase_item",
    "valuation_method",
    "end_of_life",
    "shelf_life_in_days",
    "warranty_period",
    "weight_per_unit",
    "weight_uom",
    "purchase_uom",
    "sales_uom",
    "safety_stock",
    "lead_time_days",
    "country_of_origin",
]


def _existing_fields(doctype: str, fields: list[str]) -> list[str]:
    """Return fields available on the installed schema version."""
    try:
        meta = frappe.get_meta(doctype)
        has_field = getattr(meta, "has_field", None)
        if callable(has_field):
            return [field for field in fields if field == "name" or has_field(field)]
    except Exception:
        pass
    return fields


def _item_fields() -> list[str]:
    """Return Item fields available on this ERPNext version."""
    return _existing_fields("Item", _ITEM_FIELDS)


def _whitelist(allow_guest: bool = False):
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=["GET", "POST"])


@_whitelist()
def search(
    query: str = "",
    limit: int = 20,
    page: int = 0,
    warehouse: str | None = None,
    item_group: str | None = None,
    in_stock: str | None = None,
) -> dict:
    """Search Items by item_code/item_name (LIKE) and by Item Barcode (exact).

    Optional filters: item_group, warehouse (used with in_stock), in_stock.
    Supports pagination via page (0-based).
    Returns merged, deduped results ordered by item_code.
    """
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    query = (query or "").strip()
    limit = max(1, min(int(limit), 100))
    page = max(0, int(page))

    # Nothing to search without query or filters
    if not query and not item_group and not in_stock:
        return success([])

    # Base filters applied to all Item queries
    base_filters: list = [["disabled", "=", 0]]
    if item_group:
        base_filters.append(["item_group", "=", item_group])

    if in_stock:
        bin_filters: list = [["actual_qty", ">", 0]]
        if warehouse:
            bin_filters.append(["warehouse", "=", warehouse])
        stocked = frappe.get_list(
            "Bin",
            filters=bin_filters,
            pluck="item_code",
            limit=1000,
        )
        if not stocked:
            return success([])
        base_filters.append(["item_code", "in", list(set(stocked))])

    # Exact barcode match — only on page 0, barcode hits always come first
    barcode_matches: list[dict] = []
    if query and page == 0:
        barcode_rows = frappe.get_all(
            "Item Barcode",
            filters=[["barcode", "=", query]],
            fields=["parent"],
            limit=limit,
        )
        bc_codes = [r["parent"] for r in barcode_rows]
        if bc_codes:
            barcode_matches = frappe.get_list(
                "Item",
                filters=base_filters + [["item_code", "in", bc_codes]],
                fields=_item_fields(),
                limit=limit,
            )

    # Text search or browse (empty query with filters)
    if query:
        name_matches = frappe.get_list(
            "Item",
            filters=base_filters,
            or_filters=[
                ["item_code", "like", f"%{query}%"],
                ["item_name", "like", f"%{query}%"],
            ],
            fields=_item_fields(),
            limit=limit,
            limit_start=page * limit,
            order_by="item_code asc",
        )
    else:
        name_matches = frappe.get_list(
            "Item",
            filters=base_filters,
            fields=_item_fields(),
            limit=limit,
            limit_start=page * limit,
            order_by="item_code asc",
        )

    seen: set[str] = set()
    merged: list[dict] = []
    for row in barcode_matches + name_matches:
        code = row["item_code"]
        if code in seen:
            continue
        seen.add(code)
        merged.append(row)

    return success(merged[:limit])


@_whitelist()
def list_groups() -> dict:
    """Return all leaf Item Groups (is_group=0) for the filter chip."""
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    groups = frappe.get_list(
        "Item Group",
        filters={"is_group": 0},
        pluck="name",
        order_by="name asc",
        limit=200,
    )
    return success(groups)


@_whitelist()
def get_by_barcode(barcode: str) -> dict:
    barcode = (barcode or "").strip()
    if not barcode:
        return failure("Barcode is required.", code="VALIDATION_REQUIRED")

    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    rows = frappe.get_all(
        "Item Barcode",
        filters=[["barcode", "=", barcode]],
        fields=["parent"],
        limit=1,
    )
    if not rows:
        return failure("No item matches that barcode.", code="ITEM_NOT_FOUND")

    item_code = rows[0]["parent"]
    items = frappe.get_list(
        "Item",
        filters=[["item_code", "=", item_code]],
        fields=_item_fields(),
        limit=1,
    )
    if not items:
        return failure("Barcode points to a missing item.", code="ITEM_NOT_FOUND")

    return success(items[0])


@_whitelist()
def get_ledger(item_code: str, warehouse: str | None = None, limit: int = 50) -> dict:
    """Return Stock Ledger Entry rows for an item, newest first.

    GET /api/method/bude_api.api.items.get_ledger
    """
    item_code = (item_code or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    limit = max(1, min(int(limit), 200))
    filters: list = [["item_code", "=", item_code], ["is_cancelled", "=", 0]]
    if warehouse:
        filters.append(["warehouse", "=", warehouse])

    rows = frappe.get_list(
        "Stock Ledger Entry",
        filters=filters,
        fields=[
            "posting_date",
            "posting_time",
            "voucher_type",
            "voucher_no",
            "warehouse",
            "actual_qty",
            "qty_after_transaction",
            "valuation_rate",
            "stock_value_difference",
        ],
        order_by="posting_date desc, posting_time desc",
        limit_page_length=limit,
    )
    return success(rows)


@_whitelist()
def get_stock(item_code: str, warehouse: str | None = None) -> dict:
    item_code = (item_code or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")

    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    filters: list = [["item_code", "=", item_code]]
    if warehouse:
        filters.append(["warehouse", "=", warehouse])

    bins = frappe.get_list(
        "Bin",
        filters=filters,
        fields=[
            "warehouse",
            "actual_qty",
            "reserved_qty",
            "ordered_qty",
            "projected_qty",
            "stock_uom",
        ],
        order_by="warehouse asc",
    )
    return success(bins)


@_whitelist()
def get_storage_locations(item_code: str, limit: int = 20) -> dict:
    """Return item quantities with standard Warehouse location context."""
    item_code = (item_code or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if not frappe.db.exists("Item", item_code):
        return failure(f"Item '{item_code}' not found.", code="NOT_FOUND")

    bins = frappe.get_list(
        "Bin",
        filters=[["item_code", "=", item_code]],
        fields=_existing_fields(
            "Bin",
            [
                "warehouse",
                "actual_qty",
                "reserved_qty",
                "ordered_qty",
                "projected_qty",
            ],
        ),
        order_by="actual_qty desc",
        limit_page_length=limit,
    )
    warehouse_names = [row.get("warehouse") for row in bins if row.get("warehouse")]
    if not warehouse_names:
        return success([])

    try:
        warehouses = frappe.get_list(
            "Warehouse",
            filters=[["name", "in", warehouse_names], ["disabled", "=", 0]],
            fields=_existing_fields(
                "Warehouse",
                [
                    "name",
                    "warehouse_name",
                    "parent_warehouse",
                    "warehouse_type",
                    "address_line_1",
                    "address_line_2",
                    "city",
                    "state",
                    "pin",
                    "phone_no",
                    "mobile_no",
                    "email_id",
                ],
            ),
            limit_page_length=len(warehouse_names),
        )
    except Exception:
        warehouses = []
    details = {row.get("name"): row for row in warehouses}

    result = []
    for row in bins:
        warehouse = details.get(row.get("warehouse"), {})
        result.append(
            {
                "warehouse": row.get("warehouse") or "",
                "warehouse_name": warehouse.get("warehouse_name")
                or row.get("warehouse")
                or "",
                "parent_warehouse": warehouse.get("parent_warehouse") or "",
                "warehouse_type": warehouse.get("warehouse_type") or "",
                "address": ", ".join(
                    str(value)
                    for value in (
                        warehouse.get("address_line_1"),
                        warehouse.get("address_line_2"),
                        warehouse.get("city"),
                        warehouse.get("state"),
                        warehouse.get("pin"),
                    )
                    if value
                ),
                "phone": warehouse.get("phone_no")
                or warehouse.get("mobile_no")
                or "",
                "email": warehouse.get("email_id") or "",
                "actual_qty": float(row.get("actual_qty") or 0),
                "reserved_qty": float(row.get("reserved_qty") or 0),
                "ordered_qty": float(row.get("ordered_qty") or 0),
                "projected_qty": float(row.get("projected_qty") or 0),
            }
        )
    return success(result)


@_whitelist()
def get_movement_insight(
    item_code: str,
    warehouse: str | None = None,
    days: int = 90,
) -> dict:
    """Summarize recent standard Stock Ledger movement and stock cover."""
    item_code = (item_code or "").strip()
    warehouse = (warehouse or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")
    try:
        days = int(days)
    except (TypeError, ValueError):
        return failure("days must be an integer.", code="VALIDATION_BAD_DAYS")
    if days < 7 or days > 365:
        return failure(
            "days must be between 7 and 365.",
            code="VALIDATION_BAD_DAYS",
        )
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    if not frappe.db.exists("Item", item_code):
        return failure(f"Item '{item_code}' not found.", code="NOT_FOUND")

    from_date = date.today() - timedelta(days=days - 1)
    filters: list = [
        ["item_code", "=", item_code],
        ["posting_date", ">=", from_date.isoformat()],
        ["is_cancelled", "=", 0],
    ]
    if warehouse:
        filters.append(["warehouse", "=", warehouse])
    ledger_rows = frappe.get_list(
        "Stock Ledger Entry",
        filters=filters,
        fields=_existing_fields(
            "Stock Ledger Entry",
            [
                "posting_date",
                "warehouse",
                "actual_qty",
                "voucher_type",
                "voucher_no",
            ],
        ),
        order_by="posting_date desc, posting_time desc",
        limit_page_length=1001,
    )
    truncated = len(ledger_rows) > 1000
    ledger_rows = ledger_rows[:1000]

    bin_filters: list = [["item_code", "=", item_code]]
    if warehouse:
        bin_filters.append(["warehouse", "=", warehouse])
    bins = frappe.get_list(
        "Bin",
        filters=bin_filters,
        fields=_existing_fields("Bin", ["actual_qty", "projected_qty"]),
        limit_page_length=500,
    )
    actual_qty = sum(float(row.get("actual_qty") or 0) for row in bins)
    projected_qty = sum(float(row.get("projected_qty") or 0) for row in bins)
    inbound_qty = sum(
        float(row.get("actual_qty") or 0)
        for row in ledger_rows
        if float(row.get("actual_qty") or 0) > 0
    )
    outbound_qty = sum(
        abs(float(row.get("actual_qty") or 0))
        for row in ledger_rows
        if float(row.get("actual_qty") or 0) < 0
    )
    daily_outbound = outbound_qty / days
    days_of_cover = None if daily_outbound <= 0 else actual_qty / daily_outbound
    latest = ledger_rows[0] if ledger_rows else {}

    return success(
        {
            "days": days,
            "warehouse": warehouse,
            "actual_qty": actual_qty,
            "projected_qty": projected_qty,
            "inbound_qty": inbound_qty,
            "outbound_qty": outbound_qty,
            "daily_outbound": round(daily_outbound, 4),
            "days_of_cover": None
            if days_of_cover is None
            else round(days_of_cover, 2),
            "movement_count": len(ledger_rows),
            "last_movement_date": str(latest.get("posting_date") or ""),
            "last_voucher_type": latest.get("voucher_type") or "",
            "last_voucher_no": latest.get("voucher_no") or "",
            "truncated": truncated,
        }
    )


@_whitelist()
def get_supply_demand(
    item_code: str,
    warehouse: str | None = None,
    limit: int = 10,
) -> dict:
    """Return open standard purchase supply and sales demand for an item."""
    item_code = (item_code or "").strip()
    warehouse = (warehouse or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    if not frappe.db.exists("Item", item_code):
        return failure(f"Item '{item_code}' not found.", code="NOT_FOUND")

    def open_rows(
        doctype: str,
        fulfilled_field: str,
        date_fields: list[str],
    ) -> tuple[list[dict], bool]:
        try:
            fields = _existing_fields(
                doctype,
                [
                    "parent",
                    "qty",
                    fulfilled_field,
                    "warehouse",
                    "uom",
                    *date_fields,
                ],
            )
            if not {"parent", "qty", fulfilled_field}.issubset(fields):
                return [], False
            filters: list = [
                ["item_code", "=", item_code],
                ["docstatus", "=", 1],
            ]
            if warehouse and "warehouse" in fields:
                filters.append(["warehouse", "=", warehouse])
            rows = frappe.get_list(
                doctype,
                filters=filters,
                fields=fields,
                order_by=f"{date_fields[0]} asc"
                if date_fields[0] in fields
                else "modified desc",
                limit_page_length=501,
            )
        except Exception:
            return [], False
        truncated = len(rows) > 500
        result = []
        for row in rows[:500]:
            qty = float(row.get("qty") or 0)
            fulfilled = float(row.get(fulfilled_field) or 0)
            pending = max(qty - fulfilled, 0)
            if pending <= 0:
                continue
            due_date = next(
                (str(row.get(field)) for field in date_fields if row.get(field)),
                "",
            )
            result.append(
                {
                    "document": row.get("parent") or "",
                    "due_date": due_date,
                    "warehouse": row.get("warehouse") or "",
                    "uom": row.get("uom") or "",
                    "qty": qty,
                    "fulfilled_qty": fulfilled,
                    "pending_qty": pending,
                }
            )
        return result, truncated

    incoming, incoming_truncated = open_rows(
        "Purchase Order Item",
        "received_qty",
        ["expected_delivery_date", "schedule_date"],
    )
    outgoing, outgoing_truncated = open_rows(
        "Sales Order Item",
        "delivered_qty",
        ["delivery_date"],
    )
    incoming_qty = sum(row["pending_qty"] for row in incoming)
    outgoing_qty = sum(row["pending_qty"] for row in outgoing)
    truncated = (
        incoming_truncated
        or outgoing_truncated
        or len(incoming) > limit
        or len(outgoing) > limit
    )
    return success(
        {
            "warehouse": warehouse,
            "incoming_qty": incoming_qty,
            "outgoing_qty": outgoing_qty,
            "net_committed_qty": incoming_qty - outgoing_qty,
            "incoming": incoming[:limit],
            "outgoing": outgoing[:limit],
            "truncated": truncated,
        }
    )


@_whitelist()
def get_quality_inspections(item_code: str, limit: int = 10) -> dict:
    """Return recent standard Quality Inspection outcomes for an item."""
    item_code = (item_code or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    if not frappe.db.exists("Item", item_code):
        return failure(f"Item '{item_code}' not found.", code="NOT_FOUND")
    try:
        if not frappe.db.exists("DocType", "Quality Inspection"):
            return success(
                {"inspections": [], "accepted": 0, "rejected": 0, "cancelled": 0}
            )
        fields = _existing_fields(
            "Quality Inspection",
            [
                "name",
                "report_date",
                "status",
                "inspection_type",
                "reference_type",
                "reference_name",
                "batch_no",
                "sample_size",
                "inspected_by",
                "remarks",
            ],
        )
        rows = frappe.get_list(
            "Quality Inspection",
            filters=[["item_code", "=", item_code], ["docstatus", "!=", 2]],
            fields=fields,
            order_by="report_date desc, creation desc",
            limit_page_length=limit,
        )
    except Exception:
        rows = []
    counts = {"accepted": 0, "rejected": 0, "cancelled": 0}
    inspections = []
    for row in rows:
        status = str(row.get("status") or "")
        key = status.lower()
        if key in counts:
            counts[key] += 1
        inspections.append(
            {
                "name": row.get("name") or "",
                "report_date": str(row.get("report_date") or ""),
                "status": status,
                "inspection_type": row.get("inspection_type") or "",
                "reference_type": row.get("reference_type") or "",
                "reference_name": row.get("reference_name") or "",
                "batch_no": row.get("batch_no") or "",
                "sample_size": float(row.get("sample_size") or 0),
                "inspected_by": row.get("inspected_by") or "",
                "remarks": row.get("remarks") or "",
            }
        )
    return success({"inspections": inspections, **counts})


@_whitelist()
def get_reservations(
    item_code: str,
    warehouse: str | None = None,
    limit: int = 10,
) -> dict:
    """Return active standard Stock Reservation Entries for an item."""
    item_code = (item_code or "").strip()
    warehouse = (warehouse or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    if not frappe.db.exists("Item", item_code):
        return failure(f"Item '{item_code}' not found.", code="NOT_FOUND")
    empty = {"reservations": [], "reserved_qty": 0.0, "remaining_qty": 0.0}
    try:
        if not frappe.db.exists("DocType", "Stock Reservation Entry"):
            return success(empty)
        filters: list = [
            ["item_code", "=", item_code],
            ["docstatus", "=", 1],
            ["status", "not in", ["Delivered", "Cancelled", "Closed"]],
        ]
        if warehouse:
            filters.append(["warehouse", "=", warehouse])
        rows = frappe.get_list(
            "Stock Reservation Entry",
            filters=filters,
            fields=_existing_fields(
                "Stock Reservation Entry",
                [
                    "name",
                    "status",
                    "warehouse",
                    "stock_uom",
                    "voucher_type",
                    "voucher_no",
                    "voucher_qty",
                    "reserved_qty",
                    "delivered_qty",
                    "reservation_based_on",
                    "project",
                    "company",
                ],
            ),
            order_by="creation desc",
            limit_page_length=limit,
        )
    except Exception:
        return success(empty)
    reservations = []
    for row in rows:
        reserved = float(row.get("reserved_qty") or 0)
        delivered = float(row.get("delivered_qty") or 0)
        reservations.append(
            {
                "name": row.get("name") or "",
                "status": row.get("status") or "",
                "warehouse": row.get("warehouse") or "",
                "uom": row.get("stock_uom") or "",
                "voucher_type": row.get("voucher_type") or "",
                "voucher_no": row.get("voucher_no") or "",
                "voucher_qty": float(row.get("voucher_qty") or 0),
                "reserved_qty": reserved,
                "delivered_qty": delivered,
                "remaining_qty": max(reserved - delivered, 0),
                "reservation_based_on": row.get("reservation_based_on") or "",
                "project": row.get("project") or "",
                "company": row.get("company") or "",
            }
        )
    return success(
        {
            "reservations": reservations,
            "reserved_qty": sum(row["reserved_qty"] for row in reservations),
            "remaining_qty": sum(row["remaining_qty"] for row in reservations),
        }
    )


@_whitelist()
def get_alternatives(
    item_code: str,
    warehouse: str | None = None,
    limit: int = 20,
) -> dict:
    """Return standard alternative items with current Bin availability."""
    item_code = (item_code or "").strip()
    warehouse = (warehouse or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    if not frappe.db.exists("Item", item_code):
        return failure(f"Item '{item_code}' not found.", code="NOT_FOUND")
    if not _doctype_exists("Item Alternative"):
        return success({"alternatives": [], "warehouse": warehouse})

    fields = _existing_fields(
        "Item Alternative",
        [
            "name",
            "item_code",
            "alternative_item_code",
            "alternative_item_name",
            "two_way",
        ],
    )
    try:
        direct = frappe.get_list(
            "Item Alternative",
            filters=[["item_code", "=", item_code]],
            fields=fields,
            order_by="creation desc",
            limit_page_length=limit,
        )
        reverse = frappe.get_list(
            "Item Alternative",
            filters=[
                ["alternative_item_code", "=", item_code],
                ["two_way", "=", 1],
            ],
            fields=fields,
            order_by="creation desc",
            limit_page_length=limit,
        )
    except Exception:
        return success({"alternatives": [], "warehouse": warehouse})

    alternative_codes: list[str] = []
    rules: dict[str, dict] = {}
    for row in direct:
        code = str(row.get("alternative_item_code") or "")
        if code and code != item_code and code not in rules:
            alternative_codes.append(code)
            rules[code] = row
    for row in reverse:
        code = str(row.get("item_code") or "")
        if code and code != item_code and code not in rules:
            alternative_codes.append(code)
            rules[code] = row
    alternative_codes = alternative_codes[:limit]
    if not alternative_codes:
        return success({"alternatives": [], "warehouse": warehouse})

    try:
        item_rows = frappe.get_list(
            "Item",
            filters=[["name", "in", alternative_codes]],
            fields=_existing_fields(
                "Item",
                ["name", "item_code", "item_name", "stock_uom", "disabled"],
            ),
            limit_page_length=len(alternative_codes),
        )
    except Exception:
        item_rows = []
    item_by_code = {
        str(row.get("item_code") or row.get("name") or ""): row
        for row in item_rows
    }

    bin_filters: list = [["item_code", "in", alternative_codes]]
    if warehouse:
        bin_filters.append(["warehouse", "=", warehouse])
    try:
        bins = frappe.get_list(
            "Bin",
            filters=bin_filters,
            fields=_existing_fields(
                "Bin",
                ["item_code", "warehouse", "actual_qty", "projected_qty"],
            ),
            limit_page_length=1000,
        )
    except Exception:
        bins = []
    quantities: dict[str, dict] = {}
    for row in bins:
        code = str(row.get("item_code") or "")
        summary = quantities.setdefault(
            code,
            {"actual_qty": 0.0, "projected_qty": 0.0, "warehouses": set()},
        )
        summary["actual_qty"] += float(row.get("actual_qty") or 0)
        summary["projected_qty"] += float(row.get("projected_qty") or 0)
        if row.get("warehouse"):
            summary["warehouses"].add(row["warehouse"])

    alternatives = []
    for code in alternative_codes:
        rule = rules[code]
        item = item_by_code.get(code, {})
        qty = quantities.get(
            code,
            {"actual_qty": 0.0, "projected_qty": 0.0, "warehouses": set()},
        )
        alternatives.append(
            {
                "item_code": code,
                "item_name": item.get("item_name")
                or rule.get("alternative_item_name")
                or code,
                "uom": item.get("stock_uom") or "",
                "two_way": bool(rule.get("two_way")),
                "disabled": bool(item.get("disabled")),
                "actual_qty": qty["actual_qty"],
                "projected_qty": qty["projected_qty"],
                "warehouse_count": len(qty["warehouses"]),
            }
        )
    return success({"alternatives": alternatives, "warehouse": warehouse})


@_whitelist()
def get_batches(
    item_code: str,
    warehouse: str | None = None,
    limit: int = 20,
) -> dict:
    """Return active standard batches in FEFO order with available quantity."""
    item_code = (item_code or "").strip()
    warehouse = (warehouse or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    items = frappe.get_list(
        "Item",
        filters=[["item_code", "=", item_code]],
        fields=_existing_fields("Item", ["name", "item_code", "has_batch_no"]),
        limit_page_length=1,
    )
    if not items:
        return failure("Item not found.", code="ITEM_NOT_FOUND")
    empty = {
        "item_code": item_code,
        "warehouse": warehouse,
        "batches": [],
        "total_qty": 0.0,
        "truncated": False,
    }
    if not _truthy(items[0].get("has_batch_no")) or not _doctype_exists("Batch"):
        return success(empty)

    batch_fields = _existing_fields(
        "Batch",
        [
            "name",
            "batch_id",
            "manufacturing_date",
            "expiry_date",
            "batch_qty",
            "stock_uom",
            "supplier",
            "reference_doctype",
            "reference_name",
            "disabled",
        ],
    )
    batch_filters = [["item", "=", item_code]]
    if "disabled" in batch_fields:
        batch_filters.append(["disabled", "=", 0])
    try:
        rows = frappe.get_list(
            "Batch",
            filters=batch_filters,
            fields=batch_fields,
            order_by="expiry_date asc, manufacturing_date asc, name asc",
            limit_page_length=200,
        )
    except Exception:
        return success(empty)
    if not rows:
        return success(empty)

    quantity_by_batch: dict[str, float] = {}
    if warehouse:
        batch_names = [
            str(row.get("name") or row.get("batch_id") or "")
            for row in rows
            if row.get("name") or row.get("batch_id")
        ]
        if not batch_names:
            return success(empty)
        ledger_fields = _existing_fields(
            "Stock Ledger Entry",
            ["batch_no", "is_cancelled"],
        )
        if "batch_no" not in ledger_fields:
            return success(empty)
        ledger_filters = [
            ["item_code", "=", item_code],
            ["warehouse", "=", warehouse],
            ["batch_no", "in", batch_names],
        ]
        if "is_cancelled" in ledger_fields:
            ledger_filters.append(["is_cancelled", "=", 0])
        try:
            ledger_rows = frappe.get_list(
                "Stock Ledger Entry",
                filters=ledger_filters,
                fields=["batch_no", "sum(actual_qty) as qty"],
                group_by="batch_no",
                limit_page_length=len(batch_names),
            )
        except Exception:
            return success(empty)
        quantity_by_batch = {
            str(row.get("batch_no") or ""): float(row.get("qty") or 0)
            for row in ledger_rows
        }

    today = date.today()
    batches = []
    for row in rows:
        batch_no = str(row.get("name") or row.get("batch_id") or "")
        quantity = (
            quantity_by_batch.get(batch_no, 0.0)
            if warehouse
            else float(row.get("batch_qty") or 0)
        )
        if not batch_no or quantity <= 0:
            continue
        expiry = _date_or_none(row.get("expiry_date"))
        batches.append(
            {
                "batch_no": batch_no,
                "manufacturing_date": str(row.get("manufacturing_date") or ""),
                "expiry_date": str(row.get("expiry_date") or ""),
                "days_to_expiry": (expiry - today).days if expiry else None,
                "expired": bool(expiry and expiry < today),
                "quantity": quantity,
                "uom": row.get("stock_uom") or "",
                "supplier": row.get("supplier") or "",
                "reference_doctype": row.get("reference_doctype") or "",
                "reference_name": row.get("reference_name") or "",
            }
        )
    batches.sort(
        key=lambda row: (
            not bool(row["expiry_date"]),
            row["expiry_date"] or "9999-12-31",
            row["manufacturing_date"],
            row["batch_no"],
        )
    )
    truncated = len(batches) > limit or len(rows) >= 200
    visible = batches[:limit]
    return success(
        {
            "item_code": item_code,
            "warehouse": warehouse,
            "batches": visible,
            "total_qty": sum(row["quantity"] for row in batches),
            "truncated": truncated,
        }
    )


@_whitelist()
def get_manufacturing_readiness(
    item_code: str,
    warehouse: str | None = None,
    quantity: float = 1,
    limit: int = 20,
) -> dict:
    """Return direct active-BOM component availability from standard stock."""
    item_code = (item_code or "").strip()
    warehouse = (warehouse or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")
    try:
        quantity = float(quantity)
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        return failure(
            "quantity and limit must be numeric.",
            code="VALIDATION_BAD_LIMIT",
        )
    if quantity <= 0:
        return failure(
            "quantity must be greater than zero.",
            code="VALIDATION_REQUIRED",
        )
    empty = {
        "item_code": item_code,
        "warehouse": warehouse,
        "requested_qty": quantity,
        "bom": "",
        "bom_output_qty": 0.0,
        "uom": "",
        "currency": "",
        "total_cost": 0.0,
        "quality_inspection_required": False,
        "components": [],
        "ready": False,
        "possible_qty": 0.0,
        "shortage_count": 0,
        "truncated": False,
    }
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    if not _doctype_exists("BOM") or not _doctype_exists("BOM Item"):
        return success(empty)
    try:
        item = frappe.get_list(
            "Item",
            filters=[["item_code", "=", item_code]],
            fields=_existing_fields("Item", ["name", "item_code"]),
            limit_page_length=1,
        )
    except Exception:
        item = []
    if not item:
        return failure("Item not found.", code="ITEM_NOT_FOUND")

    bom_fields = _existing_fields(
        "BOM",
        [
            "name",
            "quantity",
            "uom",
            "currency",
            "total_cost",
            "inspection_required",
            "is_active",
            "is_default",
        ],
    )
    filters = [["item", "=", item_code], ["docstatus", "=", 1]]
    if "is_active" in bom_fields:
        filters.append(["is_active", "=", 1])
    try:
        boms = frappe.get_list(
            "BOM",
            filters=filters,
            fields=bom_fields,
            order_by=(
                "is_default desc, modified desc"
                if "is_default" in bom_fields
                else "modified desc"
            ),
            limit_page_length=1,
        )
    except Exception:
        return success(empty)
    if not boms:
        return success(empty)
    bom = boms[0]
    output_qty = float(bom.get("quantity") or 1)
    scale = quantity / output_qty if output_qty > 0 else quantity

    component_fields = _existing_fields(
        "BOM Item",
        [
            "item_code",
            "item_name",
            "qty",
            "uom",
            "stock_qty",
            "stock_uom",
            "conversion_factor",
            "source_warehouse",
            "is_stock_item",
            "sourced_by_supplier",
        ],
    )
    try:
        rows = frappe.get_list(
            "BOM Item",
            filters=[
                ["parent", "=", bom.get("name")],
                ["parenttype", "=", "BOM"],
            ],
            fields=component_fields,
            order_by="idx asc",
            limit_page_length=200,
        )
    except Exception:
        return success(empty)

    required_by_item: dict[str, dict] = {}
    for row in rows:
        code = str(row.get("item_code") or "")
        if not code or row.get("is_stock_item") in (0, "0", False):
            continue
        stock_qty = row.get("stock_qty")
        if stock_qty in (None, ""):
            stock_qty = float(row.get("qty") or 0) * float(
                row.get("conversion_factor") or 1
            )
        summary = required_by_item.setdefault(
            code,
            {
                "item_code": code,
                "item_name": row.get("item_name") or code,
                "uom": row.get("stock_uom") or row.get("uom") or "",
                "required_qty": 0.0,
                "source_warehouse": row.get("source_warehouse") or "",
                "sourced_by_supplier": bool(row.get("sourced_by_supplier")),
            },
        )
        summary["required_qty"] += float(stock_qty or 0) * scale

    codes = list(required_by_item)
    stock_by_item: dict[str, dict] = {}
    if codes and _doctype_exists("Bin"):
        stock_filters = [["item_code", "in", codes]]
        if warehouse:
            stock_filters.append(["warehouse", "=", warehouse])
        try:
            stocks = frappe.get_list(
                "Bin",
                filters=stock_filters,
                fields=[
                    "item_code",
                    "sum(actual_qty) as actual_qty",
                    "sum(projected_qty) as projected_qty",
                ],
                group_by="item_code",
                limit_page_length=len(codes),
            )
        except Exception:
            stocks = []
        stock_by_item = {
            str(row.get("item_code") or ""): row for row in stocks
        }

    components = []
    possible_qty: float | None = None
    for summary in required_by_item.values():
        stock = stock_by_item.get(summary["item_code"], {})
        actual = float(stock.get("actual_qty") or 0)
        projected = float(stock.get("projected_qty") or 0)
        required = float(summary["required_qty"])
        shortage = max(required - actual, 0.0)
        per_output = required / quantity if quantity else 0
        component_possible = (
            actual / per_output if per_output > 0 else quantity
        )
        possible_qty = (
            component_possible
            if possible_qty is None
            else min(possible_qty, component_possible)
        )
        components.append(
            {
                **summary,
                "actual_qty": actual,
                "projected_qty": projected,
                "shortage_qty": shortage,
                "available": shortage <= 0,
            }
        )
    components.sort(
        key=lambda row: (
            row["available"],
            -row["shortage_qty"],
            row["item_code"],
        )
    )
    truncated = len(components) > limit or len(rows) >= 200
    shortage_count = sum(not row["available"] for row in components)
    return success(
        {
            **empty,
            "bom": bom.get("name") or "",
            "bom_output_qty": output_qty,
            "uom": bom.get("uom") or "",
            "currency": bom.get("currency") or "",
            "total_cost": float(bom.get("total_cost") or 0) * scale,
            "quality_inspection_required": bool(
                bom.get("inspection_required")
            ),
            "components": components[:limit],
            "ready": bool(components) and shortage_count == 0,
            "possible_qty": max(possible_qty or 0, 0.0),
            "shortage_count": shortage_count,
            "truncated": truncated,
        }
    )


@_whitelist()
def get_production_status(item_code: str, limit: int = 10) -> dict:
    """Return active standard Work Orders and operation-level progress."""
    item_code = (item_code or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    empty = {
        "item_code": item_code,
        "orders": [],
        "planned_qty": 0.0,
        "produced_qty": 0.0,
        "remaining_qty": 0.0,
        "overdue_count": 0,
        "truncated": False,
    }
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    if not _doctype_exists("Work Order"):
        return success(empty)
    try:
        if not frappe.get_list(
            "Item",
            filters=[["item_code", "=", item_code]],
            fields=_existing_fields("Item", ["name", "item_code"]),
            limit_page_length=1,
        ):
            return failure("Item not found.", code="ITEM_NOT_FOUND")
        rows = frappe.get_list(
            "Work Order",
            filters=[
                ["production_item", "=", item_code],
                ["docstatus", "=", 1],
                [
                    "status",
                    "not in",
                    ["Completed", "Stopped", "Closed", "Cancelled"],
                ],
            ],
            fields=_existing_fields(
                "Work Order",
                [
                    "name",
                    "status",
                    "bom_no",
                    "company",
                    "stock_uom",
                    "qty",
                    "produced_qty",
                    "material_transferred_for_manufacturing",
                    "process_loss_qty",
                    "planned_start_date",
                    "planned_end_date",
                    "actual_start_date",
                    "expected_delivery_date",
                    "source_warehouse",
                    "wip_warehouse",
                    "fg_warehouse",
                    "sales_order",
                    "project",
                ],
            ),
            order_by="planned_end_date asc, creation desc",
            limit_page_length=101,
        )
    except Exception:
        return success(empty)

    truncated = len(rows) > 100
    rows = rows[:100]
    visible_names = [
        str(row.get("name") or "") for row in rows[:limit] if row.get("name")
    ]
    operations_by_order: dict[str, list[dict]] = {}
    if visible_names and _doctype_exists("Work Order Operation"):
        operation_fields = _existing_fields(
            "Work Order Operation",
            [
                "parent",
                "operation",
                "status",
                "workstation",
                "workstation_type",
                "completed_qty",
                "pending_qty",
                "planned_start_time",
                "planned_end_time",
                "actual_start_time",
                "actual_end_time",
                "time_in_mins",
                "actual_operation_time",
                "quality_inspection_required",
                "is_subcontracted",
            ],
        )
        if "parent" in operation_fields:
            try:
                operation_rows = frappe.get_list(
                    "Work Order Operation",
                    filters=[
                        ["parent", "in", visible_names],
                        ["parenttype", "=", "Work Order"],
                    ],
                    fields=operation_fields,
                    order_by="parent asc, idx asc",
                    limit_page_length=1000,
                )
            except Exception:
                operation_rows = []
            for operation in operation_rows:
                parent = str(operation.get("parent") or "")
                completed_qty = float(operation.get("completed_qty") or 0)
                pending_qty = float(operation.get("pending_qty") or 0)
                total_qty = completed_qty + pending_qty
                planned_end = _datetime_or_none(
                    operation.get("planned_end_time")
                )
                status = str(operation.get("status") or "")
                operations_by_order.setdefault(parent, []).append(
                    {
                        "operation": operation.get("operation") or "",
                        "status": status,
                        "workstation": operation.get("workstation") or "",
                        "workstation_type": operation.get("workstation_type")
                        or "",
                        "completed_qty": completed_qty,
                        "pending_qty": pending_qty,
                        "progress": min(
                            max(
                                (
                                    completed_qty / total_qty * 100
                                    if total_qty > 0
                                    else 100 if status == "Completed" else 0
                                ),
                                0,
                            ),
                            100,
                        ),
                        "planned_start": str(
                            operation.get("planned_start_time") or ""
                        ),
                        "planned_end": str(
                            operation.get("planned_end_time") or ""
                        ),
                        "actual_start": str(
                            operation.get("actual_start_time") or ""
                        ),
                        "actual_end": str(
                            operation.get("actual_end_time") or ""
                        ),
                        "planned_minutes": float(
                            operation.get("time_in_mins") or 0
                        ),
                        "actual_minutes": float(
                            operation.get("actual_operation_time") or 0
                        ),
                        "quality_inspection_required": bool(
                            operation.get("quality_inspection_required")
                        ),
                        "subcontracted": bool(
                            operation.get("is_subcontracted")
                        ),
                        "overdue": bool(
                            planned_end
                            and planned_end < datetime.now()
                            and status != "Completed"
                        ),
                    }
                )
    job_cards_by_order: dict[str, list[dict]] = {}
    if visible_names and _doctype_exists("Job Card"):
        job_card_fields = _existing_fields(
            "Job Card",
            [
                "name",
                "work_order",
                "status",
                "operation",
                "operation_id",
                "workstation",
                "posting_date",
                "for_quantity",
                "total_completed_qty",
                "total_time_in_mins",
                "transferred_qty",
                "requested_qty",
                "pending_qty",
                "manufactured_qty",
                "quality_inspection",
                "expected_start_date",
                "expected_end_date",
                "actual_start_date",
                "actual_end_date",
                "is_paused",
            ],
        )
        try:
            job_card_rows = frappe.get_list(
                "Job Card",
                filters=[
                    ["work_order", "in", visible_names],
                    ["docstatus", "!=", 2],
                    ["status", "!=", "Cancelled"],
                ],
                fields=job_card_fields,
                order_by="expected_start_date asc, creation asc",
                limit_page_length=500,
            )
        except Exception:
            job_card_rows = []
        log_summary: dict[str, dict] = {}
        job_card_names = [
            str(row.get("name") or "")
            for row in job_card_rows
            if row.get("name")
        ]
        if job_card_names and _doctype_exists("Job Card Time Log"):
            log_fields = _existing_fields(
                "Job Card Time Log",
                ["parent", "from_time", "to_time", "time_in_mins", "completed_qty"],
            )
            if "parent" in log_fields:
                try:
                    time_logs = frappe.get_list(
                        "Job Card Time Log",
                        filters=[
                            ["parent", "in", job_card_names],
                            ["parenttype", "=", "Job Card"],
                        ],
                        fields=log_fields,
                        order_by="parent asc, from_time asc, idx asc",
                        limit_page_length=5000,
                    )
                except Exception:
                    time_logs = []
                for time_log in time_logs:
                    parent = str(time_log.get("parent") or "")
                    summary = log_summary.setdefault(
                        parent,
                        {
                            "count": 0,
                            "minutes": 0.0,
                            "completed_qty": 0.0,
                            "last_activity": "",
                        },
                    )
                    summary["count"] += 1
                    summary["minutes"] += float(
                        time_log.get("time_in_mins") or 0
                    )
                    summary["completed_qty"] += float(
                        time_log.get("completed_qty") or 0
                    )
                    activity = str(
                        time_log.get("to_time")
                        or time_log.get("from_time")
                        or ""
                    )
                    if activity > summary["last_activity"]:
                        summary["last_activity"] = activity
        for job_card in job_card_rows:
            name = str(job_card.get("name") or "")
            work_order = str(job_card.get("work_order") or "")
            status = str(job_card.get("status") or "")
            expected_end = _datetime_or_none(
                job_card.get("expected_end_date")
            )
            logs = log_summary.get(
                name,
                {
                    "count": 0,
                    "minutes": 0.0,
                    "completed_qty": 0.0,
                    "last_activity": "",
                },
            )
            job_cards_by_order.setdefault(work_order, []).append(
                {
                    "name": name,
                    "status": status,
                    "operation": job_card.get("operation") or "",
                    "operation_id": job_card.get("operation_id") or "",
                    "workstation": job_card.get("workstation") or "",
                    "posting_date": str(job_card.get("posting_date") or ""),
                    "for_quantity": float(job_card.get("for_quantity") or 0),
                    "completed_qty": float(
                        job_card.get("total_completed_qty") or 0
                    ),
                    "pending_qty": float(job_card.get("pending_qty") or 0),
                    "manufactured_qty": float(
                        job_card.get("manufactured_qty") or 0
                    ),
                    "transferred_qty": float(
                        job_card.get("transferred_qty") or 0
                    ),
                    "requested_qty": float(
                        job_card.get("requested_qty") or 0
                    ),
                    "total_minutes": float(
                        job_card.get("total_time_in_mins")
                        or logs["minutes"]
                        or 0
                    ),
                    "quality_inspection": job_card.get("quality_inspection")
                    or "",
                    "expected_start": str(
                        job_card.get("expected_start_date") or ""
                    ),
                    "expected_end": str(
                        job_card.get("expected_end_date") or ""
                    ),
                    "actual_start": str(
                        job_card.get("actual_start_date") or ""
                    ),
                    "actual_end": str(
                        job_card.get("actual_end_date") or ""
                    ),
                    "paused": bool(job_card.get("is_paused")),
                    "time_log_count": logs["count"],
                    "last_activity": logs["last_activity"],
                    "overdue": bool(
                        expected_end
                        and expected_end < datetime.now()
                        and status not in {"Completed", "Cancelled"}
                    ),
                }
            )
    now = datetime.now()
    orders = []
    for row in rows[:limit]:
        planned = float(row.get("qty") or 0)
        produced = float(row.get("produced_qty") or 0)
        remaining = max(planned - produced, 0.0)
        end = _datetime_or_none(row.get("planned_end_date"))
        operations = operations_by_order.get(str(row.get("name") or ""), [])
        job_cards = job_cards_by_order.get(str(row.get("name") or ""), [])
        orders.append(
            {
                "name": row.get("name") or "",
                "status": row.get("status") or "",
                "bom": row.get("bom_no") or "",
                "company": row.get("company") or "",
                "uom": row.get("stock_uom") or "",
                "planned_qty": planned,
                "produced_qty": produced,
                "remaining_qty": remaining,
                "transferred_qty": float(
                    row.get("material_transferred_for_manufacturing") or 0
                ),
                "process_loss_qty": float(
                    row.get("process_loss_qty") or 0
                ),
                "progress": min(
                    max((produced / planned * 100) if planned > 0 else 0, 0),
                    100,
                ),
                "planned_start": str(row.get("planned_start_date") or ""),
                "planned_end": str(row.get("planned_end_date") or ""),
                "actual_start": str(row.get("actual_start_date") or ""),
                "expected_delivery": str(
                    row.get("expected_delivery_date") or ""
                ),
                "source_warehouse": row.get("source_warehouse") or "",
                "wip_warehouse": row.get("wip_warehouse") or "",
                "target_warehouse": row.get("fg_warehouse") or "",
                "sales_order": row.get("sales_order") or "",
                "project": row.get("project") or "",
                "overdue": bool(end and end < now and remaining > 0),
                "operations": operations,
                "completed_operations": sum(
                    operation["status"] == "Completed"
                    for operation in operations
                ),
                "overdue_operations": sum(
                    operation["overdue"] for operation in operations
                ),
                "job_cards": job_cards,
                "active_job_cards": sum(
                    job_card["status"] not in {"Completed", "Cancelled"}
                    for job_card in job_cards
                ),
                "overdue_job_cards": sum(
                    job_card["overdue"] for job_card in job_cards
                ),
            }
        )
    planned_total = sum(float(row.get("qty") or 0) for row in rows)
    produced_total = sum(
        float(row.get("produced_qty") or 0) for row in rows
    )
    overdue_count = sum(
        bool(
            (end := _datetime_or_none(row.get("planned_end_date")))
            and end < now
            and float(row.get("qty") or 0)
            > float(row.get("produced_qty") or 0)
        )
        for row in rows
    )
    return success(
        {
            "item_code": item_code,
            "orders": orders,
            "planned_qty": planned_total,
            "produced_qty": produced_total,
            "remaining_qty": max(planned_total - produced_total, 0.0),
            "overdue_count": overdue_count,
            "truncated": truncated,
        }
    )


@_whitelist()
def get_planning(
    item_code: str,
    warehouse: str | None = None,
    horizon_days: int = 90,
) -> dict:
    """Return standard ERPNext reorder and batch-expiry planning context."""
    item_code = (item_code or "").strip()
    warehouse = (warehouse or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")
    try:
        horizon_days = int(horizon_days)
    except (TypeError, ValueError):
        return failure(
            "horizon_days must be an integer.",
            code="VALIDATION_BAD_HORIZON",
        )
    if horizon_days < 1 or horizon_days > 365:
        return failure(
            "horizon_days must be between 1 and 365.",
            code="VALIDATION_BAD_HORIZON",
        )
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    item_rows = frappe.get_list(
        "Item",
        filters=[["item_code", "=", item_code]],
        fields=_existing_fields("Item", ["name", "item_code", "has_batch_no"]),
        limit_page_length=1,
    )
    if not item_rows:
        return failure("Item not found.", code="ITEM_NOT_FOUND")

    try:
        reorder_rules = _reorder_rules(item_code, warehouse)
    except Exception:
        reorder_rules = []
    expiring_batches = []
    if _truthy(item_rows[0].get("has_batch_no")):
        try:
            expiring_batches = _expiring_batches(
                item_code,
                warehouse,
                horizon_days,
            )
        except Exception:
            expiring_batches = []
    return success(
        {
            "reorder_rules": reorder_rules,
            "expiring_batches": expiring_batches,
            "horizon_days": horizon_days,
        }
    )


@_whitelist()
def get_buying_insight(item_code: str, limit: int = 5) -> dict:
    """Return optional standard buying defaults and recent receipts for an item."""
    item_code = (item_code or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if limit < 1 or limit > 20:
        return failure("limit must be between 1 and 20.", code="VALIDATION_BAD_LIMIT")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    items = frappe.get_list(
        "Item",
        filters=[["item_code", "=", item_code]],
        fields=["name"],
        limit_page_length=1,
    )
    if not items:
        return failure("Item not found.", code="ITEM_NOT_FOUND")
    return success(
        {
            "defaults": _buying_defaults(item_code),
            "recent_receipts": _recent_item_receipts(item_code, limit),
        }
    )


@_whitelist()
def get_serial_warranty(item_code: str, limit: int = 20) -> dict:
    """Return standard Serial No warranty and AMC status for an item."""
    item_code = (item_code or "").strip()
    if not item_code:
        return failure("item_code is required.", code="VALIDATION_REQUIRED")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if limit < 1 or limit > 100:
        return failure("limit must be between 1 and 100.", code="VALIDATION_BAD_LIMIT")
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    items = frappe.get_list(
        "Item",
        filters=[["item_code", "=", item_code]],
        fields=_existing_fields("Item", ["name", "item_code", "has_serial_no"]),
        limit_page_length=1,
    )
    if not items:
        return failure("Item not found.", code="ITEM_NOT_FOUND")
    empty = {
        "serials": [],
        "total": 0,
        "active_warranty": 0,
        "expiring_warranty": 0,
        "expired_warranty": 0,
        "unknown_warranty": 0,
    }
    if not _truthy(items[0].get("has_serial_no")) or not _doctype_exists("Serial No"):
        return success(empty)
    fields = _existing_fields(
        "Serial No",
        [
            "name",
            "serial_no",
            "item_code",
            "status",
            "warehouse",
            "customer",
            "warranty_expiry_date",
            "amc_expiry_date",
            "maintenance_status",
            "warranty_period",
        ],
    )
    if "item_code" not in fields:
        return success(empty)
    try:
        rows = frappe.get_list(
            "Serial No",
            filters=[["item_code", "=", item_code]],
            fields=fields,
            order_by="warranty_expiry_date asc, modified desc",
            limit_page_length=limit,
        )
    except Exception:
        return success(empty)
    today = _today_date()
    serials = []
    counts = {
        "active_warranty": 0,
        "expiring_warranty": 0,
        "expired_warranty": 0,
        "unknown_warranty": 0,
    }
    for row in rows:
        expiry = _date_or_none(row.get("warranty_expiry_date"))
        days = (expiry - today).days if expiry else None
        if days is None:
            warranty_status = "unknown"
            counts["unknown_warranty"] += 1
        elif days < 0:
            warranty_status = "expired"
            counts["expired_warranty"] += 1
        elif days <= 30:
            warranty_status = "expiring"
            counts["expiring_warranty"] += 1
        else:
            warranty_status = "active"
            counts["active_warranty"] += 1
        serials.append(
            {
                "serial_no": row.get("serial_no") or row.get("name") or "",
                "status": row.get("status") or "",
                "warehouse": row.get("warehouse") or "",
                "customer": row.get("customer") or "",
                "warranty_expiry_date": str(row.get("warranty_expiry_date") or ""),
                "amc_expiry_date": str(row.get("amc_expiry_date") or ""),
                "maintenance_status": row.get("maintenance_status") or "",
                "warranty_period": int(row.get("warranty_period") or 0),
                "days_to_warranty_expiry": days,
                "warranty_status": warranty_status,
            }
        )
    return success({"serials": serials, "total": len(serials), **counts})


def _buying_defaults(item_code: str) -> list[dict]:
    if not _doctype_exists("Item Default"):
        return []
    fields = _existing_fields(
        "Item Default",
        ["company", "default_supplier", "default_price_list", "default_warehouse"],
    )
    if "default_supplier" not in fields:
        return []
    try:
        rows = frappe.get_list(
            "Item Default",
            filters=[
                ["parent", "=", item_code],
                ["parenttype", "=", "Item"],
                ["default_supplier", "is", "set"],
            ],
            fields=fields,
            order_by="idx asc",
            limit_page_length=100,
        )
    except Exception:
        return []
    return [
        {
            "company": row.get("company") or "",
            "supplier": row.get("default_supplier") or "",
            "price_list": row.get("default_price_list") or "",
            "warehouse": row.get("default_warehouse") or "",
        }
        for row in rows
    ]


def _recent_item_receipts(item_code: str, limit: int) -> list[dict]:
    if not _doctype_exists("Purchase Receipt Item") or not _doctype_exists(
        "Purchase Receipt"
    ):
        return []
    fields = _existing_fields(
        "Purchase Receipt Item",
        ["parent", "item_code", "item_name", "qty", "uom", "rate", "amount", "warehouse"],
    )
    if not {"parent", "item_code"}.issubset(fields):
        return []
    try:
        item_rows = frappe.get_list(
            "Purchase Receipt Item",
            filters=[
                ["item_code", "=", item_code],
                ["docstatus", "=", 1],
            ],
            fields=fields,
            order_by="modified desc",
            limit_page_length=limit,
        )
        parents = [row.get("parent") for row in item_rows if row.get("parent")]
        receipt_rows = (
            frappe.get_list(
                "Purchase Receipt",
                filters=[["name", "in", parents], ["docstatus", "=", 1]],
                fields=_existing_fields(
                    "Purchase Receipt",
                    ["name", "supplier", "posting_date", "currency", "status"],
                ),
                limit_page_length=max(1, len(parents)),
            )
            if parents
            else []
        )
    except Exception:
        return []
    receipts = {row.get("name"): row for row in receipt_rows}
    result = []
    for row in item_rows:
        receipt = receipts.get(row.get("parent"), {})
        result.append(
            {
                "receipt": row.get("parent") or "",
                "supplier": receipt.get("supplier") or "",
                "posting_date": str(receipt.get("posting_date") or ""),
                "currency": receipt.get("currency") or "",
                "status": receipt.get("status") or "",
                "item_name": row.get("item_name") or "",
                "qty": float(row.get("qty") or 0),
                "uom": row.get("uom") or "",
                "rate": float(row.get("rate") or 0),
                "amount": float(row.get("amount") or 0),
                "warehouse": row.get("warehouse") or "",
            }
        )
    return result


def _reorder_rules(item_code: str, warehouse: str) -> list[dict]:
    if not _doctype_exists("Item Reorder"):
        return []
    filters: list = [["parent", "=", item_code]]
    if warehouse:
        filters.append(["warehouse", "=", warehouse])
    rules = frappe.get_list(
        "Item Reorder",
        filters=filters,
        fields=_existing_fields(
            "Item Reorder",
            [
                "warehouse",
                "warehouse_group",
                "warehouse_reorder_level",
                "warehouse_reorder_qty",
                "material_request_type",
            ],
        ),
        order_by="idx asc",
        limit_page_length=200,
    )
    warehouses = sorted({str(row.get("warehouse")) for row in rules if row.get("warehouse")})
    bins = []
    if warehouses:
        bins = frappe.get_list(
            "Bin",
            filters=[
                ["item_code", "=", item_code],
                ["warehouse", "in", warehouses],
            ],
            fields=["warehouse", "actual_qty", "projected_qty"],
            limit_page_length=max(1, len(warehouses)),
        )
    bin_by_warehouse = {row.get("warehouse"): row for row in bins}
    payload = []
    for rule in rules:
        rule_warehouse = rule.get("warehouse") or ""
        bin_row = bin_by_warehouse.get(rule_warehouse, {})
        quantity_available = bool(rule_warehouse)
        actual_qty = float(bin_row.get("actual_qty") or 0)
        projected_qty = float(bin_row.get("projected_qty") or 0)
        reorder_level = float(rule.get("warehouse_reorder_level") or 0)
        reorder_qty = float(rule.get("warehouse_reorder_qty") or 0)
        below_reorder = quantity_available and projected_qty <= reorder_level
        shortfall = max(reorder_level - projected_qty, 0) if quantity_available else 0
        suggested_qty = (reorder_qty if reorder_qty > 0 else shortfall) if below_reorder else 0
        payload.append(
            {
                "warehouse": rule_warehouse,
                "warehouse_group": rule.get("warehouse_group") or "",
                "material_request_type": (rule.get("material_request_type") or "Purchase"),
                "actual_qty": actual_qty,
                "projected_qty": projected_qty,
                "reorder_level": reorder_level,
                "reorder_qty": reorder_qty,
                "shortfall": shortfall,
                "suggested_qty": suggested_qty,
                "below_reorder": below_reorder,
                "quantity_available": quantity_available,
            }
        )
    return payload


def _expiring_batches(
    item_code: str,
    warehouse: str,
    horizon_days: int,
) -> list[dict]:
    if not _doctype_exists("Batch"):
        return []
    today = _today_date()
    horizon = today + timedelta(days=horizon_days)
    rows = frappe.get_list(
        "Batch",
        filters=[
            ["item", "=", item_code],
            ["disabled", "=", 0],
            ["expiry_date", "is", "set"],
            ["expiry_date", "<=", horizon.isoformat()],
        ],
        fields=_existing_fields(
            "Batch",
            ["name", "batch_id", "expiry_date", "disabled"],
        ),
        order_by="expiry_date asc, name asc",
        limit_page_length=100,
    )
    if warehouse and rows:
        available = set(
            frappe.get_list(
                "Stock Ledger Entry",
                filters=[
                    ["item_code", "=", item_code],
                    ["warehouse", "=", warehouse],
                    ["batch_no", "is", "set"],
                    ["is_cancelled", "=", 0],
                ],
                pluck="batch_no",
                limit_page_length=5000,
            )
        )
        rows = [row for row in rows if (row.get("name") or row.get("batch_id")) in available]
    payload = []
    for row in rows:
        try:
            expiry = date.fromisoformat(str(row.get("expiry_date")))
        except (TypeError, ValueError):
            continue
        days_to_expiry = (expiry - today).days
        payload.append(
            {
                "batch_no": row.get("name") or row.get("batch_id") or "",
                "expiry_date": expiry.isoformat(),
                "days_to_expiry": days_to_expiry,
                "expired": days_to_expiry < 0,
                "status": "expired" if days_to_expiry < 0 else "expiring",
            }
        )
    return payload


def _doctype_exists(doctype: str) -> bool:
    try:
        return bool(frappe.db.exists("DocType", doctype))
    except Exception:
        return False


def _truthy(value) -> bool:
    return value in (True, 1, "1", "true", "True")


def _today_date() -> date:
    try:
        return date.fromisoformat(str(frappe.utils.nowdate()))
    except Exception:
        return date.today()


def _date_or_none(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except (TypeError, ValueError):
        return None


def _datetime_or_none(value) -> datetime | None:
    try:
        if not value:
            return None
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(
            tzinfo=None
        )
    except (TypeError, ValueError):
        return None
