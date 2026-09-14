from unittest.mock import MagicMock, patch

from bude_api.api import warehouse_tasks as tasks_api


class _FakePermissionError(Exception):
    pass


class _FakeValidationError(Exception):
    pass


def _wire_exceptions(mock_frappe):
    mock_frappe.PermissionError = _FakePermissionError
    mock_frappe.ValidationError = _FakeValidationError


def _get_list_side_effect():
    def get_list(doctype, **kwargs):
        if doctype == "ToDo":
            return [
                {
                    "name": "TODO-SO",
                    "allocated_to": "picker@example.com",
                    "reference_type": "Sales Order",
                    "reference_name": "SO-001",
                    "description": "Pick today",
                    "priority": "High",
                    "date": "2026-07-02",
                },
                {
                    "name": "TODO-PO",
                    "allocated_to": "receiver@example.com",
                    "reference_type": "Purchase Order",
                    "reference_name": "PO-001",
                    "description": "Receive",
                    "priority": "Medium",
                    "date": "2026-07-03",
                },
                {
                    "name": "TODO-IGNORED",
                    "allocated_to": "receiver@example.com",
                    "reference_type": "Issue",
                    "reference_name": "ISS-001",
                    "description": "Unsupported",
                    "priority": "High",
                    "date": "2026-07-01",
                },
            ]
        if doctype == "Purchase Order":
            return [
                {
                    "name": "PO-001",
                    "supplier": "Acme Supplies",
                    "transaction_date": "2026-07-01",
                    "schedule_date": "2026-07-03",
                    "status": "To Receive",
                    "company": "Company A",
                }
            ]
        if doctype == "Purchase Order Item":
            return [{"parent": "PO-001"}, {"parent": "PO-001"}]
        if doctype == "Sales Order":
            return [
                {
                    "name": "SO-001",
                    "customer": "Acme Customer",
                    "transaction_date": "2026-07-01",
                    "delivery_date": "2026-07-02",
                    "status": "To Deliver",
                    "company": "Company A",
                }
            ]
        if doctype == "Sales Order Item":
            return [
                {"parent": "SO-001", "qty": 5, "delivered_qty": 2},
                {"parent": "SO-001", "qty": 1, "delivered_qty": 1},
            ]
        if doctype == "Asset":
            return [{"name": "AST-001"}]
        if doctype == "Asset Maintenance Log":
            return [
                {
                    "name": "AML-001",
                    "asset_name": "AST-001",
                    "item_code": "ITEM-A",
                    "task": "Calibrate",
                    "due_date": "2026-07-04",
                    "maintenance_status": "Planned",
                }
            ]
        return []

    return get_list


@patch("bude_api.api.warehouse_tasks.frappe")
def test_list_open_returns_normalized_tasks_and_sorts_by_priority(mock_frappe):
    mock_frappe.get_list.side_effect = _get_list_side_effect()
    mock_frappe.get_all.side_effect = _get_list_side_effect()

    result = tasks_api.list_open(company="Company A")

    assert result["ok"] is True
    tasks = result["data"]
    assert [task["kind"] for task in tasks] == [
        "fulfillSalesOrder",
        "receivePurchaseOrder",
        "assetMaintenance",
    ]
    sales = tasks[0]
    assert sales["id"] == "TODO-SO"
    assert sales["title"] == "Fulfill SO-001"
    assert sales["assigned_to"] == "picker@example.com"
    assert sales["priority"] == "High"
    assert sales["item_count"] == 1
    assert sales["pending_qty"] == 3.0

    receipt = tasks[1]
    assert receipt["todo_name"] == "TODO-PO"
    assert receipt["item_count"] == 2
    assert receipt["source_doctype"] == "Purchase Order"

    asset = tasks[2]
    assert asset["source_name"] == "AML-001"
    assert asset["asset_name"] == "AST-001"
    assert asset["company"] == "Company A"


