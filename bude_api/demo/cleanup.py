"""Cleanup generated demo records by run tag."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import frappe
except ImportError:  # pragma: no cover
    frappe = None

from .config import demo_runs_root, require_write_guard, validate_run_id

DELETE_ORDER = [
    # HR first, and within it the documents that reference payroll setup
    # before the setup itself, so nothing is deleted out from under a link.
    "Salary Slip",
    "Employee Tax Exemption Declaration",
    "Salary Structure Assignment",
    "Salary Structure",
    "Income Tax Slab",
    "Payroll Period",
    "Timesheet",
    "Attendance",
    "Employee Checkin",
    "Leave Application",
    "Leave Allocation",
    "Compensatory Leave Request",
    "Attendance Request",
    "Shift Request",
    "Shift Assignment",
    "Travel Request",
    "Employee Advance",
    "Expense Claim",
    "Employee Grievance",
    "Shift Type",
    # Before "Holiday List": an assignment left behind points at a deleted
    # list, and HRMS then resolves *no* holidays for the employee, which
    # silently breaks leave, comp-off and salary slips on the next seed.
    "Holiday List Assignment",
    "Holiday List",
    # Master lists last: a document still linking to one blocks its delete.
    # Only entries this tool created are in the manifest, so a list the site
    # already owned is never touched.
    "Leave Type",
    "Expense Claim Type",
    "Activity Type",
    "Purpose of Travel",
    "Grievance Type",
    "Employee Grade",
    "Branch",
    "Employment Type",
    "Asset Maintenance Log",
    "Asset Maintenance Task",
    "Asset Repair",
    "Asset Movement",
    "Asset",
    "Stock Reconciliation",
    "Stock Entry",
    "Purchase Receipt",
    "Delivery Note",
    "Sales Order",
    "Purchase Order",
    "Customer",
    "Supplier",
    "Item",
    "Item Group",
    "User",
    "Warehouse",
    "Location",
    "Asset Category",
    "Company",
]


def run(
    run_id: str,
    dry_run: bool = False,
    confirm_demo_data: bool = False,
    base_url: str | None = None,
) -> dict:
    tag = validate_run_id(run_id)
    if frappe is None and not dry_run:
        raise RuntimeError("Frappe is not available. Run inside a Frappe bench.")
    if not dry_run:
        site = getattr(getattr(frappe, "local", None), "site", None)
        require_write_guard(
            run_id=tag,
            site=site,
            base_url=base_url,
            confirm_demo_data=confirm_demo_data,
        )
    cleaner = DemoCleaner(tag, dry_run=dry_run)
    report = cleaner.cleanup()
    cleaner.write_report(report)
    return report


class DemoCleaner:
    def __init__(self, run_id: str, dry_run: bool = False) -> None:
        self.run_id = validate_run_id(run_id)
        self.dry_run = dry_run
        self._savepoint_seq = 0
        self.manifest = self._read_manifest()
        self.report: dict[str, Any] = {
            "run_id": run_id,
            "dry_run": dry_run,
            "deleted": {},
            "warnings": [],
        }

    def cleanup(self) -> dict:
        for doctype in DELETE_ORDER:
            names = self._demo_names(doctype)
            deleted = []
            for name in names:
                if self._delete_doc(doctype, name):
                    deleted.append(name)
            self.report["deleted"][doctype] = {"count": len(deleted), "names": deleted[:50]}
        if frappe and not self.dry_run:
            frappe.db.commit()
        return self.report

    def write_report(self, report: dict) -> Path:
        root = demo_runs_root() / self.run_id
        root.mkdir(parents=True, exist_ok=True)
        path = root / "cleanup-report.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _demo_names(self, doctype: str) -> list[str]:
        names = self._manifest_names(doctype)
        if self.dry_run:
            return names
        filters = [["name", "like", f"{self.run_id}%"]]
        names = list(
            dict.fromkeys(
                [
                    *names,
                    *frappe.get_all(
                        doctype,
                        filters=filters,
                        pluck="name",
                        limit_page_length=100_000,
                    ),
                ]
            )
        )
        if doctype in {
            "Stock Entry",
            "Stock Reconciliation",
            "Purchase Receipt",
        } and self._has_field(doctype, "remarks"):
            by_remarks = frappe.get_all(
                doctype,
                filters=[["remarks", "like", f"%{self.run_id}%"]],
                pluck="name",
                limit_page_length=100_000,
            )
            names = list(dict.fromkeys([*names, *by_remarks]))
        return names

    def _read_manifest(self) -> dict:
        path = demo_runs_root() / self.run_id / "manifest.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _manifest_names(self, doctype: str) -> list[str]:
        records = self.manifest.get("records") or {}
        names = []
        if doctype in records:
            names.extend(records[doctype].get("names") or [])
        if doctype in {"Stock Entry", "Stock Reconciliation"} and "Stock Operation" in records:
            names.extend(records["Stock Operation"].get("names") or [])
        return list(dict.fromkeys(names))

    def _delete_doc(self, doctype: str, name: str) -> bool:
        if not self._is_tagged(doctype, name):
            self.report["warnings"].append(f"Refused untagged {doctype} {name}")
            return False
        if self.dry_run:
            return True
        if not frappe.db.exists(doctype, name):
            return False
        # A savepoint, not frappe.db.rollback(): a plain rollback undoes the
        # whole open transaction, so one document that refuses to cancel would
        # silently resurrect every record already deleted in this pass — the
        # cleanup then reports the same count forever and never converges.
        savepoint = f"undemo_{self._savepoint_seq}"
        self._savepoint_seq += 1
        frappe.db.savepoint(savepoint)
        try:
            docstatus = frappe.db.get_value(doctype, name, "docstatus")
            if docstatus == 1:
                try:
                    doc = frappe.get_doc(doctype, name)
                    doc.flags.ignore_permissions = True
                    doc.flags.ignore_links = True
                    doc.cancel()
                except Exception:
                    # A cancel runs the document's own on_cancel hooks, which
                    # can depend on master data an earlier pass already
                    # removed — a submitted leave application needs the
                    # holiday list it was validated against, and then neither
                    # cancel nor delete will touch it.
                    #
                    # Marking the row cancelled in the database skips those
                    # hooks. That is wrong for a real document and right for a
                    # demo row: the alternative is data this tool created and
                    # can no longer remove.
                    frappe.db.rollback(save_point=savepoint)
                    frappe.db.set_value(
                        doctype, name, "docstatus", 2, update_modified=False
                    )
            frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
            return True
        except Exception as exc:  # pragma: no cover - depends on ERPNext state
            self.report["warnings"].append(f"Could not delete {doctype} {name}: {exc}")
            frappe.db.rollback(save_point=savepoint)
            return False

    def _is_tagged(self, doctype: str, name: str) -> bool:
        if name.startswith(self.run_id):
            return True
        if name in self._manifest_names(doctype):
            return True
        if self.dry_run or doctype not in {
            "Stock Entry",
            "Stock Reconciliation",
            "Purchase Receipt",
        }:
            return False
        if not self._has_field(doctype, "remarks"):
            return False
        remarks = frappe.db.get_value(doctype, name, "remarks") or ""
        return self.run_id in remarks

    def _has_field(self, doctype: str, fieldname: str) -> bool:
        if self.dry_run:
            return False
        return bool(frappe.get_meta(doctype).has_field(fieldname))
