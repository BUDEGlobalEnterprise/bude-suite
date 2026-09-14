from unittest.mock import MagicMock, patch

import pytest

from bude_api.api import auth as auth_api
from bude_api.services.auth_service import AuthError, AuthService


@patch("bude_api.services.auth_service.frappe")
def test_login_returns_session_dict_with_api_keys(mock_frappe):
    login_manager = MagicMock()
    mock_frappe.auth.LoginManager.return_value = login_manager
    mock_frappe.session.user = "alice@example.com"

    user_doc = MagicMock()
    user_doc.api_key = "existing_key"
    user_doc.get_password.return_value = "existing_secret"
    user_doc.full_name = "Alice Example"
    mock_frappe.get_doc.return_value = user_doc
    mock_frappe.get_roles.return_value = ["Stock Manager", "System Manager"]
    mock_frappe.db.get_value.return_value = "Stores - A"

    result = AuthService().login("alice@example.com", "hunter2")

    login_manager.authenticate.assert_called_once_with(user="alice@example.com", pwd="hunter2")
    login_manager.post_login.assert_called_once()
    assert result == {
        "user": "alice@example.com",
        "full_name": "Alice Example",
        "api_key": "existing_key",
        "api_secret": "existing_secret",
        "roles": ["Stock Manager", "System Manager"],
        "default_warehouse": "Stores - A",
    }


@patch("bude_api.services.auth_service.frappe")
def test_login_generates_keys_when_missing(mock_frappe):
    login_manager = MagicMock()
    mock_frappe.auth.LoginManager.return_value = login_manager
    mock_frappe.session.user = "bob@example.com"
    mock_frappe.generate_hash.side_effect = ["new_key", "new_secret"]

    user_doc = MagicMock()
    user_doc.api_key = None
    user_doc.get_password.return_value = None
    user_doc.full_name = "Bob Example"
    mock_frappe.get_doc.return_value = user_doc
    mock_frappe.get_roles.return_value = ["Stock User"]
    mock_frappe.db.get_value.return_value = ""

    result = AuthService().login("bob@example.com", "hunter2")

    assert result["api_key"] == "new_key"
    assert result["api_secret"] == "new_secret"
    user_doc.save.assert_called_once_with(ignore_permissions=True)


@patch("bude_api.services.auth_service.frappe")
def test_login_raises_auth_error_on_invalid_credentials(mock_frappe):
    class _AuthError(Exception):
        pass

    mock_frappe.AuthenticationError = _AuthError
    login_manager = MagicMock()
    login_manager.authenticate.side_effect = _AuthError("bad creds")
    mock_frappe.auth.LoginManager.return_value = login_manager

    with pytest.raises(AuthError):
        AuthService().login("nobody", "wrong")


@patch.object(auth_api, "_service")
def test_login_endpoint_returns_failure_envelope_on_auth_error(mock_service):
    mock_service.login.side_effect = AuthError("Invalid username or password.")
    result = auth_api.login("u", "p")
    assert result["ok"] is False
    assert result["code"] == "AUTH_INVALID_CREDENTIALS"


@patch.object(auth_api, "_service")
def test_login_endpoint_returns_success_envelope(mock_service):
    mock_service.login.return_value = {"user": "u", "full_name": "U", "api_key": "k", "api_secret": "s"}
    result = auth_api.login("u", "p")
    assert result["ok"] is True
    assert result["data"]["user"] == "u"


@patch.object(auth_api, "_service")
def test_session_info_returns_failure_when_no_user(mock_service):
    mock_service.current_user.return_value = None
    result = auth_api.session_info()
    assert result["ok"] is False
    assert result["code"] == "AUTH_NO_SESSION"


@patch.object(auth_api, "_service")
@patch("bude_api.api.auth.frappe")
def test_session_info_includes_roles(mock_frappe, mock_service):
    mock_service.current_user.return_value = "alice@example.com"
    mock_frappe.db.get_value.return_value = "Alice"
    mock_frappe.get_roles.return_value = ["Stock Manager", "All"]
    mock_frappe.db.get_value.side_effect = lambda *a, **kw: (
        "Alice" if a[2] == "full_name" else ""
    )

    result = auth_api.session_info()

    assert result["ok"] is True
    assert "Stock Manager" in result["data"]["roles"]


@patch("bude_api.services.auth_service.frappe")
@patch.object(auth_api, "_service")
@patch("bude_api.api.auth.frappe")
def test_session_info_includes_default_warehouse(
    mock_frappe, mock_service, mock_service_frappe
):
    mock_service.current_user.return_value = "alice@example.com"
    mock_frappe.get_roles.return_value = ["All"]
    mock_frappe.db.get_value.return_value = "Alice"
    # The warehouse lookup happens in auth_service and is guarded by has_field.
    mock_service_frappe.get_meta.return_value.has_field.return_value = True
    mock_service_frappe.db.get_value.return_value = "Stores - A"

    result = auth_api.session_info()

    assert result["ok"] is True
    assert result["data"]["default_warehouse"] == "Stores - A"


