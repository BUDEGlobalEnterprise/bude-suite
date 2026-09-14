from unittest.mock import MagicMock

from bude_api.api.permissions import (
    require_any_role,
    require_sales_role,
    require_stock_execution_role,
)


def test_require_any_role_returns_auth_expired_for_guest_session():
    frappe = MagicMock()
    frappe.session.user = "Guest"

    result = require_any_role(frappe, {"Stock User"})

    assert result["ok"] is False
    assert result["code"] == "AUTH_EXPIRED"
    frappe.get_roles.assert_not_called()


def test_require_any_role_returns_auth_expired_for_missing_session_user():
    frappe = MagicMock()
    frappe.session.user = None

    result = require_any_role(frappe, {"Stock User"})

    assert result["ok"] is False
    assert result["code"] == "AUTH_EXPIRED"
    frappe.get_roles.assert_not_called()


def test_require_stock_execution_role_allows_stock_user():
    frappe = MagicMock()
    frappe.session.user = "warehouse.user@example.com"
    frappe.get_roles.return_value = ["Stock User"]

    assert require_stock_execution_role(frappe) is None


def test_require_stock_execution_role_distinguishes_permission_denial():
    frappe = MagicMock()
    frappe.session.user = "sales.user@example.com"
    frappe.get_roles.return_value = ["Sales User"]

    result = require_stock_execution_role(frappe)

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"


def test_require_sales_role_allows_sales_user():
    frappe = MagicMock()
    frappe.session.user = "sales.user@example.com"
    frappe.get_roles.return_value = ["Sales User"]

    assert require_sales_role(frappe) is None


def test_require_sales_role_denies_stock_only_user():
    frappe = MagicMock()
    frappe.session.user = "warehouse.user@example.com"
    frappe.get_roles.return_value = ["Stock User"]

    result = require_sales_role(frappe)

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
