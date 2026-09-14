"""Idempotently create/update the read-only public demo login referenced in
the project README. Safe to re-run: an existing user just gets its role set
and password refreshed rather than being duplicated.

Roles are the real operational ones the mobile apps' client-side navigation
recognises (Stock User, HR User, Sales User, Accounts User, Agent) -- never
System Manager or Administrator. Write/submit/delete access is independently
stripped for this exact user via services/common/demo_readonly.py regardless
of what these roles would otherwise allow; see that module for why, and add
any new role here to DOCTYPES_READ_ONLY there too if it can reach new
doctypes.
"""

from __future__ import annotations

import frappe

DEMO_USER = "demo@budeglobal.in"
DEMO_ROLES = ["Stock User", "HR User", "Sales User", "Accounts User", "Agent"]


def ensure(password: str) -> str:
    """Create or update the demo user with `password`. Returns the username."""
    if frappe.db.exists("User", DEMO_USER):
        doc = frappe.get_doc("User", DEMO_USER)
    else:
        doc = frappe.get_doc(
            {
                "doctype": "User",
                "email": DEMO_USER,
                "first_name": "Public Demo",
                "enabled": 1,
                "send_welcome_email": 0,
                "user_type": "System User",
            }
        )
        doc.insert(ignore_permissions=True)

    doc.enabled = 1
    doc.new_password = password
    doc.roles = []
    for role in DEMO_ROLES:
        doc.append("roles", {"role": role})
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return DEMO_USER
