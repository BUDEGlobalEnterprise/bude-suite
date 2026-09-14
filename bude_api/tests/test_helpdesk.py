from unittest.mock import MagicMock, patch

from bude_api.api import helpdesk as helpdesk_api


class _FakePermissionError(Exception):
    pass


class _FakeValidationError(Exception):
    pass


REQUESTER = "requester@example.com"


def _wire(mock_frappe, roles=None, user=REQUESTER):
    mock_frappe.PermissionError = _FakePermissionError
    mock_frappe.ValidationError = _FakeValidationError
    mock_frappe.session.user = user
    mock_frappe.get_roles.return_value = roles or ["Employee"]


def _ticket(raised_by=REQUESTER):
    return {
        "name": "HD-0001",
        "subject": "Laptop broken",
        "status": "Open",
        "priority": "Medium",
        "ticket_type": "Incident",
        "agent_group": "IT",
        "raised_by": raised_by,
        "response_by": "",
        "resolution_by": "2026-07-10 17:00:00",
        "agreement_status": "Fulfilled",
        "customer": "Acme",
        "contact": "CONT-001",
        "via_customer_portal": 1,
        "opening_date": "2026-07-10",
        "creation": "2026-07-10",
        "modified": "2026-07-10",
        "description": "Screen flickers",
        "resolution_details": "<p>Display cable replaced.</p>",
        "feedback": "Works perfectly now",
        "feedback_rating": 1,
    }


@patch("bude_api.api.helpdesk.frappe")
def test_my_tickets_requires_login(mock_frappe):
    _wire(mock_frappe, user="Guest")

    result = helpdesk_api.my_tickets()

    assert result["ok"] is False
    assert result["code"] == "AUTH_EXPIRED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.helpdesk.frappe")
