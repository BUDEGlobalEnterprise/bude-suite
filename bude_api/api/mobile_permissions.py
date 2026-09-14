"""Whitelisted endpoints for mobile screen permissions.

    GET  /api/method/bude_api.api.mobile_permissions.get_my_mobile_permissions
    GET  /api/method/bude_api.api.mobile_permissions.get_effective_permission_preview  (admin)
    POST /api/method/bude_api.api.mobile_permissions.invalidate_permission_cache        (admin)

Logic lives in ``bude_api.services.mobile_permissions``. These wrappers only
handle whitelisting, session identity, and admin gating.
"""

try:
    import frappe
    from frappe import _
except ImportError:
    frappe = None

    def _(msg):
        return msg

from ..services.mobile_permissions import service, versioning
from ..services.mobile_permissions.constants import (
    MOBILE_PERMISSION_MANAGER_ROLE,
    SYSTEM_MANAGER_ROLE,
)
from ..utils.response import failure, success


def _whitelist(methods=None, allow_guest=False):
    if frappe is None:
        def decorator(fn):
            return fn
        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=methods or ["GET"])


def _require_permission_admin() -> None:
    roles = set(frappe.get_roles())
    if frappe.session.user == "Administrator":
        return
    if roles & {SYSTEM_MANAGER_ROLE, MOBILE_PERMISSION_MANAGER_ROLE}:
        return
    frappe.throw(_("Not permitted."), frappe.PermissionError)


@_whitelist(methods=["GET", "POST"])
def get_my_mobile_permissions(app_key: str):
    """Permissions for the CURRENT session user only. Never takes a user arg."""
    try:
        return success(service.build_permission_response(app_key=app_key))
    except service.MobilePermissionError as exc:
        # Bad/disabled app_key — generic, no internal rule leakage.
        return failure(str(exc), code="PERMISSION_INVALID_APP")


@_whitelist(methods=["GET"])
def get_effective_permission_preview(user: str, app_key: str):
    """Admin-only: preview another user's effective access."""
    _require_permission_admin()
    try:
        return success(service.build_permission_response(user=user, app_key=app_key))
    except service.MobilePermissionError as exc:
        return failure(str(exc), code="PERMISSION_INVALID_APP")


@_whitelist(methods=["POST"])
def invalidate_permission_cache(app_key: str):
    """Admin-only 'Refresh access' action: bumps permission_version so every
    client refetches on next check."""
    _require_permission_admin()
    app = frappe.db.exists("Mobile Application", app_key)
    if not app:
        return failure(_("Unknown application."), code="PERMISSION_INVALID_APP")
    versioning.bump_app_version(frappe._dict(app=app_key))
    return success({"app_key": app_key})
