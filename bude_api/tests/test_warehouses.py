from unittest.mock import patch

from bude_api.api import warehouses as warehouses_api


@patch("bude_api.api.warehouses.frappe")
def test_list_returns_warehouse_names(mock_frappe):
    mock_frappe.get_list.return_value = [
        {"name": "Stores - X"},
        {"name": "Finished Goods - X"},
    ]
    result = warehouses_api.list()
    assert result["ok"] is True
    assert result["data"] == ["Stores - X", "Finished Goods - X"]


@patch("bude_api.api.warehouses.frappe")
def test_list_returns_empty_when_no_warehouses(mock_frappe):
    mock_frappe.get_list.return_value = []
    result = warehouses_api.list()
    assert result["ok"] is True
    assert result["data"] == []


@patch("bude_api.api.warehouses.frappe")
def test_list_passes_disabled_filter(mock_frappe):
    mock_frappe.get_list.return_value = []
    warehouses_api.list()
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["filters"] == {"disabled": 0}


@patch("bude_api.api.warehouses.frappe")
def test_list_filters_by_company_when_given(mock_frappe):
    mock_frappe.get_list.return_value = [{"name": "Stores - A"}]
    result = warehouses_api.list(company="Company A")
    assert result["ok"] is True
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["filters"] == {"disabled": 0, "company": "Company A"}


@patch("bude_api.api.warehouses.frappe")
def test_list_respects_limit(mock_frappe):
    mock_frappe.get_list.return_value = []
    warehouses_api.list(limit=25)
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["limit_page_length"] == 25


@patch("bude_api.api.warehouses.frappe")
def test_list_respects_limit_bounds(mock_frappe):
    mock_frappe.get_list.return_value = []
    warehouses_api.list(limit=9999)
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["limit_page_length"] == 500

    warehouses_api.list(limit=0)
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["limit_page_length"] == 1


@patch("bude_api.api.warehouses.frappe")
def test_list_rejects_bad_limit(mock_frappe):
    result = warehouses_api.list(limit="bad")
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_LIMIT"


# ── get_stock ─────────────────────────────────────────────────────────────────

@patch("bude_api.api.warehouses.frappe")
def test_get_stock_returns_bin_rows(mock_frappe):
    mock_frappe.get_list.return_value = [
        {
            "item_code": "ITEM-A",
            "item_name": "Widget A",
            "actual_qty": 20.0,
            "reserved_qty": 2.0,
            "ordered_qty": 0.0,
            "projected_qty": 18.0,
            "stock_uom": "Nos",
        },
        {
            "item_code": "ITEM-B",
            "item_name": "Widget B",
            "actual_qty": 5.0,
            "reserved_qty": 0.0,
            "ordered_qty": 10.0,
            "projected_qty": 15.0,
            "stock_uom": "Nos",
        },
    ]
    result = warehouses_api.get_stock("Stores - X")
    assert result["ok"] is True
    assert len(result["data"]) == 2
    assert result["data"][0]["item_code"] == "ITEM-A"
    assert result["data"][1]["actual_qty"] == 5.0


def test_get_stock_requires_warehouse():
    result = warehouses_api.get_stock("   ")
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


@patch("bude_api.api.warehouses.frappe")
def test_get_stock_filters_by_warehouse(mock_frappe):
    mock_frappe.get_list.return_value = []
    warehouses_api.get_stock("Stores - X")
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["filters"] == [["warehouse", "=", "Stores - X"]]


@patch("bude_api.api.warehouses.frappe")
def test_get_stock_respects_limit_bounds(mock_frappe):
    mock_frappe.get_list.return_value = []

    warehouses_api.get_stock("Stores - X", limit=9999)
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["limit_page_length"] == 500

    warehouses_api.get_stock("Stores - X", limit=0)
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["limit_page_length"] == 1


def test_list_locations_requires_warehouse():
    result = warehouses_api.list_locations("   ")
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


@patch("bude_api.api.warehouses.frappe")
def test_list_locations_filters_by_parent_and_company(mock_frappe):
    mock_frappe.get_list.return_value = [
        {"name": "Rack A - A"},
        {"name": "Staging - A"},
    ]

    result = warehouses_api.list_locations(
        warehouse="Stores - A",
        company="Company A",
        limit=25,
    )

    assert result["ok"] is True
    assert result["data"] == ["Rack A - A", "Staging - A"]
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["filters"] == {
        "disabled": 0,
        "parent_warehouse": "Stores - A",
        "company": "Company A",
    }
    assert kwargs["limit_page_length"] == 25


@patch("bude_api.api.warehouses.frappe")
def test_list_locations_respects_limit_bounds(mock_frappe):
    mock_frappe.get_list.return_value = []

    warehouses_api.list_locations("Stores - X", limit=9999)
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["limit_page_length"] == 500

    warehouses_api.list_locations("Stores - X", limit=0)
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["limit_page_length"] == 1


@patch("bude_api.api.warehouses.frappe")
def test_list_locations_rejects_bad_limit(mock_frappe):
    result = warehouses_api.list_locations("Stores - X", limit="bad")
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_LIMIT"
