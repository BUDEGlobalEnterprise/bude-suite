"""Grouped admin.notifications endpoints: notification_payloads."""

from ._notifications_shared import *  # noqa: F401,F403

def payloads(limit: int | None = None, offset: int = 0) -> dict:
    """Return routeable notification payloads for the current user's devices."""
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    user = _user()
    if not user:
        return auth_expired()
    page = parse_page(limit, offset, default_limit=50, max_limit=200)
    if not isinstance(page, Page):
        return page

    prefs = _preferences(user)
    tokens = [
        row["token"]
        for row in _devices(user).values()
        if (row.get("token") or "").strip()
    ]
    rows = frappe.get_list(
        "Notification Log",
        filters=[["for_user", "=", user]],
        fields=["name", "subject", "email_content", "document_type", "document_name"],
        order_by="creation desc",
        limit_start=page.offset,
        limit_page_length=page.limit,
    )
    result = []
    for row in rows:
        category = _category_for(row)
        if not prefs.get(category, True):
            continue
        result.append({
            "notification_log": row.get("name"),
            "category": category,
            "title": row.get("subject") or category.replace("_", " ").title(),
            "body": row.get("email_content") or "",
            "route": _route_for_log(row, category),
            "tokens": tokens,
            "ref_doctype": row.get("document_type"),
            "ref_name": row.get("document_name"),
        })
    return success({
        "payloads": result,
        "limit": page.limit,
        "offset": page.offset,
        "total": len(result),
    })
