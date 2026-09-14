"""Server-side permission service.

Business logic for mobile screen permissions. The whitelisted endpoints in
``bude_api.api.mobile_permissions`` are thin wrappers over these functions.

Security notes:
- The current user is always ``frappe.session.user``; the endpoint never accepts
  a target email from the client. Internal functions accept ``user`` only so the
  admin preview and tests can resolve a chosen user through the SAME code path.
- Reads of the permission DocTypes use ``ignore_permissions=True`` because the
  session user is deliberately NOT allowed to read those config rows. We only
  ever return the caller's own *computed* access, never raw permission records.
"""

from datetime import datetime

try:
    import frappe
    from frappe import _
except ImportError:  # allows import + pure-logic tests without a bench
    frappe = None

    def _(msg):
        return msg

from .constants import (
    ACTIONS,
    ADMINISTRATOR,
    DEFAULT_CACHE_TTL_SECONDS,
    GUEST,
    SYSTEM_MANAGER_ROLE,
)
from .resolver import resolve


def sync_frappe(module):
    """Injection hook used by the api wrapper/tests to swap the frappe module."""
    global frappe
    frappe = module


class MobilePermissionError(Exception):
    """Raised for bad app_key / disabled app so callers can map to a 4xx."""


# --------------------------------------------------------------------------- #
# Session / identity helpers
# --------------------------------------------------------------------------- #
def _current_user(user: str | None) -> str:
    resolved = user or (frappe.session.user if frappe else None)
    if not resolved or resolved == GUEST:
        raise frappe.PermissionError(_("Guest users have no application access."))
    if not _is_user_enabled(resolved):
        raise frappe.PermissionError(_("This user account is disabled."))
    return resolved


def _is_user_enabled(user: str) -> bool:
    if user == ADMINISTRATOR:
        return True
    return bool(frappe.db.get_value("User", user, "enabled"))


def _user_roles(user: str) -> list[str]:
    return list(frappe.get_roles(user))


def _is_privileged(user: str, roles: list[str]) -> bool:
    """Administrator and System Manager get all active screens (documented rule)."""
    return user == ADMINISTRATOR or SYSTEM_MANAGER_ROLE in roles


# --------------------------------------------------------------------------- #
# DocType reads (see module docstring re: ignore_permissions)
# --------------------------------------------------------------------------- #
def _app(app_key: str) -> dict:
    app = frappe.db.get_value(
        "Mobile Application",
        app_key,
        ["name", "is_active", "permission_version"],
        as_dict=True,
    )
    if not app:
        raise MobilePermissionError(_("Unknown application: {0}").format(app_key))
    if not app.is_active:
        raise MobilePermissionError(_("Application is disabled: {0}").format(app_key))
    return app


def _active_screens(app_key: str) -> dict:
    rows = frappe.get_all(
        "Mobile App Screen",
        filters={"app": app_key, "is_active": 1},
        fields=["name", "screen_key", "route_path", "allow_offline_access"],
        ignore_permissions=True,
    )
    return {r["name"]: r for r in rows}


_CAN_COLUMNS = [f"can_{a}" for a in ACTIONS]


def _normalize(row: dict) -> dict:
    """Rename stored ``can_<action>`` columns to the bare keys the resolver uses."""
    out = {k: v for k, v in row.items() if not k.startswith("can_")}
    for action in ACTIONS:
        out[action] = row.get(f"can_{action}")
    return out


def get_role_screen_permissions(roles: list[str], screen_names: list[str]) -> list[dict]:
    """Role grants for the given screens. ``Mobile Screen Role Permission`` is a
    child table of ``Mobile App Screen``; its ``parent`` column IS the screen's
    docname (== permission_code), so filtering by parent replaces the old
    standalone ``app``/``screen`` link fields."""
    if not roles or not screen_names:
        return []
    rows = frappe.get_all(
        "Mobile Screen Role Permission",
        filters={"parent": ["in", screen_names], "is_active": 1, "role": ["in", roles]},
        fields=["parent", *_CAN_COLUMNS],
        ignore_permissions=True,
    )
    for row in rows:
        row["screen"] = row.pop("parent")
    return [_normalize(r) for r in rows]


def get_user_screen_overrides(user: str, screen_names: list[str]) -> list[dict]:
    if not screen_names:
        return []
    rows = frappe.get_all(
        "Mobile Screen User Override",
        filters={"parent": ["in", screen_names], "is_active": 1, "user": user},
        fields=["parent", "access_mode", "valid_from", "valid_until", *_CAN_COLUMNS],
        ignore_permissions=True,
    )
    now = frappe.utils.now_datetime() if frappe else datetime.now()
    out = []
    for row in rows:
        row["screen"] = row.pop("parent")
        if _override_in_window(row, now):
            out.append(_normalize(row))
    return out


def _override_in_window(row: dict, now) -> bool:
    start, end = row.get("valid_from"), row.get("valid_until")
    if start and start > now:
        return False
    if end and end < now:
        return False
    return True


# --------------------------------------------------------------------------- #
# Public resolution API
# --------------------------------------------------------------------------- #
def get_user_mobile_permissions(user: str | None = None, app_key: str = None) -> dict:
    """Effective per-screen flags for ``user`` in ``app_key`` (view-only screens
    already dropped). Keys are permission codes."""
    user = _current_user(user)
    _app(app_key)  # validates app exists and is active (raises otherwise)
    screens = _active_screens(app_key)
    screen_names = list(screens)
    roles = _user_roles(user)
    return resolve(
        role_rows=get_role_screen_permissions(roles, screen_names),
        override_rows=get_user_screen_overrides(user, screen_names),
        all_screen_codes=set(screens),
        is_system_manager=_is_privileged(user, roles),
    )


def build_permission_response(user: str | None = None, app_key: str = None) -> dict:
    """The full endpoint payload: metadata + only-allowed screens keyed by
    screen_key, matching the documented contract."""
    user = _current_user(user)
    app = _app(app_key)
    screens = _active_screens(app_key)
    effective = get_user_mobile_permissions(user, app_key)

    out = {}
    for code, flags in effective.items():
        meta = screens.get(code)
        if not meta:
            continue
        out[meta["screen_key"]] = {
            "permission_code": code,
            "route": meta["route_path"],
            **{f"can_{a}": bool(flags[a]) for a in ACTIONS},
            "allow_offline_access": bool(meta.get("allow_offline_access")),
        }
    return {
        "app_key": app_key,
        "user": user,
        "permission_version": app.permission_version or 1,
        "generated_at": (frappe.utils.now() if frappe else datetime.now().isoformat()),
        "cache_ttl_seconds": DEFAULT_CACHE_TTL_SECONDS,
        "screens": out,
    }


def has_mobile_permission(
    permission_code: str, action: str = "view", user: str | None = None
) -> bool:
    if action not in ACTIONS:
        return False
    app_key = permission_code.split(".", 1)[0]
    try:
        effective = get_user_mobile_permissions(user, app_key)
    except (MobilePermissionError, Exception):
        # Fail closed: any resolution problem denies. PermissionError for Guest/
        # disabled users lands here too, which is the correct default-deny.
        return False
    return bool(effective.get(permission_code, {}).get(action))


def check_mobile_permission(
    permission_code: str, action: str = "view", user: str | None = None
) -> None:
    """Raise ``frappe.PermissionError`` unless the user may perform ``action``."""
    if not has_mobile_permission(permission_code, action, user):
        frappe.throw(
            _("You do not have permission for this action."),
            frappe.PermissionError,
        )
