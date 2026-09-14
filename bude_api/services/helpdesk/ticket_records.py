"""Grouped helpdesk ticket endpoints: ticket_records."""

from datetime import date, datetime, timedelta, timezone
import json
import re

from ._tickets_shared import *  # noqa: F401,F403


_CLOSED_TICKET_STATUSES = {"Closed", "Resolved"}
_PRIORITY_RANK = {"urgent": 0, "high": 1, "medium": 2, "low": 3}


def _pulse_datetime(value) -> datetime | None:
    """Parse Frappe timestamps without depending on a particular framework version."""
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _pulse_unassigned(value) -> bool:
    if value in (None, "", [], ()):
        return True
    if isinstance(value, str):
        raw = value.strip()
        if raw in {"", "[]", "null"}:
            return True
        try:
            decoded = json.loads(raw)
            return not decoded if isinstance(decoded, list) else False
        except (TypeError, ValueError):
            return False
    return False


def _pulse_deadline(row: dict) -> datetime | None:
    if not row.get("first_responded_on"):
        response_deadline = _pulse_datetime(row.get("response_by"))
        if response_deadline:
            return response_deadline
    return _pulse_datetime(row.get("resolution_by"))


def _pulse_ticket(row: dict, now: datetime, due_soon_hours: int) -> dict:
    payload = _serialize_ticket(row)
    deadline = _pulse_deadline(row)
    if deadline is None:
        sla_state = "none"
        due_in_minutes = None
    else:
        due_in_minutes = int((deadline - now).total_seconds() // 60)
        if due_in_minutes < 0:
            sla_state = "overdue"
        elif deadline <= now + timedelta(hours=due_soon_hours):
            sla_state = "due_soon"
        else:
            sla_state = "on_track"
    payload.update(
        {
            "assigned": not _pulse_unassigned(row.get("_assign")),
            "sla_state": sla_state,
            "next_deadline": str(deadline or ""),
            "due_in_minutes": due_in_minutes,
        }
    )
    return payload


def _pulse_sort_key(row: dict) -> tuple:
    deadline = _pulse_deadline(row) or datetime.max
    priority = _PRIORITY_RANK.get(str(row.get("priority") or "").lower(), 4)
    created = _pulse_datetime(row.get("creation")) or datetime.max
    return (deadline, priority, created, str(row.get("name") or ""))


def support_pulse(limit: int = 5, due_soon_hours: int = 4) -> dict:
    """Return an agent-safe operations snapshot and deterministic next-work queue.

    The query uses ``get_list`` (not ``get_all``) so Helpdesk's standard team
    and document permissions remain the source of truth. Metrics explicitly
    report when the bounded scan was truncated.
    """
    denied = require_helpdesk_agent_role(frappe)
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    try:
        limit = int(limit)
        due_soon_hours = int(due_soon_hours)
    except (TypeError, ValueError):
        return failure("limit and due_soon_hours must be integers.", code="VALIDATION_BAD_LIMIT")
    if limit < 1 or limit > 20:
        return failure("limit must be between 1 and 20.", code="VALIDATION_BAD_LIMIT")
    if due_soon_hours < 1 or due_soon_hours > 24:
        return failure(
            "due_soon_hours must be between 1 and 24.",
            code="VALIDATION_BAD_WINDOW",
        )

    fields = _ticket_fields()
    if "_assign" not in fields:
        fields.append("_assign")
    rows = frappe.get_list(
        "HD Ticket",
        filters=[["status", "not in", sorted(_CLOSED_TICKET_STATUSES)]],
        fields=fields,
        order_by="creation asc",
        limit_page_length=SUPPORT_PULSE_SCAN_LIMIT + 1,
    )
    truncated = len(rows) > SUPPORT_PULSE_SCAN_LIMIT
    rows = rows[:SUPPORT_PULSE_SCAN_LIMIT]
    try:
        now = _pulse_datetime(frappe.utils.now_datetime()) or datetime.now()
    except Exception:
        now = datetime.now()

    enriched = [_pulse_ticket(row, now, due_soon_hours) for row in rows]
    unassigned_rows = [row for row in rows if _pulse_unassigned(row.get("_assign"))]
    next_rows = sorted(unassigned_rows or rows, key=_pulse_sort_key)[:limit]

    priority_counts: dict[str, int] = {}
    team_counts: dict[str, int] = {}
    for row in rows:
        priority = str(row.get("priority") or "Unspecified")
        team = str(row.get("agent_group") or "Unassigned team")
        priority_counts[priority] = priority_counts.get(priority, 0) + 1
        team_counts[team] = team_counts.get(team, 0) + 1

    counts = {
        "open": len(rows),
        "unassigned": len(unassigned_rows),
        "overdue": sum(item["sla_state"] == "overdue" for item in enriched),
        "due_soon": sum(item["sla_state"] == "due_soon" for item in enriched),
        "urgent": sum(str(row.get("priority") or "").lower() == "urgent" for row in rows),
    }
    return success(
        {
            "server_now": str(now),
            "due_soon_hours": due_soon_hours,
            "counts": counts,
            "next_up": [_pulse_ticket(row, now, due_soon_hours) for row in next_rows],
            "by_priority": [
                {"label": label, "count": count}
                for label, count in sorted(
                    priority_counts.items(),
                    key=lambda item: (_PRIORITY_RANK.get(item[0].lower(), 4), item[0]),
                )
            ],
            "by_team": [
                {"label": label, "count": count}
                for label, count in sorted(team_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "scan_limit": SUPPORT_PULSE_SCAN_LIMIT,
            "scan_truncated": truncated,
        }
    )


def my_tickets(
    status: str | None = None,
    priority: str | None = None,
    ticket_type: str | None = None,
    team: str | None = None,
    search: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
) -> dict:
    denied = _require_login()
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    page = parse_page(limit, offset, default_limit=DEFAULT_PAGE_LIMIT, max_limit=MAX_PAGE_LIMIT)
    if isinstance(page, dict):
        return page
    filters = [["raised_by", "=", _current_user()]]
    if status:
        filters.append(["status", "=", status])
    _add_optional_ticket_filters(
        filters,
        priority=priority,
        ticket_type=ticket_type,
        team=team,
        from_date=from_date,
        to_date=to_date,
    )
    kwargs = {
        "filters": filters,
        "fields": _ticket_fields(),
        "order_by": "modified desc",
        "limit_start": page.offset,
        "limit_page_length": page.limit,
        "ignore_permissions": True,
    }
    or_filters = _ticket_search_or_filters(search)
    if or_filters:
        kwargs["or_filters"] = or_filters
    rows = frappe.get_list("HD Ticket", **kwargs)
    return success([_serialize_ticket(row) for row in rows])


def agent_tickets(
    status: str | None = None,
    priority: str | None = None,
    ticket_type: str | None = None,
    team: str | None = None,
    search: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    assigned_to_me: bool = False,
    unassigned: bool = False,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
) -> dict:
    denied = require_helpdesk_agent_role(frappe)
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    page = parse_page(limit, offset, default_limit=DEFAULT_PAGE_LIMIT, max_limit=MAX_PAGE_LIMIT)
    if isinstance(page, dict):
        return page
    filters = []
    if status:
        filters.append(["status", "=", status])
    if team:
        filters.append(["agent_group", "=", team])
    if assigned_to_me in (True, 1, "1", "true", "True"):
        filters.append(["_assign", "like", f"%{_current_user()}%"])
    _add_optional_ticket_filters(
        filters,
        priority=priority,
        ticket_type=ticket_type,
        from_date=from_date,
        to_date=to_date,
        unassigned=unassigned,
    )
    kwargs = {
        "filters": filters,
        "fields": _ticket_fields(),
        "order_by": "modified desc",
        "limit_start": page.offset,
        "limit_page_length": page.limit,
    }
    or_filters = _ticket_search_or_filters(search, include_requester=True)
    if or_filters:
        kwargs["or_filters"] = or_filters
    rows = frappe.get_list("HD Ticket", **kwargs)
    return success([_serialize_ticket(row) for row in rows])


def ticket_detail(ticket_name: str) -> dict:
    denied = _require_login()
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name:
        return failure("ticket_name is required.", code="VALIDATION_REQUIRED")
    ticket, error = _visible_ticket(ticket_name)
    if error:
        return error
    conversation = frappe.get_list(
        "Communication",
        filters=[
            ["reference_doctype", "=", "HD Ticket"],
            ["reference_name", "=", ticket_name],
            ["communication_type", "=", "Communication"],
        ],
        fields=["name", "sender", "sender_full_name", "content", "sent_or_received", "creation"],
        order_by="creation asc",
        limit_page_length=MAX_CONVERSATION_ROWS,
        ignore_permissions=True,
    )
    payload = _serialize_ticket(ticket)
    try:
        payload["server_now"] = str(frappe.utils.now_datetime())
    except Exception:
        payload["server_now"] = ""
    payload["description"] = ticket.get("description") or ""
    payload["attachments"] = _ticket_attachments(ticket_name)
    payload["conversation"] = [
        {
            "name": str(row.get("name") or ""),
            "sender": row.get("sender") or "",
            "sender_name": row.get("sender_full_name") or "",
            "content": row.get("content") or "",
            "direction": row.get("sent_or_received") or "",
            "creation": str(row.get("creation") or ""),
        }
        for row in conversation
    ]
    if _is_agent():
        comments = frappe.get_list(
            "HD Ticket Comment",
            filters=[["reference_ticket", "=", ticket_name]],
            fields=["name", "commented_by", "content", "creation"],
            order_by="creation asc",
            limit_page_length=MAX_CONVERSATION_ROWS,
        )
        payload["comments"] = [
            {
                "name": str(row.get("name") or ""),
                "commented_by": row.get("commented_by") or "",
                "content": row.get("content") or "",
                "creation": str(row.get("creation") or ""),
            }
            for row in comments
        ]
    return success(payload)


def suggest_articles(ticket_name: str, limit: int = 3) -> dict:
    """Suggest published standard Helpdesk articles for a visible ticket."""
    denied = _require_login()
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name:
        return failure("ticket_name is required.", code="VALIDATION_REQUIRED")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if limit < 1 or limit > 10:
        return failure(
            "limit must be between 1 and 10.",
            code="VALIDATION_BAD_LIMIT",
        )
    ticket, error = _visible_ticket(ticket_name)
    if error:
        return error
    if not _optional_doctype_exists("HD Article"):
        return success([])

    terms = []
    for term in re.findall(r"[A-Za-z0-9]+", ticket.get("subject") or ""):
        normalized = term.lower()
        if len(normalized) < 4 or normalized in terms:
            continue
        terms.append(normalized)
        if len(terms) == 5:
            break
    if not terms:
        return success([])
    fields = _optional_fields(
        "HD Article",
        [
            "name",
            "title",
            "title_slug",
            "category",
            "content",
            "views",
            "published_on",
        ],
    )
    if "title" not in fields:
        return success([])
    or_filters = []
    for term in terms:
        or_filters.append(["title", "like", f"%{term}%"])
        if "content" in fields:
            or_filters.append(["content", "like", f"%{term}%"])
    try:
        rows = frappe.get_list(
            "HD Article",
            filters=[["status", "=", "Published"]],
            or_filters=or_filters,
            fields=fields,
            order_by="views desc, modified desc",
            limit_page_length=limit,
            ignore_permissions=True,
        )
    except Exception:
        return success([])
    return success(
        [
            {
                "name": str(row.get("name") or ""),
                "title": row.get("title") or "",
                "title_slug": row.get("title_slug") or "",
                "category": row.get("category") or "",
                "content": row.get("content") or "",
                "views": int(row.get("views") or 0),
                "published_on": str(row.get("published_on") or ""),
            }
            for row in rows
        ]
    )


def related_tickets(ticket_name: str, limit: int = 5) -> dict:
    """Return other visible-context tickets raised by the same requester."""
    denied = _require_login()
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name:
        return failure("ticket_name is required.", code="VALIDATION_REQUIRED")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if limit < 1 or limit > 20:
        return failure("limit must be between 1 and 20.", code="VALIDATION_BAD_LIMIT")
    ticket, error = _visible_ticket(ticket_name)
    if error:
        return error
    requester = str(ticket.get("raised_by") or "").strip()
    if not requester:
        return success([])
    try:
        rows = frappe.get_list(
            "HD Ticket",
            filters=[
                ["raised_by", "=", requester],
                ["name", "!=", ticket_name],
            ],
            fields=_ticket_fields(),
            order_by="modified desc",
            limit_page_length=limit,
            ignore_permissions=True,
        )
    except Exception:
        return success([])
    return success([_serialize_ticket(row) for row in rows])


def customer_ticket_context(ticket_name: str, limit: int = 5) -> dict:
    """Return agent-only workload context for the ticket's customer/requester."""
    denied = require_helpdesk_agent_role(frappe)
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name:
        return failure("ticket_name is required.", code="VALIDATION_REQUIRED")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if limit < 1 or limit > 20:
        return failure("limit must be between 1 and 20.", code="VALIDATION_BAD_LIMIT")
    ticket, error = _visible_ticket(ticket_name)
    if error:
        return error
    customer = str(ticket.get("customer") or "").strip()
    requester = str(ticket.get("raised_by") or "").strip()
    scope_field = "customer" if customer else "raised_by"
    scope_value = customer or requester
    if not scope_value:
        return success(
            {
                "scope": "",
                "open": 0,
                "urgent": 0,
                "resolved": 0,
                "recent": [],
                "truncated": False,
            }
        )
    try:
        rows = frappe.get_list(
            "HD Ticket",
            filters=[[scope_field, "=", scope_value]],
            fields=_ticket_fields(),
            order_by="modified desc",
            limit_page_length=101,
        )
    except Exception:
        rows = []
    truncated = len(rows) > 100
    rows = rows[:100]
    open_statuses = {"open", "replied", "on hold"}
    resolved_statuses = {"resolved", "closed"}
    return success(
        {
            "scope": scope_value,
            "open": sum(
                1 for row in rows if str(row.get("status") or "").lower() in open_statuses
            ),
            "urgent": sum(
                1
                for row in rows
                if str(row.get("priority") or "").lower() in {"high", "urgent"}
                and str(row.get("status") or "").lower() in open_statuses
            ),
            "resolved": sum(
                1
                for row in rows
                if str(row.get("status") or "").lower() in resolved_statuses
            ),
            "recent": [
                _serialize_ticket(row)
                for row in rows
                if row.get("name") != ticket_name
            ][:limit],
            "truncated": truncated,
        }
    )


def ticket_assignments(ticket_name: str) -> dict:
    """Return active standard ToDo assignments for an agent-visible ticket."""
    denied = require_helpdesk_agent_role(frappe)
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name:
        return failure("ticket_name is required.", code="VALIDATION_REQUIRED")
    _, error = _visible_ticket(ticket_name)
    if error:
        return error
    if not _optional_doctype_exists("ToDo"):
        return success([])
    fields = _optional_fields(
        "ToDo",
        [
            "name",
            "status",
            "priority",
            "date",
            "allocated_to",
            "assigned_by",
            "assigned_by_full_name",
            "description",
        ],
    )
    try:
        rows = frappe.get_list(
            "ToDo",
            filters=[
                ["reference_type", "=", "HD Ticket"],
                ["reference_name", "=", ticket_name],
                ["status", "=", "Open"],
            ],
            fields=fields,
            order_by="date asc, creation asc",
            limit_page_length=50,
        )
    except Exception:
        rows = []
    return success(
        [
            {
                "name": row.get("name") or "",
                "status": row.get("status") or "",
                "priority": row.get("priority") or "",
                "due_date": str(row.get("date") or ""),
                "allocated_to": row.get("allocated_to") or "",
                "assigned_by": row.get("assigned_by") or "",
                "assigned_by_name": row.get("assigned_by_full_name") or "",
                "description": row.get("description") or "",
            }
            for row in rows
        ]
    )


def saved_replies(ticket_name: str, limit: int = 5) -> dict:
    """Return saved replies visible to the current agent and ticket team."""
    denied = require_helpdesk_agent_role(frappe)
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name:
        return failure("ticket_name is required.", code="VALIDATION_REQUIRED")
    try:
        limit = max(1, min(int(limit), 20))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    ticket, error = _visible_ticket(ticket_name)
    if error:
        return error
    if not _optional_doctype_exists("HD Saved Reply"):
        return success([])

    fields = _optional_fields(
        "HD Saved Reply",
        ["name", "title", "message", "scope", "owner", "modified"],
    )
    try:
        rows = frappe.get_list(
            "HD Saved Reply",
            fields=fields,
            order_by="modified desc",
            limit_page_length=200,
        )
    except Exception:
        rows = []

    team = str(ticket.get("agent_group") or "")
    team_reply_names: set[str] = set()
    team_candidates = [
        str(row.get("name") or "")
        for row in rows
        if str(row.get("scope") or "Global") == "Team"
    ]
    if team and team_candidates and _optional_doctype_exists("HD Saved Reply Team"):
        try:
            links = frappe.get_list(
                "HD Saved Reply Team",
                filters=[
                    ["parent", "in", team_candidates],
                    ["parenttype", "=", "HD Saved Reply"],
                    ["team", "=", team],
                ],
                fields=_optional_fields(
                    "HD Saved Reply Team",
                    ["parent", "team"],
                ),
                limit_page_length=200,
            )
        except Exception:
            links = []
        team_reply_names = {
            str(row.get("parent") or "") for row in links if row.get("parent")
        }

    user = _current_user()
    visible = []
    for row in rows:
        scope = str(row.get("scope") or "Global")
        name = str(row.get("name") or "")
        if scope == "Personal" and row.get("owner") != user:
            continue
        if scope == "Team" and name not in team_reply_names:
            continue
        if scope not in {"Global", "Personal", "Team"}:
            continue
        visible.append(
            {
                "name": name,
                "title": row.get("title") or name,
                "message": row.get("message") or "",
                "scope": scope,
            }
        )
        if len(visible) >= limit:
            break
    return success(visible)


def ticket_sla_context(ticket_name: str) -> dict:
    """Return the standard SLA policy and timing target for a visible ticket."""
    denied = _require_login()
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name:
        return failure("ticket_name is required.", code="VALIDATION_REQUIRED")
    ticket, error = _visible_ticket(ticket_name)
    if error:
        return error
    empty = {
        "sla": "",
        "description": "",
        "start_date": "",
        "end_date": "",
        "holiday_list": "",
        "holiday_list_description": "",
        "holiday_list_from": "",
        "holiday_list_to": "",
        "holidays": [],
        "apply_sla_for_resolution": False,
        "priority": ticket.get("priority") or "",
        "response_time": 0,
        "resolution_time": 0,
        "working_hours": [],
        "raised_outside_working_hours": bool(
            ticket.get("raised_outside_working_hours")
        ),
        "on_hold_since": str(ticket.get("on_hold_since") or ""),
        "total_hold_time": float(ticket.get("total_hold_time") or 0),
    }
    sla = str(ticket.get("sla") or "")
    if not sla or not _optional_doctype_exists("HD Service Level Agreement"):
        return success(empty)

    agreement_fields = _optional_fields(
        "HD Service Level Agreement",
        [
            "name",
            "service_level",
            "description",
            "start_date",
            "end_date",
            "holiday_list",
            "apply_sla_for_resolution",
            "enabled",
        ],
    )
    agreement_filters = [["name", "=", sla]]
    if "enabled" in agreement_fields:
        agreement_filters.append(["enabled", "=", 1])
    try:
        agreements = frappe.get_list(
            "HD Service Level Agreement",
            filters=agreement_filters,
            fields=agreement_fields,
            limit_page_length=1,
            ignore_permissions=True,
        )
    except Exception:
        agreements = []
    if not agreements:
        return success(empty)
    agreement = agreements[0]

    priority_rows = []
    if _optional_doctype_exists("HD Service Level Priority"):
        try:
            priority_rows = frappe.get_list(
                "HD Service Level Priority",
                filters=[
                    ["parent", "=", sla],
                    ["parenttype", "=", "HD Service Level Agreement"],
                ],
                fields=_optional_fields(
                    "HD Service Level Priority",
                    [
                        "priority",
                        "response_time",
                        "resolution_time",
                        "default_priority",
                    ],
                ),
                order_by="idx asc",
                limit_page_length=50,
                ignore_permissions=True,
            )
        except Exception:
            priority_rows = []
    priority = str(ticket.get("priority") or "")
    target = next(
        (
            row
            for row in priority_rows
            if str(row.get("priority") or "") == priority
        ),
        None,
    )
    if target is None:
        target = next(
            (row for row in priority_rows if row.get("default_priority")),
            {},
        )

    working_hours = []
    if _optional_doctype_exists("HD Service Day"):
        try:
            days = frappe.get_list(
                "HD Service Day",
                filters=[
                    ["parent", "=", sla],
                    ["parenttype", "=", "HD Service Level Agreement"],
                ],
                fields=_optional_fields(
                    "HD Service Day",
                    ["workday", "start_time", "end_time"],
                ),
                order_by="idx asc",
                limit_page_length=14,
                ignore_permissions=True,
            )
        except Exception:
            days = []
        working_hours = [
            {
                "workday": row.get("workday") or "",
                "start_time": str(row.get("start_time") or ""),
                "end_time": str(row.get("end_time") or ""),
            }
            for row in days
        ]

    holiday_list = str(agreement.get("holiday_list") or "")
    holiday_description = ""
    holiday_from = ""
    holiday_to = ""
    holidays = []
    if (
        holiday_list
        and _optional_doctype_exists("HD Service Holiday List")
        and _optional_doctype_exists("HD Holiday")
    ):
        try:
            calendars = frappe.get_list(
                "HD Service Holiday List",
                filters=[["name", "=", holiday_list]],
                fields=_optional_fields(
                    "HD Service Holiday List",
                    [
                        "name",
                        "holiday_list_name",
                        "description",
                        "from_date",
                        "to_date",
                        "weekly_off",
                    ],
                ),
                limit_page_length=1,
                ignore_permissions=True,
            )
        except Exception:
            calendars = []
        if calendars:
            calendar = calendars[0]
            holiday_description = calendar.get("description") or ""
            holiday_from = str(calendar.get("from_date") or "")
            holiday_to = str(calendar.get("to_date") or "")
            try:
                holiday_rows = frappe.get_list(
                    "HD Holiday",
                    filters=[
                        ["parent", "=", holiday_list],
                        ["parenttype", "=", "HD Service Holiday List"],
                        ["holiday_date", ">=", date.today().isoformat()],
                    ],
                    fields=_optional_fields(
                        "HD Holiday",
                        ["holiday_date", "description", "weekly_off"],
                    ),
                    order_by="holiday_date asc, idx asc",
                    limit_page_length=20,
                    ignore_permissions=True,
                )
            except Exception:
                holiday_rows = []
            holidays = [
                {
                    "date": str(row.get("holiday_date") or ""),
                    "description": row.get("description") or "",
                    "weekly_off": bool(row.get("weekly_off")),
                }
                for row in holiday_rows
                if row.get("holiday_date")
            ]

    return success(
        {
            **empty,
            "sla": agreement.get("service_level")
            or agreement.get("name")
            or sla,
            "description": agreement.get("description") or "",
            "start_date": str(agreement.get("start_date") or ""),
            "end_date": str(agreement.get("end_date") or ""),
            "holiday_list": holiday_list,
            "holiday_list_description": holiday_description,
            "holiday_list_from": holiday_from,
            "holiday_list_to": holiday_to,
            "holidays": holidays,
            "apply_sla_for_resolution": bool(
                agreement.get("apply_sla_for_resolution")
            ),
            "response_time": float(target.get("response_time") or 0),
            "resolution_time": float(target.get("resolution_time") or 0),
            "working_hours": working_hours,
        }
    )


def ticket_classification(ticket_name: str) -> dict:
    """Explain the visible ticket's standard type and template safely."""
    denied = _require_login()
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name:
        return failure("ticket_name is required.", code="VALIDATION_REQUIRED")
    ticket, error = _visible_ticket(ticket_name)
    if error:
        return error
    empty = {
        "ticket_type": ticket.get("ticket_type") or "",
        "type_description": "",
        "recommended_priority": "",
        "template": ticket.get("template") or "",
        "template_about": "",
        "fields": [],
    }
    ticket_type = str(ticket.get("ticket_type") or "")
    if ticket_type and _optional_doctype_exists("HD Ticket Type"):
        try:
            types = frappe.get_list(
                "HD Ticket Type",
                filters=[["name", "=", ticket_type]],
                fields=_optional_fields(
                    "HD Ticket Type",
                    ["name", "description", "priority", "disabled"],
                ),
                limit_page_length=1,
                ignore_permissions=True,
            )
        except Exception:
            types = []
        if types and not types[0].get("disabled"):
            empty["type_description"] = types[0].get("description") or ""
            empty["recommended_priority"] = types[0].get("priority") or ""

    template = str(ticket.get("template") or "")
    if not template or not _optional_doctype_exists("HD Ticket Template"):
        return success(empty)
    try:
        templates = frappe.get_list(
            "HD Ticket Template",
            filters=[["name", "=", template]],
            fields=_optional_fields(
                "HD Ticket Template",
                ["name", "template_name", "about"],
            ),
            limit_page_length=1,
            ignore_permissions=True,
        )
    except Exception:
        templates = []
    if templates:
        empty["template"] = (
            templates[0].get("template_name")
            or templates[0].get("name")
            or template
        )
        empty["template_about"] = templates[0].get("about") or ""
    if not _optional_doctype_exists("HD Ticket Template Field"):
        return success(empty)
    try:
        fields = frappe.get_list(
            "HD Ticket Template Field",
            filters=[
                ["parent", "=", template],
                ["parenttype", "=", "HD Ticket Template"],
            ],
            fields=_optional_fields(
                "HD Ticket Template Field",
                ["fieldname", "required", "hide_from_customer"],
            ),
            order_by="idx asc",
            limit_page_length=100,
            ignore_permissions=True,
        )
    except Exception:
        fields = []
    is_agent = _is_agent()
    empty["fields"] = [
        {
            "fieldname": row.get("fieldname") or "",
            "required": bool(row.get("required")),
        }
        for row in fields
        if row.get("fieldname")
        and (is_agent or not row.get("hide_from_customer"))
    ]
    return success(empty)


def ticket_team_context(ticket_name: str) -> dict:
    """Return active members and availability for an agent-visible team."""
    denied = require_helpdesk_agent_role(frappe)
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name:
        return failure("ticket_name is required.", code="VALIDATION_REQUIRED")
    ticket, error = _visible_ticket(ticket_name)
    if error:
        return error
    team = str(ticket.get("agent_group") or "")
    empty = {
        "team": team,
        "team_name": "",
        "assignment_rule": "",
        "members": [],
        "active_count": 0,
        "away_count": 0,
        "unavailable_count": 0,
    }
    required = ["HD Team", "HD Team Member", "HD Agent"]
    if not team or any(not _optional_doctype_exists(row) for row in required):
        return success(empty)
    try:
        teams = frappe.get_list(
            "HD Team",
            filters=[["name", "=", team]],
            fields=_optional_fields(
                "HD Team",
                ["name", "team_name", "assignment_rule", "disabled"],
            ),
            limit_page_length=1,
            ignore_permissions=True,
        )
    except Exception:
        teams = []
    if not teams or teams[0].get("disabled"):
        return success(empty)
    empty["team_name"] = teams[0].get("team_name") or team
    empty["assignment_rule"] = teams[0].get("assignment_rule") or ""
    try:
        member_rows = frappe.get_list(
            "HD Team Member",
            filters=[
                ["parent", "=", team],
                ["parenttype", "=", "HD Team"],
            ],
            fields=_optional_fields("HD Team Member", ["user"]),
            order_by="idx asc",
            limit_page_length=100,
            ignore_permissions=True,
        )
    except Exception:
        member_rows = []
    users = [
        str(row.get("user") or "") for row in member_rows if row.get("user")
    ]
    if not users:
        return success(empty)
    try:
        agents = frappe.get_list(
            "HD Agent",
            filters=[["user", "in", users], ["is_active", "=", 1]],
            fields=_optional_fields(
                "HD Agent",
                [
                    "user",
                    "agent_name",
                    "availability",
                    "availability_changed_on",
                ],
            ),
            limit_page_length=100,
            ignore_permissions=True,
        )
    except Exception:
        agents = []
    statuses = {}
    names = {
        str(row.get("availability") or "")
        for row in agents
        if row.get("availability")
    }
    if names and _optional_doctype_exists("HD Agent Status"):
        try:
            status_rows = frappe.get_list(
                "HD Agent Status",
                filters=[["name", "in", sorted(names)]],
                fields=_optional_fields(
                    "HD Agent Status",
                    ["name", "agent_status", "category", "color"],
                ),
                limit_page_length=len(names),
                ignore_permissions=True,
            )
        except Exception:
            status_rows = []
        statuses = {
            str(row.get("name") or ""): row for row in status_rows
        }
    members = []
    for row in agents:
        availability = str(row.get("availability") or "")
        status = statuses.get(availability, {})
        members.append(
            {
                "user": row.get("user") or "",
                "name": row.get("agent_name") or row.get("user") or "",
                "availability": status.get("agent_status") or availability,
                "category": status.get("category") or "",
                "color": status.get("color") or "",
                "changed_on": str(
                    row.get("availability_changed_on") or ""
                ),
            }
        )
    members.sort(key=lambda row: (row["category"] != "Active", row["name"]))
    empty["members"] = members
    empty["active_count"] = sum(
        row["category"] == "Active" for row in members
    )
    empty["away_count"] = sum(row["category"] == "Away" for row in members)
    empty["unavailable_count"] = sum(
        row["category"] == "Unavailable" for row in members
    )
    return success(empty)


def ticket_organization_context(ticket_name: str) -> dict:
    """Return safe standard HD Customer context for a visible ticket."""
    denied = _require_login()
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name:
        return failure("ticket_name is required.", code="VALIDATION_REQUIRED")
    ticket, error = _visible_ticket(ticket_name)
    if error:
        return error
    customer = str(ticket.get("customer") or "").strip()
    empty = {
        "customer": customer,
        "customer_name": "",
        "customer_type": "",
        "domain": "",
        "country": "",
        "erpnext_customer": "",
        "members": [],
        "member_count": 0,
        "members_visible": False,
    }
    if not customer or not _optional_doctype_exists("HD Customer"):
        return success(empty)
    try:
        customers = frappe.get_list(
            "HD Customer",
            filters=[["name", "=", customer]],
            fields=_optional_fields(
                "HD Customer",
                [
                    "name",
                    "customer_name",
                    "customer_type",
                    "domain",
                    "country",
                    "erpnext_customer",
                ],
            ),
            limit_page_length=1,
            ignore_permissions=True,
        )
    except Exception:
        customers = []
    if not customers:
        return success(empty)
    row = customers[0]
    result = {
        **empty,
        "customer_name": row.get("customer_name") or customer,
        "customer_type": row.get("customer_type") or "",
        "domain": row.get("domain") or "",
        "country": row.get("country") or "",
        "erpnext_customer": row.get("erpnext_customer") or "",
    }
    if not _is_agent() or not _optional_doctype_exists("HD Customer Member"):
        return success(result)
    try:
        members = frappe.get_list(
            "HD Customer Member",
            filters=[
                ["parent", "=", customer],
                ["parenttype", "=", "HD Customer"],
            ],
            fields=_optional_fields(
                "HD Customer Member",
                ["contact_name", "is_manager"],
            ),
            order_by="is_manager desc, idx asc",
            limit_page_length=100,
            ignore_permissions=True,
        )
    except Exception:
        members = []
    contact_names = [
        str(member.get("contact_name") or "")
        for member in members
        if member.get("contact_name")
    ]
    contacts_by_name = {}
    if contact_names and _optional_doctype_exists("Contact"):
        try:
            contacts = frappe.get_list(
                "Contact",
                filters=[["name", "in", contact_names]],
                fields=_optional_fields(
                    "Contact",
                    ["name", "full_name", "email_id", "mobile_no"],
                ),
                limit_page_length=len(contact_names),
                ignore_permissions=True,
            )
        except Exception:
            contacts = []
        contacts_by_name = {
            str(contact.get("name") or ""): contact for contact in contacts
        }
    result["members_visible"] = True
    result["member_count"] = len(members)
    result["members"] = [
        {
            "contact": contact_name,
            "name": contacts_by_name.get(contact_name, {}).get("full_name")
            or contact_name,
            "email": contacts_by_name.get(contact_name, {}).get("email_id")
            or "",
            "mobile": contacts_by_name.get(contact_name, {}).get("mobile_no")
            or "",
            "manager": bool(member.get("is_manager")),
        }
        for member in members
        if (contact_name := str(member.get("contact_name") or ""))
    ]
    return success(result)


def ticket_activity(ticket_name: str, limit: int = 30) -> dict:
    """Return a privacy-filtered activity timeline from standard Version rows."""
    denied = _require_login()
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name:
        return failure("ticket_name is required.", code="VALIDATION_REQUIRED")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if limit < 1 or limit > 100:
        return failure("limit must be between 1 and 100.", code="VALIDATION_BAD_LIMIT")
    _, error = _visible_ticket(ticket_name)
    if error:
        return error
    if not _optional_doctype_exists("Version"):
        return success([])
    fields = _optional_fields(
        "Version",
        ["name", "data", "owner", "creation"],
    )
    if "data" not in fields:
        return success([])
    try:
        rows = frappe.get_list(
            "Version",
            filters=[
                ["ref_doctype", "=", "HD Ticket"],
                ["docname", "=", ticket_name],
            ],
            fields=fields,
            order_by="creation desc",
            limit_page_length=100,
            ignore_permissions=True,
        )
    except Exception:
        return success([])

    allowed = {
        "status": "Status",
        "priority": "Priority",
        "ticket_type": "Ticket type",
        "agent_group": "Team",
        "customer": "Customer",
        "contact": "Contact",
        "response_by": "Response deadline",
        "resolution_by": "Resolution deadline",
    }
    if _is_agent():
        allowed["_assign"] = "Assignment"
    events = []
    for row in rows:
        data = _version_data(row.get("data"))
        for change in data.get("changed") or []:
            if not isinstance(change, list) or len(change) < 3:
                continue
            fieldname = str(change[0] or "")
            if fieldname not in allowed:
                continue
            events.append(
                {
                    "field": fieldname,
                    "label": allowed[fieldname],
                    "from": _activity_value(change[1]),
                    "to": _activity_value(change[2]),
                    "actor": row.get("owner") or "",
                    "creation": str(row.get("creation") or ""),
                }
            )
            if len(events) == limit:
                return success(events)
    return success(events)


def _version_data(value) -> dict:
    if isinstance(value, dict):
        return value
    try:
        decoded = json.loads(value or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _activity_value(value) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _optional_doctype_exists(doctype: str) -> bool:
    try:
        exists = frappe.db.exists("DocType", doctype)
    except Exception:
        return False
    return isinstance(exists, (bool, str)) and bool(exists)


def _optional_fields(doctype: str, fields: list[str]) -> list[str]:
    try:
        meta = frappe.get_meta(doctype)
        has_field = getattr(meta, "has_field", None)
        if callable(has_field):
            return [field for field in fields if field == "name" or has_field(field)]
    except Exception:
        pass
    return fields


def create_ticket(
    subject: str,
    description: str,
    priority: str | None = None,
    ticket_type: str | None = None,
) -> dict:
    denied = _require_login()
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not subject or not description:
        return failure("subject and description are required.", code="VALIDATION_REQUIRED")
    payload = {
        "doctype": "HD Ticket",
        "subject": subject,
        "description": description,
        "raised_by": _current_user(),
        "via_customer_portal": 1,
    }
    if priority:
        payload["priority"] = priority
    if ticket_type:
        payload["ticket_type"] = ticket_type
    try:
        doc = frappe.get_doc(payload)
        # ponytail: portal-style insert, same as upstream helpdesk's own portal API
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(str(exc), code="VALIDATION_ERPNEXT")
    return success({"name": doc.name, "status": doc.get("status")})


def close_ticket(ticket_name: str) -> dict:
    denied = _require_login()
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name:
        return failure("ticket_name is required.", code="VALIDATION_REQUIRED")
    return _set_ticket_status(ticket_name, DEFAULT_CLOSED_STATUS)


def reopen_ticket(ticket_name: str) -> dict:
    denied = _require_login()
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name:
        return failure("ticket_name is required.", code="VALIDATION_REQUIRED")
    return _set_ticket_status(ticket_name, DEFAULT_OPEN_STATUS)


def set_status(ticket_name: str, status: str) -> dict:
    denied = require_helpdesk_agent_role(frappe)
    if denied:
        return denied
    missing = _require_helpdesk()
    if missing:
        return missing
    if not ticket_name or not status:
        return failure("ticket_name and status are required.", code="VALIDATION_REQUIRED")
    if not frappe.db.exists("HD Ticket Status", status):
        return failure(f"Unknown ticket status: {status}", code="TICKET_STATUS_INVALID")
    return _set_ticket_status(ticket_name, status)
