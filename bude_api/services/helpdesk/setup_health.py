"""Manager-only Helpdesk setup and customer-activation diagnostics."""

from __future__ import annotations

import re
from datetime import datetime, timezone

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import success
from ..common.permissions import HELPDESK_MANAGER_ROLES, require_any_role

SUPPORTED_FRAPPE_MAJORS = {15, 16}
PORTAL_ROLES = {"HD Customer", "HD Customer Manager"}
ACTIVATION_SCAN_LIMIT = 500


def setup_health() -> dict:
    """Return a privacy-safe preflight and observed activation funnel.

    The endpoint intentionally remains read-only. Invitation and configuration
    actions are handed off to the standard Helpdesk/Desk screens so upstream
    continues to own role assignment, invitation expiry, and email delivery.
    """
    denied = require_any_role(
        frappe,
        HELPDESK_MANAGER_ROLES,
        "Agent Manager access is required for Setup Health.",
    )
    if denied:
        return denied

    installed = _installed_apps()
    versions = _versions()
    helpdesk_ready = "helpdesk" in installed and _exists("DocType", "HD Ticket")
    frappe_major = _major(versions.get("frappe", ""))
    version_supported = frappe_major in SUPPORTED_FRAPPE_MAJORS
    incoming_ready = (
        _count(
            "Email Account",
            {"enable_incoming": 1, "default_incoming": 1, "awaiting_password": 0},
        )
        > 0
    )
    outgoing_ready = (
        _count(
            "Email Account",
            {"enable_outgoing": 1, "default_outgoing": 1, "awaiting_password": 0},
        )
        > 0
    )
    scheduler_ready = _scheduler_active()
    agents = _count("HD Agent", {"is_active": 1})
    teams = _count("HD Team", {"disabled": 0})
    slas = _count("HD Service Level Agreement", {"enabled": 1})
    default_slas = _count("HD Service Level Agreement", {"enabled": 1, "default_sla": 1})
    setup_complete = bool(_single_value("HD Settings", "setup_complete"))
    portal_roles_ready = all(_exists("Role", role) for role in PORTAL_ROLES)
    default_portal_role = str(_single_value("Portal Settings", "default_role") or "")
    portal_ready = portal_roles_ready and default_portal_role == "HD Customer"
    activation = _activation_snapshot() if helpdesk_ready else _empty_activation()
    push_ready = _push_configured()
    public_url_ready = bool(_conf("host_name"))

    checks = [
        _check(
            "helpdesk",
            "Helpdesk application",
            "pass" if helpdesk_ready else "fail",
            "Helpdesk and HD Ticket are installed."
            if helpdesk_ready
            else "Install Helpdesk and migrate the site before onboarding.",
            "/app/installed-applications",
        ),
        _check(
            "versions",
            "Server compatibility",
            "pass" if version_supported else "warn",
            _version_detail(versions, frappe_major),
            "/app/installed-applications",
        ),
        _check(
            "helpdesk_setup",
            "Helpdesk basic setup",
            "pass" if setup_complete else "warn",
            "The upstream setup wizard is complete."
            if setup_complete
            else "Finish Helpdesk branding, defaults, and basic setup.",
            "/helpdesk/settings",
        ),
        _check(
            "incoming_email",
            "Default incoming email",
            "pass" if incoming_ready else "fail",
            "A default incoming account is enabled and credential-ready."
            if incoming_ready
            else "Enable a credential-ready default incoming Email Account.",
            "/app/email-account",
        ),
        _check(
            "outgoing_email",
            "Default outgoing email",
            "pass" if outgoing_ready else "fail",
            "A default outgoing account is enabled and credential-ready."
            if outgoing_ready
            else "Enable a credential-ready default outgoing Email Account.",
            "/app/email-account",
        ),
        _check(
            "scheduler",
            "Background scheduler",
            "pass" if scheduler_ready else "fail",
            "Scheduler is active for email pulls, SLA updates, and retries."
            if scheduler_ready
            else "Enable the site scheduler before testing email and SLA flows.",
            "/app/system-health-report",
        ),
        _check(
            "agents",
            "Active agents",
            "pass" if agents > 0 else "fail",
            f"{agents} active agent{'s' if agents != 1 else ''} available."
            if agents
            else "Invite and activate at least one Helpdesk agent.",
            "/helpdesk/settings/agents",
        ),
        _check(
            "teams",
            "Routing teams",
            "pass" if teams > 0 else "warn",
            f"{teams} enabled team{'s' if teams != 1 else ''} configured."
            if teams
            else "Create a team and add agents before enabling auto-routing.",
            "/helpdesk/settings/teams",
        ),
        _check(
            "sla",
            "Service level agreement",
            "pass" if slas > 0 and default_slas > 0 else "fail",
            f"{slas} enabled SLA{'s' if slas != 1 else ''}, including a default."
            if slas > 0 and default_slas > 0
            else "Enable an SLA and mark one agreement as the default.",
            "/app/hd-service-level-agreement",
        ),
        _check(
            "customer_portal",
            "Customer portal roles",
            "pass" if portal_ready else "fail",
            "Portal roles exist and new sign-ups default to HD Customer."
            if portal_ready
            else "Set Portal Settings Default Role to HD Customer and run migrations.",
            "/app/portal-settings",
        ),
        _check(
            "customer_activation",
            "Customer activation",
            "pass" if activation["activation_rate"] >= 70 else "warn",
            _activation_detail(activation),
            "/helpdesk/customers",
        ),
        _check(
            "public_url",
            "Public site URL",
            "pass" if public_url_ready else "warn",
            "host_name is configured for reliable invitation and portal links."
            if public_url_ready
            else "Set host_name so invitation and portal links use the public URL.",
            "/app/site-settings",
        ),
        _check(
            "push",
            "Push notifications",
            "pass" if push_ready else "warn",
            "FCM server credentials are configured."
            if push_ready
            else "Optional: configure FCM credentials for mobile alerts.",
            "/app/bude-mobile-device",
        ),
        _check(
            "backup",
            "Recovery readiness",
            "warn",
            "Verify the latest off-site backup and a restore exercise manually.",
            "/app/download-backups",
        ),
    ]
    test_run = _test_run(portal_ready)
    weighted = sum(
        100 if row["status"] == "pass" else 50 if row["status"] == "warn" else 0 for row in checks
    )
    return success(
        {
            "healthy": not any(row["status"] == "fail" for row in checks),
            "score": round(weighted / len(checks)),
            "checks": checks,
            "activation": activation,
            "test_run": test_run,
            "versions": versions,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def _activation_snapshot() -> dict:
    members = _list(
        "HD Customer Member",
        fields=["parent", "contact_name", "is_manager"],
        order_by="idx asc",
        limit_page_length=ACTIVATION_SCAN_LIMIT + 1,
        ignore_permissions=True,
    )
    truncated = len(members) > ACTIVATION_SCAN_LIMIT
    members = members[:ACTIVATION_SCAN_LIMIT]
    contact_names = sorted(
        {str(row.get("contact_name") or "") for row in members if row.get("contact_name")}
    )
    contacts = (
        _list(
            "Contact",
            filters=[["name", "in", contact_names]],
            fields=["name", "email_id", "user"],
            limit_page_length=max(1, len(contact_names)),
            ignore_permissions=True,
        )
        if contact_names
        else []
    )
    account_ids = sorted(
        {
            str(row.get("user") or row.get("email_id") or "").strip().lower()
            for row in contacts
            if row.get("user") or row.get("email_id")
        }
    )
    users = (
        _list(
            "User",
            filters=[["name", "in", account_ids]],
            fields=["name", "enabled", "last_login"],
            limit_page_length=max(1, len(account_ids)),
            ignore_permissions=True,
        )
        if account_ids
        else []
    )
    user_names = {str(row.get("name") or "") for row in users}
    role_rows = (
        _list(
            "Has Role",
            filters=[
                ["parent", "in", sorted(user_names)],
                ["parenttype", "=", "User"],
                ["role", "in", sorted(PORTAL_ROLES)],
            ],
            fields=["parent", "role"],
            limit_page_length=max(1, len(user_names) * 2),
            ignore_permissions=True,
        )
        if user_names
        else []
    )
    roles_by_user: dict[str, set[str]] = {}
    for row in role_rows:
        roles_by_user.setdefault(str(row.get("parent") or ""), set()).add(
            str(row.get("role") or "")
        )
    invited_users = [
        row
        for row in users
        if bool(row.get("enabled")) and roles_by_user.get(str(row.get("name") or ""))
    ]
    activated = sum(bool(row.get("last_login")) for row in invited_users)
    managers = sum(
        "HD Customer Manager" in roles_by_user.get(str(row.get("name") or ""), set())
        for row in invited_users
    )
    invited = len(invited_users)
    return {
        "customers": len({str(row.get("parent") or "") for row in members if row.get("parent")}),
        "members": len(members),
        "contacts_with_accounts": len(users),
        "invited": invited,
        "activated": activated,
        "customer_managers": managers,
        "activation_rate": round(activated * 100 / invited) if invited else 0,
        "scan_limit": ACTIVATION_SCAN_LIMIT,
        "scan_truncated": truncated,
    }


def _empty_activation() -> dict:
    return {
        "customers": 0,
        "members": 0,
        "contacts_with_accounts": 0,
        "invited": 0,
        "activated": 0,
        "customer_managers": 0,
        "activation_rate": 0,
        "scan_limit": ACTIVATION_SCAN_LIMIT,
        "scan_truncated": False,
    }


def _test_run(portal_ready: bool) -> list[dict]:
    intake = _count("HD Ticket", {"via_customer_portal": 1}) > 0
    assigned = bool(
        _list(
            "HD Ticket",
            filters=[["_assign", "not in", ["", "[]"]]],
            fields=["name"],
            limit_page_length=1,
            ignore_permissions=True,
        )
    )
    replied = (
        _count(
            "Communication",
            {
                "reference_doctype": "HD Ticket",
                "sent_or_received": "Sent",
                "communication_type": "Communication",
            },
        )
        > 0
    )
    return [
        _step(
            "portal",
            "Portal access",
            portal_ready,
            "Open the customer portal as the invited contact.",
            "/helpdesk",
        ),
        _step(
            "intake",
            "Customer intake",
            intake,
            "Submit one ticket from the customer portal.",
            "/helpdesk/tickets",
        ),
        _step(
            "assignment",
            "Agent assignment",
            assigned,
            "Assign the test ticket to an active agent.",
            "/helpdesk/tickets",
        ),
        _step(
            "reply",
            "Reply delivery",
            replied,
            "Reply from the agent and confirm the customer receives it.",
            "/helpdesk/tickets",
        ),
    ]


def _check(key: str, label: str, status: str, detail: str, desk_path: str) -> dict:
    return {"key": key, "label": label, "status": status, "detail": detail, "desk_path": desk_path}


def _step(key: str, label: str, complete: bool, detail: str, desk_path: str) -> dict:
    return {
        "key": key,
        "label": label,
        "complete": complete,
        "detail": detail,
        "desk_path": desk_path,
    }


def _installed_apps() -> set[str]:
    try:
        values = frappe.get_installed_apps()
    except Exception:
        return set()
    return {str(value) for value in values} if isinstance(values, list | tuple | set) else set()


def _versions() -> dict[str, str]:
    try:
        raw = frappe.get_versions()
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    result = {}
    for app, value in raw.items():
        if isinstance(value, dict):
            result[str(app)] = str(value.get("version") or value.get("branch") or "")
        elif isinstance(value, str):
            result[str(app)] = value
    return result


def _major(value: str) -> int | None:
    match = re.search(r"(?:^|v)(\d+)", str(value or ""))
    return int(match.group(1)) if match else None


def _version_detail(versions: dict[str, str], frappe_major: int | None) -> str:
    detected = ", ".join(
        f"{app} {versions[app]}" for app in ("frappe", "helpdesk") if versions.get(app)
    )
    prefix = f"Detected {detected}. " if detected else "Versions could not be read. "
    if frappe_major in SUPPORTED_FRAPPE_MAJORS:
        return prefix + "Bude supports Frappe majors 15 and 16."
    return prefix + "Certify this release on Frappe 15 or 16 before production."


def _scheduler_active() -> bool:
    try:
        return not bool(frappe.utils.scheduler.is_scheduler_inactive())
    except Exception:
        return True


def _push_configured() -> bool:
    return any(
        bool(_conf(key))
        for key in ("fcm_service_account", "fcm_service_account_path", "fcm_server_key")
    )


def _activation_detail(activation: dict) -> str:
    invited = activation["invited"]
    if not invited:
        return "Invite customer contacts from Helpdesk Customers, then verify their first login."
    return f'{activation["activated"]} of {invited} invited portal users have logged in ({activation["activation_rate"]}%).'


def _exists(doctype: str, name_or_filters) -> bool:
    try:
        value = frappe.db.exists(doctype, name_or_filters)
    except Exception:
        return False
    return bool(value) if isinstance(value, bool | int | str) else False


def _count(doctype: str, filters: dict | None = None) -> int:
    try:
        value = frappe.db.count(doctype, filters=filters or {})
    except Exception:
        return 0
    return int(value) if isinstance(value, bool | int) else 0


def _single_value(doctype: str, fieldname: str):
    try:
        value = frappe.db.get_single_value(doctype, fieldname)
    except Exception:
        return None
    return value if isinstance(value, str | bool | int | float) else None


def _list(doctype: str, **kwargs) -> list[dict]:
    try:
        rows = frappe.get_list(doctype, **kwargs)
    except Exception:
        return []
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _conf(key: str):
    conf = getattr(frappe, "conf", {})
    try:
        value = conf.get(key)
    except Exception:
        value = getattr(conf, key, None)
    return value if isinstance(value, str | dict) else ""
