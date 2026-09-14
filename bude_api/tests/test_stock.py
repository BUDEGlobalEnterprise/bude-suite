from unittest.mock import MagicMock, patch

from bude_api.api import stock as stock_api


class _FakeValidationError(Exception):
    """Stand-in for frappe.ValidationError in unit tests (no Frappe installed)."""


class _FakePermissionError(Exception):
    """Stand-in for frappe.PermissionError in unit tests (no Frappe installed)."""


def _grant_stock_role(mock_frappe):
    mock_frappe.get_roles.return_value = ["Stock User"]
    mock_frappe.session.user = "warehouse.user@example.com"


def _get_list_with_companies(
    warehouse_companies: dict[str, str],
    items: set[str] | None = None,
    warehouse_parents: dict[str, str] | None = None,
):
    items = items or {"A"}
    warehouse_parents = warehouse_parents or {}

    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            filters = kwargs.get("filters", [])
            name = filters[0][2] if filters else None
            if name in warehouse_companies:
                return [
                    {
                        "name": name,
                        "company": warehouse_companies[name],
                        "parent_warehouse": warehouse_parents.get(name),
                    }
                ]
            return []
        if doctype == "Item":
            codes = kwargs.get("filters", [])[0][2]
            return [{"item_code": code} for code in codes if code in items]
        return []

    return get_list


