"""Fill every screen the demo manager (persona.py) opens with realistic data.

Run after persona.py. Inventory data goes into the persona's own company with
clean names (no run-id prefixes on anything a user reads), so the user-manual
screenshots look like a real business. Every step skips records that already
exist, so a re-run only fills gaps. Each run writes its own run-id manifest;
`cleanup.run(run_id)` removes what that run created.

    bench --site <site> execute bude_api.demo.app_data.run \
      --kwargs "{'confirm_demo_data': True}"
"""

from __future__ import annotations

from datetime import date, timedelta

try:
    import frappe
except ImportError:  # pragma: no cover
    frappe = None

from .config import make_run_id, require_write_guard
from .hr_seed import HrDemoSeeder
from .persona import EMAIL

# code, name, group, rate, stock qty in Stores, reorder level (qty <= level -> low stock)
ITEMS = (
    ("PKG-1001", "Corrugated carton 18x12x12 in", "Packaging", 42, 640, 200),
    ("PKG-1002", "Stretch film roll 500 mm", "Packaging", 380, 28, 40),
    ("PKG-1003", "Bubble wrap roll 1 m x 100 m", "Packaging", 950, 34, 10),
    ("PKG-1004", "Packing tape 48 mm brown", "Packaging", 55, 410, 120),
    ("LBL-2001", "Thermal label 100x150 mm, 500/roll", "Labels and Barcodes", 260, 18, 30),
    ("LBL-2002", "UHF RFID tag inlay, 1000/reel", "Labels and Barcodes", 6200, 12, 5),
    ("LBL-2003", "Thermal ribbon 110 mm x 300 m", "Labels and Barcodes", 480, 75, 20),
    ("SAF-3001", "High-visibility vest, large", "Safety Gear", 180, 96, 25),
    ("SAF-3002", "Safety gloves, pair", "Safety Gear", 95, 40, 60),
    ("SAF-3003", "Safety helmet", "Safety Gear", 320, 52, 15),
)
CUSTOMERS = ("Kovai Auto Components", "Sri Murugan Textiles", "Coimbatore Pump Works",
             "Tiruppur Knit Exports")
SUPPLIERS = ("Apex RFID Systems", "South India Packaging Co")
# lead name, organisation, status, source, job title
LEADS = (
    ("Karthik Subramanian", "Nilgiri Fresh Foods", "Lead", "Exhibition", "Purchase Manager"),
    ("Priya Venkatesh", "Salem Steel Fabricators", "Open", "Reference", "Operations Head"),
    ("Arjun Ramesh", "Erode Handloom Co-op", "Replied", "Cold Calling", "Owner"),
    ("Lakshmi Narayanan", "Madurai Pharma Distributors", "Interested", "Campaign", "Warehouse Lead"),
    ("Sanjay Krishnan", "Hosur Electronics", "Opportunity", "Advertisement", "Plant Manager"),
    ("Deepa Mohan", "Pollachi Coir Exports", "Quotation", "Existing Customer", "Director"),
    ("Rahul Iyer", "Trichy Auto Spares", "Lead", "Walk In", "Store Incharge"),
    ("Anitha Rajan", "Karur Textiles", "Do Not Contact", "Mass Mailing", "Accounts"),
)
# party (lead index or customer), stage, amount, probability, close in days
DEALS = (
    ("lead:4", "Proposal/Price Quote", 485000, 60, 12),
    ("lead:5", "Negotiation/Review", 320000, 80, 5),
    ("lead:3", "Needs Analysis", 150000, 30, 30),
    ("cust:0", "Value Proposition", 210000, 45, 20),
    ("cust:2", "Qualification", 95000, 20, 45),
    ("cust:1", "Identifying Decision Makers", 260000, 35, -3),
)
TICKETS = (
    ("Barcode printer prints blank labels", "The Zebra printer in the dispatch bay feeds labels "
     "but prints nothing since this morning. Ribbon was replaced yesterday.", "High", "Incident",
     "dispatch@kovaiauto.example.com", True),
    ("Handheld cannot sync stock count", "Count for Stores shows 'waiting to sync' for two hours. "
     "Wi-Fi is fine on the same device.", "Urgent", "Bug", EMAIL, True),
    ("Wrong GST rate on invoice", "Our invoice for order last week shows 18% GST on stretch film; "
     "it should be 12%. Please correct and resend.", "Medium", "Question",
     "accounts@srimurugantextiles.example.com", True),
    ("Request access for new store keeper", "Arun Kumar joined the Coimbatore store. Please give "
     "him access to the inventory app.", "Low", "Question", EMAIL, False),
    ("RFID reader battery drains quickly", "The C72 reader lasts about two hours per charge "
     "instead of a full shift.", "Medium", "Incident", "stores@coimbatorepumps.example.com", False),
    ("Delivery delayed for carton order", "We were promised delivery by Friday. Can you share "
     "the new date?", "High", "Question", "purchase@tiruppurknit.example.com", True),
)


