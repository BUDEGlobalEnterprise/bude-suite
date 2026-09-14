"""Company list endpoint.

    GET /api/method/bude_api.api.companies.list_companies  (auth required)
"""

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success


def _whitelist():
    if frappe is None:
        def decorator(fn):
            return fn
        return decorator
    return frappe.whitelist(allow_guest=False, methods=["GET"])


@_whitelist()
def list_companies(limit: int = 50) -> dict:
    """Return all ERPNext companies on this instance."""
    try:
        limit = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")

    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    companies = frappe.get_list(
        "Company",
        fields=["name", "company_name", "default_currency", "country"],
        order_by="creation asc",
        limit=limit,
    )
    return success(companies)
