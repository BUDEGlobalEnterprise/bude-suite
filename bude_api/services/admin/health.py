"""Health check endpoint.

Whitelisted so unauthenticated clients can verify connectivity:

    GET /api/method/bude_api.api.health.ping

Also reports the ERPNext version, resolved server-side. Frappe's own
`frappe.utils.change_log.get_versions` is whitelisted but NOT guest-allowed,
so the mobile onboarding wizard (which probes before any login) cannot call
it directly — this endpoint does it on the guest's behalf.
"""

from datetime import datetime, timezone

try:
    import frappe
    from frappe.utils.change_log import get_versions
except ImportError:
    frappe = None
    get_versions = None

from ... import __version__


def _whitelist(allow_guest: bool = False):
    if frappe is None:
        def decorator(fn):
            return fn
        return decorator
    return frappe.whitelist(allow_guest=allow_guest)


@_whitelist(allow_guest=True)
def ping() -> dict:
    return {
        "status": "ok",
        "service": "bude_api",
        "version": __version__,
        "erpnext_version": _erpnext_version(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _erpnext_version() -> str | None:
    if get_versions is None:
        return None
    try:
        erpnext = get_versions().get("erpnext")
    except Exception:
        return None
    if not erpnext:
        return None
    return erpnext.get("version")
