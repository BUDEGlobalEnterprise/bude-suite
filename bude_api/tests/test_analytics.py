from unittest.mock import patch

from bude_api.api import analytics as analytics_api


def _grant_stock_role(mock_frappe):
    mock_frappe.session.user = "manager@example.com"
    mock_frappe.get_roles.return_value = ["Stock Manager"]


def _wire_aging_rows(mock_frappe, *, bins, item_rows=None, ledger_rows=None):
    item_rows = item_rows or []
    ledger_rows = ledger_rows or []
    mock_frappe.utils.nowdate.return_value = "2026-06-15"

    def date_diff(today, previous):
        from datetime import date

        return (date.fromisoformat(str(today)) - date.fromisoformat(str(previous))).days

    mock_frappe.utils.date_diff.side_effect = date_diff

    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            filters = kwargs.get("filters") or []
            name = filters[0][2] if filters else None
            return [{"name": name}] if name == "Stores - X" else []
        if doctype == "Bin":
            return bins
        if doctype == "Item":
            return item_rows
        if doctype == "Stock Ledger Entry":
            return ledger_rows
        return []

    mock_frappe.get_list.side_effect = get_list


# ── get_stock_aging ────────────────────────────────────────────────────────────

@patch("bude_api.api.analytics.frappe")
def test_aging_returns_rows(mock_frappe):
    _wire_aging_rows(
        mock_frappe,
        bins=[
            {"item_code": "BOLT-M8", "actual_qty": 100.0},
            {"item_code": "NUT-M8", "actual_qty": 50.0},
        ],
        item_rows=[{"item_code": "BOLT-M8", "item_name": "Bolt M8"}],
        ledger_rows=[{"item_code": "BOLT-M8", "posting_date": "2026-05-01"}],
    )
    result = analytics_api.get_stock_aging("Stores - X")
    assert result["ok"] is True
    assert len(result["data"]) == 2
    assert result["data"][0]["item_code"] == "BOLT-M8"
    assert result["data"][0]["days_idle"] == 45
    mock_frappe.db.sql.assert_not_called()


def test_aging_requires_warehouse():
    result = analytics_api.get_stock_aging("   ")
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


@patch("bude_api.api.analytics.frappe")
def test_aging_unknown_warehouse_returns_error(mock_frappe):
    mock_frappe.get_list.return_value = []
    result = analytics_api.get_stock_aging("No-Such-WH")
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_UNKNOWN_WAREHOUSE"


@patch("bude_api.api.analytics.frappe")
def test_aging_respects_threshold_and_limit(mock_frappe):
    _wire_aging_rows(
        mock_frappe,
        bins=[
            {"item_code": f"ITEM-{index:03}", "actual_qty": 1}
            for index in range(600)
        ],
    )
    result = analytics_api.get_stock_aging("Stores - X", threshold_days=9999, limit=9999)
    assert result["ok"] is True
    assert len(result["data"]) == 500


@patch("bude_api.api.analytics.frappe")
def test_aging_date_converted_to_string(mock_frappe):
    from datetime import date
    _wire_aging_rows(
        mock_frappe,
        bins=[{"item_code": "ITEM-1", "actual_qty": 10.0}],
        item_rows=[{"item_code": "ITEM-1", "item_name": "Item 1"}],
        ledger_rows=[{"item_code": "ITEM-1", "posting_date": date(2026, 1, 15)}],
    )
    result = analytics_api.get_stock_aging("Stores - X")
    assert result["ok"] is True
    assert result["data"][0]["last_movement_date"] == "2026-01-15"


# ── get_reconciliation_history ─────────────────────────────────────────────────

