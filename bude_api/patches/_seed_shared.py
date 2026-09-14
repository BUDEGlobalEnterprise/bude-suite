"""Shared helpers for the per-app mobile-screen seed patches.

Each app's patch defines SCREENS (screen_key -> metadata tuple) and
ROLE_GRANTS (role -> {screen_key: (view, create, edit, delete, approve,
export)}), then calls seed_app + seed_screens_and_role_grants. Role grants are
written as Mobile Screen Role Permission child rows on their Mobile App
Screen — one get_doc + one save per screen, idempotent by role.
"""

import frappe

ACTIONS = ("view", "create", "edit", "delete", "approve", "export")


def seed_app(app_key: str, app_name: str) -> None:
    if not frappe.db.exists("Mobile Application", app_key):
        frappe.get_doc(
            {
                "doctype": "Mobile Application",
                "app_key": app_key,
                "app_name": app_name,
                "is_active": 1,
            }
        ).insert(ignore_permissions=True)


def seed_screens_and_role_grants(app_key: str, screens: dict, role_grants: dict) -> None:
    for table in ("tabMobile Screen Role Permission", "tabMobile Screen User Override"):
        if frappe.db.table_exists(table):
            frappe.db.sql(
                f"ALTER TABLE `{table}` "
                "ADD COLUMN IF NOT EXISTS parent VARCHAR(140), "
                "ADD COLUMN IF NOT EXISTS parentfield VARCHAR(140), "
                "ADD COLUMN IF NOT EXISTS parenttype VARCHAR(140)"
            )

    frappe.reload_doc("bude_api", "doctype", "mobile_screen_role_permission", force=True)
    frappe.reload_doc("bude_api", "doctype", "mobile_screen_user_override", force=True)
    frappe.reload_doc("bude_api", "doctype", "mobile_app_screen", force=True)

    by_screen: dict[str, list] = {}
    for role, grants in role_grants.items():
        if not frappe.db.exists("Role", role):
            continue  # role not installed on this site; skip its grants
        for key, flags in grants.items():
            by_screen.setdefault(key, []).append((role, flags))

    for key, (name, route, group, order, sensitive, offline) in screens.items():
        code = f"{app_key}.{key}"
        if frappe.db.exists("Mobile App Screen", code):
            screen = frappe.get_doc("Mobile App Screen", code)
            is_new = False
        else:
            screen = frappe.get_doc(
                {
                    "doctype": "Mobile App Screen",
                    "app": app_key,
                    "screen_key": key,
                    "screen_name": name,
                    "route_path": route,
                    "menu_group": group,
                    "sort_order": order,
                    "is_active": 1,
                    "is_sensitive": sensitive,
                    "allow_offline_access": offline,
                }
            )
            is_new = True

        existing_roles = {row.role for row in screen.role_permissions}
        changed = is_new
        for role, flags in by_screen.get(key, []):
            if role in existing_roles:
                continue
            row = screen.append("role_permissions", {"role": role, "is_active": 1})
            for action, value in zip(ACTIONS, flags, strict=True):
                setattr(row, f"can_{action}", value)
            changed = True

        if is_new:
            screen.insert(ignore_permissions=True)
        elif changed:
            screen.save(ignore_permissions=True)

    frappe.db.commit()