def run(run_id: str | None = None, confirm_demo_data: bool = False) -> dict:
    tag = run_id or make_run_id("appdata")
    require_write_guard(run_id=tag, site=getattr(getattr(frappe, "local", None), "site", None),
                        confirm_demo_data=confirm_demo_data)
    seeder = AppDataSeeder(tag)
    manifest = seeder.seed_all()
    seeder.write_manifest(manifest)
    return {"run_id": tag, "records": {k: v["count"] for k, v in manifest["records"].items()},
            "warnings": manifest["warnings"]}


class AppDataSeeder(HrDemoSeeder):
    def __init__(self, run_id: str) -> None:
        super().__init__(run_id)
        self.manifest["kind"] = "appdata"
        emp = frappe.db.get_value("Employee", {"user_id": EMAIL}, ["name", "company"], as_dict=True)
        if not emp:
            raise RuntimeError("Run bude_api.demo.persona first.")
        self.employee = dict(emp)
        self.company = emp.company
        self.abbr = frappe.db.get_value("Company", self.company, "abbr")
        self.today = date.today()

    def seed_all(self) -> dict:
        frappe.flags.mute_emails = True  # demo addresses are not real inboxes
        for step in (self._hr_polish, self._masters, self._stock, self._purchase_orders,
                     self._sales_orders, self._invoices, self._count_tasks,
                     self._floor_exceptions, self._crm,
                     self._helpdesk, self._notifications, self._tidy_old_demo_names):
            try:
                step()
                self._commit()
            except Exception as exc:  # pragma: no cover - depends on site state
                self._warn(f"{step.__name__} failed: {exc}")
                self._rollback()
        return self.manifest

    # -- helpers ---------------------------------------------------------- #
    def _wh(self, name: str) -> str:
        return f"{name} - {self.abbr}"

    def _once(self, filters: dict, payload: dict, submit: bool = False) -> str | None:
        """Insert unless a matching record exists, so a re-run only fills gaps."""
        existing = frappe.db.get_value(payload["doctype"], filters, "name")
        return existing or self._insert(payload, submit=submit)

    def _as_persona(self, fn, *args, **kwargs):
        previous = frappe.session.user
        frappe.set_user(EMAIL)
        try:
            return fn(*args, **kwargs)
        finally:
            frappe.set_user(previous)

    # -- HR gaps left by persona.py --------------------------------------- #
    def _hr_polish(self) -> None:
        # Readable names for the run-tagged holiday list / shift type the
        # profile and roster display.
        for doctype, new in (("Holiday List", f"{self.company} Holidays {self.today.year}"),
                             ("Shift Type", "General Shift")):
            old = frappe.db.get_value(doctype, {"name": ["like", "BUDE-DEMO-%-persona%"]}, "name")
            if old and not frappe.db.exists(doctype, new):
                frappe.rename_doc(doctype, old, new, force=True)
                self._record(doctype, new)
        shift = "General Shift" if frappe.db.exists("Shift Type", "General Shift") else None
        team = frappe.get_all("Employee", filters={"name": ["like", "HR-EMP-DEMO-%"]},
                              order_by="name asc", pluck="name")
        for i, emp in enumerate(team):
            frappe.db.set_value("Employee", emp, "cell_number", f"+91 98400 1{i:04d}")
            if shift:
                self._once({"employee": emp, "shift_type": shift, "docstatus": 1},
                           {"doctype": "Shift Assignment", "employee": emp, "shift_type": shift,
                            "company": self.company, "status": "Active",
                            "start_date": str(self.today.replace(day=1)),
                            "end_date": str(self.today.replace(day=28))}, submit=True)

    # -- inventory -------------------------------------------------------- #
    def _masters(self) -> None:
        frappe.defaults.set_user_default("company", self.company, EMAIL)
        for group in sorted({i[2] for i in ITEMS}):
            self._once({"name": group}, {"doctype": "Item Group", "item_group_name": group,
                                         "parent_item_group": "All Item Groups"})
        for name in ("Receiving Dock", "Dispatch Bay"):
            self._once({"name": self._wh(name)}, {"doctype": "Warehouse", "warehouse_name": name,
                                                  "company": self.company})
        for code, name, group, rate, _qty, level in ITEMS:
            # This site defaults new items to serial tracking; demo stock is not serialised.
            if frappe.db.exists("Item", code):
                frappe.db.set_value("Item", code, {"has_serial_no": 0, "has_batch_no": 0})
                continue
            self._insert({
                "doctype": "Item", "item_code": code, "item_name": name, "item_group": group,
                "stock_uom": "Nos", "is_stock_item": 1, "has_serial_no": 0, "has_batch_no": 0,
                "valuation_rate": rate, "standard_rate": round(rate * 1.35), "description": name,
                "barcodes": [{"barcode": f"89012340{code[-4:]}{len(code)}"}],
                "item_defaults": [{"company": self.company,
                                   "default_warehouse": self._wh("Stores")}],
                "reorder_levels": [{"warehouse": self._wh("Stores"),
                                    "warehouse_reorder_level": level,
                                    "warehouse_reorder_qty": level * 3,
                                    "material_request_type": "Purchase"}],
            })
        for name in CUSTOMERS:
            # The site marks primary contact/address mandatory; demo customers have neither.
            self._once({"name": name}, {"doctype": "Customer", "customer_name": name,
                                        "customer_group": "Commercial", "territory": "India",
                                        "customer_type": "Company", "__ignore_mandatory": True})
        for name in SUPPLIERS:
            self._once({"name": name}, {"doctype": "Supplier", "supplier_name": name,
                                        "supplier_group": "Distributor"})

    def _stock(self) -> None:
        rows = [{"item_code": c, "qty": q, "basic_rate": r, "t_warehouse": self._wh("Stores")}
                for c, _n, _g, r, q, _l in ITEMS]
        rows += [{"item_code": c, "qty": max(5, q // 4), "basic_rate": r,
                  "t_warehouse": self._wh("Finished Goods")}
                 for c, _n, _g, r, q, _l in ITEMS[::3]]
        self._once({"remarks": ["like", "Opening stock BUDE-DEMO-%"], "docstatus": 1},
                   {"doctype": "Stock Entry", "stock_entry_type": "Material Receipt",
                    "company": self.company, "remarks": f"Opening stock {self.run_id}",
                    "items": rows}, submit=True)
        # A little movement history for the item History tab and analytics.
        self._once({"remarks": ["like", "Replenish dispatch bay BUDE-DEMO-%"], "docstatus": 1},
                   {"doctype": "Stock Entry", "stock_entry_type": "Material Transfer",
                    "company": self.company, "remarks": f"Replenish dispatch bay {self.run_id}",
                    "items": [{"item_code": "PKG-1001", "qty": 120,
                               "s_warehouse": self._wh("Stores"),
                               "t_warehouse": self._wh("Dispatch Bay")},
                              {"item_code": "PKG-1004", "qty": 60,
                               "s_warehouse": self._wh("Stores"),
                               "t_warehouse": self._wh("Dispatch Bay")}]}, submit=True)

    def _purchase_orders(self) -> None:
        plans = ((SUPPLIERS[1], 0, [("PKG-1002", 120), ("PKG-1003", 20)]),
                 (SUPPLIERS[0], 0, [("LBL-2001", 60), ("LBL-2002", 10)]),
                 (SUPPLIERS[0], 2, [("SAF-3002", 200)]))
        if frappe.db.count("Purchase Order", {"supplier": ["in", SUPPLIERS], "docstatus": 1}) >= 3:
            return
        rate = {c: r for c, _n, _g, r, _q, _l in ITEMS}
        for supplier, days, lines in plans:
            due = str(self.today + timedelta(days=days))
            self._insert({"doctype": "Purchase Order", "supplier": supplier, "company": self.company,
                          "transaction_date": str(self.today - timedelta(days=5)),
                          "schedule_date": due, "set_warehouse": self._wh("Receiving Dock"),
                          "items": [{"item_code": c, "qty": q, "rate": rate[c], "schedule_date": due,
                                     "warehouse": self._wh("Receiving Dock")} for c, q in lines]},
                         submit=True)

    def _sales_orders(self) -> None:
        plans = ((CUSTOMERS[0], 0, [("PKG-1001", 150), ("PKG-1004", 40)]),
                 (CUSTOMERS[1], 1, [("LBL-2003", 12), ("SAF-3001", 20)]),
                 (CUSTOMERS[2], 2, [("SAF-3003", 15), ("SAF-3002", 10)]),
                 (CUSTOMERS[3], 3, [("PKG-1003", 6)]))
        price = {c: round(r * 1.35) for c, _n, _g, r, _q, _l in ITEMS}
        for customer, days, lines in plans:
            due = str(self.today + timedelta(days=days))
            self._once({"customer": customer, "docstatus": 1},
                       {"doctype": "Sales Order", "customer": customer, "company": self.company,
                        "transaction_date": str(self.today - timedelta(days=2)),
                        "delivery_date": due, "set_warehouse": self._wh("Stores"),
                        "items": [{"item_code": c, "qty": q, "rate": price[c], "delivery_date": due,
                                   "warehouse": self._wh("Stores")} for c, q in lines]},
                       submit=True)

    def _invoices(self) -> None:
        price = {c: round(r * 1.35) for c, _n, _g, r, _q, _l in ITEMS}
        for customer, days_ago, code, qty in ((CUSTOMERS[0], 45, "PKG-1001", 300),
                                              (CUSTOMERS[1], 38, "LBL-2001", 40),
                                              (CUSTOMERS[2], 10, "SAF-3003", 25)):
            posted = self.today - timedelta(days=days_ago)
            self._once({"customer": customer, "docstatus": 1},
                       {"doctype": "Sales Invoice", "customer": customer, "company": self.company,
                        "posting_date": str(posted), "set_posting_time": 1,
                        "due_date": str(posted + timedelta(days=30)), "update_stock": 0,
                        "items": [{"item_code": code, "qty": qty, "rate": price[code]}]},
                       submit=True)

    def _count_tasks(self) -> None:
        from bude_api.services.analytics import counts

        def mine():
            return set(frappe.get_all("ToDo", filters={"allocated_to": EMAIL, "status": "Open",
                                                       "description": ["like", "%Cycle count%"]},
                                      pluck="name"))

        before = mine()
        if before:
            return
        self._as_persona(counts.generate_schedule, warehouse=self._wh("Stores"), days=7,
                         item_limit=6, assigned_to=EMAIL)
        for name in mine() - before:
            self._record("ToDo", name)

    def _floor_exceptions(self) -> None:
        """Exceptions list + reconciliation history/variance, through the
        app's own exception service so records look exactly like real ones."""
        from bude_api.services.analytics import exceptions

        if frappe.db.exists("ToDo", {"allocated_to": EMAIL, "description": ["like", "Exception:%"]}):
            return
        before_todo = set(frappe.get_all("ToDo", pluck="name", filters={"allocated_to": EMAIL}))
        before_rec = set(frappe.get_all("Stock Reconciliation", pluck="name",
                                        filters={"company": self.company}))
        stores = self._wh("Stores")
        for kwargs in (
            {"exception_type": "shortage", "item_code": "PKG-1004", "counted_qty": 344,
             "warehouse": stores, "note": "Six rolls missing from rack A3"},
            {"exception_type": "unknown_scan", "barcode": "8901234099990", "warehouse": stores,
             "note": "Label torn; carton found on rack B2", "allocated_to": EMAIL},
            {"exception_type": "blocked_stock", "item_code": "SAF-3003", "warehouse": stores,
             "note": "Helmets held for quality check", "allocated_to": EMAIL},
        ):
            result = self._as_persona(exceptions.report, **kwargs)
            if not (result or {}).get("ok"):
                self._warn(f"exception {kwargs['exception_type']}: {(result or {}).get('message')}")
        for name in set(frappe.get_all("ToDo", pluck="name", filters={"allocated_to": EMAIL})) - before_todo:
            self._record("ToDo", name)
        for name in set(frappe.get_all("Stock Reconciliation", pluck="name",
                                       filters={"company": self.company})) - before_rec:
            self._record("Stock Reconciliation", name)

    # -- sales CRM (ERPNext provider: Lead / Opportunity / ToDo) ----------- #
    def _crm(self) -> None:
        leads = []
        for i, (person, org, status, source, title) in enumerate(LEADS):
            first, last = person.split(" ", 1)
            leads.append(self._once({"lead_name": person, "lead_owner": EMAIL}, {
                "doctype": "Lead", "first_name": first, "last_name": last, "lead_name": person,
                "company_name": org, "status": status, "job_title": title,
                "utm_source": source if frappe.db.exists("UTM Source", source) else None,
                "territory": "India", "lead_owner": EMAIL, "company": self.company,
                "email_id": f"{first.lower()}@{org.split()[0].lower()}.example.com",
                "mobile_no": f"+91 94430 2{i:04d}",
            }))
        for party, stage, amount, prob, close in DEALS:
            kind, idx = party.split(":")
            name = leads[int(idx)] if kind == "lead" else CUSTOMERS[int(idx)]
            if not name:
                continue
            self._once({"party_name": name, "opportunity_owner": EMAIL}, {
                "doctype": "Opportunity", "opportunity_from": "Lead" if kind == "lead" else "Customer",
                "party_name": name, "sales_stage": stage, "opportunity_amount": amount,
                "probability": prob, "expected_closing": str(self.today + timedelta(days=close)),
                "opportunity_owner": EMAIL, "company": self.company, "status": "Open",
                "opportunity_type": "Sales", "currency": "INR",
            })
        tasks = (("Call back about RFID pilot pricing", 0, -2, "High"),
                 ("Send revised quotation", 1, 0, "High"),
                 ("Share case study and site visit dates", 2, 0, "Medium"),
                 ("Confirm decision makers for rollout", 3, 2, "Medium"),
                 ("Follow up on sample cartons", 4, 5, "Low"),
                 ("Collect GST details for onboarding", 6, -1, "Medium"))
        for text, idx, days, priority in tasks:
            if leads[idx]:
                self._once({"description": text, "allocated_to": EMAIL},
                           {"doctype": "ToDo", "description": text, "allocated_to": EMAIL,
                            "reference_type": "Lead", "reference_name": leads[idx],
                            "status": "Open", "priority": priority,
                            "date": str(self.today + timedelta(days=days))})
        for idx, note in ((1, "Met at the Coimbatore expo. Needs 40 handhelds across 3 sites."),
                          (4, "Budget approved for Q1. Wants a two-week pilot first."),
                          (5, "Asked for a 5% volume discount on tags.")):
            if leads[idx] and not frappe.db.exists("Comment", {"reference_name": leads[idx],
                                                               "content": note}):
                comment = frappe.get_doc("Lead", leads[idx]).add_comment(
                    "Comment", note, comment_email=EMAIL)
                self._record("Comment", comment.name)

    # -- helpdesk --------------------------------------------------------- #
    def _helpdesk(self) -> None:
        if not frappe.db.exists("DocType", "HD Ticket"):
            return
        from frappe.desk.form.assign_to import add as assign

        replies = ("Thanks for reporting this. I'm checking it now and will update you shortly.",
                   "Could you share a photo of the screen showing the error?")
        for i, (subject, body, priority, ttype, raised_by, assigned) in enumerate(TICKETS):
            if frappe.db.exists("HD Ticket", {"subject": subject}):
                continue
            # No agent_group: the site's team assignment rules have no agents and crash.
            name = self._insert({"doctype": "HD Ticket", "subject": subject, "description": body,
                                 "raised_by": raised_by, "priority": priority, "ticket_type": ttype})
            if not name:
                continue
            if assigned:
                assign({"doctype": "HD Ticket", "name": name, "assign_to": [EMAIL]})
            if i % 2 == 0:
                comm = frappe.get_doc({
                    "doctype": "Communication", "communication_type": "Communication",
                    "communication_medium": "Email", "sent_or_received": "Sent",
                    "sender": EMAIL, "recipients": raised_by, "subject": f"Re: {subject}",
                    "content": replies[i % 2], "reference_doctype": "HD Ticket",
                    "reference_name": name})
                comm.insert(ignore_permissions=True)
                self._record("Communication", comm.name)

    # -- notifications ---------------------------------------------------- #
    def _notifications(self) -> None:
        notes = (("Your leave request for 25 Nov was approved", "Leave Application"),
                 ("Payslip for October 2026 is ready", "Salary Slip"),
                 ("Divya Shankar applied for leave", "Leave Application"),
                 ("Expense claim from Arun Kumar needs your approval", "Expense Claim"),
                 ("Stretch film roll 500 mm is below reorder level", "Item"),
                 ("New ticket assigned: Barcode printer prints blank labels", "HD Ticket"))
        for subject, doctype in notes:
            self._once({"for_user": EMAIL, "subject": subject},
                       {"doctype": "Notification Log", "for_user": EMAIL, "type": "Alert",
                        "subject": subject, "document_type": doctype,
                        "from_user": "Administrator"})

    def _tidy_old_demo_names(self) -> None:
        """Earlier demo runs prefixed asset names with their run id; the asset
        list shows asset_name, so strip the prefix (display field only)."""
        for row in frappe.get_all("Asset", filters={"asset_name": ["like", "BUDE-DEMO-%preview %"]},
                                  fields=["name", "asset_name"]):
            frappe.db.set_value("Asset", row.name, "asset_name",
                                row.asset_name.split("preview ", 1)[1], update_modified=False)
