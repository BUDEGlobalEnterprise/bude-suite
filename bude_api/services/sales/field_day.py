"""Offline-ready field day pack assembled from standard ERPNext records."""

from datetime import date, datetime, timedelta

from ._mobile_shared import *  # noqa: F401,F403
from .catalog import items
from .customers import customers


def _serial(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def field_day(day: str | None = None, territory: str | None = None) -> dict:
    denied = require_sales_role(frappe)
    if denied:
        return denied
    try:
        selected = date.fromisoformat(day) if day else date.today()
    except ValueError:
        return failure("day must use YYYY-MM-DD.", code="VALIDATION_DATE")
    customer_result = customers(
        territory=territory,
        assigned_to_me=True,
        limit=200,
        offset=0,
    )
    if customer_result.get("ok") is not True:
        return customer_result
    customer_rows = customer_result["data"]["customers"]
    customer_names = [row.get("name") for row in customer_rows if row.get("name")]
    planned = _planned_visits(selected, customer_names)
    planned_names = [row["customer"] for row in planned]
    sequence = {name: index + 1 for index, name in enumerate(planned_names)}
    next_sequence = len(sequence) + 1
    for row in customer_rows:
        name = row.get("name")
        row["beat_sequence"] = sequence.get(name)
        row["planned"] = name in sequence
        if row["beat_sequence"] is None:
            row["suggested_sequence"] = next_sequence
            next_sequence += 1
    catalog_result = items(limit=200, offset=0)
    catalog = catalog_result.get("data", {}).get("items", []) if catalog_result.get("ok") else []
    return success(
        {
            "day": selected.isoformat(),
            "territory": territory or "",
            "generated_at": _serial(frappe.utils.now_datetime() if frappe else datetime.now()),
            "customers": customer_rows,
            "planned_visits": planned,
            "follow_ups": _customer_followups(selected, customer_names),
            "items": catalog,
            "customer_total": customer_result["data"].get("total", len(customer_rows)),
            "truncated": customer_result["data"].get("total", 0) > len(customer_rows),
        }
    )


def _planned_visits(selected: date, customer_names: list[str]) -> list[dict]:
    if not customer_names:
        return []
    try:
        participants = frappe.get_list(
            "Event Participants",
            filters=[
                ["reference_doctype", "=", "Customer"],
                ["reference_docname", "in", customer_names],
            ],
            fields=["parent", "reference_docname"],
            limit_page_length=500,
        )
        event_names = list({row.get("parent") for row in participants if row.get("parent")})
        if not event_names:
            return []
        start = selected.isoformat()
        end = (selected + timedelta(days=1)).isoformat()
        events = frappe.get_list(
            "Event",
            filters=[
                ["name", "in", event_names],
                ["starts_on", ">=", start],
                ["starts_on", "<", end],
            ],
            fields=["name", "subject", "starts_on", "ends_on", "status", "owner"],
            order_by="starts_on asc",
            limit_page_length=500,
        )
    except Exception:
        return []
    customer_by_event = {row.get("parent"): row.get("reference_docname") for row in participants}
    return [
        {
            "event": row.get("name") or "",
            "customer": customer_by_event.get(row.get("name")) or "",
            "subject": row.get("subject") or "Customer visit",
            "starts_on": _serial(row.get("starts_on")),
            "ends_on": _serial(row.get("ends_on")),
            "status": row.get("status") or "Open",
        }
        for row in events
        if customer_by_event.get(row.get("name"))
    ]


def _customer_followups(selected: date, customer_names: list[str]) -> list[dict]:
    if not customer_names:
        return []
    try:
        rows = frappe.get_list(
            "ToDo",
            filters=[
                ["reference_type", "=", "Customer"],
                ["reference_name", "in", customer_names],
                ["allocated_to", "=", _current_user()],
                ["status", "!=", "Closed"],
                ["date", "<=", selected.isoformat()],
            ],
            fields=["name", "description", "priority", "date", "reference_name", "status"],
            order_by="date asc, priority desc",
            limit_page_length=200,
        )
    except Exception:
        return []
    return [
        {
            "name": row.get("name") or "",
            "title": row.get("description") or "Follow up",
            "customer": row.get("reference_name") or "",
            "due_date": _serial(row.get("date")),
            "priority": row.get("priority") or "Medium",
            "status": row.get("status") or "Open",
        }
        for row in rows
    ]
