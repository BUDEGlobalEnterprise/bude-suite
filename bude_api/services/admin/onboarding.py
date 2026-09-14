"""Admin onboarding console helpers.

These endpoints keep early rollout work out of developer-only scripts: managers
can assign standard role profiles, inspect paired devices, revoke a stale
device, and intentionally trigger demo/pilot data seeding.
"""

try:
    import frappe
except ImportError:
    frappe = None

from ...demo.seed import run as seed_demo_run
from ...utils.response import failure, success
from .notifications import list_registered_devices, revoke_registered_device
from ..common.permissions import require_any_role

ADMIN_ONBOARDING_ROLES = {"Stock Manager", "System Manager"}


def _read(fn):
    return fn if frappe is None else frappe.whitelist()(fn)


def _write(fn):
    return fn if frappe is None else frappe.whitelist(methods=["POST"])(fn)


def _require_admin():
    return require_any_role(
        frappe,
        ADMIN_ONBOARDING_ROLES,
        "A stock manager or system manager role is required for onboarding.",
    )


@_read
def role_profiles(limit: int = 50) -> dict:
    denied = _require_admin()
    if denied:
        return denied
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    rows = frappe.get_list(
        "Role Profile",
        fields=["name", "role_profile"],
        limit_page_length=_coerce_limit(limit, 50, 200),
        order_by="name asc",
    )
    return success(rows)


@_read
def users(limit: int = 50, search: str | None = None) -> dict:
    denied = _require_admin()
    if denied:
        return denied
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    filters = [["enabled", "=", 1], ["user_type", "=", "System User"]]
    or_filters = None
    if search:
        term = f"%{search}%"
        or_filters = [["name", "like", term], ["full_name", "like", term]]
    rows = frappe.get_list(
        "User",
        fields=["name", "full_name", "role_profile_name"],
        filters=filters,
        or_filters=or_filters,
        limit_page_length=_coerce_limit(limit, 50, 200),
        order_by="modified desc",
    )
    return success(rows)


@_write
def assign_role_profile(user: str, role_profile: str) -> dict:
    denied = _require_admin()
    if denied:
        return denied
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    user = (user or "").strip()
    role_profile = (role_profile or "").strip()
    if not user or not role_profile:
        return failure("user and role_profile are required.", code="VALIDATION_REQUIRED")
    if not frappe.db.exists("User", user):
        return failure(f"User '{user}' was not found.", code="NOT_FOUND")
    if not frappe.db.exists("Role Profile", role_profile):
        return failure(f"Role Profile '{role_profile}' was not found.", code="NOT_FOUND")

    try:
        doc = frappe.get_doc("User", user)
        doc.set("role_profile_name", role_profile)
        doc.save(ignore_permissions=False)
        frappe.db.commit()
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    return success({"user": user, "role_profile": role_profile})


@_read
def devices() -> dict:
    denied = _require_admin()
    if denied:
        return denied
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    return success(list_registered_devices())


@_write
def revoke_device(user: str, device_id: str) -> dict:
    denied = _require_admin()
    if denied:
        return denied
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    removed = revoke_registered_device(user, device_id)
    return success({"user": user, "device_id": device_id, "revoked": removed})


@_write
def seed_pilot_workflow(
    confirm: bool = False,
    profile: str = "preview",
    base_url: str | None = None,
    dry_run: bool = False,
) -> dict:
    denied = _require_admin()
    if denied:
        return denied
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    if not _as_bool(confirm):
        return failure(
            "Confirmation is required before pilot workflow data is seeded.",
            code="CONFIRMATION_REQUIRED",
        )
    try:
        manifest = seed_demo_run(
            profile=profile,
            base_url=base_url,
            confirm_demo_data=True,
            dry_run=_as_bool(dry_run),
        )
    except ValueError as exc:
        return failure(str(exc), code="VALIDATION_DEMO_SEED")
    return success(manifest)


def _coerce_limit(value, default, cap):
    try:
        return max(1, min(int(value), cap))
    except (TypeError, ValueError):
        return default


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)