@patch("bude_api.api.warehouse_tasks.frappe")
def test_list_open_uses_permission_aware_get_list_and_company_filter(mock_frappe):
    mock_frappe.get_list.side_effect = _get_list_side_effect()
    mock_frappe.get_all.side_effect = _get_list_side_effect()

    tasks_api.list_open(company="Company A", limit=25)

    doctypes = [call.args[0] for call in mock_frappe.get_list.call_args_list]
    assert "ToDo" in doctypes
    assert "Purchase Order" in doctypes
    assert "Sales Order" in doctypes
    child_doctypes = [call.args[0] for call in mock_frappe.get_all.call_args_list]
    assert "Purchase Order Item" in child_doctypes
    assert "Sales Order Item" in child_doctypes
    purchase_call = [
        call for call in mock_frappe.get_list.call_args_list if call.args[0] == "Purchase Order"
    ][0]
    assert ["company", "=", "Company A"] in purchase_call.kwargs["filters"]
    assert purchase_call.kwargs["limit_page_length"] == 500


@patch("bude_api.api.warehouse_tasks.frappe")
def test_list_open_surfaces_cycle_count_todos(mock_frappe):
    def get_list(doctype, **kwargs):
        if doctype == "ToDo":
            return [
                {
                    "name": "TODO-COUNT",
                    "allocated_to": "counter@example.com",
                    "reference_type": "Item",
                    "reference_name": "ITEM-001",
                    "description": (
                        "Cycle count warehouse: Stores - A\nABC class: A\nVelocity: 20"
                    ),
                    "priority": "High",
                    "date": "2026-07-06",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = tasks_api.list_open()

    assert result["ok"] is True
    assert result["data"] == [
        {
            "id": "TODO-COUNT",
            "kind": "cycleCount",
            "title": "Count ITEM-001",
            "subtitle": "Stores - A",
            "priority": "High",
            "due_date": "2026-07-06",
            "assigned_to": "counter@example.com",
            "company": None,
            "source_doctype": "Item",
            "source_name": "ITEM-001",
            "todo_name": "TODO-COUNT",
            "item_count": 1,
            "pending_qty": 0.0,
            "asset_name": None,
            "abc_class": "A",
            "warehouse": "Stores - A",
        }
    ]


@patch("bude_api.api.warehouse_tasks.frappe")
def test_list_open_rejects_bad_limit(mock_frappe):
    result = tasks_api.list_open(limit="bad")
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_LIMIT"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.warehouse_tasks.frappe")
def test_list_open_permission_error_returns_clean_envelope(mock_frappe):
    _wire_exceptions(mock_frappe)
    mock_frappe.get_list.side_effect = _FakePermissionError("no read")

    result = tasks_api.list_open()

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"


@patch("bude_api.api.warehouse_tasks.frappe")
def test_complete_closes_todo_with_permissions(mock_frappe):
    _wire_exceptions(mock_frappe)
    mock_frappe.get_list.return_value = [{"name": "TODO-001"}]
    doc = MagicMock()
    doc.get.return_value = "Existing note"
    mock_frappe.get_doc.return_value = doc

    result = tasks_api.complete(
        "TODO-001",
        result_doctype="Purchase Receipt",
        result_name="PREC-001",
    )

    assert result["ok"] is True
    assert doc.status == "Closed"
    assert "Purchase Receipt PREC-001" in doc.description
    doc.save.assert_called_once_with(ignore_permissions=False)


@patch("bude_api.api.warehouse_tasks.frappe")
def test_complete_read_permission_error_returns_clean_envelope(mock_frappe):
    _wire_exceptions(mock_frappe)
    mock_frappe.get_list.side_effect = _FakePermissionError("no read")

    result = tasks_api.complete("TODO-001")

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.warehouse_tasks.frappe")
def test_complete_permission_error_returns_clean_envelope(mock_frappe):
    _wire_exceptions(mock_frappe)
    mock_frappe.get_list.return_value = [{"name": "TODO-001"}]
    doc = MagicMock()
    doc.get.return_value = ""
    doc.save.side_effect = _FakePermissionError("no write")
    mock_frappe.get_doc.return_value = doc

    result = tasks_api.complete("TODO-001")

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.db.rollback.assert_called_once()
