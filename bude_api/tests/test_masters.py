from unittest.mock import MagicMock, patch

from bude_api.api import masters as masters_api


class _FakeValidationError(Exception):
    """Stand-in for frappe.ValidationError (no Frappe installed in unit tests)."""


class _FakePermissionError(Exception):
    """Stand-in for frappe.PermissionError."""


def _wire_exceptions(mock_frappe):
    mock_frappe.ValidationError = _FakeValidationError
    mock_frappe.PermissionError = _FakePermissionError


# ── Pure validation (no Frappe) ─────────────────────────────────────────────
def test_list_masters_returns_catalog():
    result = masters_api.list_masters()
    assert result["ok"] is True
    keys = {m["key"] for m in result["data"]}
    assert {"item", "warehouse", "supplier", "employee"}.issubset(keys)
    item = next(m for m in result["data"] if m["key"] == "item")
    assert item["can_disable"] is True
    group = next(m for m in result["data"] if m["key"] == "item_group")
    assert group["can_disable"] is False  # no disable field


def test_list_records_unknown_master():
    result = masters_api.list_records("nope")
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_UNKNOWN_MASTER"


def test_create_record_unknown_master():
    result = masters_api.create_record("nope", {"x": 1})
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_UNKNOWN_MASTER"


def test_create_record_required_missing():
    result = masters_api.create_record("item", {"item_code": "ABC"})
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"  # item_name etc. missing


def test_set_disabled_unsupported_master():
    result = masters_api.set_disabled("item_group", "Products")
    assert result["ok"] is False
    assert result["code"] == "DISABLE_NOT_SUPPORTED"


# ── Mocked Frappe ───────────────────────────────────────────────────────────
@patch("bude_api.api.masters.frappe")
def test_create_record_drops_unknown_fields(mock_frappe):
    _wire_exceptions(mock_frappe)
    doc = MagicMock()
    doc.name = "Acme"
    mock_frappe.get_doc.return_value = doc

    result = masters_api.create_record(
        "brand", {"brand": "Acme", "owner": "hacker", "creation": "2000-01-01"}
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "Brand"
    assert payload["brand"] == "Acme"
    assert "owner" not in payload and "creation" not in payload
    doc.insert.assert_called_once()


@patch("bude_api.api.masters.frappe")
def test_create_record_happy_path(mock_frappe):
    _wire_exceptions(mock_frappe)
    doc = MagicMock()
    doc.name = "Acme"
    mock_frappe.get_doc.return_value = doc

    result = masters_api.create_record("brand", {"brand": "Acme"})

    assert result["ok"] is True
    assert result["data"]["name"] == "Acme"
    doc.insert.assert_called_once()


@patch("bude_api.api.masters.frappe")
def test_create_record_validation_error_rolls_back(mock_frappe):
    _wire_exceptions(mock_frappe)
    doc = MagicMock()
    doc.insert.side_effect = _FakeValidationError("Item Group is mandatory")
    mock_frappe.get_doc.return_value = doc

    result = masters_api.create_record("brand", {"brand": "Acme"})

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_ERPNEXT"
    mock_frappe.db.rollback.assert_called_once()


@patch("bude_api.api.masters.frappe")
def test_create_record_permission_error(mock_frappe):
    _wire_exceptions(mock_frappe)
    doc = MagicMock()
    doc.insert.side_effect = _FakePermissionError("no perm")
    mock_frappe.get_doc.return_value = doc

    result = masters_api.create_record("brand", {"brand": "Acme"})

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.db.rollback.assert_called_once()


@patch("bude_api.api.masters.frappe")
def test_update_record_saves_cleaned_values(mock_frappe):
    _wire_exceptions(mock_frappe)
    mock_frappe.get_list.return_value = [{"name": "Acme"}]
    doc = MagicMock()
    doc.name = "Acme"
    mock_frappe.get_doc.return_value = doc

    result = masters_api.update_record(
        "brand", "Acme", {"description": "Tools", "name": "hacked"}
    )

    assert result["ok"] is True
    set_keys = {call.args[0] for call in doc.set.call_args_list}
    assert "description" in set_keys
    assert "name" not in set_keys  # name is not an editable field, dropped
    doc.save.assert_called_once()


@patch("bude_api.api.masters.frappe")
def test_update_record_missing(mock_frappe):
    _wire_exceptions(mock_frappe)
    mock_frappe.get_list.return_value = []
    result = masters_api.update_record("brand", "Nope", {"description": "x"})
    assert result["ok"] is False
    assert result["code"] == "NOT_FOUND"


@patch("bude_api.api.masters.frappe")
def test_set_disabled_uom_uses_inverted_enabled(mock_frappe):
    _wire_exceptions(mock_frappe)
    mock_frappe.get_list.return_value = [{"name": "Box"}]
    doc = MagicMock()
    doc.name = "Box"
    mock_frappe.get_doc.return_value = doc

    result = masters_api.set_disabled("uom", "Box", disabled=True)

    assert result["ok"] is True
    doc.set.assert_called_once_with("enabled", 0)  # disable => enabled=0
    doc.save.assert_called_once()


@patch("bude_api.api.masters.frappe")
def test_list_link_options_rejects_unknown_doctype(mock_frappe):
    result = masters_api.list_link_options("User")
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_DOCTYPE"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.masters.frappe")
def test_list_link_options_allowed_doctype(mock_frappe):
    mock_frappe.get_list.return_value = [{"name": "Products"}, {"name": "Raw"}]
    result = masters_api.list_link_options("Item Group", search="r")
    assert result["ok"] is True
    assert result["data"] == ["Products", "Raw"]
