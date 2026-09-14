"""Seed realistic HR demo data for one employee.

The HR mobile app has a lot of screens that only mean anything with records
behind them — a leave calendar, a payslip list, a requests inbox. A site with
zero Leave Applications and zero Salary Slips renders as a wall of empty
states, which makes the app impossible to review or screenshot.

This seeds one employee's year: attendance, leave, expenses, advances, the
whole requests inbox, and three months of payroll. It deliberately reuses the
existing demo machinery rather than inventing a parallel one:

* `require_write_guard` — refuses to write unless the target is clearly a
  local/dev site, or the caller explicitly passes `confirm_demo_data=True`.
* the run-id manifest — every record created is written to
  `demo_runs/<run_id>/manifest.json`, which is exactly what `cleanup.run()`
  reads to reverse a seed. Nothing here is unremovable.

Every block is independently fault-tolerant: a site missing a doctype or a
dependency records a warning and the rest still seeds. Partial data is far
more useful than an all-or-nothing seeder that aborts on the first surprise.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

try:
    import frappe
except ImportError:  # pragma: no cover - frappe is absent in unit tests
    frappe = None

from .config import demo_runs_root, make_run_id, require_write_guard

# Deliberately modest: enough rows to exercise lists, filters, calendars and
# pagination without turning a review site into a data dump.
ATTENDANCE_DAYS = 45
CHECKIN_DAYS = 10
PAYSLIP_MONTHS = 3

# The lists behind the app's dropdowns. A stock ERPNext + HRMS install ships
# most of these, but a bare site does not, and an empty list makes a working
# screen look broken. Only missing entries are created — see `_ensure_master`.
MASTER_LISTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Leave Type also gates which leaves can be allocated below.
    (
        "Leave Type",
        ("Casual Leave", "Sick Leave", "Privilege Leave", "Compensatory Off", "Leave Without Pay"),
    ),
    ("Expense Claim Type", ("Travel", "Food", "Medical", "Calls", "Others")),
    ("Activity Type", ("Execution", "Planning", "Research", "Communication")),
    ("Purpose of Travel", ("Customer visit", "Conference", "Training", "Internal review")),
    ("Grievance Type", ("General", "Workplace", "Payroll", "Facilities")),
    ("Employee Grade", ("L1", "L2", "L3", "L4")),
    ("Branch", ("Head Office", "Warehouse")),
    ("Employment Type", ("Full-time", "Part-time", "Contract", "Intern")),
)


def run(
    run_id: str | None = None,
    employee: str | None = None,
    dry_run: bool = False,
    confirm_demo_data: bool = False,
    base_url: str | None = None,
) -> dict:
    """Seed HR demo data and return the manifest `cleanup.run()` consumes."""
    tag = run_id or make_run_id("hr")
    if not dry_run:
        site = getattr(getattr(frappe, "local", None), "site", None) if frappe else None
        require_write_guard(
            run_id=tag,
            site=site,
            base_url=base_url,
            confirm_demo_data=confirm_demo_data,
        )
    seeder = HrDemoSeeder(tag, employee=employee, dry_run=dry_run)
    manifest = seeder.seed_all()
    seeder.write_manifest(manifest)
    return manifest


class HrDemoSeeder:
    def __init__(
        self,
        run_id: str,
        employee: str | None = None,
        dry_run: bool = False,
    ) -> None:
        self.run_id = run_id
        self.dry_run = dry_run
        self._employee_arg = employee
        self._savepoint_seq = 0
        self.employee: dict[str, Any] = {}
        # No document may be dated before the employee joined — ERPNext
        # rejects those outright. Set once the employee is resolved.
        self.floor: date | None = None
        self.manifest: dict[str, Any] = {
            "run_id": run_id,
            "kind": "hr",
            "dry_run": dry_run,
            "records": {},
            "warnings": [],
        }

    # -- orchestration ---------------------------------------------------- #
    def seed_all(self) -> dict:
        if frappe is None and not self.dry_run:
            raise RuntimeError("Frappe is not available. Run inside a Frappe bench.")
        if not self._resolve_employee():
            return self.manifest

        # Ordered by dependency: scaffolding first, then the documents that
        # reference it.
        for step in (
            self._seed_masters,
            self._seed_holiday_list,
            self._seed_shift_type,
            self._seed_attendance,
            self._seed_checkins,
            self._seed_leave,
            self._seed_expense_claims,
            self._seed_advances,
            self._seed_travel_requests,
            self._seed_grievance,
            self._seed_attendance_requests,
            self._seed_shift_requests,
            self._seed_timesheets,
            self._seed_payroll,
            self._seed_tax_declaration,
        ):
            try:
                step()
                self._commit()
            except Exception as exc:  # pragma: no cover - depends on site state
                self._warn(f"{step.__name__} failed: {exc}")
                self._rollback()
        return self.manifest

    def write_manifest(self, manifest: dict) -> Path:
        root = demo_runs_root() / self.run_id
        root.mkdir(parents=True, exist_ok=True)
        path = root / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return path

    # -- employee resolution ---------------------------------------------- #
    def _resolve_employee(self) -> bool:
        """Default to the Employee linked to the signed-in Administrator, so a
        reviewer logging in as Administrator actually sees this data."""
        if self.dry_run:
            self.employee = {"name": self._employee_arg or "HR-EMP-DRYRUN"}
            return True
        name = self._employee_arg
        if not name:
            name = frappe.db.get_value("Employee", {"user_id": "Administrator"}, "name")
        if not name:
            name = frappe.db.get_value("Employee", {"status": "Active"}, "name")
        if not name:
            self._warn("No Employee record found — nothing to seed against.")
            return False
        row = frappe.db.get_value(
            "Employee",
            name,
            ["name", "company", "date_of_joining", "holiday_list", "department"],
            as_dict=True,
        )
        self.employee = dict(row or {"name": name})
        self.manifest["employee"] = self.employee.get("name")
        joined = self.employee.get("date_of_joining")
        if joined:
            self.floor = joined if isinstance(joined, date) else date.fromisoformat(str(joined)[:10])
        return True

    def _from(self, day: date) -> date:
        """Clamp a seeded date to the employee's joining date."""
        return max(day, self.floor) if self.floor else day

    def _before_joining(self, day: date) -> bool:
        return self.floor is not None and day < self.floor

    # -- scaffolding ------------------------------------------------------ #
    def _seed_masters(self) -> None:
        """Fill in any dropdown list this site is missing."""
        for doctype, values in MASTER_LISTS:
            if not self.dry_run and not frappe.db.exists("DocType", doctype):
                continue
            for value in values:
                self._ensure_master(doctype, value)

    def _ensure_master(self, doctype: str, value: str) -> None:
        """Create one master entry, but only when the site does not have it.

        Anything already present is left alone and stays out of the manifest,
        so cleanup can never delete a list the site owned before this ran.
        """
        if self.dry_run:
            self._record(doctype, value)
            return
        if frappe.db.exists(doctype, value):
            return
        # Masters name themselves differently — some from a field, some from
        # the name given — so ask the doctype rather than guess per list.
        autoname = (frappe.get_meta(doctype).autoname or "").strip()
        payload: dict[str, Any] = {"doctype": doctype}
        if autoname.startswith("field:"):
            payload[autoname.split(":", 1)[1]] = value
        else:
            payload["__newname"] = value
        self._insert(payload)

    def _seed_holiday_list(self) -> None:
        """Leave balances and the calendar both read the holiday list; without
        one the leave screens look broken rather than empty."""
        today = date.today()
        start, end = date(today.year, 1, 1), date(today.year, 12, 31)
        holidays = []
        cursor = start
        while cursor <= end:  # weekends
            if cursor.weekday() == 6:
                holidays.append({"holiday_date": str(cursor), "description": "Sunday"})
            cursor += timedelta(days=1)
        for month, day, label in ((1, 1, "New Year"), (5, 1, "Labour Day"), (12, 25, "Holiday")):
            holidays.append(
                {"holiday_date": str(date(today.year, month, day)), "description": label}
            )
        name = self._insert(
            {
                "doctype": "Holiday List",
                "holiday_list_name": f"{self.run_id} Holidays {today.year}",
                "from_date": str(start),
                "to_date": str(end),
                "holidays": holidays,
            }
        )
        if name and not self.dry_run:
            # Attach it to the employee so leave/attendance screens resolve it.
            frappe.db.set_value("Employee", self.employee["name"], "holiday_list", name)
            # Newer HRMS resolves holidays through Holiday List Assignment
            # instead of that field. Without an assignment, attendance
            # requests, comp-off and salary slips are all rejected with
            # "No Holiday List was found for Employee".
            if frappe.db.exists("DocType", "Holiday List Assignment"):
                self._insert(
                    {
                        "doctype": "Holiday List Assignment",
                        "applicable_for": "Employee",
                        "assigned_to": self.employee["name"],
                        "holiday_list": name,
                        "from_date": str(start),
                    },
                    submit=True,
                )
            self.employee["holiday_list"] = name

    def _seed_shift_type(self) -> None:
        self._insert(
            {
                "doctype": "Shift Type",
                "name": f"{self.run_id} Day Shift",
                "start_time": "09:00:00",
                "end_time": "18:00:00",
            }
        )

    # -- attendance ------------------------------------------------------- #
    def _seed_attendance(self) -> None:
        today = date.today()
        for offset in range(1, ATTENDANCE_DAYS + 1):
            day = today - timedelta(days=offset)
            if day.weekday() == 6:  # matches the seeded holiday list
                continue
            if self._before_joining(day):
                break
            status = "Present"
            if offset % 17 == 0:
                status = "Absent"
            elif offset % 11 == 0:
                status = "Half Day"
            self._insert(
                {
                    "doctype": "Attendance",
                    "employee": self.employee["name"],
                    "attendance_date": str(day),
                    "status": status,
                    "company": self.employee.get("company"),
                    "working_hours": 0 if status == "Absent" else (4 if status == "Half Day" else 8),
                    "late_entry": 1 if offset % 7 == 0 else 0,
                    "early_exit": 1 if offset % 13 == 0 else 0,
                },
                submit=True,
            )

    def _seed_checkins(self) -> None:
        today = date.today()
        for offset in range(1, CHECKIN_DAYS + 1):
            day = today - timedelta(days=offset)
            if day.weekday() == 6:
                continue
            if self._before_joining(day):
                break
            for hour, log_type in ((9, "IN"), (18, "OUT")):
                self._insert(
                    {
                        "doctype": "Employee Checkin",
                        "employee": self.employee["name"],
                        "time": f"{day} {hour:02d}:05:00",
                        "log_type": log_type,
                    }
                )

    # -- leave ------------------------------------------------------------ #
    def _seed_leave(self) -> None:
        today = date.today()
        year_start = self._from(date(today.year, 1, 1))
        year_end = date(today.year, 12, 31)
        leave_types = [
            t for t in ("Casual Leave", "Sick Leave", "Privilege Leave")
            if self.dry_run or frappe.db.exists("Leave Type", t)
        ]
        if not leave_types:
            self._warn("No usable Leave Type found; skipping leave.")
            return

        for leave_type, days in zip(leave_types, (12, 8, 15), strict=False):
            self._insert(
                {
                    "doctype": "Leave Allocation",
                    "employee": self.employee["name"],
                    "leave_type": leave_type,
                    "from_date": str(year_start),
                    "to_date": str(year_end),
                    "new_leaves_allocated": days,
                },
                submit=True,
            )

        # One of each status so the list, the status chips and the detail
        # screen's cancel affordance all have something to render.
        plans = [
            (leave_types[0], today + timedelta(days=4), 2, "Approved", "Family function"),
            (leave_types[0], today + timedelta(days=10), 1, "Open", "Personal errand"),
        ]
        if len(leave_types) > 1:
            plans.append(
                (leave_types[1], today + timedelta(days=25), 1, "Approved", "Fever")
            )
        for leave_type, start, span, status, reason in plans:
            end = start + timedelta(days=span - 1)
            self._insert(
                {
                    "doctype": "Leave Application",
                    "employee": self.employee["name"],
                    "leave_type": leave_type,
                    "from_date": str(start),
                    "to_date": str(end),
                    "description": reason,
                    "status": status,
                    "company": self.employee.get("company"),
                    "leave_approver": self._approver("leave_approver"),
                },
                submit=status == "Approved",
            )

    # -- expenses & advances ---------------------------------------------- #
    def _seed_expense_claims(self) -> None:
        today = date.today()
        claims = [
            ("Travel", 1250.0, "Client site visit — taxi and parking", True),
            ("Food", 320.0, "Team lunch during stock count", True),
            ("Others", 480.0, "Replacement scanner strap", False),
        ]
        account = self._expense_account()
        cost_center = self._cost_center()
        for claim_type, amount, description, submit in claims:
            if not self.dry_run and not frappe.db.exists("Expense Claim Type", claim_type):
                continue
            posting = self._from(today - timedelta(days=len(description) % 25 + 3))
            self._insert(
                {
                    "doctype": "Expense Claim",
                    "employee": self.employee["name"],
                    "company": self.employee.get("company"),
                    "posting_date": str(posting),
                    "expense_approver": self._approver(),
                    "currency": self._currency(),
                    "exchange_rate": 1,
                    "payable_account": self._payable_account(),
                    # A submitted claim without this is rejected outright.
                    "approval_status": "Approved" if submit else "Draft",
                    "expenses": [
                        {
                            "expense_date": str(posting),
                            "expense_type": claim_type,
                            "description": description,
                            "amount": amount,
                            "sanctioned_amount": amount,
                            "default_account": account,
                            "cost_center": cost_center,
                        }
                    ],
                },
                submit=submit,
            )

    def _seed_advances(self) -> None:
        today = date.today()
        for purpose, amount, offset in (
            ("Site travel float", 5000.0, 12),
            ("Conference registration", 2500.0, 30),
        ):
            self._insert(
                {
                    "doctype": "Employee Advance",
                    "employee": self.employee["name"],
                    "company": self.employee.get("company"),
                    "posting_date": str(today - timedelta(days=offset)),
                    "purpose": purpose,
                    "advance_amount": amount,
                    "exchange_rate": 1,
                }
            )

    # -- request inbox ---------------------------------------------------- #
    def _seed_travel_requests(self) -> None:
        today = date.today()
        self._insert(
            {
                "doctype": "Travel Request",
                "employee": self.employee["name"],
                "travel_type": "Domestic",
                "purpose_of_travel": self._travel_purpose(),
                "description": "Two-day onsite visit to configure handheld readers.",
                "travel_funding": "Require Full Funding",
                "date_of_departure": str(today + timedelta(days=14)),
                "date_of_return": str(today + timedelta(days=16)),
            }
        )

    def _seed_grievance(self) -> None:
        today = date.today()
        self._insert(
            {
                "doctype": "Employee Grievance",
                "raised_by": self.employee["name"],
                "subject": "Workstation ergonomics",
                "date": str(self._from(today - timedelta(days=6))),
                "description": "Requesting an adjustable chair for the packing desk.",
                "status": "Open",
                "grievance_type": self._grievance_type(),
                # Grievance Against is a Dynamic Link; pointing it at the
                # employee's own department keeps the demo record impersonal.
                "grievance_against_party": "Department"
                if self.employee.get("department")
                else "Company",
                "grievance_against": self.employee.get("department")
                or self.employee.get("company"),
            }
        )

    def _travel_purpose(self) -> str | None:
        if self.dry_run:
            return None
        return frappe.db.get_value("Purpose of Travel", {}, "name")

    def _grievance_type(self) -> str | None:
        if self.dry_run:
            return None
        return frappe.db.get_value("Grievance Type", {}, "name")

    def _seed_attendance_requests(self) -> None:
        today = date.today()
        # HRMS rejects a request that would not change anything, and this
        # seeder has already marked every recent working day. Target a day it
        # marked Absent so the request actually regularises something.
        start = self._absent_day() or today - timedelta(days=9)
        self._insert(
            {
                "doctype": "Attendance Request",
                "employee": self.employee["name"],
                "company": self.employee.get("company"),
                "from_date": str(start),
                "to_date": str(start),
                "reason": "On Duty",
                "explanation": "Offsite customer training; forgot to check in.",
            }
        )
        # Comp-off is only valid for a day that is actually a holiday — the
        # seeded holiday list makes every Sunday one.
        comp_day = self._recent_sunday()
        if comp_day is None:
            self._warn("No seeded holiday in range; skipping comp-off request.")
            return
        # Working that holiday is the thing being compensated, so the
        # attendance has to exist before the request will validate.
        self._insert(
            {
                "doctype": "Attendance",
                "employee": self.employee["name"],
                "attendance_date": str(comp_day),
                "status": "Present",
                "company": self.employee.get("company"),
                "working_hours": 8,
            },
            submit=True,
        )
        self._insert(
            {
                "doctype": "Compensatory Leave Request",
                "employee": self.employee["name"],
                "work_from_date": str(comp_day),
                "work_end_date": str(comp_day),
                "reason": "Weekend go-live support",
                "leave_type": "Compensatory Off",
            }
        )

    def _absent_day(self) -> date | None:
        """The most recent day _seed_attendance marked Absent (offset % 17)."""
        today = date.today()
        for offset in range(17, ATTENDANCE_DAYS + 1, 17):
            day = today - timedelta(days=offset)
            if day.weekday() != 6 and not self._before_joining(day):
                return day
        return None

    def _recent_sunday(self) -> date | None:
        today = date.today()
        for offset in range(1, ATTENDANCE_DAYS + 1):
            day = today - timedelta(days=offset)
            if day.weekday() == 6 and not self._before_joining(day):
                return day
        return None

    def _seed_shift_requests(self) -> None:
        today = date.today()
        shift = f"{self.run_id} Day Shift"
        if not self.dry_run and not frappe.db.exists("Shift Type", shift):
            return
        if not self.dry_run and not frappe.db.get_value(
            "Employee", self.employee["name"], "shift_request_approver"
        ):
            # The approver field is mandatory *and* validated against the
            # employee's own approvers, so a site that configured neither can
            # never hold a shift request.
            frappe.db.set_value(
                "Employee",
                self.employee["name"],
                "shift_request_approver",
                "Administrator",
            )
        self._insert(
            {
                "doctype": "Shift Request",
                "employee": self.employee["name"],
                "company": self.employee.get("company"),
                "shift_type": shift,
                "from_date": str(today + timedelta(days=7)),
                "to_date": str(today + timedelta(days=21)),
                "approver": self._approver("shift_request_approver"),
                "status": "Draft",
            }
        )

    def _seed_timesheets(self) -> None:
        today = date.today()
        activity = "Execution"
        if not self.dry_run and not frappe.db.exists("Activity Type", activity):
            activity = frappe.db.get_value("Activity Type", {}, "name")
        if not activity:
            self._warn("No Activity Type found; skipping timesheets.")
            return
        for offset, hours in ((5, 7.5), (12, 6.0)):
            day = today - timedelta(days=offset)
            self._insert(
                {
                    "doctype": "Timesheet",
                    "employee": self.employee["name"],
                    "company": self.employee.get("company"),
                    "time_logs": [
                        {
                            "activity_type": activity,
                            "from_time": f"{day} 09:00:00",
                            "to_time": f"{day} {9 + int(hours):02d}:{int((hours % 1) * 60):02d}:00",
                            "hours": hours,
                            "description": "Warehouse rollout support",
                        }
                    ],
                }
            )

    # -- payroll ---------------------------------------------------------- #
    def _seed_payroll(self) -> None:
        """Salary Slip has the deepest dependency chain in HR — period, tax
        slab, structure, assignment — so it is seeded last and each link is
        checked before the next is attempted."""
        today = date.today()
        year_start = self._from(date(today.year, 1, 1))
        year_end = date(today.year, 12, 31)

        period = self._insert(
            {
                "doctype": "Payroll Period",
                "name": f"{self.run_id} {today.year}",
                "company": self.employee.get("company"),
                "start_date": str(year_start),
                "end_date": str(year_end),
            }
        )
        slab = self._insert(
            {
                "doctype": "Income Tax Slab",
                "name": f"{self.run_id} Slab",
                "company": self.employee.get("company"),
                "effective_from": str(year_start),
                "currency": "INR",
                "slabs": [
                    {"from_amount": 0, "to_amount": 300000, "percent_deduction": 0},
                    {"from_amount": 300001, "to_amount": 700000, "percent_deduction": 5},
                    {"from_amount": 700001, "percent_deduction": 20},
                ],
            },
            submit=True,
        )

        components = [c for c in ("Basic", "House Rent Allowance") if self._component_exists(c)]
        deductions = [c for c in ("Income Tax",) if self._component_exists(c)]
        if not components:
            self._warn("No Salary Component found; skipping salary structure.")
            return

        structure = self._insert(
            {
                "doctype": "Salary Structure",
                "name": f"{self.run_id} Structure",
                "company": self.employee.get("company"),
                "payroll_frequency": "Monthly",
                "currency": self._currency(),
                "earnings": [
                    {"salary_component": c, "amount": amount}
                    for c, amount in zip(components, (60000, 24000), strict=False)
                ],
                "deductions": [
                    {"salary_component": c, "amount": 4000} for c in deductions
                ],
            },
            submit=True,
        )
        if not structure:
            return

        self._insert(
            {
                "doctype": "Salary Structure Assignment",
                "employee": self.employee["name"],
                "salary_structure": structure,
                "company": self.employee.get("company"),
                "from_date": str(year_start),
                "base": 84000,
                "income_tax_slab": slab,
                "payroll_payable_account": None,
            },
            submit=True,
        )

        for back in range(1, PAYSLIP_MONTHS + 1):
            anchor = _month_start(today, -back)
            month_end = _month_end(anchor)
            if month_end < year_start:
                # The employee was not yet employed for any of this month, and
                # ERPNext rejects a slip outside the payroll period.
                break
            # The month they joined is paid from the joining date, not from
            # the first of the month.
            self._insert(
                {
                    "doctype": "Salary Slip",
                    "employee": self.employee["name"],
                    "company": self.employee.get("company"),
                    "salary_structure": structure,
                    "payroll_frequency": "Monthly",
                    "start_date": str(max(anchor, year_start)),
                    "end_date": str(month_end),
                    "posting_date": str(month_end),
                },
                submit=True,
            )

        if period:
            self._insert(
                {
                    "doctype": "Employee Tax Exemption Declaration",
                    "employee": self.employee["name"],
                    "company": self.employee.get("company"),
                    "payroll_period": period,
                    "currency": self._currency(),
                },
                submit=True,
            )

    def _seed_tax_declaration(self) -> None:
        # Folded into _seed_payroll because it needs the payroll period; kept
        # as a named step so a future standalone declaration has a home.
        return

    def _component_exists(self, component: str) -> bool:
        return self.dry_run or bool(frappe.db.exists("Salary Component", component))

    def _approver(self, field: str = "expense_approver") -> str | None:
        """Approver fields are mandatory on several HR doctypes.

        The employee's own configured approver is preferred; without one the
        document is rejected outright, so fall back to Administrator rather
        than lose the record.
        """
        if self.dry_run:
            return None
        return (
            frappe.db.get_value("Employee", self.employee["name"], field)
            or frappe.db.get_value("Employee", self.employee["name"], "expense_approver")
            or "Administrator"
        )

    def _currency(self) -> str | None:
        if self.dry_run:
            return None
        return frappe.db.get_value("Company", self.employee.get("company"), "default_currency")

    def _payable_account(self) -> str | None:
        """Submitting a claim posts to the ledger, which needs this account."""
        if self.dry_run:
            return None
        company = self.employee.get("company")
        return frappe.db.get_value(
            "Company", company, "default_payable_account"
        ) or frappe.db.get_value(
            "Account",
            {"company": company, "account_type": "Payable", "is_group": 0},
            "name",
        )

    def _cost_center(self) -> str | None:
        if self.dry_run:
            return None
        company = self.employee.get("company")
        return frappe.db.get_value("Company", company, "cost_center") or frappe.db.get_value(
            "Cost Center", {"company": company, "is_group": 0}, "name"
        )

    def _expense_account(self) -> str | None:
        """An Expense Claim Type with no account configured for this company
        makes ERPNext reject the claim. Naming an account on the row itself
        bypasses that lookup, so a site that never configured expense claims
        still gets demo claims."""
        if self.dry_run:
            return None
        return frappe.db.get_value(
            "Account",
            {
                "company": self.employee.get("company"),
                "root_type": "Expense",
                "is_group": 0,
            },
            "name",
        )

    # -- primitives ------------------------------------------------------- #
    def _insert(self, payload: dict, submit: bool = False) -> str | None:
        """Create one document, recording its name so cleanup can reverse it."""
        doctype = payload["doctype"]
        if self.dry_run:
            self._record(doctype, payload.get("name") or f"{self.run_id}-dry")
            return payload.get("name")
        if not frappe.db.exists("DocType", doctype):
            self._warn(f"{doctype} is not installed on this site; skipped.")
            return None
        # A savepoint, not frappe.db.rollback(): a plain rollback undoes the
        # whole open transaction, so one rejected document would silently
        # destroy every record inserted since the last commit while the
        # manifest still claimed them. Only the failed document is reversed.
        savepoint = f"demo_{self._savepoint_seq}"
        self._savepoint_seq += 1
        frappe.db.savepoint(savepoint)
        try:
            doc = frappe.get_doc({k: v for k, v in payload.items() if v is not None})
            doc.insert(ignore_permissions=True)
            if submit:
                doc.submit()
            self._record(doctype, doc.name)
            return doc.name
        except Exception as exc:  # pragma: no cover - depends on site state
            self._warn(f"Could not create {doctype}: {exc}")
            frappe.db.rollback(save_point=savepoint)
            return None

    def _record(self, doctype: str, name: str) -> None:
        entry = self.manifest["records"].setdefault(doctype, {"count": 0, "names": []})
        entry["names"].append(name)
        entry["count"] = len(entry["names"])

    def _warn(self, message: str) -> None:
        self.manifest["warnings"].append(message)

    def _commit(self) -> None:
        if frappe and not self.dry_run:
            frappe.db.commit()

    def _rollback(self) -> None:
        if frappe and not self.dry_run:
            frappe.db.rollback()


def _month_start(anchor: date, months_offset: int) -> date:
    month = anchor.month + months_offset
    year = anchor.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return date(year, month, 1)


def _month_end(start: date) -> date:
    return _month_start(start, 1) - timedelta(days=1)
