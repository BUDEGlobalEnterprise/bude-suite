"""Permission-scoped collections queue from submitted Sales Invoices."""

from datetime import date

from ._mobile_shared import *  # noqa: F401,F403


def collections_queue(
    search: str | None = None,
    overdue_only: bool = False,
    company: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict:
    denied = require_sales_role(frappe)
    if denied:
        return denied
    page = _page(limit, offset)
    if not isinstance(page, Page):
        return page
    filters = [
        ["docstatus", "=", 1],
        ["outstanding_amount", ">", 0],
        ["is_return", "=", 0],
    ]
    if company:
        filters.append(["company", "=", company])
    if overdue_only in (True, 1, "1", "true", "True"):
        filters.append(["due_date", "<", date.today().isoformat()])
    if not _is_sales_manager():
        filters.append(["owner", "=", _current_user()])
    term = str(search or "").strip()
    or_filters = None
    if term:
        or_filters = [
            ["name", "like", f"%{term}%"],
            ["customer", "like", f"%{term}%"],
            ["customer_name", "like", f"%{term}%"],
        ]
    fields = _existing_fields(
        "Sales Invoice",
        [
            "name",
            "customer",
            "customer_name",
            "company",
            "posting_date",
            "due_date",
            "currency",
            "grand_total",
            "outstanding_amount",
            "status",
            "owner",
            "modified",
        ],
    )
    rows = frappe.get_list(
        "Sales Invoice",
        filters=filters,
        or_filters=or_filters,
        fields=fields,
        order_by="due_date asc, outstanding_amount desc",
        limit_start=page.offset,
        limit_page_length=page.limit,
    )
    normalized = [_collection_row(row) for row in rows]
    summary_rows = frappe.get_list(
        "Sales Invoice",
        filters=filters,
        or_filters=or_filters,
        fields=["currency", "outstanding_amount", "due_date"],
        limit_page_length=500,
    )
    totals = {}
    today = date.today()
    for row in summary_rows:
        currency = row.get("currency") or "Company Currency"
        bucket = totals.setdefault(currency, {"currency": currency, "outstanding": 0.0, "overdue": 0.0})
        amount = float(row.get("outstanding_amount") or 0)
        bucket["outstanding"] += amount
        due = _date(row.get("due_date"))
        if due and due < today:
            bucket["overdue"] += amount
    total = len(summary_rows) if term else _count("Sales Invoice", filters)
    return success(
        {
            "invoices": normalized,
            "totals": list(totals.values()),
            "total": total,
            "limit": page.limit,
            "offset": page.offset,
            "summary_truncated": total > len(summary_rows),
        }
    )


def _collection_row(row):
    due = _date(row.get("due_date"))
    overdue_days = max((date.today() - due).days, 0) if due else 0
    return {
        **row,
        "grand_total": float(row.get("grand_total") or 0),
        "outstanding_amount": float(row.get("outstanding_amount") or 0),
        "overdue_days": overdue_days,
        "overdue": overdue_days > 0,
    }


def _date(value):
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except (TypeError, ValueError):
        return None
