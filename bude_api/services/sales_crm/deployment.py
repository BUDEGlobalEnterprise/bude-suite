"""Deployment diagnostics, optional entitlements, and privacy-safe telemetry."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone

from ...utils.response import failure, success
from ..common.permissions import has_any_role, permission_denied, require_sales_role

MANAGER_ROLES = {"Sales Manager", "System Manager"}
SUPPORTED_MAJORS = {15, 16}
EVENTS = {
    "app_open",
    "setup_doctor_opened",
    "lead_created",
    "lead_merged",
    "deal_created",
    "lead_converted",
    "quotation_created",
    "sales_order_created",
    "offline_sync_completed",
    "offline_sync_failed",
}
SENSITIVE_KEYS = {
    "email",
    "phone",
    "mobile",
    "name",
    "customer",
    "lead",
    "deal",
    "record",
    "address",
    "content",
    "notes",
}


def deployment_status(frappe_module) -> dict:
    denied = require_sales_role(frappe_module)
    if denied:
        return denied
    if not has_any_role(frappe_module, MANAGER_ROLES):
        return permission_denied("Sales Manager access is required for Setup Doctor.")

    conf = getattr(frappe_module, "conf", {})
    installed = _installed_apps(frappe_module)
    provider = _conf(conf, "bude_sales_crm_provider") or "erpnext"
    crm_enabled = _truthy(conf.get("bude_sales_crm_enabled"))
    versions = _versions(frappe_module)
    provider_ready = provider == "erpnext" or (
        "crm" in installed and _exists(frappe_module, "DocType", "CRM Lead")
    )
    required = (
        ["CRM Lead", "CRM Deal", "CRM Task"]
        if provider == "frappe_crm"
        else ["Lead", "Opportunity", "ToDo"]
    )
    missing = [doctype for doctype in required if not _exists(frappe_module, "DocType", doctype)]
    scheduler_active = _scheduler_active(frappe_module)
    checks = [
        _check(
            "crm_enabled",
            "Sales CRM feature flag",
            "pass" if crm_enabled else "fail",
            "Enabled." if crm_enabled else "Set bude_sales_crm_enabled to 1 in site_config.json.",
        ),
        _check(
            "provider",
            "CRM provider",
            "pass" if provider_ready and provider in {"erpnext", "frappe_crm"} else "fail",
            f"Active provider: {provider}." if provider_ready else f"Provider {provider} is not installed or invalid.",
        ),
        _check(
            "doctypes",
            "Required records",
            "pass" if not missing else "fail",
            "All required DocTypes are available." if not missing else f"Missing: {', '.join(missing)}.",
        ),
        _check(
            "versions",
            "Supported server versions",
            _version_status(versions),
            _version_detail(versions),
        ),
        _check(
            "scheduler",
            "Background scheduler",
            "pass" if scheduler_active else "fail",
            "Scheduler is active." if scheduler_active else "Enable the site scheduler so reminders and retries can run.",
        ),
        _check(
            "idempotency",
            "Offline replay protection",
            "pass" if _exists(frappe_module, "DocType", "Integration Request") else "fail",
            "Integration Request is available for idempotent writes.",
        ),
        _check(
            "company",
            "ERPNext company",
            "pass" if _count(frappe_module, "Company") > 0 else "fail",
            "At least one Company is configured." if _count(frappe_module, "Company") > 0 else "Create a Company before selling.",
        ),
        _check(
            "price_list",
            "Selling price list",
            "pass" if _count(frappe_module, "Price List", {"selling": 1, "enabled": 1}) > 0 else "warn",
            "An enabled selling Price List is available." if _count(frappe_module, "Price List", {"selling": 1, "enabled": 1}) > 0 else "Configure an enabled selling Price List before the pilot.",
        ),
        _check(
            "push",
            "Push notifications",
            "pass" if bool(_conf(conf, "bude_firebase_service_account_json")) else "warn",
            "Firebase credentials are configured." if bool(_conf(conf, "bude_firebase_service_account_json")) else "Optional: configure Firebase credentials for assignment and reminder push alerts.",
        ),
        _check(
            "intake_security",
            "Public lead intake security",
            "pass" if bool(_conf(conf, "bude_sales_intake_secret")) else "warn",
            "Signed lead intake is configured." if bool(_conf(conf, "bude_sales_intake_secret")) else "Set an intake secret before enabling public webhook channels.",
        ),
        _check(
            "quote_response_security",
            "Customer quotation response links",
            "pass" if bool(_conf(conf, "bude_sales_quote_response_secret")) else "warn",
            "Signed quotation response links are configured."
            if bool(_conf(conf, "bude_sales_quote_response_secret"))
            else "Set a dedicated quotation response secret before sharing customer links.",
        ),
        _check(
            "telemetry",
            "Privacy-safe product telemetry",
            "pass" if _truthy(conf.get("bude_sales_telemetry_enabled")) else "warn",
            "Anonymous event telemetry is enabled." if _truthy(conf.get("bude_sales_telemetry_enabled")) else "Optional and disabled. Enable it to measure adoption without storing customer data.",
        ),
    ]
    entitlement = entitlement_status(frappe_module)["data"]
    return success(
        {
            "healthy": not any(row["status"] == "fail" for row in checks),
            "provider": provider,
            "versions": versions,
            "checks": checks,
            "entitlement": entitlement,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def entitlement_status(frappe_module) -> dict:
    denied = require_sales_role(frappe_module)
    if denied:
        return denied
    conf = getattr(frappe_module, "conf", {})
    plan = _conf(conf, "bude_sales_plan") or "community"
    status = _conf(conf, "bude_sales_entitlement_status") or "active"
    valid_until = _conf(conf, "bude_sales_entitlement_valid_until")
    expired = False
    if valid_until:
        try:
            expired = date.fromisoformat(valid_until[:10]) < date.today()
        except ValueError:
            status = "configuration_error"
    if expired:
        status = "expired"
    features = [
        item.strip()
        for item in _conf(conf, "bude_sales_entitlement_features").split(",")
        if item.strip()
    ]
    return success(
        {
            "plan": plan,
            "status": status,
            "valid_until": valid_until,
            "features": features,
            "core_available": True,
            "managed_service": plan != "community",
        }
    )


def track_event(frappe_module, event, properties=None, client_request_id=None) -> dict:
    denied = require_sales_role(frappe_module)
    if denied:
        return denied
    event = str(event or "").strip().lower()
    if event not in EVENTS:
        return failure("Unsupported telemetry event.", code="VALIDATION_EVENT")
    conf = getattr(frappe_module, "conf", {})
    if not _truthy(conf.get("bude_sales_telemetry_enabled")):
        return success({"accepted": False, "reason": "disabled"})
    clean = _sanitize(properties if isinstance(properties, dict) else {})
    request_id = str(client_request_id or "").strip()[:140]
    if request_id and _exists(
        frappe_module,
        "Integration Request",
        {"integration_request_service": "bude_sales_telemetry", "request_id": request_id},
    ):
        return success({"accepted": True, "duplicate": True})
    try:
        doc = frappe_module.get_doc(
            {
                "doctype": "Integration Request",
                "integration_request_service": "bude_sales_telemetry",
                "status": "Completed",
                "request_id": request_id or None,
                "request_description": event,
                "data": json.dumps(clean, separators=(",", ":"), default=str),
            }
        )
        doc.insert(ignore_permissions=True)
    except Exception:
        return failure("Telemetry event could not be recorded.", code="TELEMETRY_WRITE_FAILED")
    return success({"accepted": True})


def _check(key, label, status, detail):
    return {"key": key, "label": label, "status": status, "detail": detail}


def _installed_apps(frappe_module):
    try:
        values = frappe_module.get_installed_apps()
        return {str(value) for value in values} if isinstance(values, list | tuple | set) else set()
    except Exception:
        return set()


def _versions(frappe_module):
    try:
        raw = frappe_module.get_versions()
    except Exception:
        raw = {}
    result = {}
    if isinstance(raw, dict):
        for app, value in raw.items():
            if isinstance(value, dict):
                result[str(app)] = str(value.get("version") or value.get("branch") or "")
            elif isinstance(value, str):
                result[str(app)] = value
    return result


def _version_status(versions):
    majors = [_major(versions.get(app, "")) for app in ("frappe", "erpnext")]
    return "pass" if majors and all(major in SUPPORTED_MAJORS for major in majors) else "warn"


def _version_detail(versions):
    if not versions:
        return "Could not read server versions; certify manually before production."
    labels = ", ".join(f"{app} {value}" for app, value in versions.items() if app in {"frappe", "erpnext", "crm"})
    return f"Detected {labels}. Supported ERPNext/Frappe majors: 15 and 16."


def _major(version):
    match = re.search(r"(?:^|v)(\d+)", str(version or ""))
    return int(match.group(1)) if match else None


def _scheduler_active(frappe_module):
    try:
        return not bool(frappe_module.utils.scheduler.is_scheduler_inactive())
    except Exception:
        return True


def _exists(frappe_module, doctype, name_or_filters):
    try:
        value = frappe_module.db.exists(doctype, name_or_filters)
        return bool(value) if isinstance(value, bool | int | str) else False
    except Exception:
        return False


def _count(frappe_module, doctype, filters=None):
    try:
        return int(frappe_module.db.count(doctype, filters=filters or {}))
    except Exception:
        return 0


def _conf(conf, key):
    try:
        value = conf.get(key)
    except Exception:
        return ""
    return value.strip() if isinstance(value, str) else ""


def _truthy(value):
    return value in {True, 1, "1", "true", "True", "yes", "on"}


def _sanitize(properties):
    clean = {}
    for key, value in list(properties.items())[:20]:
        safe_key = re.sub(r"[^a-z0-9_]", "_", str(key).lower())[:40]
        if not safe_key or safe_key in SENSITIVE_KEYS:
            continue
        if isinstance(value, bool | int | float):
            clean[safe_key] = value
        elif isinstance(value, str):
            clean[safe_key] = value[:100]
    return clean