@patch("bude_api.api.analytics.frappe")
def test_recon_history_returns_rows(mock_frappe):
    def get_list(doctype, **kwargs):
        if doctype == "Stock Reconciliation":
            return [
                {
                    "name": "SRECON-001",
                    "posting_date": "2026-05-10",
                    "set_warehouse": "Stores - X",
                },
            ]
        if doctype == "Stock Reconciliation Item":
            return [
                {
                    "item_code": "BOLT-M8",
                    "item_name": "Bolt M8",
                    "qty": 50.0,
                    "current_qty": 45.0,
                    "warehouse": "Stores - X",
                },
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = analytics_api.get_reconciliation_history()
    assert result["ok"] is True
    assert len(result["data"]) == 1
    row = result["data"][0]
    assert row["name"] == "SRECON-001"
    assert len(row["items"]) == 1
    assert row["items"][0]["variance"] == 5.0


@patch("bude_api.api.analytics.frappe")
def test_recon_history_filters_by_warehouse(mock_frappe):
    mock_frappe.get_list.return_value = []
    analytics_api.get_reconciliation_history(warehouse="Stores - X")
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["filters"]["set_warehouse"] == "Stores - X"


@patch("bude_api.api.analytics.frappe")
def test_recon_history_no_warehouse_filter_when_absent(mock_frappe):
    mock_frappe.get_list.return_value = []
    analytics_api.get_reconciliation_history()
    _, kwargs = mock_frappe.get_list.call_args
    assert "set_warehouse" not in kwargs["filters"]


@patch("bude_api.api.analytics.frappe")
def test_recon_history_respects_limit(mock_frappe):
    mock_frappe.get_list.return_value = []
    analytics_api.get_reconciliation_history(limit=9999)
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["limit_page_length"] == 200


# ── kpi_summary / movers ──────────────────────────────────────────────────────

@patch("bude_api.api.analytics.frappe")
def test_kpi_summary_uses_cache_and_rolls_up_standard_doctypes(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.utils.nowdate.return_value = "2026-07-07"
    mock_frappe.utils.add_days.return_value = "2026-04-08"
    cache = mock_frappe.cache.return_value
    cache.get_value.return_value = None

    def get_list(doctype, **kwargs):
        if doctype == "Bin":
            return [
                {"item_code": "FAST", "actual_qty": 10, "valuation_rate": 5},
                {"item_code": "DEAD", "actual_qty": 4, "valuation_rate": 8},
            ]
        if doctype == "Stock Ledger Entry":
            return [{"item_code": "FAST", "actual_qty": -20}]
        if doctype == "Sales Invoice Item":
            return [{"item_code": "FAST", "qty": 3, "warehouse": "Stores - A"}]
        if doctype == "Delivery Note":
            return [
                {"name": "DN-1", "remarks": ""},
                {"name": "DN-2", "remarks": "corrected pick"},
            ]
        if doctype == "Stock Reconciliation":
            return [
                {
                    "name": "SRECON-1",
                    "posting_date": "2026-06-01",
                    "set_warehouse": "Stores - A",
                }
            ]
        if doctype == "Stock Reconciliation Item":
            return [{"qty": 12, "current_qty": 10}]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = analytics_api.kpi_summary(warehouse="Stores - A", days=90)

    assert result["ok"] is True
    assert result["data"]["stock_value"] == 82
    assert result["data"]["turnover_qty"] == 20
    assert result["data"]["dead_stock_value"] == 32
    assert result["data"]["sales_velocity_qty"] == 3
    assert result["data"]["pick_accuracy"] == 0.5
    assert result["data"]["variance_trend"][0]["absolute_variance_qty"] == 2
    cache.set_value.assert_called_once()


@patch("bude_api.api.analytics.frappe")
def test_kpi_summary_returns_cached_value(mock_frappe):
    _grant_stock_role(mock_frappe)
    cache = mock_frappe.cache.return_value
    cache.get_value.return_value = {"stock_value": 10}

    result = analytics_api.kpi_summary()

    assert result["ok"] is True
    assert result["data"] == {"stock_value": 10}
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.analytics.frappe")
def test_movers_returns_explainable_reorder_quantities(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.utils.nowdate.return_value = "2026-07-07"
    mock_frappe.utils.add_days.return_value = "2026-06-07"

    def get_list(doctype, **kwargs):
        if doctype == "Stock Ledger Entry":
            return [
                {"item_code": "FAST", "actual_qty": -30},
                {"item_code": "SLOW", "actual_qty": -3},
            ]
        if doctype == "Bin":
            return [
                {"item_code": "FAST", "actual_qty": 2, "valuation_rate": 5},
                {"item_code": "SLOW", "actual_qty": 20, "valuation_rate": 2},
                {"item_code": "DEAD", "actual_qty": 8, "valuation_rate": 4},
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = analytics_api.movers(
        warehouse="Stores - A",
        days=30,
        lead_time_days=10,
        safety_stock_days=5,
    )

    assert result["ok"] is True
    assert result["data"]["fast"][0]["item_code"] == "FAST"
    assert result["data"]["fast"][0]["daily_velocity"] == 1
    assert result["data"]["fast"][0]["suggested_reorder_qty"] == 13
    assert (
        "1.0 per day x 15 days - 2.0 on hand" ==
        result["data"]["fast"][0]["explanation"]
    )
    assert result["data"]["dead"][0]["item_code"] == "DEAD"


@patch("bude_api.api.analytics.frappe")
def test_movers_requires_stock_role(mock_frappe):
    mock_frappe.session.user = "sales@example.com"
    mock_frappe.get_roles.return_value = ["Sales User"]

    result = analytics_api.movers()

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
