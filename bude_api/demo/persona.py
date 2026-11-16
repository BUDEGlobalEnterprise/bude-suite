"""Seed one demo manager who can open every screen of all four apps.

The user manual's screenshots need a login that is not Administrator (whose
password differs per site) and that has real-looking data behind every
screen: their own HR year, a small team with requests waiting for approval,
and a Helpdesk agent profile. Everything goes into one run-id manifest, so
`cleanup.run(run_id)` removes it again.

    bench --site <site> execute bude_api.demo.persona.run \
      --kwargs "{'password': '<choose one>', 'confirm_demo_data': True}"
"""

from __future__ import annotations

from datetime import date, timedelta

try:
    import frappe
except ImportError:  # pragma: no cover
    frappe = None

from .config import make_run_id, require_write_guard
from .hr_seed import HrDemoSeeder

EMAIL = "demo.manager@budeglobal.in"
FIRST, LAST = "Meena", "Raghavan"
ROLES = (
    "Employee", "HR User", "HR Manager", "Leave Approver", "Expense Approver",
    "Stock User", "Stock Manager", "Sales User", "Sales Manager", "Accounts User",
    "Agent", "Agent Manager",
)
# (first, last, department suffix, designation) — departments exist on the
# site as "<name> - <company abbr>"; a missing one is simply left blank.
TEAM = (
    ("Arun", "Kumar", "Operations", "Store Keeper"),
    ("Divya", "Shankar", "Sales", "Sales Executive"),
    ("Farhan", "Ali", "Dispatch", "Support Engineer"),
)


def run(
    password: str,
    company: str | None = None,
    run_id: str | None = None,
    confirm_demo_data: bool = False,
) -> dict:
    tag = run_id or make_run_id("persona")
    require_write_guard(
        run_id=tag,
        site=getattr(getattr(frappe, "local", None), "site", None),
        confirm_demo_data=confirm_demo_data,
    )
    seeder = PersonaSeeder(tag, password=password, company=company)
    manifest = seeder.seed_all()
    seeder.write_manifest(manifest)
    return {"run_id": tag, "user": EMAIL, "employee": manifest.get("employee"),
            "records": {k: v["count"] for k, v in manifest["records"].items()},
            "warnings": manifest["warnings"]}


