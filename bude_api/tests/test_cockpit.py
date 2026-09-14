from unittest.mock import patch

from bude_api.api import cockpit as cockpit_api


def _grant_stock_role(mock_frappe):
    mock_frappe.session.user = "warehouse.user@example.com"
    mock_frappe.get_roles.return_value = ["Stock User"]


@patch("bude_api.api.cockpit.frappe")
def test_today_requires_stock_role(mock_frappe):
    mock_frappe.session.user = "sales.user@example.com"
    mock_frappe.get_roles.return_value = ["Sales User"]

    result = cockpit_api.today()

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.cockpit.alerts_api._low_stock_rows")
@patch("bude_api.api.cockpit.frappe")
def test_today_returns_summary_shape_and_scoped_queries(mock_frappe, mock_low_stock):
    _grant_stock_role(mock_frappe)
    mock_frappe.utils.nowdate.return_value = "2026-07-06"
    mock_frappe.cache.return_value.get_value.return_value = None
    mock_low_stock.return_value = [{"item_code": "ITEM-LOW"}]

    def get_list(doctype, **kwargs):
        if doctype == "Purchase Order":
            return [{"name": "PO-1"}, {"name": "PO-2"}]
        if doctype == "Sales Order":
            return [{"name": "SO-1"}]
        if doctype == "Pick List":
            return [{"name": "PICK-1"}, {"name": "PICK-2"}, {"name": "PICK-3"}]
        if doctype == "ToDo":
            return [{"name": "TODO-1"}]
        if doctype == "Workflow Action":
            return [{"name": "WA-1"}, {"name": "WA-2"}]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = cockpit_api.today(company="Company A")

    assert result["ok"] is True
    assert result["data"] == {
        "date": "2026-07-06",
        "po_due_today": 2,
        "open_sales_orders": 1,
        "open_pick_lists": 3,
        "assigned_count_tasks": 1,
        "low_stock_count": 1,
        "pending_approvals": 2,
    }

    calls = {
        call.args[0]: call.kwargs["filters"]
        for call in mock_frappe.get_list.call_args_list
    }
    assert ["company", "=", "Company A"] in calls["Purchase Order"]
    assert ["company", "=", "Company A"] in calls["Sales Order"]
    assert ["company", "=", "Company A"] in calls["Pick List"]
    assert ["allocated_to", "=", "warehouse.user@example.com"] in calls["ToDo"]
    assert ["user", "=", "warehouse.user@example.com"] in calls["Workflow Action"]
    for call in mock_frappe.get_list.call_args_list:
        assert call.kwargs["limit_page_length"] == 1000


@patch("bude_api.api.cockpit.alerts_api._low_stock_rows")
@patch("bude_api.api.cockpit.frappe")
def test_today_uses_short_cache(mock_frappe, mock_low_stock):
    _grant_stock_role(mock_frappe)
    cached = {
        "date": "2026-07-06",
        "po_due_today": 1,
        "open_sales_orders": 2,
        "open_pick_lists": 3,
        "assigned_count_tasks": 4,
        "low_stock_count": 5,
        "pending_approvals": 6,
    }
    mock_frappe.cache.return_value.get_value.return_value = cached

    result = cockpit_api.today()

    assert result["ok"] is True
    assert result["data"] == cached
    mock_frappe.get_list.assert_not_called()
    mock_low_stock.assert_not_called()


@patch("bude_api.api.cockpit.alerts_api._low_stock_rows")
@patch("bude_api.api.cockpit.frappe")
def test_today_caches_computed_summary(mock_frappe, mock_low_stock):
    _grant_stock_role(mock_frappe)
    mock_frappe.utils.nowdate.return_value = "2026-07-06"
    cache = mock_frappe.cache.return_value
    cache.get_value.return_value = None
    mock_low_stock.return_value = []
    mock_frappe.get_list.return_value = []

    result = cockpit_api.today()

    assert result["ok"] is True
    cache.set_value.assert_called_once_with(
        "bude_api:cockpit:today:warehouse.user@example.com:*",
        result["data"],
        expires_in_sec=60,
    )
