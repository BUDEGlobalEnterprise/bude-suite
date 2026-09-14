from unittest.mock import MagicMock, patch

from bude_api.api import exceptions as exceptions_api


class _FakePermissionError(Exception):
    pass


class _FakeValidationError(Exception):
    pass


def _grant_stock_role(mock_frappe):
    mock_frappe.session.user = "stock@example.com"
    mock_frappe.get_roles.return_value = ["Stock User"]
    mock_frappe.PermissionError = _FakePermissionError
    mock_frappe.ValidationError = _FakeValidationError
    mock_frappe.utils.nowdate.return_value = "2026-07-07"


@patch("bude_api.api.exceptions.frappe")
def test_damage_exception_creates_material_transfer(mock_frappe):
    _grant_stock_role(mock_frappe)
    doc = MagicMock()
    doc.name = "STE-001"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = exceptions_api.report(
        exception_type="damage",
        item_code="ITEM-001",
        qty=2,
        warehouse="Stores - A",
        damage_warehouse="Quarantine - A",
        note="crushed carton",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "Stock Entry"
    assert payload["items"][0]["s_warehouse"] == "Stores - A"
    assert payload["items"][0]["t_warehouse"] == "Quarantine - A"
    assert "Exception: damage" in payload["remarks"]
    doc.insert.assert_called_once_with(ignore_permissions=False)
    doc.submit.assert_called_once()


@patch("bude_api.api.exceptions.frappe")
def test_shortage_exception_creates_reconciliation(mock_frappe):
    _grant_stock_role(mock_frappe)
    doc = MagicMock()
    doc.name = "SRECON-001"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = exceptions_api.report(
        exception_type="shortage",
        item_code="ITEM-001",
        counted_qty=0,
        warehouse="Stores - A",
        note="empty bin",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "Stock Reconciliation"
    assert payload["items"] == [
        {"item_code": "ITEM-001", "warehouse": "Stores - A", "qty": 0.0}
    ]
    assert "Exception: shortage" in payload["remarks"]


@patch("bude_api.api.exceptions.frappe")
def test_unknown_scan_exception_creates_todo(mock_frappe):
    _grant_stock_role(mock_frappe)
    doc = MagicMock()
    doc.name = "TODO-001"
    mock_frappe.get_doc.return_value = doc

    result = exceptions_api.report(
        exception_type="unknown_scan",
        barcode="890123",
        warehouse="Stores - A",
        allocated_to="owner@example.com",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "ToDo"
    assert payload["allocated_to"] == "owner@example.com"
    assert "Exception: unknown_scan" in payload["description"]
    assert "Barcode: 890123" in payload["description"]


@patch("bude_api.api.exceptions.frappe")
def test_blocked_stock_exception_creates_item_todo(mock_frappe):
    _grant_stock_role(mock_frappe)
    doc = MagicMock()
    doc.name = "TODO-002"
    mock_frappe.get_doc.return_value = doc

    result = exceptions_api.report(
        exception_type="blocked_stock",
        item_code="ITEM-001",
        warehouse="Stores - A",
        note="hold rack A",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["reference_type"] == "Item"
    assert payload["reference_name"] == "ITEM-001"
    assert "Exception: blocked_stock" in payload["description"]


@patch("bude_api.api.exceptions.frappe")
def test_list_open_returns_exception_todos(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.return_value = [
        {
            "name": "TODO-001",
            "description": "Exception: blocked_stock\nItem: ITEM-001",
            "reference_type": "Item",
            "reference_name": "ITEM-001",
            "allocated_to": "manager@example.com",
            "priority": "High",
            "date": "2026-07-07",
        }
    ]

    result = exceptions_api.list_open(limit=25, offset=50)

    assert result["ok"] is True
    assert result["data"]["total"] == 1
    assert result["data"]["offset"] == 50
    assert result["data"]["exceptions"][0]["reference_name"] == "ITEM-001"
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["limit_start"] == 50
    assert kwargs["limit_page_length"] == 25


@patch("bude_api.api.exceptions.frappe")
def test_report_requires_stock_role(mock_frappe):
    mock_frappe.session.user = "sales@example.com"
    mock_frappe.get_roles.return_value = ["Sales User"]

    result = exceptions_api.report(exception_type="unknown_scan", barcode="1")

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
