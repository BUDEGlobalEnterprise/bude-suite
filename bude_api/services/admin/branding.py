"""Branding aggregator endpoint.

    GET /api/method/bude_api.api.branding.get   (auth required)

Returns a single payload that the mobile client uses to render the customer's
company identity (name, logo, address) plus version info for the connection-
info screen. Reads only standard ERPNext DocTypes (Company, Address) plus
the Frappe version helper — no custom DocTypes.
"""

import json

try:
    import frappe
    from frappe.utils.change_log import get_versions
except ImportError:
    frappe = None
    get_versions = None

from ... import __version__
from ...utils.response import success

# Frappe default key holding the site-wide per-role navigation config JSON.
NAV_CONFIG_KEY = "bude_nav_config"
DEFAULT_COMPANY_LOGO = "/assets/bude_api/images/logo.png"


def _whitelist(allow_guest: bool = False):
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=["GET"])


@_whitelist()
def get() -> dict:
    if frappe is None:
        return success(
            {
                "company_name": None,
                "company_logo": DEFAULT_COMPANY_LOGO,
                "company_address": None,
                "erpnext_version": None,
                "bude_api_version": __version__,
                "feature_flags": {"transfer": True, "receipt": True, "reconciliation": True},
            }
        )

    company_name = _resolve_company_name()
    company = _load_company(company_name) if company_name else None

    return success(
        {
            "company_name": company_name,
            "company_logo": _resolve_company_logo(company),
            "company_address": _resolve_address(company),
            "erpnext_version": _resolve_erpnext_version(),
            "bude_api_version": __version__,
            "feature_flags": _resolve_feature_flags(),
            "navigation": _resolve_navigation(),
        }
    )


def _resolve_navigation() -> dict | None:
    """Return the admin-configured per-role navigation config, or None."""
    if frappe is None:
        return None
    raw = frappe.db.get_default(NAV_CONFIG_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def _resolve_company_name() -> str | None:
    name = frappe.db.get_default("company")
    if name:
        return name
    rows = frappe.get_list("Company", fields=["name"], limit=1, order_by="creation asc")
    return rows[0]["name"] if rows else None


def _load_company(name: str) -> dict | None:
    fields = ["name", "company_logo", "country", "default_currency"]
    rows = frappe.get_list(
        "Company",
        filters=[["name", "=", name]],
        fields=fields,
        limit=1,
    )
    return rows[0] if rows else None


def _resolve_company_logo(company: dict | None) -> str:
    if company and company.get("company_logo"):
        return company["company_logo"]
    return DEFAULT_COMPANY_LOGO


def _resolve_address(company: dict | None) -> str | None:
    if not company:
        return None
    # Use the standard Address dynamic-link pattern: Address links to the
    # Company via Dynamic Link. Pull the first display string we can find.
    try:
        rows = frappe.get_all(
            "Dynamic Link",
            filters=[
                ["link_doctype", "=", "Company"],
                ["link_name", "=", company["name"]],
                ["parenttype", "=", "Address"],
            ],
            fields=["parent"],
            limit=1,
        )
    except Exception:
        return None
    if not rows:
        return None
    try:
        address = frappe.get_all(
            "Address",
            filters=[["name", "=", rows[0]["parent"]]],
            fields=["address_line1", "address_line2", "city", "state", "country", "pincode"],
            limit=1,
        )
    except Exception:
        return None
    if not address:
        return None
    a = address[0]
    parts = [
        a.get("address_line1"),
        a.get("address_line2"),
        a.get("city"),
        a.get("state"),
        a.get("country"),
        a.get("pincode"),
    ]
    return ", ".join(p for p in parts if p)


def _resolve_feature_flags() -> dict:
    """Return a map of feature → enabled based on installed apps / permissions."""
    flags = {
        "transfer": True,
        "receipt": True,
        "reconciliation": True,
    }
    try:
        installed = frappe.get_installed_apps()
        # If erpnext isn't installed, disable stock operations.
        if "erpnext" not in installed:
            flags["transfer"] = False
            flags["receipt"] = False
            flags["reconciliation"] = False
    except Exception:
        pass
    return flags


def _resolve_erpnext_version() -> str | None:
    if get_versions is None:
        return None
    try:
        versions = get_versions()
    except Exception:
        return None
    erpnext = versions.get("erpnext")
    if not erpnext:
        return None
    return erpnext.get("version")
