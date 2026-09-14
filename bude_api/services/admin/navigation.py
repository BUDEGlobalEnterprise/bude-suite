"""Per-role navigation config — admin write endpoint.

    POST /api/method/bude_api.api.navigation.save   (auth required, admin only)

The config is read back via `bude_api.api.branding.get` (every client already
fetches branding on connect). This module only handles the admin write.

# ponytail: site-wide singleton via get/set_default; promote to a Single DocType
# only if it needs versioning or desk-UI editing.
"""

import json

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success
from .branding import NAV_CONFIG_KEY


def _whitelist(allow_guest: bool = False):
    if frappe is None:
        def decorator(fn):
            return fn
        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=["POST"])


def _is_admin() -> bool:
    if frappe is None:
        return False
    return (
        frappe.session.user == "Administrator"
        or "System Manager" in frappe.get_roles()
    )


@_whitelist(allow_guest=False)
def save(config_json: str) -> dict:
    if frappe is None:
        return failure("Server unavailable.", code="AUTH_NO_SESSION")
    if not _is_admin():
        return failure("Admin only.", code="PERMISSION_DENIED")

    # Validate it parses (and re-serialize to strip anything odd) before storing.
    try:
        parsed = json.loads(config_json)
    except (ValueError, TypeError):
        return failure("Invalid JSON.", code="VALIDATION_INVALID_JSON")
    if not isinstance(parsed, dict):
        return failure("Config must be an object.", code="VALIDATION_INVALID_JSON")

    frappe.db.set_default(NAV_CONFIG_KEY, json.dumps(parsed))
    return success(parsed)
