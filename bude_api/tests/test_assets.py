from unittest.mock import MagicMock, patch

from bude_api.api import assets as assets_api


class _FakeValidationError(Exception):
    pass


class _FakePermissionError(Exception):
    pass


def _wire_exceptions(mock_frappe):
    mock_frappe.ValidationError = _FakeValidationError
    mock_frappe.PermissionError = _FakePermissionError


def _grant_stock_role(mock_frappe):
    mock_frappe.get_roles.return_value = ["Stock User"]
    mock_frappe.session.user = "warehouse.user@example.com"


# ---------------------------------------------------------------------------
# Permission guard — applies to all 4 write endpoints
# ---------------------------------------------------------------------------


@patch("bude_api.api.assets.frappe")
def test_asset_write_endpoints_require_stock_role(mock_frappe):
    _wire_exceptions(mock_frappe)
    mock_frappe.get_roles.return_value = ["Sales User"]
    mock_frappe.session.user = "sales.user@example.com"

    epc = assets_api.set_epc("Asset", "AST-001", "EPC-001")
    movement = assets_api.create_asset_movement(
        assets=["AST-001"], purpose="Transfer", target_location="Floor"
    )
    repair = assets_api.create_asset_repair(asset="AST-001")
    log = assets_api.complete_maintenance_log("LOG-001")

    assert epc["code"] == "PERMISSION_DENIED"
    assert movement["code"] == "PERMISSION_DENIED"
    assert repair["code"] == "PERMISSION_DENIED"
    assert log["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()
    mock_frappe.get_doc.assert_not_called()


# ---------------------------------------------------------------------------
# set_epc
# ---------------------------------------------------------------------------


@patch("bude_api.api.assets.frappe")
def test_set_epc_saves_with_permissions(mock_frappe):
    _wire_exceptions(mock_frappe)
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [{"name": "AST-001"}],
        [],
    ]
    doc = MagicMock()
    mock_frappe.get_doc.return_value = doc

    result = assets_api.set_epc("Asset", "AST-001", "EPC-001")

    assert result["ok"] is True
    mock_frappe.get_doc.assert_called_once_with("Asset", "AST-001")
    doc.set.assert_called_once_with("bude_epc", "EPC-001")
    doc.save.assert_called_once_with(ignore_permissions=False)
    mock_frappe.db.set_value.assert_not_called()


@patch("bude_api.api.assets.frappe")
def test_set_epc_permission_error_returns_clean_envelope(mock_frappe):
    _wire_exceptions(mock_frappe)
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [{"name": "AST-001"}],
        [],
    ]
    doc = MagicMock()
    doc.save.side_effect = _FakePermissionError("no write")
    mock_frappe.get_doc.return_value = doc

    result = assets_api.set_epc("Asset", "AST-001", "EPC-001")

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.db.rollback.assert_called_once()


@patch("bude_api.api.assets.frappe")
def test_set_epc_not_found(mock_frappe):
    _wire_exceptions(mock_frappe)
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.return_value = []

    result = assets_api.set_epc("Asset", "AST-999", "EPC-001")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_NOT_FOUND"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.assets.frappe")
def test_set_epc_taken_by_another_record(mock_frappe):
    _wire_exceptions(mock_frappe)
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [{"name": "AST-001"}],
        [{"name": "AST-002"}],
    ]

    result = assets_api.set_epc("Asset", "AST-001", "EPC-001")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_EPC_TAKEN"
    assert "AST-002" in result["message"]
    mock_frappe.get_doc.assert_not_called()


def test_set_epc_rejects_unknown_doctype():
    result = assets_api.set_epc("Warehouse", "WH-001", "EPC-001")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_DOCTYPE"


# ---------------------------------------------------------------------------
# create_asset_movement
# ---------------------------------------------------------------------------


@patch("bude_api.api.assets.frappe")
def test_create_asset_movement_inserts_with_permissions(mock_frappe):
    _wire_exceptions(mock_frappe)
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.return_value = [
        {
            "location": "Stores",
            "custodian": None,
            "company": "Bude",
        }
    ]
    mock_frappe.utils.now_datetime.return_value = "2026-06-26"
    doc = MagicMock()
    doc.name = "MOV-001"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = assets_api.create_asset_movement(
        assets=["AST-001"],
        purpose="Transfer",
        target_location="Floor",
    )

    assert result["ok"] is True
    doc.insert.assert_called_once_with(ignore_permissions=False)
    doc.submit.assert_called_once()


