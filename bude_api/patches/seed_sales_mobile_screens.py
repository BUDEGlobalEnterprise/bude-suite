"""Seed the Sales app's screen registry and role permissions.

Role model matches bude_api.services.common.permissions.SALES_ROLES and the
Flutter session's isSalesManager:
  base    = Sales User, Sales Manager, Accounts User, System Manager
  manager = Sales Manager, System Manager
Base roles get every screen except manager/setup_doctor. Sales Manager gets
everything. System Manager gets everything automatically via the resolver's
broad grant.

Idempotent: skips any record/role-row that already exists.
"""

from ._seed_shared import seed_app, seed_screens_and_role_grants

APP_KEY = "sales"

# screen_key -> (screen_name, route_path, menu_group, sort_order, sensitive, offline)
SCREENS = {
    "crm_today": ("Today", "/", "CRM", 10, 0, 1),
    "leads": ("Leads", "/leads", "CRM", 20, 0, 0),
    "pipeline": ("Pipeline", "/pipeline", "CRM", 30, 0, 0),
    "crm_tasks": ("Tasks", "/crm-tasks", "CRM", 40, 0, 0),
    "sales_dashboard": ("Sales Dashboard", "/sales-dashboard", "Sales", 50, 0, 0),
    "customers": ("Customers", "/customers", "Sales", 60, 0, 1),
    "sell": ("Sell", "/sell", "Sales", 70, 0, 1),
    "field_day": ("Field Day", "/field-day", "Sales", 80, 0, 0),
    "collections": ("Collections", "/collections", "Sales", 90, 0, 0),
    "manager": ("Team", "/manager", "Admin", 100, 1, 0),
    "pending": ("Pending Sync", "/pending", "Sales", 110, 0, 1),
    "settings": ("Settings", "/settings", "Sales", 120, 0, 1),
    "setup_doctor": ("Setup Doctor", "/setup-doctor", "Admin", 130, 1, 0),
}

BASE_KEYS = [k for k in SCREENS if k not in ("manager", "setup_doctor")]

# role -> {screen_key: (view, create, edit, delete, approve, export)}
BASE_GRANTS = {k: (1, 1, 1, 0, 0, 0) for k in BASE_KEYS}
SALES_MANAGER_GRANTS = {k: (1, 1, 1, 1, 1, 1) for k in SCREENS}
ROLE_GRANTS = {
    "Sales User": BASE_GRANTS,
    "Accounts User": BASE_GRANTS,
    "Sales Manager": SALES_MANAGER_GRANTS,
}


def execute():
    seed_app(APP_KEY, "Bude Sales")
    seed_screens_and_role_grants(APP_KEY, SCREENS, ROLE_GRANTS)
