"""Permission-version bumping for cache invalidation.

Wired to ``on_update``/``on_trash`` of Mobile App Screen via hooks. Role grants
and user overrides are child tables of that doctype, so editing either grid and
saving the screen already fires this — no separate hook needed for them. Any
change increments the owning ``Mobile Application.permission_version``, which
tells every Flutter client its cached permissions are stale on next check.

We intentionally do NOT keep a server-side response cache (permission_version +
the client cache already deliver freshness/offline). If a hot resolve query ever
shows up in profiling, add a version-keyed cache here — never one that can
outlive a DENY or a disabled user.
"""

try:
    import frappe
except ImportError:
    frappe = None


def _app_of(doc) -> str | None:
    return getattr(doc, "app", None)


def bump_app_version(doc, method=None) -> None:
    """doc_events handler for permission DocTypes."""
    if frappe is None:
        return
    app_key = _app_of(doc)
    if not app_key:
        return
    current = frappe.db.get_value("Mobile Application", app_key, "permission_version") or 0
    frappe.db.set_value(
        "Mobile Application", app_key, "permission_version", current + 1
    )