@patch("bude_api.services.auth_service.frappe")
@patch.object(auth_api, "_service")
@patch("bude_api.api.auth.frappe")
def test_session_info_empty_warehouse_without_custom_field(
    mock_frappe, mock_service, mock_service_frappe
):
    # HR-only sites have no default_warehouse column; login must not query it.
    mock_service.current_user.return_value = "alice@example.com"
    mock_frappe.get_roles.return_value = ["All"]
    mock_frappe.db.get_value.return_value = "Alice"
    mock_service_frappe.get_meta.return_value.has_field.return_value = False

    result = auth_api.session_info()

    assert result["ok"] is True
    assert result["data"]["default_warehouse"] == ""
    mock_service_frappe.db.get_value.assert_not_called()


# ── Google sign-in ──────────────────────────────────────────────────────────


@patch("bude_api.services.auth_service.frappe")
def test_google_config_reports_enabled_client_id(mock_frappe):
    mock_frappe.db.get_value.return_value = {"client_id": "cid-123", "enable_social_login": 1}
    assert AuthService().google_config() == {"enabled": True, "client_id": "cid-123"}


@patch("bude_api.services.auth_service.frappe")
def test_google_config_disabled_when_key_missing(mock_frappe):
    mock_frappe.db.get_value.return_value = None
    assert AuthService().google_config() == {"enabled": False, "client_id": None}


@patch("bude_api.services.auth_service.frappe")
def test_google_config_accepts_capitalized_standard_key(mock_frappe):
    mock_frappe.db.get_value.side_effect = [
        None,
        {"client_id": "cid-456", "enable_social_login": 1},
    ]

    assert AuthService().google_config() == {
        "enabled": True,
        "client_id": "cid-456",
    }


@patch.object(AuthService, "_verify_google_token", return_value="alice@example.com")
@patch("bude_api.services.auth_service.frappe")
def test_login_with_google_returns_session_for_existing_user(mock_frappe, _verify):
    def get_value(doctype, *args, **kwargs):
        if doctype == "Social Login Key":
            return {"client_id": "cid-123", "enable_social_login": 1}
        if doctype == "User" and isinstance(args[0], dict):  # the email->User lookup
            return "alice@example.com"
        return ""

    mock_frappe.db.get_value.side_effect = get_value
    mock_frappe.get_meta.return_value.has_field.return_value = False  # no warehouse field

    user_doc = MagicMock()
    user_doc.api_key = "existing_key"
    user_doc.get_password.return_value = "existing_secret"
    user_doc.full_name = "Alice Example"
    mock_frappe.get_doc.return_value = user_doc
    mock_frappe.get_roles.return_value = ["Stock User"]

    result = AuthService().login_with_google("google-id-token")

    _verify.assert_called_once_with("google-id-token", "cid-123")
    assert result["user"] == "alice@example.com"
    assert result["api_key"] == "existing_key"
    assert result["api_secret"] == "existing_secret"
    assert result["roles"] == ["Stock User"]


@patch.object(AuthService, "_verify_google_token", return_value="ghost@example.com")
@patch("bude_api.services.auth_service.frappe")
def test_login_with_google_rejects_unknown_user(mock_frappe, _verify):
    def get_value(doctype, *args, **kwargs):
        if doctype == "Social Login Key":
            return {"client_id": "cid-123", "enable_social_login": 1}
        return None  # no matching enabled User

    mock_frappe.db.get_value.side_effect = get_value

    with pytest.raises(AuthError):
        AuthService().login_with_google("google-id-token")


@patch("bude_api.services.auth_service.frappe")
def test_login_with_google_requires_configuration(mock_frappe):
    mock_frappe.db.get_value.return_value = None  # Google not configured
    with pytest.raises(AuthError):
        AuthService().login_with_google("google-id-token")


@patch.object(auth_api, "_service")
def test_login_with_google_endpoint_returns_failure_envelope(mock_service):
    mock_service.login_with_google.side_effect = AuthError("No active ERPNext account.")
    result = auth_api.login_with_google("tok")
    assert result["ok"] is False
    assert result["code"] == "AUTH_GOOGLE_DENIED"


@patch.object(auth_api, "_service")
def test_google_config_endpoint_returns_success_envelope(mock_service):
    mock_service.google_config.return_value = {"enabled": True, "client_id": "cid-123"}
    result = auth_api.google_config()
    assert result["ok"] is True
    assert result["data"]["client_id"] == "cid-123"
