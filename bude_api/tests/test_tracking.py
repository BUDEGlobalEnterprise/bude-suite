from unittest.mock import MagicMock, patch

from bude_api.api import stock as stock_api
from bude_api.api import tracking as tracking_api


def _grant_stock_role(mock_frappe):
    mock_frappe.get_roles.return_value = ["Stock User"]
    mock_frappe.session.user = "warehouse.user@example.com"


def _warehouse_and_items(*, expired_batch=False):
    def get_list(doctype, **kwargs):
        filters = kwargs.get("filters") or []
        if doctype == "Warehouse":
            name = filters[0][2]
            return [{"name": name, "company": "Company A", "parent_warehouse": None}]
        if doctype == "Item":
            value = filters[0][2]
            codes = value if isinstance(value, list) else [value]
            return [
                {
                    "item_code": code,
                    "has_batch_no": 1,
                    "has_serial_no": 0,
                    "create_new_batch": 1,
                    "stock_uom": "Nos",
                }
                for code in codes
                if code == "BATCHED"
            ]
        if doctype == "Batch":
            batch_no = filters[0][2]
            if batch_no == "B-OLD":
                return [
                    {
                        "name": "B-OLD",
                        "batch_id": "B-OLD",
                        "item": "BATCHED",
                        "expiry_date": "2020-01-01" if expired_batch else "2030-01-01",
                        "disabled": 0,
                    }
                ]
            return []
        if doctype == "Serial No":
            return []
        return []

    return get_list


@patch("bude_api.api.tracking.frappe")
def test_batch_endpoint_filters_expired_batches(mock_frappe):
    mock_frappe.utils.nowdate.return_value = "2026-06-28"
    mock_frappe.get_list.return_value = [
        {
            "name": "B-OLD",
            "batch_id": "B-OLD",
            "item": "BATCHED",
            "expiry_date": "2020-01-01",
            "disabled": 0,
        },
        {
            "name": "B-FRESH",
            "batch_id": "B-FRESH",
            "item": "BATCHED",
            "expiry_date": "2030-01-01",
            "disabled": 0,
        },
    ]

    result = tracking_api.batches("BATCHED")

    assert result["ok"] is True
    assert [row["batch_no"] for row in result["data"]] == ["B-FRESH"]


@patch("bude_api.api.stock.frappe")
def test_receipt_creates_new_batch_and_maps_allocation(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = _warehouse_and_items()
    batch_doc = MagicMock()
    receipt_doc = MagicMock()
    receipt_doc.name = "STE-001"
    receipt_doc.docstatus = 1
    mock_frappe.get_doc.side_effect = [batch_doc, receipt_doc]

    result = stock_api.create_receipt(
        target_warehouse="Stores - A",
        items=[
            {
                "item_code": "BATCHED",
                "qty": 5,
                "allocations": [
                    {
                        "batch_no": "B-NEW",
                        "expiry_date": "2030-12-31",
                        "qty": 5,
                    }
                ],
            }
        ],
    )

    assert result["ok"] is True
    batch_payload = mock_frappe.get_doc.call_args_list[0][0][0]
    receipt_payload = mock_frappe.get_doc.call_args_list[1][0][0]
    assert batch_payload == {
        "doctype": "Batch",
        "batch_id": "B-NEW",
        "item": "BATCHED",
        "expiry_date": "2030-12-31",
    }
    assert receipt_payload["items"][0]["batch_no"] == "B-NEW"
    assert receipt_payload["items"][0]["qty"] == 5.0


@patch("bude_api.api.stock.frappe")
def test_transfer_rejects_expired_outbound_batch(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.utils.nowdate.return_value = "2026-06-28"
    mock_frappe.get_list.side_effect = _warehouse_and_items(expired_batch=True)

    result = stock_api.create_transfer(
        source_warehouse="Stores - A",
        target_warehouse="Finished - A",
        items=[
            {
                "item_code": "BATCHED",
                "qty": 1,
                "allocations": [{"batch_no": "B-OLD", "qty": 1}],
            }
        ],
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_EXPIRED_BATCH"


@patch("bude_api.api.stock.frappe")
def test_transfer_rejects_wrong_serial_count(mock_frappe):
    _grant_stock_role(mock_frappe)
    def get_list(doctype, **kwargs):
        filters = kwargs.get("filters") or []
        if doctype == "Warehouse":
            name = filters[0][2]
            return [{"name": name, "company": "Company A", "parent_warehouse": None}]
        if doctype == "Item":
            value = filters[0][2]
            codes = value if isinstance(value, list) else [value]
            return [
                {
                    "item_code": code,
                    "has_batch_no": 0,
                    "has_serial_no": 1,
                    "create_new_batch": 0,
                    "stock_uom": "Nos",
                }
                for code in codes
                if code == "SERIALIZED"
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = stock_api.create_transfer(
        source_warehouse="Stores - A",
        target_warehouse="Finished - A",
        items=[
            {
                "item_code": "SERIALIZED",
                "qty": 2,
                "allocations": [{"qty": 2, "serial_nos": ["SN-001"]}],
            }
        ],
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_SERIAL_COUNT_MISMATCH"
