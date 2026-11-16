"""frappe.get_list on a child table without parent_doctype raises
PermissionError for every non-Administrator user on Frappe v15+. The unit
tests mock frappe, so only this static check catches it."""

import pathlib
import re

# Child tables queried directly by bude_api services (checked against the
# live site's DocType.istable). Add new ones here when you query them.
CHILD_TABLES = {
    "Appraisal Goal", "BOM Item", "Customer Credit Limit", "Employee Boarding Activity",
    "Employee Group Table", "Employee Property History", "Employee Skill", "Employee Training",
    "Event Participants", "Expense Claim Detail", "HD Customer Member", "HD Holiday",
    "HD Saved Reply Team", "HD Service Day", "HD Service Level Priority", "HD Team Member",
    "HD Ticket Template Field", "Has Role", "Item Default", "Item Reorder", "Job Card Time Log",
    "Leave Block List Allow", "Leave Block List Date", "Maintenance Schedule Detail",
    "Overdue Payment", "Payment Entry Reference", "Purchase Order Item", "Purchase Receipt Item",
    "Salary Detail", "Sales Invoice Item", "Sales Order Item", "Sales Team",
    "Stock Reconciliation Item", "Training Event Employee", "UOM Conversion Detail",
    "Work Order Operation",
}
CALL = re.compile(r'frappe\.get_list\(\s*"([^"]+)"')


def _call_text(src: str, start: int) -> str:
    depth, i = 0, src.index("(", start)
    for j in range(i, len(src)):
        depth += {"(": 1, ")": -1}.get(src[j], 0)
        if depth == 0:
            return src[start:j]
    return src[start:]


def test_child_table_get_list_passes_parent_doctype():
    root = pathlib.Path(__file__).resolve().parents[1] / "services"
    missing = []
    for path in root.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        for m in CALL.finditer(src):
            if m.group(1) in CHILD_TABLES and "parent_doctype" not in _call_text(src, m.start()):
                missing.append(f"{path.relative_to(root)}:{src[:m.start()].count(chr(10)) + 1} {m.group(1)}")
    assert not missing, "get_list on child table without parent_doctype:\n" + "\n".join(missing)
