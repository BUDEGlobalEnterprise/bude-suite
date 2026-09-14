"""Seed the HR app's screen registry and role permissions.

Role model matches bude_api.services.hr._mobile_shared:
  HR_ROLES      = Employee, HR User, HR Manager, System Manager
  MANAGER_ROLES = HR User, HR Manager, System Manager, Leave Approver, Expense Approver
Employee gets every screen except Manager. HR User/HR Manager get everything.
System Manager gets everything automatically via the resolver's broad grant.

Idempotent: skips any record/role-row that already exists.
"""

from ._seed_shared import seed_app, seed_screens_and_role_grants

APP_KEY = "hr"

# screen_key -> (screen_name, route_path, menu_group, sort_order, sensitive, offline)
SCREENS = {
    "dashboard": ("Dashboard", "/", "Main", 10, 0, 1),
    "attendance": ("Attendance", "/attendance", "Main", 20, 0, 1),
    "leave": ("Leave", "/leave", "Main", 30, 0, 1),
    "requests": ("Requests", "/requests", "Main", 40, 0, 0),
    "shift_roster": ("Shift Roster", "/shift-roster", "Main", 50, 0, 0),
    "expenses": ("Expenses", "/expenses", "Main", 60, 0, 0),
    "salary": ("Salary", "/salary", "Sensitive", 70, 1, 0),
    "profile": ("Profile", "/profile", "Main", 80, 0, 1),
    "notifications": ("Notifications", "/notifications", "Main", 90, 0, 0),
    "pending": ("Pending Sync", "/pending", "Main", 100, 0, 1),
    "manager": ("Manager", "/manager", "Admin", 110, 1, 0),
    "settings": ("Settings", "/settings", "Main", 120, 0, 1),
}

# role -> {screen_key: (view, create, edit, delete, approve, export)}
EMPLOYEE_GRANTS = {
    "dashboard": (1, 1, 1, 0, 0, 0),
    "attendance": (1, 1, 1, 0, 0, 0),
    "leave": (1, 1, 1, 0, 0, 0),
    "requests": (1, 1, 1, 0, 0, 0),
    "shift_roster": (1, 1, 1, 0, 0, 0),
    "expenses": (1, 1, 1, 0, 0, 0),
    "salary": (1, 1, 1, 0, 0, 0),
    "profile": (1, 1, 1, 0, 0, 0),
    "notifications": (1, 1, 1, 0, 0, 0),
    "pending": (1, 1, 1, 0, 0, 0),
    "settings": (1, 1, 1, 0, 0, 0),
}
HR_USER_GRANTS = {**EMPLOYEE_GRANTS, "manager": (1, 1, 1, 0, 1, 0)}
HR_MANAGER_GRANTS = {k: (1, 1, 1, 1, 1, 1) for k in SCREENS}
ROLE_GRANTS = {
    "Employee": EMPLOYEE_GRANTS,
    "HR User": HR_USER_GRANTS,
    "HR Manager": HR_MANAGER_GRANTS,
}


def execute():
    seed_app(APP_KEY, "Bude HR")
    seed_screens_and_role_grants(APP_KEY, SCREENS, ROLE_GRANTS)
