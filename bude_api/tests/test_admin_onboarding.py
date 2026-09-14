from unittest.mock import MagicMock, patch

from bude_api.api import admin_onboarding as admin_api


class _FakePermissionError(Exception):
    pass


def _login(mock_frappe, roles=None, user="manager@example.com"):
    mock_frappe.session.user = user
    mock_frappe.get_roles.return_value = roles or ["Stock Manager"]
    mock_frappe.PermissionError = _FakePermissionError


@patch("bude_api.api.admin_onboarding.frappe")
def test_role_profiles_require_manager_role(mock_frappe):
    _login(mock_frappe, roles=["Stock User"])

    result = admin_api.role_profiles()

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.admin_onboarding.frappe")
def test_role_profiles_lists_standard_role_profiles(mock_frappe):
    _login(mock_frappe)
    mock_frappe.get_list.return_value = [
        {"name": "Stock Operators", "role_profile": "Stock Operators"}
    ]

    result = admin_api.role_profiles(limit=10)

    assert result["ok"] is True
    assert result["data"][0]["name"] == "Stock Operators"
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["doctype"] if "doctype" in kwargs else True
    assert mock_frappe.get_list.call_args.args[0] == "Role Profile"
    assert kwargs["limit_page_length"] == 10


@patch("bude_api.api.admin_onboarding.frappe")
def test_assign_role_profile_sets_user_role_profile(mock_frappe):
    _login(mock_frappe)
    mock_frappe.db.exists.side_effect = lambda doctype, name: True
    doc = MagicMock()
    mock_frappe.get_doc.return_value = doc

    result = admin_api.assign_role_profile("user@example.com", "Stock Operators")

    assert result["ok"] is True
    doc.set.assert_called_once_with("role_profile_name", "Stock Operators")
    doc.save.assert_called_once_with(ignore_permissions=False)
    mock_frappe.db.commit.assert_called_once()


@patch("bude_api.api.admin_onboarding.frappe")
def test_assign_role_profile_validates_user_and_profile(mock_frappe):
    _login(mock_frappe)
    mock_frappe.db.exists.side_effect = lambda doctype, name: False

    result = admin_api.assign_role_profile("missing@example.com", "Stock Operators")

    assert result["ok"] is False
    assert result["code"] == "NOT_FOUND"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.admin_onboarding.revoke_registered_device")
@patch("bude_api.api.admin_onboarding.frappe")
def test_revoke_device_is_manager_gated(mock_frappe, mock_revoke):
    _login(mock_frappe)
    mock_revoke.return_value = True

    result = admin_api.revoke_device("user@example.com", "device-1")

    assert result["ok"] is True
    assert result["data"]["revoked"] is True
    mock_revoke.assert_called_once_with("user@example.com", "device-1")


@patch("bude_api.api.admin_onboarding.seed_demo_run")
@patch("bude_api.api.admin_onboarding.frappe")
def test_seed_pilot_workflow_requires_confirmation(mock_frappe, mock_seed):
    _login(mock_frappe)

    result = admin_api.seed_pilot_workflow(confirm=False)

    assert result["ok"] is False
    assert result["code"] == "CONFIRMATION_REQUIRED"
    mock_seed.assert_not_called()


@patch("bude_api.api.admin_onboarding.seed_demo_run")
@patch("bude_api.api.admin_onboarding.frappe")
def test_seed_pilot_workflow_calls_demo_seed_with_guard(mock_frappe, mock_seed):
    _login(mock_frappe)
    mock_seed.return_value = {"run_id": "preview-20260707", "records": {}}

    result = admin_api.seed_pilot_workflow(
        confirm=True,
        profile="preview",
        base_url="https://erp.example.test",
        dry_run="1",
    )

    assert result["ok"] is True
    assert result["data"]["run_id"] == "preview-20260707"
    mock_seed.assert_called_once_with(
        profile="preview",
        base_url="https://erp.example.test",
        confirm_demo_data=True,
        dry_run=True,
    )