class PersonaSeeder(HrDemoSeeder):
    def __init__(self, run_id: str, password: str, company: str | None) -> None:
        super().__init__(run_id)
        self.manifest["kind"] = "persona"
        self._password = password
        self._company = company or frappe.db.get_value(
            "Employee", {"user_id": "Administrator"}, "company"
        ) or frappe.defaults.get_global_default("company")
        self._abbr = frappe.db.get_value("Company", self._company, "abbr")

    def seed_all(self) -> dict:
        self._seed_user()
        self._employee_arg = self._employee(FIRST, LAST, "Operations", "Operations Manager",
                                            user=EMAIL, approver="Administrator")
        self._commit()
        if not self._employee_arg:
            return self.manifest
        self._seed_agent()
        super().seed_all()  # the persona's own year of HR records
        try:
            self._seed_team()
            self._commit()
        except Exception as exc:  # pragma: no cover - depends on site state
            self._warn(f"_seed_team failed: {exc}")
            self._rollback()
        return self.manifest

    # -- persona ---------------------------------------------------------- #
    def _seed_user(self) -> None:
        if frappe.db.exists("User", EMAIL):
            user = frappe.get_doc("User", EMAIL)
        else:
            user = frappe.get_doc({"doctype": "User", "email": EMAIL, "first_name": FIRST,
                                   "last_name": LAST, "send_welcome_email": 0,
                                   "user_type": "System User"})
            user.insert(ignore_permissions=True)
        self._record("User", EMAIL)  # dedicated demo login: always ours to remove
        user.add_roles(*[r for r in ROLES if frappe.db.exists("Role", r)])
        from frappe.utils.password import update_password

        update_password(EMAIL, self._password)

    def _employee(self, first, last, dept, designation, user=None, approver=None):
        existing = user and frappe.db.get_value("Employee", {"user_id": user}, "name")
        if existing:
            return existing
        self._emp_seq = getattr(self, "_emp_seq", 0) + 1
        return self._insert({
            "doctype": "Employee",
            # The site's HR-EMP- series lags behind hand-made IDs; name explicitly.
            "__set_name": f"HR-EMP-DEMO-{self._emp_seq:02d}",
            "first_name": first,
            "last_name": last,
            "gender": frappe.db.get_value("Gender", {}, "name"),
            "date_of_birth": "1990-06-15",
            "date_of_joining": str(date.today().replace(year=date.today().year - 2, month=4, day=1)),
            "company": self._company,
            "status": "Active",
            "user_id": user,
            "department": frappe.db.exists("Department", f"{dept} - {self._abbr}") or None,
            "designation": designation if frappe.db.exists("Designation", designation) else None,
            "reports_to": None if user else self._employee_arg,
            "leave_approver": approver or EMAIL,
            "expense_approver": approver or EMAIL,
            "shift_request_approver": approver or EMAIL,
            "cell_number": "+91 98400 12345",
            "company_email": user,
        })

    def _seed_agent(self) -> None:
        if not frappe.db.exists("DocType", "HD Agent") or frappe.db.exists("HD Agent", EMAIL):
            return
        self._insert({"doctype": "HD Agent", "user": EMAIL, "agent_name": f"{FIRST} {LAST}",
                      "is_active": 1})

    # -- team waiting on the persona's approval --------------------------- #
    def _seed_team(self) -> None:
        today = date.today()
        holiday_list = self.employee.get("holiday_list")
        leave_type = "Casual Leave" if frappe.db.exists("Leave Type", "Casual Leave") else None
        shift_type = frappe.db.get_value("Shift Type", {"name": ["like", f"{self.run_id}%"]}, "name")
        for i, (first, last, dept, designation) in enumerate(TEAM):
            emp = self._employee(first, last, dept, designation)
            if not emp:
                continue
            if holiday_list:
                frappe.db.set_value("Employee", emp, "holiday_list", holiday_list)
                self._insert({"doctype": "Holiday List Assignment", "applicable_for": "Employee",
                              "assigned_to": emp, "holiday_list": holiday_list,
                              "from_date": str(date(today.year, 1, 1))}, submit=True)
            # Today tab + attendance exceptions: one present, one late, one absent.
            for back in range(0, 6):
                day = today - timedelta(days=back)
                if day.weekday() == 6:
                    continue
                status = "Absent" if (i == 2 and back == 1) else "Present"
                self._insert({"doctype": "Attendance", "employee": emp, "company": self._company,
                              "attendance_date": str(day), "status": status,
                              "late_entry": 1 if (i == 1 and back in (0, 2)) else 0,
                              "working_hours": 0 if status == "Absent" else 8}, submit=True)
            if leave_type:
                self._insert({"doctype": "Leave Allocation", "employee": emp,
                              "leave_type": leave_type, "new_leaves_allocated": 12,
                              "from_date": str(date(today.year, 1, 1)),
                              "to_date": str(date(today.year, 12, 31))}, submit=True)
                start = today + timedelta(days=7 + i * 3)
                self._insert({"doctype": "Leave Application", "employee": emp,
                              "leave_type": leave_type, "from_date": str(start),
                              "to_date": str(start + timedelta(days=i % 2)),
                              "description": ("Sister's wedding", "Medical check-up",
                                              "Hometown visit")[i],
                              "status": "Open", "company": self._company,
                              "leave_approver": EMAIL})
            self.employee, saved = {"name": emp, "company": self._company}, self.employee
            amount = (860.0, 2150.0, 540.0)[i]
            self._insert({
                "doctype": "Expense Claim", "employee": emp, "company": self._company,
                "posting_date": str(today - timedelta(days=2 + i)), "expense_approver": EMAIL,
                "currency": self._currency(), "exchange_rate": 1,
                "payable_account": self._payable_account(), "approval_status": "Draft",
                "expenses": [{"expense_date": str(today - timedelta(days=2 + i)),
                              "expense_type": "Travel" if frappe.db.exists(
                                  "Expense Claim Type", "Travel") else None,
                              "description": ("Courier charges for urgent dispatch",
                                              "Customer visit — Tiruppur, fuel and tolls",
                                              "Site visit auto fare")[i],
                              "amount": amount, "sanctioned_amount": amount,
                              "default_account": self._expense_account(),
                              "cost_center": self._cost_center()}],
            })
            self.employee = saved
            if shift_type:
                day = today + timedelta(days=3 + i)
                self._insert({"doctype": "Shift Request", "employee": emp,
                              "shift_type": shift_type, "from_date": str(day), "to_date": str(day),
                              "status": "Draft", "company": self._company, "approver": EMAIL})
