from unittest.mock import MagicMock, patch

from bude_api.api import counts as counts_api


class _FakePermissionError(Exception):
    pass


class _FakeValidationError(Exception):
    pass


def _grant_stock_role(mock_frappe):
    mock_frappe.session.user = "warehouse.user@example.com"
    mock_frappe.get_roles.return_value = ["Stock Manager"]
    mock_frappe.PermissionError = _FakePermissionError
    mock_frappe.ValidationError = _FakeValidationError
    mock_frappe.utils.nowdate.return_value = "2026-07-06"
    mock_frappe.utils.add_days.side_effect = lambda date, days: "2026-04-07"


@patch("bude_api.api.counts.frappe")
def test_generate_schedule_requires_stock_role(mock_frappe):
    mock_frappe.session.user = "sales.user@example.com"
    mock_frappe.get_roles.return_value = ["Sales User"]

    result = counts_api.generate_schedule(warehouse="Stores - A")

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.counts.frappe")
def test_generate_schedule_classifies_velocity_and_creates_todos(mock_frappe):
    _grant_stock_role(mock_frappe)

    def get_list(doctype, **kwargs):
        if doctype == "Stock Ledger Entry":
            return [
                {"item_code": "FAST", "actual_qty": -80},
                {"item_code": "MED", "actual_qty": -15},
                {"item_code": "SLOW", "actual_qty": -5},
            ]
        if doctype == "ToDo":
            return []
        return []

    mock_frappe.get_list.side_effect = get_list
    docs = []

    def get_doc(payload):
        doc = MagicMock()
        doc.name = f"TODO-{payload['reference_name']}"
        doc.payload = payload
        docs.append(doc)
        return doc

    mock_frappe.get_doc.side_effect = get_doc

    result = counts_api.generate_schedule(
        warehouse="Stores - A",
        days=90,
        item_limit=10,
        assigned_to="counter@example.com",
    )

    assert result["ok"] is True
    assert [row["abc_class"] for row in result["data"]["created"]] == ["A", "B", "C"]
    assert [doc.payload["reference_name"] for doc in docs] == ["FAST", "MED", "SLOW"]
    assert docs[0].payload["priority"] == "High"
    assert docs[0].payload["allocated_to"] == "counter@example.com"
    assert "Cycle count warehouse: Stores - A" in docs[0].payload["description"]
    assert "Frequency days: 7" in docs[0].payload["description"]
    for doc in docs:
        doc.insert.assert_called_once_with(ignore_permissions=False)


@patch("bude_api.api.counts.frappe")
def test_generate_schedule_is_idempotent_for_open_cycle_todos(mock_frappe):
    _grant_stock_role(mock_frappe)

    def get_list(doctype, **kwargs):
        if doctype == "Stock Ledger Entry":
            return [{"item_code": "FAST", "actual_qty": -20}]
        if doctype == "ToDo":
            return [
                {
                    "name": "TODO-EXISTING",
                    "reference_name": "FAST",
                    "description": "Cycle count warehouse: Stores - A\nABC class: A",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = counts_api.generate_schedule(warehouse="Stores - A")

    assert result["ok"] is True
    assert result["data"]["created"] == []
    assert result["data"]["skipped"] == [
        {"item_code": "FAST", "todo_name": "TODO-EXISTING"}
    ]
    mock_frappe.get_doc.assert_not_called()


def test_generate_schedule_requires_warehouse():
    result = counts_api.generate_schedule(warehouse="  ")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"
