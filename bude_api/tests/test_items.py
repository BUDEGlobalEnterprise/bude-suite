from unittest.mock import patch

from bude_api.api import items as items_api


@patch("bude_api.api.items.frappe")
def test_search_empty_query_returns_empty_list(mock_frappe):
    result = items_api.search("   ")
    assert result["ok"] is True
    assert result["data"] == []
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.items.frappe")
def test_search_returns_name_and_barcode_matches_deduped(mock_frappe):
    def get_list(doctype, **kwargs):
        if doctype == "Item Barcode":
            return [{"parent": "ITEM-A"}]
        if doctype == "Item":
            filters = kwargs.get("filters", [])
            if any(f[0] == "item_code" and f[1] == "in" for f in filters):
                return [
                    {
                        "name": "ITEM-A",
                        "item_code": "ITEM-A",
                        "item_name": "Widget A",
                        "description": "",
                        "stock_uom": "Nos",
                        "image": None,
                        "disabled": 0,
                    }
                ]
            return [
                {
                    "name": "ITEM-A",
                    "item_code": "ITEM-A",
                    "item_name": "Widget A",
                    "description": "",
                    "stock_uom": "Nos",
                    "image": None,
                    "disabled": 0,
                },
                {
                    "name": "ITEM-B",
                    "item_code": "ITEM-B",
                    "item_name": "Widget B",
                    "description": "",
                    "stock_uom": "Nos",
                    "image": None,
                    "disabled": 0,
                },
            ]
        return []

    mock_frappe.get_all.side_effect = get_list
    mock_frappe.get_list.side_effect = get_list
    result = items_api.search("Widget")

    assert result["ok"] is True
    codes = [r["item_code"] for r in result["data"]]
    assert codes == ["ITEM-A", "ITEM-B"]
    mock_frappe.get_all.assert_called_once()


@patch("bude_api.api.items.frappe")
def test_search_respects_limit_bounds(mock_frappe):
    mock_frappe.get_list.return_value = []
    items_api.search("x", limit=500)
    item_calls = [call for call in mock_frappe.get_list.call_args_list if call.args[0] == "Item"]
    _, kwargs = item_calls[-1]
    assert kwargs["limit"] == 100

    items_api.search("x", limit=0)
    item_calls = [call for call in mock_frappe.get_list.call_args_list if call.args[0] == "Item"]
    _, kwargs = item_calls[-1]
    assert kwargs["limit"] == 1


@patch("bude_api.api.items.frappe")
def test_get_by_barcode_returns_item(mock_frappe):
    def get_list(doctype, **kwargs):
        if doctype == "Item Barcode":
            return [{"parent": "ITEM-1"}]
        if doctype == "Item":
            return [
                {
                    "name": "ITEM-1",
                    "item_code": "ITEM-1",
                    "item_name": "Thing",
                    "description": "",
                    "stock_uom": "Nos",
                    "image": None,
                    "disabled": 0,
                }
            ]
        return []

    mock_frappe.get_all.side_effect = get_list
    mock_frappe.get_list.side_effect = get_list
    result = items_api.get_by_barcode("ABC123")
    assert result["ok"] is True
    assert result["data"]["item_code"] == "ITEM-1"
    item_call = [call for call in mock_frappe.get_list.call_args_list if call.args[0] == "Item"][-1]
    assert "brand" in item_call.kwargs["fields"]
    assert "safety_stock" in item_call.kwargs["fields"]
    assert "lead_time_days" in item_call.kwargs["fields"]


@patch("bude_api.api.items.frappe")
def test_list_groups_uses_permission_aware_get_list(mock_frappe):
    mock_frappe.get_list.return_value = ["Products", "Raw Materials"]

    result = items_api.list_groups()

    assert result["ok"] is True
    assert result["data"] == ["Products", "Raw Materials"]
    mock_frappe.get_list.assert_called_once()
    args, kwargs = mock_frappe.get_list.call_args
    assert args[0] == "Item Group"
    assert kwargs["filters"] == {"is_group": 0}
    mock_frappe.get_all.assert_not_called()


@patch("bude_api.api.items.frappe")
def test_get_by_barcode_returns_not_found_when_no_match(mock_frappe):
    mock_frappe.get_all.return_value = []
    result = items_api.get_by_barcode("UNKNOWN")
    assert result["ok"] is False
    assert result["code"] == "ITEM_NOT_FOUND"


def test_get_by_barcode_requires_value():
    result = items_api.get_by_barcode("   ")
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