def test_create_asset_movement_rejects_bad_purpose():
    result = assets_api.create_asset_movement(
        assets=["AST-001"], purpose="Scrap", target_location="Floor"
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_PURPOSE"


def test_create_asset_movement_rejects_empty_assets():
    result = assets_api.create_asset_movement(
        assets=[], purpose="Transfer", target_location="Floor"
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


def test_create_asset_movement_requires_target_for_transfer():
    result = assets_api.create_asset_movement(assets=["AST-001"], purpose="Transfer")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


def test_create_asset_movement_requires_target_for_receipt():
    result = assets_api.create_asset_movement(assets=["AST-001"], purpose="Receipt")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


def test_create_asset_movement_issue_requires_employee_or_location():
    result = assets_api.create_asset_movement(assets=["AST-001"], purpose="Issue")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


@patch("bude_api.api.assets.frappe")
def test_create_asset_movement_issue_accepts_employee_only(mock_frappe):
    _wire_exceptions(mock_frappe)
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.return_value = [
        {
            "location": "Stores",
            "custodian": None,
            "company": "Bude",
        }
    ]
    mock_frappe.utils.now_datetime.return_value = "2026-06-26"
    doc = MagicMock()
    doc.name = "MOV-002"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = assets_api.create_asset_movement(
        assets=["AST-001"], purpose="Issue", to_employee="EMP-001"
    )

    assert result["ok"] is True


@patch("bude_api.api.assets.frappe")
def test_create_asset_movement_unknown_asset(mock_frappe):
    _wire_exceptions(mock_frappe)
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.return_value = []

    result = assets_api.create_asset_movement(
        assets=["AST-999"], purpose="Transfer", target_location="Floor"
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_NOT_FOUND"
    mock_frappe.get_doc.assert_not_called()


# ---------------------------------------------------------------------------
# create_asset_repair
# ---------------------------------------------------------------------------


@patch("bude_api.api.assets.frappe")
def test_create_asset_repair_inserts_with_permissions(mock_frappe):
    _wire_exceptions(mock_frappe)
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.return_value = [{"name": "AST-001"}]
    mock_frappe.utils.now_datetime.return_value = "2026-06-26"
    doc = MagicMock()
    doc.name = "REP-001"
    doc.docstatus = 0
    mock_frappe.get_doc.return_value = doc

    result = assets_api.create_asset_repair(
        asset="AST-001", description="Motor noise", repair_cost=150.0
    )

    assert result["ok"] is True
    doc.insert.assert_called_once_with(ignore_permissions=False)


@patch("bude_api.api.assets.frappe")
def test_create_asset_repair_validation_error_returns_clean_envelope(mock_frappe):
    _wire_exceptions(mock_frappe)
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.return_value = [{"name": "AST-001"}]
    mock_frappe.utils.now_datetime.return_value = "2026-06-26"
    doc = MagicMock()
    doc.insert.side_effect = _FakeValidationError("Bad repair")
    mock_frappe.get_doc.return_value = doc

    result = assets_api.create_asset_repair(asset="AST-001")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_ERPNEXT"
    mock_frappe.db.rollback.assert_called_once()


@patch("bude_api.api.assets.frappe")
def test_create_asset_repair_unknown_asset(mock_frappe):
    _wire_exceptions(mock_frappe)
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.return_value = []

    result = assets_api.create_asset_repair(asset="AST-999")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_NOT_FOUND"
    mock_frappe.get_doc.assert_not_called()


# ---------------------------------------------------------------------------
# list_maintenance_logs / complete_maintenance_log
# ---------------------------------------------------------------------------


@patch("bude_api.api.assets.frappe")
def test_list_maintenance_logs_filters_by_status_and_asset(mock_frappe):
    mock_frappe.get_all.return_value = [
        {
            "name": "LOG-001",
            "asset_name": "AST-001",
            "item_code": "ITEM-A",
            "task": "Inspect belts",
            "maintenance_status": "Planned",
            "due_date": None,
            "completion_date": None,
        }
    ]

    result = assets_api.list_maintenance_logs(asset="AST-001", status="Planned")

    assert result["ok"] is True
    assert result["data"][0]["due_date"] == ""
    filters = mock_frappe.get_all.call_args.kwargs["filters"]
    assert ["maintenance_status", "=", "Planned"] in filters
    assert ["asset_name", "=", "AST-001"] in filters


@patch("bude_api.api.assets.frappe")
def test_complete_maintenance_log_saves_with_permissions(mock_frappe):
    _wire_exceptions(mock_frappe)
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.return_value = [{"name": "LOG-001"}]
    mock_frappe.utils.nowdate.return_value = "2026-06-26"
    doc = MagicMock()
    doc.name = "LOG-001"
    mock_frappe.get_doc.return_value = doc

    result = assets_api.complete_maintenance_log("LOG-001")

    assert result["ok"] is True
    assert doc.maintenance_status == "Completed"
    assert doc.completion_date == "2026-06-26"
    doc.save.assert_called_once_with(ignore_permissions=False)


@patch("bude_api.api.assets.frappe")
def test_complete_maintenance_log_not_found(mock_frappe):
    _wire_exceptions(mock_frappe)
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.return_value = []

    result = assets_api.complete_maintenance_log("LOG-999")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_NOT_FOUND"
    mock_frappe.get_doc.assert_not_called()


# ---------------------------------------------------------------------------
# Reads — list_assets, get_asset, get_asset_movements, list_locations,
# list_asset_categories
# ---------------------------------------------------------------------------


@patch("bude_api.api.assets.frappe")
def test_list_assets_builds_filters_and_clamps_limit(mock_frappe):
    mock_frappe.get_all.return_value = [
        {
            "name": "AST-001",
            "asset_name": "Forklift 1",
            "item_code": "FORKLIFT",
            "asset_category": "Vehicles",
            "location": "Yard",
            "custodian": None,
            "status": "Submitted",
            "purchase_amount": 1000,
            "value_after_depreciation": 800,
            "bude_epc": None,
        }
    ]

    result = assets_api.list_assets(
        search="fork",
        location="Yard",
        status="Submitted",
        category="Vehicles",
        limit=9999,
    )

    assert result["ok"] is True
    assert result["data"][0]["gross_purchase_amount"] == 1000
    kwargs = mock_frappe.get_all.call_args.kwargs
    assert kwargs["limit_page_length"] == 200
    assert ["location", "=", "Yard"] in kwargs["filters"]
    assert ["status", "=", "Submitted"] in kwargs["filters"]
    assert ["asset_category", "=", "Vehicles"] in kwargs["filters"]
    assert kwargs["or_filters"] == [
        ["asset_name", "like", "%fork%"],
        ["name", "like", "%fork%"],
        ["item_code", "like", "%fork%"],
    ]


@patch("bude_api.api.assets.frappe")
def test_get_asset_returns_detail_with_custodian_and_schedule(mock_frappe):
    def get_list(doctype, **kwargs):
        if doctype == "Asset":
            return [{"name": "AST-001"}]
        if doctype == "Employee":
            return [{"employee_name": "Jane Doe"}]
        return []

    mock_frappe.get_all.side_effect = get_list
    doc = MagicMock()
    doc.name = "AST-001"
    doc.get.side_effect = lambda key, default=None: {
        "asset_name": "Forklift 1",
        "item_code": "FORKLIFT",
        "asset_category": "Vehicles",
        "company": "Bude",
        "status": "Submitted",
        "location": "Yard",
        "custodian": "EMP-001",
        "purchase_date": None,
        "available_for_use_date": None,
        "gross_purchase_amount": 1000,
        "value_after_depreciation": 800,
        "maintenance_required": True,
        "bude_epc": "EPC-001",
        "schedules": [
            MagicMock(
                get=lambda k, default=None: {
                    "schedule_date": "2026-01-01",
                    "depreciation_amount": 10,
                    "accumulated_depreciation_amount": 10,
                    "journal_entry": "JV-001",
                }.get(k, default)
            )
        ],
    }.get(key, default)
    mock_frappe.get_doc.return_value = doc

    result = assets_api.get_asset("AST-001")

    assert result["ok"] is True
    assert result["data"]["custodian_name"] == "Jane Doe"
    assert result["data"]["depreciation_schedule"] == [
        {
            "schedule_date": "2026-01-01",
            "depreciation_amount": 10,
            "accumulated_depreciation_amount": 10,
            "journal_entry": "JV-001",
        }
    ]


@patch("bude_api.api.assets.frappe")
def test_get_asset_not_found(mock_frappe):
    mock_frappe.get_all.return_value = []

    result = assets_api.get_asset("AST-999")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_NOT_FOUND"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.assets.frappe")
def test_get_asset_movements_decorates_rows_with_parent_meta(mock_frappe):
    def get_list(doctype, **kwargs):
        if doctype == "Asset Movement Item":
            return [
                {
                    "parent": "MOV-001",
                    "source_location": "Stores",
                    "target_location": "Floor",
                    "from_employee": None,
                    "to_employee": None,
                }
            ]
        if doctype == "Asset Movement":
            return [
                {
                    "name": "MOV-001",
                    "transaction_date": "2026-06-01",
                    "purpose": "Transfer",
                }
            ]
        return []

    mock_frappe.get_all.side_effect = get_list

    result = assets_api.get_asset_movements("AST-001")

    assert result["ok"] is True
    assert result["data"][0]["transaction_date"] == "2026-06-01"
    assert result["data"][0]["purpose"] == "Transfer"


@patch("bude_api.api.assets.frappe")
def test_list_locations_clamps_limit(mock_frappe):
    mock_frappe.get_all.return_value = []

    result = assets_api.list_locations(limit=9999)

    assert result["ok"] is True
    assert mock_frappe.get_all.call_args.kwargs["limit_page_length"] == 500


@patch("bude_api.api.assets.frappe")
def test_list_asset_categories_returns_name_list(mock_frappe):
    mock_frappe.get_all.return_value = [{"name": "Vehicles"}, {"name": "IT"}]

    result = assets_api.list_asset_categories()

    assert result["ok"] is True
    assert result["data"] == ["Vehicles", "IT"]
