from unittest.mock import patch

from bude_api.api import scan as scan_api


@patch("bude_api.api.scan.frappe")
def test_resolve_epc_uses_internal_reads_for_asset(mock_frappe):
    def get_list(doctype, **kwargs):
        if doctype == "Asset":
            return [{"name": "AST-001", "asset_name": "Tablet", "bude_epc": "EPC-1"}]
        return []

    mock_frappe.get_all.side_effect = get_list

    result = scan_api.resolve_epc("EPC-1")

    assert result["ok"] is True
    assert result["data"]["match_type"] == "asset"
    assert result["data"]["asset"]["name"] == "AST-001"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.scan.frappe")
def test_resolve_epc_uses_internal_reads_for_barcode(mock_frappe):
    def get_list(doctype, **kwargs):
        if doctype == "Item Barcode":
            return [{"parent": "ITEM-1"}]
        if doctype == "Item":
            filters = kwargs.get("filters") or []
            if ["item_code", "=", "ITEM-1"] in filters:
                return [{"name": "ITEM-1", "item_code": "ITEM-1"}]
        return []

    mock_frappe.get_all.side_effect = get_list

    result = scan_api.resolve_epc("BAR-1")

    assert result["ok"] is True
    assert result["data"]["match_type"] == "item"
    assert result["data"]["item"]["item_code"] == "ITEM-1"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.scan.frappe")
def test_resolve_epc_returns_unregistered_when_no_permission_visible_match(mock_frappe):
    mock_frappe.get_all.return_value = []

    result = scan_api.resolve_epc("UNKNOWN")

    assert result["ok"] is True
    assert result["data"]["match_type"] is None
    mock_frappe.get_list.assert_not_called()
