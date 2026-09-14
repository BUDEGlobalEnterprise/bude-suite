from unittest.mock import patch

from bude_api.api import items as items_api


@patch("bude_api.api.items.frappe")
def test_get_ledger_returns_entries(mock_frappe):
    mock_frappe.get_list.return_value = [
        {
            "posting_date": "2024-01-15",
            "posting_time": "10:30:00",
            "voucher_type": "Stock Entry",
            "voucher_no": "STE-00001",
            "warehouse": "Stores - X",
            "actual_qty": -5.0,
            "qty_after_transaction": 45.0,
            "valuation_rate": 100.0,
            "stock_value_difference": -500.0,
        },
        {
            "posting_date": "2024-01-10",
            "posting_time": "09:00:00",
            "voucher_type": "Purchase Receipt",
            "voucher_no": "PREC-00001",
            "warehouse": "Stores - X",
            "actual_qty": 50.0,
            "qty_after_transaction": 50.0,
            "valuation_rate": 100.0,
            "stock_value_difference": 5000.0,
        },
    ]
    result = items_api.get_ledger("ITEM-1")
    assert result["ok"] is True
    assert len(result["data"]) == 2
    assert result["data"][0]["voucher_type"] == "Stock Entry"
    assert result["data"][1]["voucher_no"] == "PREC-00001"


def test_get_ledger_requires_item_code():
    result = items_api.get_ledger("   ")
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


@patch("bude_api.api.items.frappe")
def test_get_ledger_filters_by_warehouse_when_given(mock_frappe):
    mock_frappe.get_list.return_value = []
    items_api.get_ledger("ITEM-1", warehouse="Stores - X")
    _, kwargs = mock_frappe.get_list.call_args
    filters = kwargs["filters"]
    assert ["item_code", "=", "ITEM-1"] in filters
    assert ["warehouse", "=", "Stores - X"] in filters
    assert ["is_cancelled", "=", 0] in filters


@patch("bude_api.api.items.frappe")
def test_get_ledger_omits_warehouse_filter_when_not_given(mock_frappe):
    mock_frappe.get_list.return_value = []
    items_api.get_ledger("ITEM-1")
    _, kwargs = mock_frappe.get_list.call_args
    filters = kwargs["filters"]
    assert ["item_code", "=", "ITEM-1"] in filters
    assert ["is_cancelled", "=", 0] in filters
    warehouse_filters = [f for f in filters if f[0] == "warehouse"]
    assert warehouse_filters == []


@patch("bude_api.api.items.frappe")
def test_get_ledger_respects_limit_bounds(mock_frappe):
    mock_frappe.get_list.return_value = []

    items_api.get_ledger("ITEM-1", limit=999)
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["limit_page_length"] == 200

    items_api.get_ledger("ITEM-1", limit=0)
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["limit_page_length"] == 1
