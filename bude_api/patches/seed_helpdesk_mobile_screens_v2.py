"""Seed the helpdesk app's screen registry and role permissions.

v2: role grants moved from a standalone Mobile Screen Role Permission
doctype to a child table of Mobile App Screen (better Desk UX — an admin
edits one screen's grants as a grid instead of hunting through a separate
list view). Superseded seed_helpdesk_mobile_screens, which used the old
standalone-document shape; this is a fresh dotted path so it runs even
though the original already executed on sites migrated before this change.

Idempotent: skips any record/role-row that already exists, so re-running is
safe. Realises the Stage 1 permission matrix for the pilot app.
"""

from ._seed_shared import seed_app, seed_screens_and_role_grants

APP_KEY = "helpdesk"

# screen_key -> (screen_name, route_path, menu_group, sort_order, sensitive, offline)
SCREENS = {
    "tickets": ("Tickets", "/", "Main", 10, 0, 1),
    "ticket_new": ("New Ticket", "/tickets/new", "Tickets", 15, 0, 0),
    "ticket_detail": ("Ticket Detail", "/tickets/:name", "Tickets", 16, 0, 1),
    "support_pulse": ("Support Pulse", "/agent/pulse", "Agent", 20, 0, 0),
    "agent_queue": ("Agent Queue", "/agent", "Agent", 30, 0, 0),
    "setup_health": ("Setup Health", "/admin/setup", "Admin", 40, 1, 0),
    "automation": ("Automation", "/admin/automation", "Admin", 50, 1, 0),
    "channel_health": ("Channel Health", "/admin/channels", "Admin", 60, 0, 0),
    "pending_queue": ("Pending Queue", "/pending", "Main", 70, 0, 1),
    "settings": ("Settings", "/settings", "Main", 80, 0, 1),
}

# role -> {screen_key: (view, create, edit, delete, approve, export)}
AGENT_GRANTS = {
    "tickets": (1, 1, 1, 0, 0, 0),
    "ticket_new": (1, 1, 0, 0, 0, 0),
    "ticket_detail": (1, 0, 1, 0, 0, 0),
    "support_pulse": (1, 0, 0, 0, 0, 0),
    "agent_queue": (1, 0, 1, 0, 0, 0),
    "pending_queue": (1, 0, 0, 0, 0, 0),
    "settings": (1, 0, 1, 0, 0, 0),
}
MANAGER_GRANTS = {
    **AGENT_GRANTS,
    "setup_health": (1, 0, 1, 0, 1, 0),
    "automation": (1, 0, 1, 0, 1, 0),
    "channel_health": (1, 0, 1, 0, 0, 0),
}
ROLE_GRANTS = {"Agent": AGENT_GRANTS, "Agent Manager": MANAGER_GRANTS}


def execute():
    seed_app(APP_KEY, "Bude Helpdesk")
    seed_screens_and_role_grants(APP_KEY, SCREENS, ROLE_GRANTS)