def test_my_tickets_reports_missing_helpdesk_app(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = False

    result = helpdesk_api.my_tickets()

    assert result["ok"] is False
    assert result["code"] == "HELPDESK_NOT_INSTALLED"


@patch("bude_api.api.helpdesk.frappe")
def test_my_tickets_scoped_to_current_user(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [_ticket()]

    result = helpdesk_api.my_tickets(status="Open")

    assert result["ok"] is True
    assert result["data"][0]["name"] == "HD-0001"
    assert result["data"][0]["agreement_status"] == "Fulfilled"
    assert result["data"][0]["customer"] == "Acme"
    assert result["data"][0]["via_customer_portal"] is True
    _, kwargs = mock_frappe.get_list.call_args
    assert ["raised_by", "=", REQUESTER] in kwargs["filters"]
    assert ["status", "=", "Open"] in kwargs["filters"]
    assert kwargs["limit_page_length"] == 20
    assert "agreement_status" in kwargs["fields"]
    assert "first_responded_on" in kwargs["fields"]


@patch("bude_api.api.helpdesk.frappe")
def test_my_tickets_rejects_unbounded_limit(mock_frappe):
    _wire(mock_frappe)

    result = helpdesk_api.my_tickets(limit=1000)

    assert result["ok"] is False
    assert result["code"] == "PAGINATION_LIMIT_EXCEEDED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.helpdesk.frappe")
def test_support_pulse_requires_agent_role(mock_frappe):
    _wire(mock_frappe)

    result = helpdesk_api.support_pulse()

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.helpdesk.frappe")
def test_setup_health_requires_manager_role(mock_frappe):
    _wire(mock_frappe, roles=["Agent"], user="agent@example.com")

    result = helpdesk_api.setup_health()

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.helpdesk.frappe")
def test_setup_health_reports_activation_and_observed_test_run(mock_frappe):
    _wire(mock_frappe, roles=["Agent Manager"], user="manager@example.com")
    mock_frappe.get_installed_apps.return_value = ["frappe", "helpdesk", "bude_api"]
    mock_frappe.get_versions.return_value = {
        "frappe": {"version": "16.12.0"},
        "helpdesk": {"version": "1.28.0"},
    }
    mock_frappe.utils.scheduler.is_scheduler_inactive.return_value = False
    mock_frappe.conf = {
        "host_name": "support.example.com",
        "fcm_service_account_path": "/run/secrets/fcm.json",
    }

    def exists(doctype, name_or_filters):
        if doctype == "DocType" and name_or_filters == "HD Ticket":
            return "HD Ticket"
        if doctype == "Role" and name_or_filters in {
            "HD Customer",
            "HD Customer Manager",
        }:
            return name_or_filters
        return False

    def count(doctype, filters=None):
        values = {
            "Email Account": 1,
            "HD Agent": 3,
            "HD Team": 1,
            "HD Service Level Agreement": 1,
            "HD Ticket": 1,
            "Communication": 1,
        }
        return values.get(doctype, 0)

    def single_value(doctype, fieldname):
        if (doctype, fieldname) == ("HD Settings", "setup_complete"):
            return 1
        if (doctype, fieldname) == ("Portal Settings", "default_role"):
            return "HD Customer"
        return None

    def get_list(doctype, **kwargs):
        if doctype == "HD Customer Member":
            return [
                {"parent": "Acme", "contact_name": "CONT-001", "is_manager": 1},
                {"parent": "Acme", "contact_name": "CONT-002", "is_manager": 0},
            ]
        if doctype == "Contact":
            return [
                {"name": "CONT-001", "email_id": "asha@example.com", "user": "asha@example.com"},
                {"name": "CONT-002", "email_id": "sam@example.com", "user": "sam@example.com"},
            ]
        if doctype == "User":
            return [
                {"name": "asha@example.com", "enabled": 1, "last_login": "2026-08-05 09:00:00"},
                {"name": "sam@example.com", "enabled": 1, "last_login": None},
            ]
        if doctype == "Has Role":
            return [
                {"parent": "asha@example.com", "role": "HD Customer Manager"},
                {"parent": "sam@example.com", "role": "HD Customer"},
            ]
        if doctype == "HD Ticket":
            return [{"name": "HD-TEST-1"}]
        return []

    mock_frappe.db.exists.side_effect = exists
    mock_frappe.db.count.side_effect = count
    mock_frappe.db.get_single_value.side_effect = single_value
    mock_frappe.get_list.side_effect = get_list

    result = helpdesk_api.setup_health()

    assert result["ok"] is True
    data = result["data"]
    assert data["healthy"] is True
    assert data["versions"] == {"frappe": "16.12.0", "helpdesk": "1.28.0"}
    assert data["activation"] == {
        "customers": 1,
        "members": 2,
        "contacts_with_accounts": 2,
        "invited": 2,
        "activated": 1,
        "customer_managers": 1,
        "activation_rate": 50,
        "scan_limit": 500,
        "scan_truncated": False,
    }
    assert all(step["complete"] for step in data["test_run"])
    assert not any("email" in key for key in data["activation"])


@patch("bude_api.api.helpdesk.frappe")
def test_setup_health_flags_launch_blockers_without_leaking_config(mock_frappe):
    _wire(mock_frappe, roles=["System Manager"], user="manager@example.com")
    mock_frappe.get_installed_apps.return_value = ["frappe"]
    mock_frappe.get_versions.return_value = {"frappe": {"version": "17.0.0-dev"}}
    mock_frappe.db.exists.return_value = False
    mock_frappe.db.count.return_value = 0
    mock_frappe.db.get_single_value.return_value = None
    mock_frappe.get_list.return_value = []
    mock_frappe.utils.scheduler.is_scheduler_inactive.return_value = True
    mock_frappe.conf = {}

    result = helpdesk_api.setup_health()

    assert result["ok"] is True
    data = result["data"]
    assert data["healthy"] is False
    failing = {row["key"] for row in data["checks"] if row["status"] == "fail"}
    assert {"helpdesk", "incoming_email", "outgoing_email", "scheduler", "agents", "sla", "customer_portal"} <= failing
    assert "fcm_service_account" not in str(data)


@patch("bude_api.api.helpdesk.frappe")
def test_support_pulse_prioritizes_sla_then_priority_and_age(mock_frappe):
    _wire(mock_frappe, roles=["Agent"], user="agent@example.com")
    mock_frappe.db.exists.return_value = True
    mock_frappe.utils.now_datetime.return_value = "2026-08-05 10:00:00"
    overdue = {
        **_ticket("customer@example.com"),
        "name": "HD-OVERDUE",
        "subject": "Response overdue",
        "priority": "Medium",
        "response_by": "2026-08-05 09:30:00",
        "first_responded_on": "",
        "resolution_by": "2026-08-05 18:00:00",
        "creation": "2026-08-05 08:00:00",
        "_assign": "[]",
    }
    urgent = {
        **_ticket("customer@example.com"),
        "name": "HD-URGENT",
        "subject": "Urgent but later",
        "priority": "Urgent",
        "response_by": "2026-08-05 12:00:00",
        "first_responded_on": "",
        "resolution_by": "2026-08-05 19:00:00",
        "creation": "2026-08-05 09:00:00",
        "_assign": "[]",
    }
    assigned = {
        **_ticket("customer@example.com"),
        "name": "HD-ASSIGNED",
        "subject": "Already owned",
        "priority": "High",
        "response_by": "2026-08-05 10:30:00",
        "first_responded_on": "",
        "creation": "2026-08-05 07:00:00",
        "_assign": '["agent@example.com"]',
    }
    mock_frappe.get_list.return_value = [urgent, assigned, overdue]

    result = helpdesk_api.support_pulse(limit=2, due_soon_hours=4)

    assert result["ok"] is True
    data = result["data"]
    assert data["counts"] == {
        "open": 3,
        "unassigned": 2,
        "overdue": 1,
        "due_soon": 2,
        "urgent": 1,
    }
    assert [ticket["name"] for ticket in data["next_up"]] == [
        "HD-OVERDUE",
        "HD-URGENT",
    ]
    assert data["next_up"][0]["sla_state"] == "overdue"
    assert data["scan_truncated"] is False
    _, kwargs = mock_frappe.get_list.call_args
    assert ["status", "not in", ["Closed", "Resolved"]] in kwargs["filters"]
    assert kwargs["limit_page_length"] == 501
    assert "_assign" in kwargs["fields"]


@patch("bude_api.api.helpdesk.frappe")
def test_support_pulse_validates_window(mock_frappe):
    _wire(mock_frappe, roles=["Agent"], user="agent@example.com")
    mock_frappe.db.exists.return_value = True

    result = helpdesk_api.support_pulse(due_soon_hours=48)

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_WINDOW"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.helpdesk.frappe")
def test_ticket_detail_foreign_ticket_is_not_found(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = []

    result = helpdesk_api.ticket_detail("HD-0099")

    assert result["ok"] is False
    assert result["code"] == "TICKET_NOT_FOUND"
    # Non-agents must only ever see their own tickets.
    _, kwargs = mock_frappe.get_list.call_args
    assert ["raised_by", "=", REQUESTER] in kwargs["filters"]


@patch("bude_api.api.helpdesk.frappe")
def test_ticket_detail_requester_gets_conversation_not_comments(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.utils.now_datetime.return_value = "2026-07-10 09:00:00"
    mock_frappe.get_list.side_effect = [
        [_ticket()],
        [
            {
                "name": "COMM-1",
                "sender": REQUESTER,
                "sender_full_name": "Req",
                "content": "hello",
                "sent_or_received": "Received",
                "creation": "2026-07-10",
            }
        ],
        [],
    ]

    result = helpdesk_api.ticket_detail("HD-0001")

    assert result["ok"] is True
    assert result["data"]["conversation"][0]["content"] == "hello"
    assert result["data"]["attachments"] == []
    assert result["data"]["server_now"] == "2026-07-10 09:00:00"
    assert result["data"]["resolution_details"] == "<p>Display cable replaced.</p>"
    assert result["data"]["feedback"] == "Works perfectly now"
    assert result["data"]["feedback_rating"] == 1
    assert "comments" not in result["data"]


@patch("bude_api.api.helpdesk.frappe")
def test_suggest_articles_requires_visible_ticket_and_published_articles(
    mock_frappe,
):
    _wire(mock_frappe)
    mock_frappe.db.exists.side_effect = lambda doctype, name=None: (
        name if doctype == "DocType" and name in {"HD Ticket", "HD Article"} else False
    )

    def get_list(doctype, **kwargs):
        if doctype == "HD Ticket":
            return [_ticket()]
        if doctype == "HD Article":
            return [
                {
                    "name": "ART-001",
                    "title": "Fix a flickering laptop screen",
                    "title_slug": "fix-flickering-screen",
                    "category": "Hardware",
                    "content": "<p>Restart the display driver.</p>",
                    "views": 20,
                    "published_on": "2026-07-01",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = helpdesk_api.suggest_articles("HD-0001")

    assert result["ok"] is True
    assert result["data"][0]["title"] == "Fix a flickering laptop screen"
    article_call = [
        call for call in mock_frappe.get_list.call_args_list if call.args[0] == "HD Article"
    ][0]
    assert ["status", "=", "Published"] in article_call.kwargs["filters"]
    assert article_call.kwargs["ignore_permissions"] is True
    assert ["title", "like", "%laptop%"] in article_call.kwargs["or_filters"]


@patch("bude_api.api.helpdesk.frappe")
def test_suggest_articles_foreign_ticket_returns_not_found(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True
    mock_frappe.get_list.return_value = []

    result = helpdesk_api.suggest_articles("HD-0099")

    assert result["ok"] is False
    assert result["code"] == "TICKET_NOT_FOUND"
    assert all(call.args[0] != "HD Article" for call in mock_frappe.get_list.call_args_list)


@patch("bude_api.api.helpdesk.frappe")
def test_suggest_articles_is_empty_when_article_doctype_missing(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.side_effect = lambda doctype, name=None: name == "HD Ticket"
    mock_frappe.get_list.return_value = [_ticket()]

    result = helpdesk_api.suggest_articles("HD-0001")

    assert result["ok"] is True
    assert result["data"] == []


@patch("bude_api.api.helpdesk.frappe")
def test_ticket_activity_filters_private_changes_for_requesters(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "HD Ticket":
            return [_ticket()]
        if doctype == "Version":
            return [
                {
                    "name": "VER-001",
                    "owner": "agent@example.com",
                    "creation": "2026-07-17 10:00:00",
                    "data": (
                        '{"changed": [['
                        '"status", "Open", "Replied"], '
                        '["_assign", "[]", "[\\"agent@example.com\\"]"], '
                        '["description", "old private text", "new private text"]]}'
                    ),
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = helpdesk_api.ticket_activity("HD-0001")

    assert result["ok"] is True
    assert [event["field"] for event in result["data"]] == ["status"]
    assert result["data"][0]["to"] == "Replied"


@patch("bude_api.api.helpdesk.frappe")
def test_ticket_activity_includes_assignment_for_agents(mock_frappe):
    _wire(mock_frappe, roles=["Agent"])
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "HD Ticket":
            return [_ticket(raised_by="other@example.com")]
        if doctype == "Version":
            return [
                {
                    "name": "VER-001",
                    "owner": "manager@example.com",
                    "creation": "2026-07-17 10:00:00",
                    "data": {
                        "changed": [
                            ["_assign", "[]", '["agent@example.com"]'],
                        ]
                    },
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = helpdesk_api.ticket_activity("HD-0001")

    assert result["ok"] is True
    assert result["data"][0]["field"] == "_assign"
    assert result["data"][0]["label"] == "Assignment"


@patch("bude_api.api.helpdesk.frappe")
def test_ticket_activity_requires_visible_ticket(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True
    mock_frappe.get_list.return_value = []

    result = helpdesk_api.ticket_activity("HD-0099")

    assert result["ok"] is False
    assert result["code"] == "TICKET_NOT_FOUND"
    assert all(call.args[0] != "Version" for call in mock_frappe.get_list.call_args_list)


@patch("bude_api.api.helpdesk.frappe")
def test_ticket_detail_agent_gets_internal_comments(mock_frappe):
    _wire(mock_frappe, roles=["Agent"])
    mock_frappe.get_list.side_effect = [
        [_ticket(raised_by="other@example.com")],
        [],
        [
            {
                "name": "FILE-1",
                "file_name": "screen.png",
                "file_url": "/private/files/screen.png",
                "is_private": 1,
                "creation": "2026-07-10",
            }
        ],
        [
            {
                "name": "CMT-1",
                "commented_by": "agent@example.com",
                "content": "internal note",
                "creation": "2026-07-10",
            }
        ],
    ]

    result = helpdesk_api.ticket_detail("HD-0001")

    assert result["ok"] is True
    assert result["data"]["comments"][0]["content"] == "internal note"
    assert result["data"]["attachments"][0]["file_name"] == "screen.png"


@patch("bude_api.api.helpdesk.frappe")
def test_create_ticket_requires_subject_and_description(mock_frappe):
    _wire(mock_frappe)

    result = helpdesk_api.create_ticket(subject="", description="")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


@patch("bude_api.api.helpdesk.frappe")
def test_create_ticket_inserts_portal_ticket_for_current_user(mock_frappe):
    _wire(mock_frappe)
    doc = MagicMock()
    doc.name = "HD-0002"
    mock_frappe.get_doc.return_value = doc

    result = helpdesk_api.create_ticket(subject="VPN down", description="Cannot connect")

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["doctype"] == "HD Ticket"
    assert payload["raised_by"] == REQUESTER
    assert payload["via_customer_portal"] == 1
    doc.insert.assert_called_once_with(ignore_permissions=True)
    mock_frappe.db.commit.assert_called_once()


@patch("bude_api.api.helpdesk.frappe")
def test_create_ticket_maps_validation_error(mock_frappe):
    _wire(mock_frappe)
    doc = MagicMock()
    doc.insert.side_effect = _FakeValidationError("bad priority")
    mock_frappe.get_doc.return_value = doc

    result = helpdesk_api.create_ticket(subject="x", description="y", priority="Nope")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_ERPNEXT"
    mock_frappe.db.rollback.assert_called_once()


@patch("bude_api.api.helpdesk.frappe")
def test_reply_from_requester_is_received(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [_ticket()]
    doc = MagicMock()
    doc.name = "COMM-9"
    mock_frappe.get_doc.return_value = doc

    result = helpdesk_api.reply("HD-0001", "still broken")

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["doctype"] == "Communication"
    assert payload["reference_name"] == "HD-0001"
    assert payload["sent_or_received"] == "Received"


@patch("bude_api.api.helpdesk.frappe")
def test_reply_from_agent_is_sent(mock_frappe):
    _wire(mock_frappe, roles=["Agent"], user="agent@example.com")
    mock_frappe.get_list.return_value = [_ticket(raised_by="other@example.com")]
    doc = MagicMock()
    mock_frappe.get_doc.return_value = doc

    result = helpdesk_api.reply("HD-0001", "please retry now")

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["sent_or_received"] == "Sent"


@patch("bude_api.api.helpdesk.frappe")
def test_agent_tickets_requires_agent_role(mock_frappe):
    _wire(mock_frappe, roles=["Employee"])

    result = helpdesk_api.agent_tickets()

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.helpdesk.frappe")
def test_agent_tickets_assigned_to_me_filter(mock_frappe):
    _wire(mock_frappe, roles=["Agent"], user="agent@example.com")
    mock_frappe.get_list.return_value = []

    result = helpdesk_api.agent_tickets(assigned_to_me=True)

    assert result["ok"] is True
    _, kwargs = mock_frappe.get_list.call_args
    assert ["_assign", "like", "%agent@example.com%"] in kwargs["filters"]


@patch("bude_api.api.helpdesk.frappe")
def test_agent_tickets_accepts_search_and_filters(mock_frappe):
    _wire(mock_frappe, roles=["Agent"], user="agent@example.com")
    mock_frappe.get_list.return_value = []

    result = helpdesk_api.agent_tickets(
        search="vpn",
        priority="High",
        ticket_type="Incident",
        team="IT",
        unassigned=True,
    )

    assert result["ok"] is True
    _, kwargs = mock_frappe.get_list.call_args
    assert ["priority", "=", "High"] in kwargs["filters"]
    assert ["ticket_type", "=", "Incident"] in kwargs["filters"]
    assert ["agent_group", "=", "IT"] in kwargs["filters"]
    assert kwargs["or_filters"][0] == ["name", "like", "%vpn%"]


@patch("bude_api.api.helpdesk.frappe")
def test_close_ticket_saves_closed_status(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [_ticket()]
    doc = MagicMock()
    mock_frappe.get_doc.return_value = doc

    result = helpdesk_api.close_ticket("HD-0001")

    assert result["ok"] is True
    assert doc.status == "Closed"
    doc.save.assert_called_once_with(ignore_permissions=True)


@patch("bude_api.api.helpdesk.frappe")
def test_set_status_rejects_unknown_status(mock_frappe):
    _wire(mock_frappe, roles=["Agent"])
    mock_frappe.db.exists.side_effect = lambda doctype, name=None: doctype != "HD Ticket Status"

    result = helpdesk_api.set_status("HD-0001", "Bogus")

    assert result["ok"] is False
    assert result["code"] == "TICKET_STATUS_INVALID"


@patch("bude_api.api.helpdesk.frappe")
def test_set_status_requires_agent_role(mock_frappe):
    _wire(mock_frappe)

    result = helpdesk_api.set_status("HD-0001", "Resolved")

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"


@patch("bude_api.api.helpdesk.frappe")
def test_assign_ticket_uses_standard_assignment(mock_frappe):
    _wire(mock_frappe, roles=["Agent Manager"], user="lead@example.com")
    assign_add = MagicMock()
    mock_frappe.get_attr.return_value = assign_add

    result = helpdesk_api.assign_ticket("HD-0001", "agent@example.com")

    assert result["ok"] is True
    mock_frappe.get_attr.assert_called_once_with("frappe.desk.form.assign_to.add")
    args = assign_add.call_args[0][0]
    assert args["doctype"] == "HD Ticket"
    assert args["assign_to"] == ["agent@example.com"]


@patch("bude_api.api.helpdesk.frappe")
def test_add_comment_requires_agent_role(mock_frappe):
    _wire(mock_frappe)

    result = helpdesk_api.add_comment("HD-0001", "note")

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.helpdesk.frappe")
def test_upload_attachment_rejects_bad_extension(mock_frappe):
    _wire(mock_frappe)

    result = helpdesk_api.upload_ticket_attachment("HD-0001", "virus.exe", "aGVsbG8=")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"


@patch("bude_api.api.helpdesk.frappe")
def test_upload_attachment_attaches_to_owned_ticket(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [_ticket()]
    doc = MagicMock()
    doc.name = "FILE-1"
    mock_frappe.get_doc.return_value = doc

    result = helpdesk_api.upload_ticket_attachment("HD-0001", "screen.png", "aGVsbG8=")

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["attached_to_doctype"] == "HD Ticket"
    assert payload["attached_to_name"] == "HD-0001"
    assert payload["is_private"] == 1


@patch("bude_api.api.helpdesk.frappe")
def test_agents_requires_agent_role(mock_frappe):
    _wire(mock_frappe)

    result = helpdesk_api.agents()

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"


@patch("bude_api.api.helpdesk.frappe")
def test_agents_returns_assignable_users(mock_frappe):
    _wire(mock_frappe, roles=["Agent Manager"], user="lead@example.com")
    mock_frappe.get_list.side_effect = [
        [{"parent": "agent@example.com"}],
        [{"name": "agent@example.com", "full_name": "Agent One", "email": "agent@example.com"}],
    ]

    result = helpdesk_api.agents(team="IT")

    assert result["ok"] is True
    assert result["data"][0] == {
        "email": "agent@example.com",
        "full_name": "Agent One",
        "teams": ["IT"],
    }


@patch("bude_api.api.helpdesk.frappe")
def test_masters_shape(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [{"name": "Incident"}],
        [{"name": "High", "integer_value": 3}],
        [{"name": "Open", "label_agent": "Open", "category": "Open"}],
        [{"name": "IT"}],
    ]

    result = helpdesk_api.masters()

    assert result["ok"] is True
    data = result["data"]
    assert data["ticket_types"] == ["Incident"]
    assert data["priorities"][0] == {"name": "High", "level": 3}
    assert data["statuses"][0]["category"] == "Open"
    assert data["teams"] == ["IT"]
    assert data["is_agent"] is False


@patch("bude_api.api.helpdesk.frappe")
def test_related_tickets_reuses_visibility_and_requester_scope(mock_frappe):
    _wire(mock_frappe)
    current = _ticket()
    related = {
        **_ticket(),
        "name": "HD-0002",
        "subject": "VPN still unavailable",
    }
    mock_frappe.get_list.side_effect = [[current], [related]]

    result = helpdesk_api.related_tickets("HD-0001")

    assert result["ok"] is True
    assert result["data"][0]["name"] == "HD-0002"
    _, kwargs = mock_frappe.get_list.call_args
    assert ["raised_by", "=", REQUESTER] in kwargs["filters"]
    assert ["name", "!=", "HD-0001"] in kwargs["filters"]


@patch("bude_api.api.helpdesk.frappe")
def test_customer_ticket_context_is_agent_only_and_summarized(mock_frappe):
    _wire(mock_frappe, roles=["Agent"], user="agent@example.com")

    def get_list(doctype, **kwargs):
        filters = kwargs.get("filters", [])
        if ["name", "=", "HD-0001"] in filters:
            return [_ticket()]
        return [
            _ticket(),
            {
                **_ticket(),
                "name": "HD-0002",
                "status": "Open",
                "priority": "High",
            },
            {
                **_ticket(),
                "name": "HD-0003",
                "status": "Resolved",
                "priority": "Low",
            },
        ]

    mock_frappe.get_list.side_effect = get_list
    result = helpdesk_api.customer_ticket_context("HD-0001")

    assert result["ok"] is True
    assert result["data"]["scope"] == "Acme"
    assert result["data"]["open"] == 2
    assert result["data"]["urgent"] == 1
    assert result["data"]["resolved"] == 1


@patch("bude_api.api.helpdesk.frappe")
def test_ticket_assignments_are_agent_only_and_ticket_scoped(mock_frappe):
    _wire(mock_frappe, roles=["Agent"], user="agent@example.com")
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "HD Ticket":
            return [_ticket()]
        if doctype == "ToDo":
            return [
                {
                    "name": "TODO-001",
                    "status": "Open",
                    "priority": "High",
                    "date": "2026-07-20",
                    "allocated_to": "agent@example.com",
                    "assigned_by": "lead@example.com",
                    "assigned_by_full_name": "Team Lead",
                    "description": "Coordinate replacement",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = helpdesk_api.ticket_assignments("HD-0001")

    assert result["ok"] is True
    assert result["data"][0]["allocated_to"] == "agent@example.com"
    todo_call = next(
        call
        for call in mock_frappe.get_list.call_args_list
        if call.args and call.args[0] == "ToDo"
    )
    assert ["reference_name", "=", "HD-0001"] in todo_call.kwargs["filters"]
    assert ["status", "=", "Open"] in todo_call.kwargs["filters"]


@patch("bude_api.api.helpdesk.frappe")
def test_ticket_assignments_reject_requesters(mock_frappe):
    _wire(mock_frappe)

    result = helpdesk_api.ticket_assignments("HD-0001")

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.helpdesk.frappe")
def test_saved_replies_respect_global_personal_and_ticket_team_scope(mock_frappe):
    _wire(mock_frappe, roles=["Agent"], user="agent@example.com")
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "HD Ticket":
            return [{**_ticket(), "agent_group": "IT"}]
        if doctype == "HD Saved Reply":
            return [
                {
                    "name": "Global reply",
                    "title": "Global reply",
                    "message": "<p>Hello</p>",
                    "scope": "Global",
                    "owner": "lead@example.com",
                },
                {
                    "name": "My reply",
                    "title": "My reply",
                    "message": "<p>Investigating</p>",
                    "scope": "Personal",
                    "owner": "agent@example.com",
                },
                {
                    "name": "Other personal",
                    "scope": "Personal",
                    "owner": "other@example.com",
                },
                {
                    "name": "IT reply",
                    "title": "IT reply",
                    "message": "<p>Restart the device</p>",
                    "scope": "Team",
                },
                {
                    "name": "HR reply",
                    "scope": "Team",
                },
            ]
        if doctype == "HD Saved Reply Team":
            return [{"parent": "IT reply", "team": "IT"}]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = helpdesk_api.saved_replies("HD-0001")

    assert result["ok"] is True
    assert [row["name"] for row in result["data"]] == [
        "Global reply",
        "My reply",
        "IT reply",
    ]


@patch("bude_api.api.helpdesk.frappe")
def test_saved_replies_reject_requesters(mock_frappe):
    _wire(mock_frappe)

    result = helpdesk_api.saved_replies("HD-0001")

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.helpdesk.frappe")
def test_ticket_sla_context_uses_visible_ticket_priority(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "HD Ticket":
            return [
                {
                    **_ticket(),
                    "sla": "Standard Support",
                    "priority": "High",
                    "raised_outside_working_hours": 1,
                    "on_hold_since": "2026-07-18 10:00:00",
                    "total_hold_time": 1800,
                }
            ]
        if doctype == "HD Service Level Agreement":
            return [
                {
                    "name": "Standard Support",
                    "service_level": "Standard Support",
                    "description": "Business-hours support",
                    "holiday_list": "Support Holidays",
                    "apply_sla_for_resolution": 1,
                }
            ]
        if doctype == "HD Service Level Priority":
            return [
                {
                    "priority": "Low",
                    "response_time": 14400,
                    "resolution_time": 86400,
                },
                {
                    "priority": "High",
                    "response_time": 3600,
                    "resolution_time": 14400,
                },
            ]
        if doctype == "HD Service Day":
            return [
                {
                    "workday": "Monday",
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                }
            ]
        if doctype == "HD Service Holiday List":
            return [
                {
                    "name": "Support Holidays",
                    "holiday_list_name": "Support Holidays",
                    "description": "Support closure calendar",
                    "from_date": "2026-01-01",
                    "to_date": "2099-12-31",
                }
            ]
        if doctype == "HD Holiday":
            return [
                {
                    "holiday_date": "2099-12-25",
                    "description": "Support holiday",
                    "weekly_off": 0,
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = helpdesk_api.ticket_sla_context("HD-0001")

    assert result["ok"] is True
    assert result["data"]["sla"] == "Standard Support"
    assert result["data"]["priority"] == "High"
    assert result["data"]["response_time"] == 3600
    assert result["data"]["resolution_time"] == 14400
    assert result["data"]["raised_outside_working_hours"] is True
    assert result["data"]["working_hours"] == [
        {
            "workday": "Monday",
            "start_time": "09:00:00",
            "end_time": "17:00:00",
        }
    ]
    assert result["data"]["holiday_list_description"] == (
        "Support closure calendar"
    )
    assert result["data"]["holidays"] == [
        {
            "date": "2099-12-25",
            "description": "Support holiday",
            "weekly_off": False,
        }
    ]


@patch("bude_api.api.helpdesk.frappe")
def test_ticket_sla_context_reuses_requester_visibility(mock_frappe):
    _wire(mock_frappe, user="other@example.com")
    mock_frappe.get_list.return_value = []

    result = helpdesk_api.ticket_sla_context("HD-0001")

    assert result["ok"] is False
    assert result["code"] == "TICKET_NOT_FOUND"


@patch("bude_api.api.helpdesk.frappe")
def test_ticket_classification_hides_customer_private_template_fields(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "HD Ticket":
            return [{**_ticket(), "template": "Incident Form"}]
        if doctype == "HD Ticket Type":
            return [
                {
                    "name": "Incident",
                    "description": "Unexpected service interruption",
                    "priority": "High",
                    "disabled": 0,
                }
            ]
        if doctype == "HD Ticket Template":
            return [
                {
                    "name": "Incident Form",
                    "template_name": "Incident Form",
                    "about": "<p>Include reproduction steps.</p>",
                }
            ]
        if doctype == "HD Ticket Template Field":
            return [
                {
                    "fieldname": "affected_service",
                    "required": 1,
                    "hide_from_customer": 0,
                },
                {
                    "fieldname": "internal_routing",
                    "required": 0,
                    "hide_from_customer": 1,
                },
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = helpdesk_api.ticket_classification("HD-0001")

    assert result["ok"] is True
    assert result["data"]["recommended_priority"] == "High"
    assert result["data"]["fields"] == [
        {"fieldname": "affected_service", "required": True}
    ]


@patch("bude_api.api.helpdesk.frappe")
def test_ticket_team_context_returns_active_agent_availability(mock_frappe):
    _wire(mock_frappe, roles=["Agent"], user="agent@example.com")
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "HD Ticket":
            return [{**_ticket(), "agent_group": "IT"}]
        if doctype == "HD Team":
            return [
                {
                    "name": "IT",
                    "team_name": "IT Support",
                    "assignment_rule": "Round Robin",
                    "disabled": 0,
                }
            ]
        if doctype == "HD Team Member":
            return [{"user": "agent@example.com"}]
        if doctype == "HD Agent":
            return [
                {
                    "user": "agent@example.com",
                    "agent_name": "Support Agent",
                    "availability": "Online",
                    "availability_changed_on": "2026-07-18 09:00:00",
                }
            ]
        if doctype == "HD Agent Status":
            return [
                {
                    "name": "Online",
                    "agent_status": "Online",
                    "category": "Active",
                    "color": "Green",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = helpdesk_api.ticket_team_context("HD-0001")

    assert result["ok"] is True
    assert result["data"]["team_name"] == "IT Support"
    assert result["data"]["assignment_rule"] == "Round Robin"
    assert result["data"]["active_count"] == 1
    assert result["data"]["members"][0]["availability"] == "Online"


@patch("bude_api.api.helpdesk.frappe")
def test_ticket_team_context_rejects_requesters(mock_frappe):
    _wire(mock_frappe)

    result = helpdesk_api.ticket_team_context("HD-0001")

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"


@patch("bude_api.api.helpdesk.frappe")
def test_ticket_organization_context_limits_contacts_to_agents(mock_frappe):
    _wire(mock_frappe, roles=["Agent"], user="agent@example.com")
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "HD Ticket":
            return [{**_ticket(), "customer": "Acme"}]
        if doctype == "HD Customer":
            return [
                {
                    "name": "Acme",
                    "customer_name": "Acme Ltd",
                    "customer_type": "Company",
                    "domain": "acme.example",
                    "country": "India",
                    "erpnext_customer": "CUST-001",
                }
            ]
        if doctype == "HD Customer Member":
            return [{"contact_name": "CONT-001", "is_manager": 1}]
        if doctype == "Contact":
            return [
                {
                    "name": "CONT-001",
                    "full_name": "Asha Rao",
                    "email_id": "asha@acme.example",
                    "mobile_no": "+91 555 0100",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = helpdesk_api.ticket_organization_context("HD-0001")

    assert result["ok"] is True
    assert result["data"]["customer_name"] == "Acme Ltd"
    assert result["data"]["members_visible"] is True
    assert result["data"]["member_count"] == 1
    assert result["data"]["members"][0]["manager"] is True


@patch("bude_api.api.helpdesk.frappe")
def test_ticket_organization_context_hides_contacts_from_requester(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "HD Ticket":
            return [{**_ticket(), "customer": "Acme"}]
        if doctype == "HD Customer":
            return [
                {
                    "name": "Acme",
                    "customer_name": "Acme Ltd",
                    "customer_type": "Company",
                    "domain": "acme.example",
                }
            ]
        raise AssertionError(f"Requester must not read {doctype}")

    mock_frappe.get_list.side_effect = get_list
    result = helpdesk_api.ticket_organization_context("HD-0001")

    assert result["ok"] is True
    assert result["data"]["customer_name"] == "Acme Ltd"
    assert result["data"]["members"] == []
    assert result["data"]["members_visible"] is False