def test_create_transfer_requires_source_warehouse():
    result = stock_api.create_transfer(
        items=[{"item_code": "A", "qty": 1}],
        source_warehouse="",
        target_warehouse="Stores - X",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


def test_create_transfer_requires_target_warehouse():
    result = stock_api.create_transfer(
        items=[{"item_code": "A", "qty": 1}],
        source_warehouse="Stores - X",
        target_warehouse="",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


def test_create_transfer_requires_items():
    result = stock_api.create_transfer(
        items=[],
        source_warehouse="A",
        target_warehouse="B",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


def test_create_transfer_rejects_non_positive_qty():
    result = stock_api.create_transfer(
        items=[{"item_code": "A", "qty": 0}],
        source_warehouse="A",
        target_warehouse="B",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_QTY"


def test_create_transfer_rejects_non_numeric_qty():
    result = stock_api.create_transfer(
        items=[{"item_code": "A", "qty": "five"}],
        source_warehouse="A",
        target_warehouse="B",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_QTY"


def test_create_transfer_rejects_same_source_and_target():
    result = stock_api.create_transfer(
        items=[{"item_code": "A", "qty": 1}],
        source_warehouse="Same",
        target_warehouse="Same",
    )
    # Note: same-warehouse check happens after frappe is required, so this
    # test only reaches it when frappe is mocked. Without frappe, we get
    # ENV_NO_FRAPPE first. Skip this specific message check in unit mode.
    assert result["ok"] is False


@patch("bude_api.api.stock.frappe")
def test_stock_write_endpoints_require_stock_role(mock_frappe):
    mock_frappe.get_roles.return_value = ["Sales User"]
    mock_frappe.session.user = "sales.user@example.com"

    transfer = stock_api.create_transfer(
        items=[{"item_code": "A", "qty": 1}],
        source_warehouse="Src - X",
        target_warehouse="Tgt - X",
    )
    receipt = stock_api.create_receipt(
        items=[{"item_code": "A", "qty": 1}],
        target_warehouse="Tgt - X",
    )
    reconciliation = stock_api.create_reconciliation(
        counts=[{"item_code": "A", "qty": 1}],
        warehouse="Stores - X",
    )

    assert transfer["code"] == "PERMISSION_DENIED"
    assert receipt["code"] == "PERMISSION_DENIED"
    assert reconciliation["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.stock.frappe")
def test_create_material_request_requires_stock_role(mock_frappe):
    mock_frappe.get_roles.return_value = ["Sales User"]
    mock_frappe.session.user = "sales.user@example.com"

    result = stock_api.create_material_request(
        items=[{"item_code": "A", "qty": 1, "warehouse": "Stores - X"}],
    )

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()
    mock_frappe.get_doc.assert_not_called()


def test_create_material_request_rejects_empty_items():
    result = stock_api.create_material_request(items=[])

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


def test_create_material_request_rejects_bad_qty():
    result = stock_api.create_material_request(items=[{"item_code": "A", "qty": 0}])

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_QTY"


@patch("bude_api.api.stock.frappe")
def test_create_material_request_inserts_draft_purchase_request(mock_frappe):
    _grant_stock_role(mock_frappe)

    def get_list(doctype, **kwargs):
        if doctype == "Item":
            return [{"item_code": "A"}]
        if doctype == "Warehouse":
            return [{"name": "Stores - X", "company": "Bude"}]
        return []

    mock_frappe.get_list.side_effect = get_list
    mock_frappe.utils.nowdate.return_value = "2026-07-06"
    doc = MagicMock()
    doc.name = "MAT-MR-2026-00001"
    doc.docstatus = 0
    mock_frappe.get_doc.return_value = doc

    result = stock_api.create_material_request(
        items=[{"item_code": "A", "qty": 3, "warehouse": "Stores - X"}],
        company="Bude",
    )

    assert result["ok"] is True
    assert result["data"] == {"name": "MAT-MR-2026-00001", "docstatus": 0}
    mock_frappe.get_doc.assert_called_once_with({
        "doctype": "Material Request",
        "material_request_type": "Purchase",
        "schedule_date": "2026-07-06",
        "items": [
            {"item_code": "A", "qty": 3.0, "warehouse": "Stores - X"},
        ],
        "company": "Bude",
    })
    doc.insert.assert_called_once_with(ignore_permissions=False)
    doc.submit.assert_not_called()


@patch("bude_api.api.stock.frappe")
def test_create_material_request_rejects_unknown_warehouse(mock_frappe):
    _grant_stock_role(mock_frappe)

    def get_list(doctype, **kwargs):
        if doctype == "Item":
            return [{"item_code": "A"}]
        if doctype == "Warehouse":
            return []
        return []

    mock_frappe.get_list.side_effect = get_list

    result = stock_api.create_material_request(
        items=[{"item_code": "A", "qty": 3, "warehouse": "Missing - X"}],
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_UNKNOWN_WAREHOUSE"


@patch("bude_api.api.stock.frappe")
def test_create_transfer_rejects_unknown_source_warehouse(mock_frappe):
    _grant_stock_role(mock_frappe)
    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            filters = kwargs.get("filters", [])
            name = filters[0][2] if filters else None
            return [{"name": name}] if name == "Target - X" else []
        return []

    mock_frappe.get_list.side_effect = get_list
    result = stock_api.create_transfer(
        items=[{"item_code": "A", "qty": 1}],
        source_warehouse="Bad - X",
        target_warehouse="Target - X",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_UNKNOWN_WAREHOUSE"


@patch("bude_api.api.stock.frappe")
def test_create_transfer_rejects_same_source_target_after_frappe(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.return_value = [{"name": "Same - X"}]
    result = stock_api.create_transfer(
        items=[{"item_code": "A", "qty": 1}],
        source_warehouse="Same - X",
        target_warehouse="Same - X",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_SAME_WAREHOUSE"


@patch("bude_api.api.stock.frappe")
def test_create_transfer_rejects_unknown_items(mock_frappe):
    _grant_stock_role(mock_frappe)
    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            return [{"name": "X"}]
        if doctype == "Item":
            return [{"item_code": "A"}]  # 'B' is missing
        return []

    mock_frappe.get_list.side_effect = get_list
    result = stock_api.create_transfer(
        items=[
            {"item_code": "A", "qty": 1},
            {"item_code": "B", "qty": 2},
        ],
        source_warehouse="Src - X",
        target_warehouse="Tgt - X",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_UNKNOWN_ITEM"
    assert "B" in result["message"]


@patch("bude_api.api.stock.frappe")
def test_create_transfer_submits_stock_entry_on_happy_path(mock_frappe):
    _grant_stock_role(mock_frappe)
    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            return [{"name": "X"}]
        if doctype == "Item":
            return [{"item_code": "A"}, {"item_code": "B"}]
        return []

    mock_frappe.get_list.side_effect = get_list
    doc = MagicMock()
    doc.name = "STE-2026-00001"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = stock_api.create_transfer(
        items=[
            {"item_code": "A", "qty": 2.5},
            {"item_code": "B", "qty": 1},
        ],
        source_warehouse="Src - X",
        target_warehouse="Tgt - X",
        posting_date="2026-06-03",
    )

    assert result["ok"] is True
    assert result["data"]["name"] == "STE-2026-00001"
    assert result["data"]["docstatus"] == 1

    # Verify the Stock Entry doc was assembled correctly.
    args, kwargs = mock_frappe.get_doc.call_args
    payload = args[0]
    assert payload["doctype"] == "Stock Entry"
    assert payload["stock_entry_type"] == "Material Transfer"
    assert payload["posting_date"] == "2026-06-03"
    assert len(payload["items"]) == 2
    assert payload["items"][0] == {
        "item_code": "A",
        "qty": 2.5,
        "s_warehouse": "Src - X",
        "t_warehouse": "Tgt - X",
    }
    doc.insert.assert_called_once()
    doc.submit.assert_called_once()
    assert "remarks" not in payload  # nothing flagged, nothing to note


def test_create_transfer_rejects_bad_exception_type():
    result = stock_api.create_transfer(
        items=[{"item_code": "A", "qty": 1, "exception_type": "lost"}],
        source_warehouse="Src - X",
        target_warehouse="Tgt - X",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_EXCEPTION_TYPE"


@patch("bude_api.api.stock.frappe")
def test_create_transfer_folds_exceptions_and_unresolved_scans_into_remarks(
    mock_frappe,
):
    _grant_stock_role(mock_frappe)

    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            return [{"name": "X"}]
        if doctype == "Item":
            return [{"item_code": "A"}, {"item_code": "B"}]
        return []

    mock_frappe.get_list.side_effect = get_list
    doc = MagicMock()
    doc.name = "STE-2026-00003"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = stock_api.create_transfer(
        items=[
            {
                "item_code": "A",
                "qty": 3,
                "exception_type": "damage",
                "exception_note": "crushed box",
            },
            {"item_code": "B", "qty": 1},  # unflagged — no remarks entry
        ],
        source_warehouse="Src - X",
        target_warehouse="Tgt - X",
        unresolved_scans=["8901234"],
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["remarks"] == (
        "A: damage — crushed box\nUnresolved scan: 8901234"
    )


@patch("bude_api.api.stock.frappe")
def test_create_transfer_rejects_cross_company_warehouses(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = _get_list_with_companies(
        {"Src - A": "Company A", "Tgt - B": "Company B"}
    )

    result = stock_api.create_transfer(
        items=[{"item_code": "A", "qty": 1}],
        source_warehouse="Src - A",
        target_warehouse="Tgt - B",
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_WAREHOUSE_COMPANY_MISMATCH"
    assert "Company A" in result["message"]
    assert "Company B" in result["message"]


@patch("bude_api.api.stock.frappe")
def test_create_transfer_rejects_requested_company_mismatch(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = _get_list_with_companies(
        {"Src - A": "Company A", "Tgt - A": "Company A"}
    )

    result = stock_api.create_transfer(
        items=[{"item_code": "A", "qty": 1}],
        source_warehouse="Src - A",
        target_warehouse="Tgt - A",
        company="Company B",
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_WAREHOUSE_COMPANY_MISMATCH"
    assert "Company A" in result["message"]
    assert "Company B" in result["message"]


@patch("bude_api.api.stock.frappe")
def test_create_transfer_infers_company_from_warehouses(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = _get_list_with_companies(
        {"Src - A": "Company A", "Tgt - A": "Company A"}
    )
    doc = MagicMock()
    doc.name = "STE-2026-00001"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = stock_api.create_transfer(
        items=[{"item_code": "A", "qty": 1}],
        source_warehouse="Src - A",
        target_warehouse="Tgt - A",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["company"] == "Company A"


@patch("bude_api.api.stock.frappe")
def test_create_transfer_uses_valid_locations_as_effective_warehouses(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = _get_list_with_companies(
        {
            "Src - A": "Company A",
            "Tgt - A": "Company A",
            "Src Rack 1 - A": "Company A",
            "Tgt Staging - A": "Company A",
        },
        warehouse_parents={
            "Src Rack 1 - A": "Src - A",
            "Tgt Staging - A": "Tgt - A",
        },
    )
    doc = MagicMock()
    doc.name = "STE-2026-00002"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = stock_api.create_transfer(
        items=[{"item_code": "A", "qty": 1}],
        source_warehouse="Src - A",
        target_warehouse="Tgt - A",
        source_location="Src Rack 1 - A",
        target_location="Tgt Staging - A",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["items"][0]["s_warehouse"] == "Src Rack 1 - A"
    assert payload["items"][0]["t_warehouse"] == "Tgt Staging - A"
    assert payload["company"] == "Company A"


@patch("bude_api.api.stock.frappe")
def test_create_transfer_rejects_location_outside_parent_scope(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = _get_list_with_companies(
        {
            "Src - A": "Company A",
            "Tgt - A": "Company A",
            "Other Rack - A": "Company A",
        },
        warehouse_parents={"Other Rack - A": "Other Warehouse - A"},
    )

    result = stock_api.create_transfer(
        items=[{"item_code": "A", "qty": 1}],
        source_warehouse="Src - A",
        target_warehouse="Tgt - A",
        source_location="Other Rack - A",
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_LOCATION_SCOPE"


@patch("bude_api.api.stock.frappe")
def test_create_transfer_converts_erpnext_validation_error(mock_frappe):
    _grant_stock_role(mock_frappe)
    # ERPNext rejects the submit (e.g. insufficient stock). Frappe would raise
    # ValidationError → raw HTTP 417; we convert it to a clean envelope and
    # roll back the half-created draft.
    mock_frappe.ValidationError = _FakeValidationError

    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            return [{"name": "X"}]
        if doctype == "Item":
            return [{"item_code": "A"}]
        return []

    mock_frappe.get_list.side_effect = get_list
    doc = MagicMock()
    doc.submit.side_effect = _FakeValidationError(
        "Insufficient stock for Item A in Finished Goods - BUDE",
    )
    mock_frappe.get_doc.return_value = doc

    result = stock_api.create_transfer(
        items=[{"item_code": "A", "qty": 1}],
        source_warehouse="Finished Goods - BUDE",
        target_warehouse="Stores - BUDE",
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_ERPNEXT"
    assert "Insufficient stock" in result["message"]
    doc.insert.assert_called_once()
    mock_frappe.db.rollback.assert_called_once()


@patch("bude_api.api.stock.frappe")
def test_create_transfer_converts_permission_error(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.ValidationError = _FakeValidationError
    mock_frappe.PermissionError = _FakePermissionError

    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            return [{"name": "X"}]
        if doctype == "Item":
            return [{"item_code": "A"}]
        return []

    mock_frappe.get_list.side_effect = get_list
    doc = MagicMock()
    doc.submit.side_effect = _FakePermissionError("no submit")
    mock_frappe.get_doc.return_value = doc

    result = stock_api.create_transfer(
        items=[{"item_code": "A", "qty": 1}],
        source_warehouse="Finished Goods - BUDE",
        target_warehouse="Stores - BUDE",
    )

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    doc.insert.assert_called_once_with(ignore_permissions=False)
    doc.submit.assert_called_once()
    mock_frappe.db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# create_receipt
# ---------------------------------------------------------------------------


def test_create_receipt_requires_target_warehouse():
    result = stock_api.create_receipt(
        items=[{"item_code": "A", "qty": 1}],
        target_warehouse="",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


def test_create_receipt_requires_items():
    result = stock_api.create_receipt(items=[], target_warehouse="Stores - X")
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


def test_create_receipt_rejects_bad_qty():
    result = stock_api.create_receipt(
        items=[{"item_code": "A", "qty": -1}],
        target_warehouse="Stores - X",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_QTY"


def test_create_receipt_rejects_negative_rejected_qty():
    result = stock_api.create_receipt(
        items=[{"item_code": "A", "qty": 5, "rejected_qty": -1}],
        target_warehouse="Stores - X",
        against_po="PO-001",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_QTY"


def test_create_receipt_rejects_rejected_qty_without_po():
    result = stock_api.create_receipt(
        items=[{"item_code": "A", "qty": 5, "rejected_qty": 1}],
        target_warehouse="Stores - X",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REJECTED_QTY_REQUIRES_PO"


def test_create_receipt_rejects_rejected_qty_without_rejected_warehouse():
    result = stock_api.create_receipt(
        items=[{"item_code": "A", "qty": 5, "rejected_qty": 1}],
        target_warehouse="Stores - X",
        against_po="PO-001",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REJECTED_WAREHOUSE_REQUIRED"


@patch("bude_api.api.stock.frappe")
def test_create_receipt_rejects_unknown_warehouse(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.return_value = []  # no warehouse, no items
    result = stock_api.create_receipt(
        items=[{"item_code": "A", "qty": 1}],
        target_warehouse="Nope - X",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_UNKNOWN_WAREHOUSE"


@patch("bude_api.api.stock.frappe")
def test_create_receipt_material_receipt_happy_path(mock_frappe):
    _grant_stock_role(mock_frappe)
    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            return [{"name": "Tgt - X"}]
        if doctype == "Item":
            return [{"item_code": "A"}, {"item_code": "B"}]
        return []

    mock_frappe.get_list.side_effect = get_list
    doc = MagicMock()
    doc.name = "STE-MR-2026-00001"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = stock_api.create_receipt(
        items=[
            {"item_code": "A", "qty": 5},
            {"item_code": "B", "qty": 2.5},
        ],
        target_warehouse="Tgt - X",
        posting_date="2026-06-10",
    )

    assert result["ok"] is True
    assert result["data"]["name"] == "STE-MR-2026-00001"

    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["doctype"] == "Stock Entry"
    assert payload["stock_entry_type"] == "Material Receipt"
    assert payload["posting_date"] == "2026-06-10"
    assert payload["items"][0] == {
        "item_code": "A",
        "qty": 5,
        "t_warehouse": "Tgt - X",
    }
    doc.submit.assert_called_once()
    assert "remarks" not in payload


@patch("bude_api.api.stock.frappe")
def test_create_receipt_material_receipt_folds_damage_note_and_scans_into_remarks(
    mock_frappe,
):
    _grant_stock_role(mock_frappe)

    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            return [{"name": "Tgt - X"}]
        if doctype == "Item":
            return [{"item_code": "A"}]
        return []

    mock_frappe.get_list.side_effect = get_list
    doc = MagicMock()
    doc.name = "STE-MR-2026-00002"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = stock_api.create_receipt(
        items=[{"item_code": "A", "qty": 5, "damage_note": "wet carton"}],
        target_warehouse="Tgt - X",
        unresolved_scans=["1112223"],
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args[0][0]
    assert "rejected_qty" not in payload["items"][0]  # no structural split, ad-hoc
    assert payload["remarks"] == "A: wet carton\nUnresolved scan: 1112223"


@patch("bude_api.api.stock.frappe")
def test_create_receipt_rejects_company_mismatch(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = _get_list_with_companies(
        {"Receiving - A": "Company A"}
    )

    result = stock_api.create_receipt(
        items=[{"item_code": "A", "qty": 1}],
        target_warehouse="Receiving - A",
        company="Company B",
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_WAREHOUSE_COMPANY_MISMATCH"


@patch("bude_api.api.stock.frappe")
def test_create_receipt_infers_company_from_warehouse(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = _get_list_with_companies(
        {"Receiving - A": "Company A"}
    )
    doc = MagicMock()
    doc.name = "STE-MR-2026-00001"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = stock_api.create_receipt(
        items=[{"item_code": "A", "qty": 1}],
        target_warehouse="Receiving - A",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["company"] == "Company A"


@patch("bude_api.api.stock.frappe")
def test_create_receipt_uses_valid_location_as_effective_warehouse(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = _get_list_with_companies(
        {
            "Receiving - A": "Company A",
            "Receiving Rack 1 - A": "Company A",
        },
        warehouse_parents={"Receiving Rack 1 - A": "Receiving - A"},
    )
    doc = MagicMock()
    doc.name = "STE-MR-2026-00002"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = stock_api.create_receipt(
        items=[{"item_code": "A", "qty": 1}],
        target_warehouse="Receiving - A",
        target_location="Receiving Rack 1 - A",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["items"][0]["t_warehouse"] == "Receiving Rack 1 - A"
    assert payload["company"] == "Company A"


@patch("bude_api.api.stock.frappe")
def test_create_receipt_against_po_rejects_unknown_po(mock_frappe):
    _grant_stock_role(mock_frappe)
    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            return [{"name": "Tgt - X"}]
        if doctype == "Item":
            return [{"item_code": "A"}]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = stock_api.create_receipt(
        items=[{"item_code": "A", "qty": 1}],
        target_warehouse="Tgt - X",
        against_po="PO-MISSING",
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_UNKNOWN_PO"


@patch("bude_api.api.stock.frappe")
def test_create_receipt_against_po_rejects_line_mismatch(mock_frappe):
    _grant_stock_role(mock_frappe)
    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            return [{"name": "Tgt - X"}]
        if doctype == "Item":
            return [{"item_code": "A"}, {"item_code": "B"}]
        if doctype == "Purchase Order":
            return [
                {
                    "name": "PO-001",
                    "supplier": "Acme Supplies",
                    "company": "Company A",
                }
            ]
        if doctype == "Purchase Order Item":
            return [{"name": "PO-001-1", "item_code": "A", "qty": 10}]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = stock_api.create_receipt(
        items=[
            {"item_code": "A", "qty": 5},
            {"item_code": "B", "qty": 1},  # not on PO
        ],
        target_warehouse="Tgt - X",
        against_po="PO-001",
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_PO_LINE_MISMATCH"
    assert "B" in result["message"]


@patch("bude_api.api.stock.frappe")
def test_create_receipt_against_po_rejects_company_mismatch(mock_frappe):
    _grant_stock_role(mock_frappe)
    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            return [
                {
                    "name": "Receiving - A",
                    "company": "Company A",
                    "parent_warehouse": None,
                }
            ]
        if doctype == "Item":
            return [{"item_code": "A"}]
        if doctype == "Purchase Order":
            return [
                {
                    "name": "PO-001",
                    "supplier": "Acme Supplies",
                    "company": "Company B",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = stock_api.create_receipt(
        items=[{"item_code": "A", "qty": 1}],
        target_warehouse="Receiving - A",
        against_po="PO-001",
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_PO_COMPANY_MISMATCH"


@patch("bude_api.api.stock.frappe")
def test_create_receipt_against_po_happy_path(mock_frappe):
    _grant_stock_role(mock_frappe)
    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            return [{"name": "Tgt - X"}]
        if doctype == "Item":
            return [{"item_code": "A"}]
        if doctype == "Purchase Order":
            return [
                {
                    "name": "PO-001",
                    "supplier": "Acme Supplies",
                    "company": "Company A",
                }
            ]
        if doctype == "Purchase Order Item":
            return [{"name": "PO-001-1", "item_code": "A", "qty": 10}]
        return []

    mock_frappe.get_list.side_effect = get_list
    pr = MagicMock()
    pr.name = "PREC-2026-00001"
    pr.docstatus = 1
    mock_frappe.get_doc.return_value = pr

    result = stock_api.create_receipt(
        items=[{"item_code": "A", "qty": 5}],
        target_warehouse="Tgt - X",
        against_po="PO-001",
    )

    assert result["ok"] is True
    assert result["data"]["name"] == "PREC-2026-00001"

    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["doctype"] == "Purchase Receipt"
    assert payload["supplier"] == "Acme Supplies"
    assert payload["items"][0] == {
        "item_code": "A",
        "qty": 5,
        "warehouse": "Tgt - X",
        "purchase_order": "PO-001",
        "purchase_order_item": "PO-001-1",
    }
    pr.submit.assert_called_once()
    mock_frappe.get_all.assert_not_called()
    assert "remarks" not in payload


@patch("bude_api.api.stock.frappe")
def test_create_receipt_against_po_rejects_unknown_rejected_warehouse(mock_frappe):
    _grant_stock_role(mock_frappe)

    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            filters = kwargs.get("filters", [])
            name = filters[0][2] if filters else None
            return [{"name": name}] if name == "Tgt - X" else []
        if doctype == "Item":
            return [{"item_code": "A"}]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = stock_api.create_receipt(
        items=[
            {
                "item_code": "A",
                "qty": 3,
                "rejected_qty": 2,
                "rejected_warehouse": "Rejected - X",
            }
        ],
        target_warehouse="Tgt - X",
        against_po="PO-001",
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_UNKNOWN_WAREHOUSE"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.stock.frappe")
def test_create_receipt_against_po_happy_path_with_rejected_qty(mock_frappe):
    _grant_stock_role(mock_frappe)

    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            filters = kwargs.get("filters", [])
            name = filters[0][2] if filters else None
            return [{"name": name}] if name in ("Tgt - X", "Rejected - X") else []
        if doctype == "Item":
            return [{"item_code": "A"}]
        if doctype == "Purchase Order":
            return [
                {"name": "PO-001", "supplier": "Acme Supplies", "company": None}
            ]
        if doctype == "Purchase Order Item":
            return [{"name": "PO-001-1", "item_code": "A", "qty": 10}]
        return []

    mock_frappe.get_list.side_effect = get_list
    pr = MagicMock()
    pr.name = "PREC-2026-00002"
    pr.docstatus = 1
    mock_frappe.get_doc.return_value = pr

    result = stock_api.create_receipt(
        items=[
            {
                "item_code": "A",
                "qty": 3,
                "rejected_qty": 2,
                "rejected_warehouse": "Rejected - X",
                "damage_note": "corroded casing",
            }
        ],
        target_warehouse="Tgt - X",
        against_po="PO-001",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["items"][0] == {
        "item_code": "A",
        "qty": 3,
        "warehouse": "Tgt - X",
        "purchase_order": "PO-001",
        "purchase_order_item": "PO-001-1",
        "rejected_qty": 2,
        "rejected_warehouse": "Rejected - X",
    }
    assert payload["remarks"] == "A: corroded casing"


# ---------------------------------------------------------------------------
# create_reconciliation
# ---------------------------------------------------------------------------


def test_create_reconciliation_requires_warehouse():
    result = stock_api.create_reconciliation(
        counts=[{"item_code": "A", "qty": 5}],
        warehouse="",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


def test_create_reconciliation_requires_counts():
    result = stock_api.create_reconciliation(
        counts=[],
        warehouse="Stores - X",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


def test_create_reconciliation_rejects_negative_qty():
    # 0 is allowed (item present in system but counted as missing).
    # Negative is not.
    result = stock_api.create_reconciliation(
        counts=[{"item_code": "A", "qty": -1}],
        warehouse="Stores - X",
    )
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_QTY"


@patch("bude_api.api.stock.frappe")
def test_create_reconciliation_allows_zero_qty(mock_frappe):
    _grant_stock_role(mock_frappe)
    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            return [{"name": "Stores - X"}]
        if doctype == "Item":
            return [{"item_code": "A"}]
        return []

    mock_frappe.get_list.side_effect = get_list
    doc = MagicMock()
    doc.name = "RECON-2026-00001"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    # Counted zero on hand — legitimate after a full count showing nothing.
    result = stock_api.create_reconciliation(
        counts=[{"item_code": "A", "qty": 0}],
        warehouse="Stores - X",
    )

    assert result["ok"] is True
    assert result["data"]["name"] == "RECON-2026-00001"


@patch("bude_api.api.stock.frappe")
def test_create_reconciliation_rejects_company_mismatch(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = _get_list_with_companies(
        {"Stores - A": "Company A"}
    )

    result = stock_api.create_reconciliation(
        counts=[{"item_code": "A", "qty": 1}],
        warehouse="Stores - A",
        company="Company B",
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_WAREHOUSE_COMPANY_MISMATCH"


@patch("bude_api.api.stock.frappe")
def test_create_reconciliation_infers_company_from_warehouse(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = _get_list_with_companies(
        {"Stores - A": "Company A"}
    )
    doc = MagicMock()
    doc.name = "RECON-2026-00001"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = stock_api.create_reconciliation(
        counts=[{"item_code": "A", "qty": 1}],
        warehouse="Stores - A",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["company"] == "Company A"


@patch("bude_api.api.stock.frappe")
def test_create_reconciliation_uses_valid_location_as_effective_warehouse(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = _get_list_with_companies(
        {
            "Stores - A": "Company A",
            "Rack Count 1 - A": "Company A",
        },
        warehouse_parents={"Rack Count 1 - A": "Stores - A"},
    )
    doc = MagicMock()
    doc.name = "RECON-2026-00003"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = stock_api.create_reconciliation(
        counts=[{"item_code": "A", "qty": 1}],
        warehouse="Stores - A",
        location="Rack Count 1 - A",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["items"][0]["warehouse"] == "Rack Count 1 - A"
    assert payload["company"] == "Company A"


@patch("bude_api.api.stock.frappe")
def test_create_reconciliation_rejects_unknown_item(mock_frappe):
    _grant_stock_role(mock_frappe)
    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            return [{"name": "Stores - X"}]
        if doctype == "Item":
            return [{"item_code": "A"}]  # B missing
        return []

    mock_frappe.get_list.side_effect = get_list

    result = stock_api.create_reconciliation(
        counts=[
            {"item_code": "A", "qty": 10},
            {"item_code": "B", "qty": 5},
        ],
        warehouse="Stores - X",
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_UNKNOWN_ITEM"


@patch("bude_api.api.stock.frappe")
def test_create_reconciliation_happy_path_assembles_doc(mock_frappe):
    _grant_stock_role(mock_frappe)
    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            return [{"name": "Stores - X"}]
        if doctype == "Item":
            return [{"item_code": "A"}, {"item_code": "B"}]
        return []

    mock_frappe.get_list.side_effect = get_list
    doc = MagicMock()
    doc.name = "RECON-2026-00002"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = stock_api.create_reconciliation(
        counts=[
            {"item_code": "A", "qty": 12},
            {"item_code": "B", "qty": 0},
        ],
        warehouse="Stores - X",
        posting_date="2026-06-10",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["doctype"] == "Stock Reconciliation"
    assert payload["purpose"] == "Stock Reconciliation"
    assert payload["posting_date"] == "2026-06-10"
    assert payload["items"] == [
        {"item_code": "A", "warehouse": "Stores - X", "qty": 12},
        {"item_code": "B", "warehouse": "Stores - X", "qty": 0},
    ]
    doc.submit.assert_called_once()
    assert "remarks" not in payload


@patch("bude_api.api.stock.frappe")
def test_create_reconciliation_folds_variance_reason_and_scans_into_remarks(
    mock_frappe,
):
    _grant_stock_role(mock_frappe)

    def get_list(doctype, **kwargs):
        if doctype == "Warehouse":
            return [{"name": "Stores - X"}]
        if doctype == "Item":
            return [{"item_code": "A"}, {"item_code": "B"}]
        return []

    mock_frappe.get_list.side_effect = get_list
    doc = MagicMock()
    doc.name = "RECON-2026-00004"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = stock_api.create_reconciliation(
        counts=[
            {"item_code": "A", "qty": 8, "variance_reason": "found in wrong bin"},
            {"item_code": "B", "qty": 10},  # exact count — no reason needed
        ],
        warehouse="Stores - X",
        unresolved_scans=["4445556"],
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["remarks"] == (
        "A: found in wrong bin\nUnresolved scan: 4445556"
    )