@patch("bude_api.api.items.frappe")
def test_get_stock_returns_bin_rows(mock_frappe):
    mock_frappe.get_list.return_value = [
        {
            "warehouse": "Stores - X",
            "actual_qty": 10.0,
            "reserved_qty": 1.0,
            "ordered_qty": 0.0,
            "projected_qty": 9.0,
            "stock_uom": "Nos",
        }
    ]
    result = items_api.get_stock("ITEM-1")
    assert result["ok"] is True
    assert len(result["data"]) == 1
    assert result["data"][0]["warehouse"] == "Stores - X"


@patch("bude_api.api.items.frappe")
def test_get_stock_filters_by_warehouse_when_given(mock_frappe):
    mock_frappe.get_list.return_value = []
    items_api.get_stock("ITEM-1", warehouse="Stores - X")
    args, kwargs = mock_frappe.get_list.call_args
    filters = kwargs["filters"]
    assert ["item_code", "=", "ITEM-1"] in filters
    assert ["warehouse", "=", "Stores - X"] in filters


def test_get_stock_requires_item_code():
    result = items_api.get_stock("   ")
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


@patch("bude_api.api.items.frappe")
def test_get_planning_joins_reorder_rules_bins_and_batch_expiry(mock_frappe):
    mock_frappe.db.exists.return_value = True
    mock_frappe.utils.nowdate.return_value = "2026-07-17"

    def get_list(doctype, **kwargs):
        if doctype == "Item":
            return [{"name": "ITEM-1", "item_code": "ITEM-1", "has_batch_no": 1}]
        if doctype == "Item Reorder":
            return [
                {
                    "warehouse": "Stores - X",
                    "warehouse_group": "",
                    "warehouse_reorder_level": 10,
                    "warehouse_reorder_qty": 25,
                    "material_request_type": "Purchase",
                }
            ]
        if doctype == "Bin":
            return [
                {
                    "warehouse": "Stores - X",
                    "actual_qty": 4,
                    "projected_qty": 3,
                }
            ]
        if doctype == "Batch":
            return [
                {"name": "B-OLD", "expiry_date": "2026-07-10"},
                {"name": "B-SOON", "expiry_date": "2026-08-01"},
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = items_api.get_planning("ITEM-1")

    assert result["ok"] is True
    rule = result["data"]["reorder_rules"][0]
    assert rule["projected_qty"] == 3
    assert rule["shortfall"] == 7
    assert rule["suggested_qty"] == 25
    assert rule["below_reorder"] is True
    batches = result["data"]["expiring_batches"]
    assert batches[0]["status"] == "expired"
    assert batches[0]["days_to_expiry"] == -7
    assert batches[1]["status"] == "expiring"


@patch("bude_api.api.items.frappe")
def test_get_planning_returns_empty_optional_sections_when_doctypes_missing(
    mock_frappe,
):
    mock_frappe.db.exists.return_value = False
    mock_frappe.get_list.return_value = [
        {
            "name": "ITEM-1",
            "item_code": "ITEM-1",
            "has_batch_no": 0,
        }
    ]

    result = items_api.get_planning("ITEM-1")

    assert result["ok"] is True
    assert result["data"]["reorder_rules"] == []
    assert result["data"]["expiring_batches"] == []


@patch("bude_api.api.items.frappe")
def test_get_planning_keeps_primary_response_when_optional_queries_fail(
    mock_frappe,
):
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Item":
            return [
                {
                    "name": "ITEM-1",
                    "item_code": "ITEM-1",
                    "has_batch_no": 1,
                }
            ]
        raise RuntimeError(f"{doctype} is unavailable")

    mock_frappe.get_list.side_effect = get_list

    result = items_api.get_planning("ITEM-1")

    assert result["ok"] is True
    assert result["data"]["reorder_rules"] == []
    assert result["data"]["expiring_batches"] == []


def test_get_planning_validates_horizon():
    result = items_api.get_planning("ITEM-1", horizon_days=0)
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_HORIZON"


@patch("bude_api.api.items.frappe")
def test_get_buying_insight_returns_defaults_and_recent_receipts(mock_frappe):
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Item":
            return [{"name": "ITEM-1"}]
        if doctype == "Item Default":
            return [
                {
                    "company": "Bude",
                    "default_supplier": "SUP-001",
                    "default_price_list": "Standard Buying",
                    "default_warehouse": "Stores - B",
                }
            ]
        if doctype == "Purchase Receipt Item":
            return [
                {
                    "parent": "PREC-001",
                    "item_code": "ITEM-1",
                    "item_name": "Widget",
                    "qty": 4,
                    "uom": "Nos",
                    "rate": 25,
                    "amount": 100,
                    "warehouse": "Stores - B",
                }
            ]
        if doctype == "Purchase Receipt":
            return [
                {
                    "name": "PREC-001",
                    "supplier": "SUP-001",
                    "posting_date": "2026-07-16",
                    "currency": "INR",
                    "status": "Completed",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = items_api.get_buying_insight("ITEM-1")

    assert result["ok"] is True
    assert result["data"]["defaults"][0]["supplier"] == "SUP-001"
    receipt = result["data"]["recent_receipts"][0]
    assert receipt["receipt"] == "PREC-001"
    assert receipt["rate"] == 25
    assert receipt["currency"] == "INR"


@patch("bude_api.api.items.frappe")
def test_get_buying_insight_tolerates_missing_optional_doctypes(mock_frappe):
    mock_frappe.db.exists.return_value = False
    mock_frappe.get_list.return_value = [{"name": "ITEM-1"}]

    result = items_api.get_buying_insight("ITEM-1")

    assert result["ok"] is True
    assert result["data"] == {"defaults": [], "recent_receipts": []}


@patch("bude_api.api.items.frappe")
def test_get_serial_warranty_classifies_standard_serial_records(mock_frappe):
    mock_frappe.db.exists.return_value = True
    mock_frappe.utils.nowdate.return_value = "2026-07-17"

    def get_list(doctype, **kwargs):
        if doctype == "Item":
            return [{"name": "ITEM-1", "item_code": "ITEM-1", "has_serial_no": 1}]
        if doctype == "Serial No":
            return [
                {
                    "name": "SER-OLD",
                    "status": "Delivered",
                    "customer": "CUST-1",
                    "warranty_expiry_date": "2026-07-10",
                    "maintenance_status": "Out of Warranty",
                },
                {
                    "name": "SER-SOON",
                    "status": "Active",
                    "warehouse": "Stores - A",
                    "warranty_expiry_date": "2026-08-01",
                    "maintenance_status": "Under Warranty",
                },
                {
                    "name": "SER-UNKNOWN",
                    "status": "Active",
                    "warehouse": "Stores - A",
                },
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = items_api.get_serial_warranty("ITEM-1")

    assert result["ok"] is True
    assert result["data"]["total"] == 3
    assert result["data"]["expired_warranty"] == 1
    assert result["data"]["expiring_warranty"] == 1
    assert result["data"]["unknown_warranty"] == 1
    assert result["data"]["serials"][0]["days_to_warranty_expiry"] == -7


@patch("bude_api.api.items.frappe")
def test_get_serial_warranty_is_empty_for_non_serial_item(mock_frappe):
    mock_frappe.get_list.return_value = [
        {"name": "ITEM-1", "item_code": "ITEM-1", "has_serial_no": 0}
    ]

    result = items_api.get_serial_warranty("ITEM-1")

    assert result["ok"] is True
    assert result["data"]["serials"] == []
    mock_frappe.db.exists.assert_not_called()


@patch("bude_api.api.items.frappe")
def test_get_movement_insight_calculates_velocity_and_stock_cover(mock_frappe):
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Stock Ledger Entry":
            return [
                {
                    "posting_date": "2026-07-17",
                    "actual_qty": -9,
                    "voucher_type": "Delivery Note",
                    "voucher_no": "DN-001",
                },
                {"posting_date": "2026-07-10", "actual_qty": 30},
                {"posting_date": "2026-07-05", "actual_qty": -6},
            ]
        if doctype == "Bin":
            return [{"actual_qty": 45, "projected_qty": 40}]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = items_api.get_movement_insight("ITEM-1", days=30)

    assert result["ok"] is True
    assert result["data"]["inbound_qty"] == 30
    assert result["data"]["outbound_qty"] == 15
    assert result["data"]["daily_outbound"] == 0.5
    assert result["data"]["days_of_cover"] == 90
    assert result["data"]["last_voucher_no"] == "DN-001"


@patch("bude_api.api.items.frappe")
def test_get_supply_demand_calculates_open_commitments(mock_frappe):
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Purchase Order Item":
            return [
                {
                    "parent": "PO-001",
                    "qty": 10,
                    "received_qty": 4,
                    "warehouse": "Stores - A",
                    "uom": "Nos",
                    "expected_delivery_date": "2026-07-20",
                },
                {"parent": "PO-DONE", "qty": 5, "received_qty": 5},
            ]
        if doctype == "Sales Order Item":
            return [
                {
                    "parent": "SO-001",
                    "qty": 8,
                    "delivered_qty": 3,
                    "warehouse": "Stores - A",
                    "uom": "Nos",
                    "delivery_date": "2026-07-19",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = items_api.get_supply_demand("ITEM-1", warehouse="Stores - A")

    assert result["ok"] is True
    assert result["data"]["incoming_qty"] == 6
    assert result["data"]["outgoing_qty"] == 5
    assert result["data"]["net_committed_qty"] == 1
    assert result["data"]["incoming"][0]["document"] == "PO-001"
    assert result["data"]["outgoing"][0]["document"] == "SO-001"


@patch("bude_api.api.items.frappe")
def test_get_quality_inspections_summarizes_standard_results(mock_frappe):
    mock_frappe.db.exists.return_value = True
    mock_frappe.get_list.return_value = [
        {
            "name": "QI-001",
            "report_date": "2026-07-18",
            "status": "Accepted",
            "inspection_type": "Incoming",
            "reference_type": "Purchase Receipt",
            "reference_name": "PREC-001",
            "batch_no": "BATCH-1",
            "sample_size": 5,
        },
        {
            "name": "QI-002",
            "status": "Rejected",
            "inspection_type": "Outgoing",
        },
    ]

    result = items_api.get_quality_inspections("ITEM-1")

    assert result["ok"] is True
    assert result["data"]["accepted"] == 1
    assert result["data"]["rejected"] == 1
    assert result["data"]["inspections"][0]["batch_no"] == "BATCH-1"


@patch("bude_api.api.items.frappe")
def test_get_reservations_summarizes_active_standard_entries(mock_frappe):
    mock_frappe.db.exists.return_value = True
    mock_frappe.get_list.return_value = [
        {
            "name": "SRE-001",
            "status": "Partially Delivered",
            "warehouse": "Stores - A",
            "stock_uom": "Nos",
            "voucher_type": "Sales Order",
            "voucher_no": "SO-001",
            "voucher_qty": 8,
            "reserved_qty": 8,
            "delivered_qty": 3,
            "reservation_based_on": "Qty",
            "project": "Rollout",
        },
        {
            "name": "SRE-002",
            "status": "Reserved",
            "warehouse": "Stores - A",
            "stock_uom": "Nos",
            "voucher_type": "Pick List",
            "voucher_no": "PL-001",
            "reserved_qty": 2,
            "delivered_qty": 0,
        },
    ]

    result = items_api.get_reservations("ITEM-1", warehouse="Stores - A")

    assert result["ok"] is True
    assert result["data"]["reserved_qty"] == 10
    assert result["data"]["remaining_qty"] == 7
    assert result["data"]["reservations"][0]["remaining_qty"] == 5
    filters = mock_frappe.get_list.call_args.kwargs["filters"]
    assert ["warehouse", "=", "Stores - A"] in filters
    assert ["docstatus", "=", 1] in filters


@patch("bude_api.api.items.frappe")
def test_get_alternatives_includes_two_way_reverse_and_availability(mock_frappe):
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        filters = kwargs.get("filters", [])
        if doctype == "Item Alternative":
            if ["item_code", "=", "ITEM-1"] in filters:
                return [
                    {
                        "name": "ALT-1",
                        "item_code": "ITEM-1",
                        "alternative_item_code": "ITEM-2",
                        "two_way": 0,
                    }
                ]
            return [
                {
                    "name": "ALT-2",
                    "item_code": "ITEM-3",
                    "alternative_item_code": "ITEM-1",
                    "two_way": 1,
                }
            ]
        if doctype == "Item":
            return [
                {
                    "name": "ITEM-2",
                    "item_code": "ITEM-2",
                    "item_name": "Alternative A",
                    "stock_uom": "Nos",
                },
                {
                    "name": "ITEM-3",
                    "item_code": "ITEM-3",
                    "item_name": "Alternative B",
                    "stock_uom": "Nos",
                },
            ]
        if doctype == "Bin":
            return [
                {
                    "item_code": "ITEM-2",
                    "warehouse": "Stores - A",
                    "actual_qty": 6,
                    "projected_qty": 5,
                },
                {
                    "item_code": "ITEM-3",
                    "warehouse": "Stores - A",
                    "actual_qty": 2,
                    "projected_qty": 3,
                },
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = items_api.get_alternatives("ITEM-1", warehouse="Stores - A")

    assert result["ok"] is True
    assert [row["item_code"] for row in result["data"]["alternatives"]] == [
        "ITEM-2",
        "ITEM-3",
    ]
    assert result["data"]["alternatives"][0]["actual_qty"] == 6
    assert result["data"]["alternatives"][1]["two_way"] is True
    bin_call = next(
        call
        for call in mock_frappe.get_list.call_args_list
        if call.args and call.args[0] == "Bin"
    )
    assert ["warehouse", "=", "Stores - A"] in bin_call.kwargs["filters"]


@patch("bude_api.api.items.frappe")
def test_get_batches_returns_fefo_availability_and_source(mock_frappe):
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Item":
            return [
                {
                    "name": "ITEM-1",
                    "item_code": "ITEM-1",
                    "has_batch_no": 1,
                }
            ]
        if doctype == "Batch":
            return [
                {
                    "name": "BATCH-SOON",
                    "manufacturing_date": "2026-06-01",
                    "expiry_date": "2026-08-01",
                    "batch_qty": 12,
                    "stock_uom": "Nos",
                    "supplier": "SUP-001",
                    "reference_doctype": "Purchase Receipt",
                    "reference_name": "PREC-001",
                },
                {
                    "name": "BATCH-LATER",
                    "expiry_date": "2027-01-01",
                    "batch_qty": 20,
                    "stock_uom": "Nos",
                },
            ]
        if doctype == "Stock Ledger Entry":
            return [
                {"batch_no": "BATCH-SOON", "qty": 5},
                {"batch_no": "BATCH-LATER", "qty": 8},
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = items_api.get_batches("ITEM-1", warehouse="Stores - A")

    assert result["ok"] is True
    assert result["data"]["total_qty"] == 13
    assert result["data"]["batches"][0]["batch_no"] == "BATCH-SOON"
    assert result["data"]["batches"][0]["quantity"] == 5
    assert result["data"]["batches"][0]["supplier"] == "SUP-001"
    ledger_call = next(
        call
        for call in mock_frappe.get_list.call_args_list
        if call.args and call.args[0] == "Stock Ledger Entry"
    )
    assert ledger_call.kwargs["group_by"] == "batch_no"
    assert ["warehouse", "=", "Stores - A"] in ledger_call.kwargs["filters"]


@patch("bude_api.api.items.frappe")
def test_get_batches_is_empty_for_non_batch_item(mock_frappe):
    mock_frappe.get_list.return_value = [
        {"name": "ITEM-1", "item_code": "ITEM-1", "has_batch_no": 0}
    ]

    result = items_api.get_batches("ITEM-1")

    assert result["ok"] is True
    assert result["data"]["batches"] == []
    assert result["data"]["total_qty"] == 0


@patch("bude_api.api.items.frappe")
def test_manufacturing_readiness_scales_bom_and_reports_shortages(mock_frappe):
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Item":
            return [{"name": "FG-1", "item_code": "FG-1"}]
        if doctype == "BOM":
            return [
                {
                    "name": "BOM-FG-1-001",
                    "quantity": 2,
                    "uom": "Nos",
                    "currency": "USD",
                    "total_cost": 20,
                    "inspection_required": 1,
                }
            ]
        if doctype == "BOM Item":
            return [
                {
                    "item_code": "RM-1",
                    "item_name": "Raw one",
                    "stock_qty": 4,
                    "stock_uom": "Nos",
                    "is_stock_item": 1,
                },
                {
                    "item_code": "RM-2",
                    "item_name": "Raw two",
                    "stock_qty": 2,
                    "stock_uom": "Nos",
                    "is_stock_item": 1,
                },
            ]
        if doctype == "Bin":
            return [
                {"item_code": "RM-1", "actual_qty": 7, "projected_qty": 8},
                {"item_code": "RM-2", "actual_qty": 5, "projected_qty": 5},
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = items_api.get_manufacturing_readiness(
        "FG-1", warehouse="Stores - A", quantity=4
    )

    assert result["ok"] is True
    data = result["data"]
    assert data["bom"] == "BOM-FG-1-001"
    assert data["total_cost"] == 40
    assert data["ready"] is False
    assert data["shortage_count"] == 1
    assert data["possible_qty"] == 3.5
    assert data["components"][0]["item_code"] == "RM-1"
    assert data["components"][0]["required_qty"] == 8
    assert data["components"][0]["shortage_qty"] == 1
    bin_call = next(
        call
        for call in mock_frappe.get_list.call_args_list
        if call.args and call.args[0] == "Bin"
    )
    assert ["warehouse", "=", "Stores - A"] in bin_call.kwargs["filters"]


@patch("bude_api.api.items.frappe")
def test_production_status_reports_active_work_order_progress(mock_frappe):
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Item":
            return [{"name": "FG-1", "item_code": "FG-1"}]
        if doctype == "Work Order":
            return [
                {
                    "name": "WO-001",
                    "status": "In Process",
                    "bom_no": "BOM-FG-1",
                    "stock_uom": "Nos",
                    "qty": 10,
                    "produced_qty": 4,
                    "material_transferred_for_manufacturing": 8,
                    "planned_end_date": "2020-01-01 17:00:00",
                    "wip_warehouse": "WIP - A",
                    "fg_warehouse": "Finished - A",
                    "sales_order": "SO-001",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = items_api.get_production_status("FG-1")

    assert result["ok"] is True
    assert result["data"]["planned_qty"] == 10
    assert result["data"]["produced_qty"] == 4
    assert result["data"]["remaining_qty"] == 6
    assert result["data"]["overdue_count"] == 1
    assert result["data"]["orders"][0]["progress"] == 40
    assert result["data"]["orders"][0]["overdue"] is True
    work_order_call = next(
        call
        for call in mock_frappe.get_list.call_args_list
        if call.args and call.args[0] == "Work Order"
    )
    assert ["docstatus", "=", 1] in work_order_call.kwargs["filters"]


@patch("bude_api.api.items.frappe")
def test_production_status_includes_optional_operation_progress(mock_frappe):
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Item":
            return [{"name": "FG-1", "item_code": "FG-1"}]
        if doctype == "Work Order":
            return [
                {
                    "name": "WO-001",
                    "status": "In Process",
                    "stock_uom": "Nos",
                    "qty": 10,
                    "produced_qty": 4,
                }
            ]
        if doctype == "Work Order Operation":
            return [
                {
                    "parent": "WO-001",
                    "operation": "Assembly",
                    "status": "Work in Progress",
                    "workstation": "Assembly Station",
                    "completed_qty": 4,
                    "pending_qty": 6,
                    "planned_end_time": "2020-01-01 17:00:00",
                    "time_in_mins": 60,
                    "actual_operation_time": 30,
                    "quality_inspection_required": 1,
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = items_api.get_production_status("FG-1")

    assert result["ok"] is True
    order = result["data"]["orders"][0]
    assert order["completed_operations"] == 0
    assert order["overdue_operations"] == 1
    assert order["operations"][0]["operation"] == "Assembly"
    assert order["operations"][0]["progress"] == 40
    assert order["operations"][0]["quality_inspection_required"] is True


@patch("bude_api.api.items.frappe")
def test_production_status_includes_job_card_execution_summary(mock_frappe):
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Item":
            return [{"name": "FG-1", "item_code": "FG-1"}]
        if doctype == "Work Order":
            return [
                {
                    "name": "WO-001",
                    "status": "In Process",
                    "stock_uom": "Nos",
                    "qty": 10,
                    "produced_qty": 4,
                }
            ]
        if doctype == "Job Card":
            return [
                {
                    "name": "JOB-001",
                    "work_order": "WO-001",
                    "status": "Work In Progress",
                    "operation": "Assembly",
                    "workstation": "Assembly Station",
                    "for_quantity": 10,
                    "total_completed_qty": 4,
                    "pending_qty": 6,
                    "expected_end_date": "2020-01-01 17:00:00",
                    "is_paused": 1,
                }
            ]
        if doctype == "Job Card Time Log":
            return [
                {
                    "parent": "JOB-001",
                    "from_time": "2026-07-18 09:00:00",
                    "to_time": "2026-07-18 09:30:00",
                    "time_in_mins": 30,
                    "completed_qty": 4,
                    "employee": "EMP-PRIVATE",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = items_api.get_production_status("FG-1")

    assert result["ok"] is True
    order = result["data"]["orders"][0]
    assert order["active_job_cards"] == 1
    assert order["overdue_job_cards"] == 1
    job_card = order["job_cards"][0]
    assert job_card["name"] == "JOB-001"
    assert job_card["completed_qty"] == 4
    assert job_card["time_log_count"] == 1
    assert job_card["last_activity"] == "2026-07-18 09:30:00"
    assert job_card["paused"] is True
    assert "employee" not in job_card
