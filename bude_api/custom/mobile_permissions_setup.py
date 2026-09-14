"""Idempotent setup for the mobile permission system.

Runs after install/migrate (see hooks). Creates the manager role and registers
the four Flutter apps. No ERPNext core is touched — these are records in the
bude_api custom app's own DocTypes.
"""

try:
    import frappe
except ImportError:  # pragma: no cover
    frappe = None

from ..services.mobile_permissions.constants import MOBILE_PERMISSION_MANAGER_ROLE

# app_key -> display name. Confirmed identifiers; the prefix is permanent.
MOBILE_APPS = {
    "inventory": "Bude Inventory (RFID Stock)",
    "helpdesk": "Bude Helpdesk",
    "hr": "Bude HR",
    "sales": "Bude Sales",
}


def ensure_mobile_permission_setup(*args, **kwargs) -> None:
    if frappe is None:
        return
    _ensure_role()
    _ensure_apps()


def _ensure_role() -> None:
    if not frappe.db.exists("Role", MOBILE_PERMISSION_MANAGER_ROLE):
        frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": MOBILE_PERMISSION_MANAGER_ROLE,
                "desk_access": 1,
            }
        ).insert(ignore_permissions=True)


def _ensure_apps() -> None:
    for app_key, app_name in MOBILE_APPS.items():
        if not frappe.db.exists("Mobile Application", app_key):
            frappe.get_doc(
                {
                    "doctype": "Mobile Application",
                    "app_key": app_key,
                    "app_name": app_name,
                    "is_active": 1,
                    "permission_version": 1,
                }
            ).insert(ignore_permissions=True)
