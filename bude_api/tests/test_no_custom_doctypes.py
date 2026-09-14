"""Architecture guard: Bude extends ERPNext without creating DocTypes."""

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_DOCTYPES = {"DocType", "Custom DocType"}

# bude_api extends ERPNext without forking its data model. The ONLY sanctioned
# custom DocTypes are the mobile screen-permission config, which needs Desk-
# managed rows, filters and per-user override records that a JSON singleton
# cannot provide. Any doctype folder not listed here is still a violation.
ALLOWED_CUSTOM_DOCTYPES = {
    "mobile_application",
    "mobile_app_screen",
    "mobile_screen_role_permission",
    "mobile_screen_user_override",
}


def _custom_doctype_writes(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            pairs = zip(node.keys, node.values, strict=True)
            for key, value in pairs:
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "doctype"
                    and isinstance(value, ast.Constant)
                    and value.value in FORBIDDEN_DOCTYPES
                ):
                    violations.append(f"{path}:{node.lineno}")
        if not isinstance(node, ast.Call) or not node.args:
            continue
        function_name = getattr(node.func, "attr", "")
        first_arg = node.args[0]
        if (
            function_name in {"new_doc", "get_doc"}
            and isinstance(first_arg, ast.Constant)
            and first_arg.value in FORBIDDEN_DOCTYPES
        ):
            violations.append(f"{path}:{node.lineno}")
    return violations


def test_primary_backend_has_only_sanctioned_custom_doctypes():
    unexpected = []
    for container in APP_ROOT.rglob("doctype"):
        if not container.is_dir() or "tests" in container.parts:
            continue
        for child in container.iterdir():
            if child.is_dir() and child.name not in ALLOWED_CUSTOM_DOCTYPES:
                unexpected.append(str(child))
    assert unexpected == [], (
        "Unsanctioned custom DocType modules; use standard ERPNext/Frappe "
        f"DocTypes or add to ALLOWED_CUSTOM_DOCTYPES with a reason: {unexpected}"
    )


def test_primary_backend_does_not_create_doctype_definitions():
    violations: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        if "tests" not in path.parts:
            violations.extend(_custom_doctype_writes(path))
    assert violations == [], (
        "Do not create DocType definitions from Bude code. Extend standard "
        f"DocTypes with supported fields/workflows instead: {violations}"
    )
