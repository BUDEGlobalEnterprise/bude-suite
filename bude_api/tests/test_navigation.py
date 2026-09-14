import json
from unittest.mock import patch

from bude_api.api import branding as branding_api
from bude_api.api import navigation as nav_api


@patch("bude_api.api.navigation.frappe")
def test_save_rejects_non_admin(mock_frappe):
    mock_frappe.session.user = "operator@example.com"
    mock_frappe.get_roles.return_value = ["Stock User"]

    result = nav_api.save(json.dumps({"order": [], "buckets": {}}))

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.db.set_default.assert_not_called()


@patch("bude_api.api.navigation.frappe")
def test_save_persists_for_system_manager(mock_frappe):
    mock_frappe.session.user = "manager@example.com"
    mock_frappe.get_roles.return_value = ["System Manager"]
    config = {"order": ["dashboard"], "buckets": {"Stock User": {"hidden": ["reports"]}}}

    result = nav_api.save(json.dumps(config))

    assert result["ok"] is True
    assert result["data"] == config
    key, value = mock_frappe.db.set_default.call_args[0]
    assert key == nav_api.NAV_CONFIG_KEY
    assert json.loads(value) == config


@patch("bude_api.api.navigation.frappe")
def test_save_rejects_invalid_json(mock_frappe):
    mock_frappe.session.user = "Administrator"
    mock_frappe.get_roles.return_value = ["System Manager"]

    result = nav_api.save("not json {")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_INVALID_JSON"


@patch("bude_api.api.navigation.frappe")
def test_save_rejects_non_object(mock_frappe):
    mock_frappe.session.user = "Administrator"
    mock_frappe.get_roles.return_value = ["System Manager"]

    result = nav_api.save(json.dumps(["not", "an", "object"]))

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_INVALID_JSON"


@patch("bude_api.api.branding.frappe")
@patch("bude_api.api.branding.get_versions")
def test_branding_surfaces_saved_navigation(mock_get_versions, mock_frappe):
    config = {"order": ["dashboard"], "buckets": {"Stock User": {"hidden": ["reports"]}}}

    def get_default(key):
        if key == branding_api.NAV_CONFIG_KEY:
            return json.dumps(config)
        return None  # no default company

    mock_frappe.db.get_default.side_effect = get_default
    mock_frappe.get_list.return_value = []
    mock_frappe.get_installed_apps.return_value = ["frappe", "erpnext"]
    mock_get_versions.return_value = {"erpnext": {"version": "15.0.0"}}

    result = branding_api.get()

    assert result["ok"] is True
    assert result["data"]["navigation"] == config


@patch("bude_api.api.branding.frappe")
@patch("bude_api.api.branding.get_versions")
def test_branding_navigation_null_when_unset_or_garbage(mock_get_versions, mock_frappe):
    mock_frappe.db.get_default.return_value = "not valid json"
    mock_frappe.get_list.return_value = []
    mock_frappe.get_installed_apps.return_value = ["frappe", "erpnext"]
    mock_get_versions.return_value = {"erpnext": {"version": "15.0.0"}}

    result = branding_api.get()

    assert result["ok"] is True
    assert result["data"]["navigation"] is None
