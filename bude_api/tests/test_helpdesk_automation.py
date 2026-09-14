import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from bude_api.services.helpdesk import automation


def _manager_frappe(*, enabled=True):
    mocked = MagicMock()
    mocked.session.user = "manager@example.com"
    mocked.get_roles.return_value = ["Agent Manager"]
    mocked.conf = {"bude_helpdesk_automation_enabled": enabled}
    mocked.utils.now_datetime.return_value = datetime(2026, 8, 5, 12, 0)
    mocked.get_meta.return_value.has_field.return_value = True
    mocked.db.exists.return_value = False
    return mocked


@patch("bude_api.services.helpdesk.automation.frappe")
def test_automation_status_requires_manager_role(mock_frappe):
    mock_frappe.session.user = "agent@example.com"
    mock_frappe.get_roles.return_value = ["Agent"]

    result = automation.automation_status()

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.services.helpdesk.automation.frappe")
def test_live_evaluation_is_opt_in(mock_frappe):
    mock_frappe.session.user = "manager@example.com"
    mock_frappe.get_roles.return_value = ["Agent Manager"]
    mock_frappe.conf = {"bude_helpdesk_automation_enabled": False}

    result = automation.evaluate_automation(dry_run=False)

    assert result["ok"] is False
    assert result["code"] == "AUTOMATION_DISABLED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.services.helpdesk.automation.frappe")
