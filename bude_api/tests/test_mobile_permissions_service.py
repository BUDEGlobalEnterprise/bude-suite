"""Service-layer tests with a faked frappe module (no bench required)."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from bude_api.services.mobile_permissions import service


class _PermissionError(Exception):
    pass


class FakeFrappe:
    """Minimal stand-in exercising the exact calls the service makes."""

    PermissionError = _PermissionError

    def __init__(self, user="alice@example.com", roles=None, enabled=1,
                 app=None, screens=None, role_perms=None, overrides=None):
        self.session = SimpleNamespace(user=user)
        self._roles = roles or []
        self._enabled = enabled
        self._app = app if app is not None else {
            "name": "inventory", "is_active": 1, "permission_version": 7,
        }
        self._screens = screens or []
        self._role_perms = role_perms or []
        self._overrides = overrides or []
        self.utils = SimpleNamespace(
            now_datetime=lambda: datetime(2026, 8, 6, 12, 0, 0),
            now=lambda: "2026-08-06T12:00:00",
        )
        self.db = SimpleNamespace(get_value=self._get_value)

    def _get_value(self, doctype, name, fields, as_dict=False):
        if doctype == "Mobile Application":
            return SimpleNamespace(**self._app) if self._app else None
        if doctype == "User" and fields == "enabled":
            return self._enabled
        return None

    def get_roles(self, user=None):
        return self._roles

    def get_all(self, doctype, filters=None, fields=None, ignore_permissions=False):
        if doctype == "Mobile App Screen":
            return self._screens
        if doctype == "Mobile Screen Role Permission":
            return self._role_perms
        if doctype == "Mobile Screen User Override":
            return self._overrides
        return []

    def throw(self, msg, exc=None):
        raise (exc or _PermissionError)(msg)


def _screen(key, code=None, offline=0):
    return {
        "name": code or f"inventory.{key}",
        "screen_key": key,
        "route_path": f"/{key}",
        "allow_offline_access": offline,
    }


def _can(**flags):
    return {f"can_{a}": flags.get(a, 0) for a in
            ("view", "create", "edit", "delete", "approve", "export")}


@pytest.fixture(autouse=True)
def restore_frappe():
    original = service.frappe
    yield
    service.frappe = original


def _install(fake):
    service.frappe = fake
    service._ = lambda m: m  # noqa: SLF001 - bypass translation in tests


def test_guest_is_denied():
    _install(FakeFrappe(user="Guest"))
    assert service.has_mobile_permission("inventory.dashboard") is False


def test_disabled_user_is_denied():
    _install(FakeFrappe(enabled=0, roles=["Stock User"]))
    assert service.has_mobile_permission("inventory.dashboard") is False


def test_disabled_app_reports_error():
    _install(FakeFrappe(app={"name": "inventory", "is_active": 0,
                             "permission_version": 1}))
    with pytest.raises(service.MobilePermissionError):
        service.build_permission_response(app_key="inventory")


def test_response_shape_only_allowed_screens():
    fake = FakeFrappe(
        roles=["Stock User"],
        screens=[_screen("dashboard", offline=1), _screen("items")],
        role_perms=[{"parent": "inventory.dashboard", **_can(view=1)}],
    )
    _install(fake)
    resp = service.build_permission_response(app_key="inventory")
    assert resp["permission_version"] == 7
    assert resp["cache_ttl_seconds"] == 900
    assert set(resp["screens"]) == {"dashboard"}  # items not granted
    dash = resp["screens"]["dashboard"]
    assert dash["permission_code"] == "inventory.dashboard"
    assert dash["can_view"] is True
    assert dash["can_create"] is False
    assert dash["allow_offline_access"] is True


def test_deny_override_removes_screen():
    fake = FakeFrappe(
        roles=["Stock User"],
        screens=[_screen("dashboard")],
        role_perms=[{"parent": "inventory.dashboard", **_can(view=1)}],
        overrides=[{"parent": "inventory.dashboard", "access_mode": "Deny",
                    "valid_from": None, "valid_until": None, **_can(view=1)}],
    )
    _install(fake)
    resp = service.build_permission_response(app_key="inventory")
    assert resp["screens"] == {}


def test_expired_override_ignored():
    past = datetime(2026, 8, 5, 0, 0, 0)
    fake = FakeFrappe(
        roles=["Stock User"],
        screens=[_screen("dashboard")],
        role_perms=[{"parent": "inventory.dashboard", **_can(view=1)}],
        overrides=[{"parent": "inventory.dashboard", "access_mode": "Deny",
                    "valid_from": None, "valid_until": past, **_can(view=1)}],
    )
    _install(fake)
    resp = service.build_permission_response(app_key="inventory")
    assert "dashboard" in resp["screens"]  # expired deny ignored -> role grant wins


def test_future_override_ignored():
    future = datetime(2026, 8, 6, 12, 0, 0) + timedelta(days=1)
    fake = FakeFrappe(
        roles=[],
        screens=[_screen("secret")],
        overrides=[{"parent": "inventory.secret", "access_mode": "Allow",
                    "valid_from": future, "valid_until": None, **_can(view=1)}],
    )
    _install(fake)
    resp = service.build_permission_response(app_key="inventory")
    assert resp["screens"] == {}  # allow not yet in effect


def test_system_manager_sees_all_active_screens():
    fake = FakeFrappe(
        roles=["System Manager"],
        screens=[_screen("dashboard"), _screen("items")],
        role_perms=[],
    )
    _install(fake)
    resp = service.build_permission_response(app_key="inventory")
    assert set(resp["screens"]) == {"dashboard", "items"}


def test_has_permission_action_level():
    fake = FakeFrappe(
        roles=["Stock User"],
        screens=[_screen("stock_transfer")],
        role_perms=[{"parent": "inventory.stock_transfer", **_can(view=1, create=1)}],
    )
    _install(fake)
    assert service.has_mobile_permission("inventory.stock_transfer", "create") is True
    assert service.has_mobile_permission("inventory.stock_transfer", "delete") is False


def test_unknown_action_is_denied():
    _install(FakeFrappe(roles=["Stock User"]))
    assert service.has_mobile_permission("inventory.dashboard", "teleport") is False
