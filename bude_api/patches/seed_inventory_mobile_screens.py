"""Seed the Inventory (RFID stock) app's screen registry and role permissions.

screen_key values are the same `id`s already used by the Flutter app's
`allNavigationDestinations` (lib/core/ui/navigation_config.dart) — that list
is the source of truth for which screens exist, their routes, and their
managerOnly/operationsOnly/salesOnly flags; this patch mirrors it server-side.

Role model matches bude_api.services.common.permissions.STOCK_EXECUTION_ROLES
/ SALES_ROLES and navigation_config.dart's canAccessManagerDestinations /
canAccessSalesDestinations:
  Stock User    = base screens + operations screens
  Stock Manager = base + operations + manager-only screens (full control)
  Sales User / Sales Manager / Accounts User = base screens + the Sales screen
System Manager gets everything automatically via the resolver's broad grant.

Idempotent: skips any record/role-row that already exists.
"""

from ._seed_shared import seed_app, seed_screens_and_role_grants

APP_KEY = "inventory"

# screen_key -> (screen_name, route_path, menu_group, sort_order, sensitive, offline)
SCREENS = {
    "dashboard": ("Dashboard", "/", "Inventory", 10, 0, 1),
    "today": ("Today", "/today", "Inventory", 20, 0, 1),
    "search": ("Search", "/items", "Inventory", 30, 0, 1),
    "lookup": ("Lookup", "/lookup", "Inventory", 40, 0, 1),
    "tasks": ("Tasks", "/tasks", "Operations", 50, 0, 1),
    "transfer": ("Transfer", "/transfer", "Operations", 60, 0, 1),
    "receipt": ("Receive", "/receipt", "Operations", 70, 0, 1),
    "count": ("Count", "/reconcile", "Operations", 80, 0, 1),
    "fulfillment": ("Fulfill", "/fulfillment", "Operations", 90, 0, 1),
    "sales": ("Sales", "/sales", "Operations", 100, 0, 0),
    "labels": ("Labels", "/labels", "Operations", 110, 0, 0),
    "assets": ("Assets", "/assets", "Assets", 120, 0, 0),
    "asset_movement": ("Move Asset", "/asset-movement", "Assets", 130, 0, 0),
    "asset_repair": ("Repair Asset", "/asset-repair", "Assets", 140, 0, 0),
    "warehouses": ("Warehouses", "/warehouses", "Admin", 150, 1, 0),
    "masters": ("Master Data", "/masters", "Admin", 160, 1, 0),
    "admin_onboarding": ("Onboarding", "/admin-onboarding", "Admin", 170, 1, 0),
    "analytics": ("Analytics", "/analytics", "Analytics", 180, 1, 0),
    "stock_aging": ("Stock Aging", "/analytics/aging", "Analytics", 190, 1, 0),
    "variance": ("Variance", "/analytics/variance", "Analytics", 200, 1, 0),
    "throughput": ("Throughput", "/analytics/throughput", "Analytics", 210, 1, 0),
    "export": ("Export", "/analytics/export", "Analytics", 220, 1, 0),
    "alerts": ("Alerts", "/alerts", "System", 230, 0, 1),
    "exceptions": ("Exceptions", "/exceptions", "System", 240, 1, 0),
    "reports": ("Reports", "/reports", "Analytics", 250, 1, 0),
    "audit": ("Audit Trail", "/audit", "System", 260, 1, 0),
    "sync": ("Sync", "/sync", "System", 270, 0, 1),
    "settings": ("Settings", "/settings", "System", 280, 0, 1),
}

BASE_KEYS = ["dashboard", "search", "lookup", "assets", "alerts", "audit", "sync", "settings"]
OPS_KEYS = [
    "today", "tasks", "transfer", "receipt", "count", "fulfillment", "labels",
    "asset_movement", "asset_repair",
]
MANAGER_KEYS = [
    "warehouses", "masters", "admin_onboarding", "analytics", "stock_aging",
    "variance", "throughput", "export", "exceptions", "reports",
]
SALES_KEYS = ["sales"]

_EXECUTE = (1, 1, 1, 0, 0, 0)  # view, create, edit
_FULL = (1, 1, 1, 1, 1, 1)  # every action
_VIEW_ONLY = (1, 0, 0, 0, 0, 0)

STOCK_USER_GRANTS = {k: _EXECUTE for k in BASE_KEYS + OPS_KEYS}
STOCK_MANAGER_GRANTS = {k: _FULL for k in BASE_KEYS + OPS_KEYS + MANAGER_KEYS}
SALES_ROLE_GRANTS = {k: _EXECUTE for k in BASE_KEYS + SALES_KEYS}
ACCOUNTS_USER_GRANTS = {k: _VIEW_ONLY for k in BASE_KEYS + SALES_KEYS}

ROLE_GRANTS = {
    "Stock User": STOCK_USER_GRANTS,
    "Stock Manager": STOCK_MANAGER_GRANTS,
    "Sales User": SALES_ROLE_GRANTS,
    "Sales Manager": SALES_ROLE_GRANTS,
    "Accounts User": ACCOUNTS_USER_GRANTS,
}


def execute():
    seed_app(APP_KEY, "Bude Inventory (RFID Stock)")
    seed_screens_and_role_grants(APP_KEY, SCREENS, ROLE_GRANTS)
