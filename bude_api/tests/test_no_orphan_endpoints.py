"""Every whitelisted endpoint must have a caller in one of the four apps.

An endpoint nothing calls is either a feature the apps forgot to surface or
dead code — both worth knowing about. This test found `expense_attachments`,
`reports.asset_utilization` and `counts.generate_schedule` (features with no
button) and `api/stock_tracking.py` (a leaked internal helper), so it stays.

When a new endpoint is genuinely not for mobile, add it to ALLOWED_ORPHANS with
a reason rather than deleting this test.
"""

import ast
import re
from pathlib import Path

# module -> why it has no mobile caller.
ALLOWED_ORPHANS = {
    "permissions": (
        "Re-exports shared permission helpers for other backend modules; the "
        "wrapper module has no endpoints of its own."
    ),
    "notifications": (
        "Server-side push registration and preferences. No app has a push "
        "transport yet, so wiring preferences alone would gate notifications "
        "that are never delivered. Revisit when push ships."
    ),
    "admin_onboarding": (
        "Role profiles, user provisioning and device revocation — a "
        "desktop-admin surface, not a warehouse-floor one."
    ),
}

# endpoint -> why it intentionally has no mobile caller.
ALLOWED_ENDPOINTS = {
    "sales_crm.capture_intake": (
        "Signed server-to-server lead intake webhook for forms, Meta and other "
        "external channels; mobile devices must never hold its channel secret."
    ),
    "sales_crm.quotation_response_context": (
        "Public, signed quotation-response page endpoint; it is called by the "
        "bundled web page rather than a mobile client."
    ),
    "sales_crm.quotation_response": (
        "Public, signed quotation acceptance/rejection endpoint; it is called "
        "by the bundled web page rather than a mobile client."
    ),
    "mobile_permissions.get_effective_permission_preview": (
        "Admin-only effective-access preview for permission managers; a Desk "
        "surface, not a warehouse-floor one."
    ),
    "mobile_permissions.invalidate_permission_cache": (
        "Admin-only 'Refresh access' action bumping permission_version; a Desk "
        "surface, not a mobile client call."
    ),
}


def _repo() -> Path:
    return next(
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "mobile-app").is_dir() and (parent / "backend").is_dir()
    )


def _called_endpoints(repo: Path) -> set[str]:
    pattern = re.compile(r"bude_api\.api\.([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)")
    called = set()
    for path in (repo / "mobile-app").rglob("*.dart"):
        if any(part in {".dart_tool", "build"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        called.update(f"{m}.{f}" for m, f in pattern.findall(text))
    return called


def test_no_endpoint_is_left_without_a_caller():
    repo = _repo()
    called = _called_endpoints(repo)
    assert called, "found no endpoint references at all — the scan is broken"

    orphans = []
    for path in sorted((repo / "backend/bude_api/bude_api/api").glob("*.py")):
        if path.stem in ALLOWED_ORPHANS or path.stem == "__init__":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name.startswith("_"):
                continue
            endpoint = f"{path.stem}.{node.name}"
            if endpoint not in called and endpoint not in ALLOWED_ENDPOINTS:
                orphans.append(endpoint)

    assert orphans == [], (
        "no app calls these endpoints — surface them, delete them, or list the "
        f"module in ALLOWED_ORPHANS with a reason: {orphans}"
    )


def test_allowed_orphans_still_exist():
    """Stops the allowlist rotting into stale entries for deleted modules."""
    api = _repo() / "backend/bude_api/bude_api/api"
    missing = [name for name in ALLOWED_ORPHANS if not (api / f"{name}.py").is_file()]

    assert missing == [], f"ALLOWED_ORPHANS lists modules that no longer exist: {missing}"

    missing_endpoints = []
    for endpoint in ALLOWED_ENDPOINTS:
        module, function = endpoint.split(".", 1)
        path = api / f"{module}.py"
        if not path.is_file():
            missing_endpoints.append(endpoint)
            continue
        functions = {
            node.name
            for node in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef)
        }
        if function not in functions:
            missing_endpoints.append(endpoint)

    assert missing_endpoints == [], (
        "ALLOWED_ENDPOINTS lists endpoints that no longer exist: "
        f"{missing_endpoints}"
    )
