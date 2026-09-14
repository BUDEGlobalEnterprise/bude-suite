from unittest.mock import patch

from bude_api.api import purchase_orders as po_api


@patch("bude_api.api.purchase_orders.frappe")
def test_list_open_returns_po_names(mock_frappe):
    mock_frappe.get_list.return_value = [
        {"name": "PUR-ORD-2026-00001"},
        {"name": "PUR-ORD-2026-00002"},
    ]
    result = po_api.list_open()
    assert result["ok"] is True
    assert result["data"] == ["PUR-ORD-2026-00001", "PUR-ORD-2026-00002"]


@patch("bude_api.api.purchase_orders.frappe")
def test_list_open_returns_empty_when_none(mock_frappe):
    mock_frappe.get_list.return_value = []
    result = po_api.list_open()
    assert result["ok"] is True
    assert result["data"] == []


@patch("bude_api.api.purchase_orders.frappe")
def test_list_open_filters_submitted_and_open_status(mock_frappe):
    mock_frappe.get_list.return_value = []
    po_api.list_open()
    _, kwargs = mock_frappe.get_list.call_args
    filters = kwargs["filters"]
    assert ["docstatus", "=", 1] in filters
    assert ["status", "not in", ["Closed", "Completed", "Cancelled"]] in filters


@patch("bude_api.api.purchase_orders.frappe")
def test_list_open_respects_limit(mock_frappe):
    mock_frappe.get_list.return_value = []
    po_api.list_open(limit=10)
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["limit_page_length"] == 10