def test_dry_run_detects_escalation_policies_without_writes(mock_frappe):
    mock_frappe.session.user = "manager@example.com"
    mock_frappe.get_roles.return_value = ["Agent Manager"]
    mock_frappe.conf = {
        "bude_helpdesk_automation_enabled": False,
        "bude_helpdesk_vip_customers": "Acme",
    }
    mock_frappe.utils.now_datetime.return_value = datetime(2026, 8, 5, 12, 0)
    mock_frappe.get_meta.return_value.has_field.return_value = True

    def exists(doctype, name_or_filters):
        return doctype == "DocType" and name_or_filters == "HD Ticket Activity"

    mock_frappe.db.exists.side_effect = exists

    def get_list(doctype, **kwargs):
        if doctype == "HD Ticket":
            return [
                {
                    "name": "HD-0001",
                    "subject": "Checkout unavailable",
                    "status_category": "Open",
                    "priority": "Urgent",
                    "customer": "Acme",
                    "agreement_status": "Failed",
                    "resolution_by": "2026-08-05 11:00:00",
                    "creation": "2026-08-05 09:00:00",
                    "modified": "2026-08-04 08:00:00",
                    "_assign": "[]",
                }
            ]
        if doctype == "Has Role":
            return [{"parent": "manager@example.com"}]
        if doctype == "User":
            return [{"name": "manager@example.com"}]
        if doctype == "HD Ticket Status":
            return [
                {"name": "Open", "category": "Open"},
                {"name": "Resolved", "category": "Resolved"},
            ]
        if doctype == "HD Ticket Activity":
            return [
                {"ticket": "HD-0001", "action": "set status to Resolved"},
                {"ticket": "HD-0001", "action": "set status to Open"},
                {"ticket": "HD-0001", "action": "set status to Resolved"},
                {"ticket": "HD-0001", "action": "set status to Open"},
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = automation.evaluate_automation(dry_run=True)

    assert result["ok"] is True
    data = result["data"]
    assert data["enabled"] is False
    assert data["dry_run"] is True
    assert data["scanned"] == 1
    assert {
        "unassigned",
        "breach",
        "inactivity",
        "vip",
        "repeated_reopen",
        "manager_digest",
    }.issubset({match["policy"] for match in data["matches"]})
    mock_frappe.get_doc.assert_not_called()
    _, ticket_query = next(
        call for call in mock_frappe.get_list.call_args_list if call.args[0] == "HD Ticket"
    )
    assert ticket_query["ignore_permissions"] is True
    assert ticket_query["limit_page_length"] == automation.TICKET_SCAN_LIMIT + 1


def test_reopen_counts_only_resolved_to_open_transitions():
    mocked = _manager_frappe()
    mocked.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "HD Ticket Status":
            return [
                {"name": "Waiting", "category": "Open"},
                {"name": "Done", "category": "Resolved"},
            ]
        if doctype == "HD Ticket Activity":
            return [
                {"ticket": "HD-1", "action": "set status to Waiting"},
                {"ticket": "HD-1", "action": "set status to Done"},
                {"ticket": "HD-1", "action": "set status to Waiting"},
                {"ticket": "HD-1", "action": "set priority to Urgent"},
                {"ticket": "HD-1", "action": "set status to Done"},
                {"ticket": "HD-1", "action": "set status to Waiting"},
            ]
        return []

    mocked.get_list.side_effect = get_list
    with patch.object(automation, "frappe", mocked):
        assert automation._reopen_counts(["HD-1"]) == {"HD-1": 2}


def test_delivery_is_idempotent_and_records_audit():
    mocked = _manager_frappe()
    audits = []
    notifications = []

    def get_list(doctype, **kwargs):
        if doctype == "Integration Request":
            filters = kwargs.get("filters", [])
            request_filter = next((item for item in filters if item[0] == "request_id"), None)
            if request_filter:
                return [row for row in audits if row["request_id"] == request_filter[2]]
        return []

    class FakeDoc:
        def __init__(self, payload):
            self.payload = payload
            self.name = ""

        def insert(self, ignore_permissions=False):
            assert ignore_permissions is True
            if self.payload["doctype"] == "Notification Log":
                self.name = "NOTE-1"
                notifications.append(dict(self.payload))
            else:
                self.name = "AUDIT-1"
                audits.append(
                    {
                        "name": self.name,
                        "request_id": self.payload["request_id"],
                        "status": self.payload["status"],
                        "data": self.payload["data"],
                    }
                )
            return self

    mocked.get_list.side_effect = get_list
    mocked.get_doc.side_effect = FakeDoc
    event = {
        "policy": "breach",
        "ticket": "HD-1",
        "recipient": "agent@example.com",
        "subject": "Helpdesk SLA breach: HD-1",
        "content": "Ticket HD-1 breached its SLA.",
        "event_key": "breach:HD-1:agent@example.com:123",
    }

    with patch.object(automation, "frappe", mocked):
        assert automation._deliver_event(event) == "delivered"
        assert automation._deliver_event(event) == "skipped"

    assert len(notifications) == 1
    assert len(audits) == 1
    assert audits[0]["status"] == "Completed"
    assert json.loads(audits[0]["data"])["attempts"] == 1


def test_delivery_failure_does_not_escape_when_audit_also_fails():
    mocked = _manager_frappe()
    mocked.get_list.return_value = []
    mocked.get_doc.side_effect = RuntimeError("database unavailable")
    event = {
        "policy": "unassigned",
        "ticket": "HD-1",
        "recipient": "manager@example.com",
        "subject": "Unassigned",
        "content": "Needs an owner.",
        "event_key": "unassigned:HD-1:manager@example.com:123",
    }

    with patch.object(automation, "frappe", mocked):
        assert automation._deliver_event(event) == "failed"


def test_audit_attempts_tolerates_corrupt_data():
    assert automation._audit_attempts({"data": '{"attempts":"invalid"}'}) == 0


def test_automation_flag_is_case_insensitive_and_opt_in():
    mocked = _manager_frappe()
    with patch.object(automation, "frappe", mocked):
        for value in (None, False, 0, "FALSE", " Off ", "no"):
            mocked.conf = {"bude_helpdesk_automation_enabled": value}
            assert automation._enabled() is False
        for value in (True, 1, "TRUE", " yes "):
            mocked.conf = {"bude_helpdesk_automation_enabled": value}
            assert automation._enabled() is True
