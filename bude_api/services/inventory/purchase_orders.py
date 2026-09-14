"""Purchase Order list endpoint.

    GET /api/method/bude_api.api.purchase_orders.list_open

Returns submitted POs that are not yet Closed, Completed, or Cancelled —
the set a warehouse operator can receive against. Wraps Frappe's Purchase Order
DocType so mobile clients use a consistent bude_api envelope.
"""

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success


def _whitelist(allow_guest: bool = False):
    if frappe is None:
        def decorator(fn):
            return fn
        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=["GET", "POST"])


@_whitelist()
def list_open(limit: int = 50) -> dict:
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    rows = frappe.get_list(
        "Purchase Order",
        filters=[
            ["docstatus", "=", 1],
            ["status", "not in", ["Closed", "Completed", "Cancelled"]],
        ],
        fields=["name"],
        order_by="transaction_date desc",
        limit_page_length=int(limit),
    )
    return success([r["name"] for r in rows])
