from unittest.mock import patch

from bude_api.api import alerts as alerts_api


def _alert(ref_name: str) -> dict:
    return {
        "category": "low_stock",
        "severity": "medium",
        "title": ref_name,
        "subtitle": "",
        "ref_doctype": "Item",
        "ref_name": ref_name,
    }


def _grant_stock_role(mock_frappe):
    mock_frappe.session.user = "warehouse.user@example.com"
    mock_frappe.get_roles.return_value = ["Stock User"]


@patch("bude_api.api.alerts.frappe")
def test_list_alerts_requires_stock_role(mock_frappe):
    mock_frappe.session.user = "sales.user@example.com"
    mock_frappe.get_roles.return_value = ["Sales User"]

    result = alerts_api.list_alerts()

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"


@patch("bude_api.api.alerts.frappe")
def test_list_alerts_returns_auth_expired_for_guest(mock_frappe):
    mock_frappe.session.user = "Guest"

    result = alerts_api.list_alerts()

    assert result["ok"] is False
    assert result["code"] == "AUTH_EXPIRED"
    mock_frappe.get_roles.assert_not_called()


@patch("bude_api.api.alerts._stock_alerts")
@patch("bude_api.api.alerts._assets_in_maintenance")
@patch("bude_api.api.alerts._maintenance_due")
@patch("bude_api.api.alerts.frappe")
def test_list_alerts_paginates_with_cap_metadata(
    mock_frappe,
    mock_maintenance_due,
    mock_assets_in_maintenance,
    mock_stock_alerts,
):
    _grant_stock_role(mock_frappe)
    mock_maintenance_due.return_value = [_alert("A"), _alert("B")]
    mock_assets_in_maintenance.return_value = [_alert("C")]
    mock_stock_alerts.return_value = [_alert("D")]

    result = alerts_api.list_alerts(limit=2, offset=1)

    assert result["ok"] is True
    assert result["data"]["limit"] == 2
    assert result["data"]["offset"] == 1
    assert result["data"]["total"] == 4
    assert [row["ref_name"] for row in result["data"]["alerts"]] == ["B", "C"]


@patch("bude_api.api.alerts.frappe")
def test_list_alerts_rejects_over_cap_limit(mock_frappe):
    _grant_stock_role(mock_frappe)

    result = alerts_api.list_alerts(limit=501)

    assert result["ok"] is False
    assert result["code"] == "PAGINATION_LIMIT_EXCEEDED"


@patch("bude_api.api.alerts.frappe")
def test_list_alerts_rejects_negative_offset(mock_frappe):
    _grant_stock_role(mock_frappe)

    result = alerts_api.list_alerts(offset=-1)

    assert result["ok"] is False
    assert result["code"] == "PAGINATION_INVALID"


@patch("bude_api.api.alerts.frappe")
def test_low_stock_uses_reorder_level_and_suggested_qty(mock_frappe):
    _grant_stock_role(mock_frappe)

    def get_list(doctype, **kwargs):
        if doctype == "Item Reorder":
            return [
                {
                    "parent": "ITEM-LOW",
                    "warehouse": "Stores - A",
                    "warehouse_reorder_level": 10,
                    "warehouse_reorder_qty": 25,
                },
                {
                    "parent": "ITEM-OK",
                    "warehouse": "Stores - A",
                    "warehouse_reorder_level": 10,
                    "warehouse_reorder_qty": 20,
                },
            ]
        if doctype == "Bin":
            return [
                {
                    "item_code": "ITEM-LOW",
                    "warehouse": "Stores - A",
                    "actual_qty": 4,
                    "projected_qty": 4,
                },
                {
                    "item_code": "ITEM-OK",
                    "warehouse": "Stores - A",
                    "actual_qty": 11,
                    "projected_qty": 11,
                },
            ]
        return []

    mock_frappe.get_all.side_effect = get_list

    result = alerts_api.low_stock(limit=10)

    assert result["ok"] is True
    assert result["data"]["total"] == 1
    assert result["data"]["items"][0]["item_code"] == "ITEM-LOW"
    assert result["data"]["items"][0]["suggested_qty"] == 25


@patch("bude_api.api.alerts.frappe")
def test_low_stock_scopes_to_warehouse_and_paginates(mock_frappe):
    _grant_stock_role(mock_frappe)

    def get_list(doctype, **kwargs):
        if doctype == "Item Reorder":
            assert kwargs["filters"] == [["warehouse", "=", "Stores - A"]]
            return [
                {
                    "parent": "ITEM-A",
                    "warehouse": "Stores - A",
                    "warehouse_reorder_level": 10,
                    "warehouse_reorder_qty": 0,
                },
                {
                    "parent": "ITEM-B",
                    "warehouse": "Stores - A",
                    "warehouse_reorder_level": 10,
                    "warehouse_reorder_qty": 0,
                },
            ]
        if doctype == "Bin":
            return [
                {
                    "item_code": "ITEM-A",
                    "warehouse": "Stores - A",
                    "actual_qty": 3,
                    "projected_qty": 3,
                },
                {
                    "item_code": "ITEM-B",
                    "warehouse": "Stores - A",
                    "actual_qty": 2,
                    "projected_qty": 2,
                },
            ]
        return []

    mock_frappe.get_all.side_effect = get_list

    result = alerts_api.low_stock(warehouse="Stores - A", limit=1, offset=1)

    assert result["ok"] is True
    assert result["data"]["limit"] == 1
    assert result["data"]["offset"] == 1
    assert result["data"]["total"] == 2
    assert result["data"]["items"][0]["item_code"] == "ITEM-A"
    assert result["data"]["items"][0]["suggested_qty"] == 7


@patch("bude_api.api.alerts.frappe")
def test_low_stock_rejects_over_cap_limit(mock_frappe):
    _grant_stock_role(mock_frappe)

    result = alerts_api.low_stock(limit=201)

    assert result["ok"] is False
    assert result["code"] == "PAGINATION_LIMIT_EXCEEDED"


@patch("bude_api.api.alerts.frappe")
def test_alerts_summary_uses_short_cache(mock_frappe):
    _grant_stock_role(mock_frappe)
    cache = mock_frappe.cache.return_value
    cache.get_value.return_value = None
    mock_frappe.get_all.side_effect = lambda doctype, **kwargs: (
        [
            {
                "parent": "ITEM-LOW",
                "warehouse": "Stores - A",
                "warehouse_reorder_level": 5,
                "warehouse_reorder_qty": 10,
            }
        ]
        if doctype == "Item Reorder"
        else [
            {
                "item_code": "ITEM-LOW",
                "warehouse": "Stores - A",
                "actual_qty": 0,
                "projected_qty": 0,
            }
        ]
    )

    result = alerts_api.summary()

    assert result["ok"] is True
    assert result["data"] == {"low_stock_count": 1}
    cache.set_value.assert_called_once_with(
        "bude_api:alerts:summary:*",
        {"low_stock_count": 1},
        expires_in_sec=60,
    )
