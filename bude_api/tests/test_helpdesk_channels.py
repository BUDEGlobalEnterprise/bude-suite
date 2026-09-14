import json
from unittest.mock import MagicMock, patch

from bude_api.services.helpdesk import channels

TICKET = {
    "name": "HD-0001",
    "subject": "Checkout unavailable",
    "contact": "CONT-001",
    "raised_by": "customer@example.com",
}


def _frappe(*, roles=None, conf=None):
    mocked = MagicMock()
    mocked.session.user = "agent@example.com"
    mocked.get_roles.return_value = roles or ["Agent"]
    mocked.conf = conf or {}
    mocked.utils.now_datetime.return_value = "2026-08-05 15:00:00"
    mocked.db.exists.return_value = False
    return mocked


@patch.object(channels, "_require_helpdesk", return_value=None)
@patch.object(channels, "frappe")
def test_channel_health_is_manager_only_and_never_returns_configuration(mock_frappe, _):
    mock_frappe.session.user = "manager@example.com"
    mock_frappe.get_roles.return_value = ["Agent Manager"]
    mock_frappe.conf = {
        "bude_helpdesk_whatsapp_enabled": True,
        "bude_helpdesk_whatsapp_endpoint": "https://provider.example/send",
        "bude_helpdesk_whatsapp_token": "top-secret",
        "bude_helpdesk_whatsapp_templates": "ticket_update,resolution_notice",
    }

    def get_list(doctype, **kwargs):
        if doctype == "Email Queue":
            return [
                {"name": "Q-1", "status": "Sent"},
                {"name": "Q-2", "status": "Error"},
                {"name": "Q-3", "status": "Not Sent"},
            ]
        if doctype == "Email Account":
            return [{"name": "Support"}]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = channels.channel_health()

    assert result["ok"] is True
    data = result["data"]
    assert data["email"]["queue"]["accepted_rate"] == 50
    assert data["whatsapp"] == {
        "enabled": True,
        "configured": True,
        "template_count": 2,
        "consent_required": True,
        "identity_source": "Ticket contact",
    }
    assert "secret" not in json.dumps(data).lower()
    assert "endpoint" not in json.dumps(data).lower()


@patch.object(channels, "frappe")
def test_channel_health_rejects_plain_agent(mock_frappe):
    mock_frappe.session.user = "agent@example.com"
    mock_frappe.get_roles.return_value = ["Agent"]

    result = channels.channel_health()

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()


@patch.object(channels, "_visible_ticket", return_value=(TICKET, None))
@patch.object(channels, "_require_helpdesk", return_value=None)
def test_ticket_delivery_combines_standard_communication_and_queue_status(_, __):
    mocked = _frappe()

    def get_list(doctype, **kwargs):
        if doctype == "Communication":
            return [
                {
                    "name": "COMM-1",
                    "subject": "Re: Checkout",
                    "communication_medium": "Email",
                    "sent_or_received": "Sent",
                    "delivery_status": "Bounced",
                    "has_attachment": 1,
                    "creation": "2026-08-05 14:00:00",
                }
            ]
        if doctype == "Email Queue":
            return [
                {
                    "communication": "COMM-1",
                    "status": "Error",
                    "retry": 3,
                    "error": "SMTP password=should-not-leak",
                }
            ]
        if doctype == "File":
            return [{"attached_to_name": "COMM-1"}]
        return []

    mocked.get_list.side_effect = get_list
    with patch.object(channels, "frappe", mocked):
        result = channels.ticket_delivery("HD-0001")

    record = result["data"]["records"][0]
    assert record["delivery_status"] == "Bounced"
    assert record["queue_status"] == "Error"
    assert record["queue_retry"] == 3
    assert record["queue_has_error"] is True
    assert record["attachment_count"] == 1
    assert "password" not in json.dumps(result).lower()


@patch.object(channels, "_visible_ticket", return_value=(TICKET, None))
@patch.object(channels, "_require_helpdesk", return_value=None)
def test_forward_rejects_attachment_from_another_ticket(_, __):
    mocked = _frappe()

    def get_list(doctype, **kwargs):
        if doctype == "Communication":
            return [{"name": "COMM-1"}]
        if doctype == "File":
            return [
                {
                    "name": "FILE-1",
                    "attached_to_doctype": "HD Ticket",
                    "attached_to_name": "HD-OTHER",
                }
            ]
        return []

    mocked.get_list.side_effect = get_list
    with patch.object(channels, "frappe", mocked):
        result = channels.forward_ticket(
            "HD-0001",
            "expert@example.com",
            "Please review",
            "Can you help?",
            ["FILE-1"],
        )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_ATTACHMENTS"
    mocked.get_attr.assert_not_called()


@patch.object(channels, "_visible_ticket", return_value=(TICKET, None))
@patch.object(channels, "_require_helpdesk", return_value=None)
def test_forward_rejects_mixed_valid_and_invalid_recipients(_, __):
    mocked = _frappe()
    with patch.object(channels, "frappe", mocked):
        result = channels.forward_ticket(
            "HD-0001",
            "expert@example.com, not-an-email",
            "Please review",
            "Can you help?",
        )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_RECIPIENTS"
    mocked.get_attr.assert_not_called()


@patch.object(channels, "_visible_ticket", return_value=(TICKET, None))
@patch.object(channels, "_require_helpdesk", return_value=None)
def test_forward_queues_scoped_attachments_through_frappe_email(_, __):
    mocked = _frappe()

    def get_list(doctype, **kwargs):
        if doctype == "Communication":
            return [{"name": "COMM-ORIGINAL"}]
        if doctype == "File":
            return [
                {
                    "name": "FILE-1",
                    "attached_to_doctype": "Communication",
                    "attached_to_name": "COMM-ORIGINAL",
                }
            ]
        return []

    mocked.get_list.side_effect = get_list
    make = MagicMock(return_value={"name": "COMM-FORWARD"})
    mocked.get_attr.return_value = make
    with patch.object(channels, "frappe", mocked):
        result = channels.forward_ticket(
            "HD-0001",
            "Expert <expert@example.com>",
            "Please review",
            "Can you help?",
            ["FILE-1"],
            "manager@example.com",
        )

    assert result["ok"] is True
    assert result["data"]["status"] == "Queued"
    assert result["data"]["recipient_count"] == 2
    kwargs = make.call_args.kwargs
    assert kwargs["name"] == "HD-0001"
    assert kwargs["recipients"] == ["expert@example.com"]
    assert kwargs["attachments"] == ["FILE-1"]
    assert kwargs["send_email"] is True


@patch.object(channels, "_visible_ticket", return_value=(TICKET, None))
@patch.object(channels, "_require_helpdesk", return_value=None)
def test_whatsapp_requires_explicit_opt_in_before_identity_lookup(_, __):
    mocked = _frappe(conf={"bude_helpdesk_whatsapp_enabled": "FALSE"})
    with patch.object(channels, "frappe", mocked):
        result = channels.send_whatsapp_template(
            "HD-0001", "ticket_update", {}, "CRM consent #12", "request-123"
        )

    assert result["ok"] is False
    assert result["code"] == "CHANNEL_DISABLED"
    mocked.get_list.assert_not_called()


@patch.object(channels, "_visible_ticket", return_value=(TICKET, None))
@patch.object(channels, "_require_helpdesk", return_value=None)
@patch.object(channels, "_post_json", return_value={"message_id": "provider-1"})
def test_whatsapp_uses_ticket_contact_and_persists_masked_audit(mock_post, _, __):
    mocked = _frappe(
        conf={
            "bude_helpdesk_whatsapp_enabled": True,
            "bude_helpdesk_whatsapp_endpoint": "https://provider.example/send",
            "bude_helpdesk_whatsapp_token": "secret-token",
            "bude_helpdesk_whatsapp_templates": "ticket_update",
        }
    )
    inserted = []

    def get_list(doctype, **kwargs):
        if doctype == "Contact":
            return [{"name": "CONT-001", "mobile_no": "+919876543210", "phone": ""}]
        return []

    class FakeDoc:
        def __init__(self, payload):
            self.payload = payload
            self.name = "COMM-NEW" if payload["doctype"] == "Communication" else "AUDIT-1"

        def insert(self, ignore_permissions=False):
            assert ignore_permissions is True
            inserted.append(self.payload)
            return self

    mocked.get_list.side_effect = get_list
    mocked.get_doc.side_effect = FakeDoc
    with patch.object(channels, "frappe", mocked):
        result = channels.send_whatsapp_template(
            "HD-0001",
            "ticket_update",
            {"status": "Investigating"},
            "CRM consent #12",
            "request-123",
        )

    assert result["ok"] is True
    endpoint, token, payload = mock_post.call_args.args
    assert endpoint == "https://provider.example/send"
    assert token == "secret-token"
    assert payload["to"] == "+919876543210"
    assert payload["ticket"] == "HD-0001"
    audit = next(row for row in inserted if row["doctype"] == "Integration Request")
    assert "+919876543210" not in audit["data"]
    assert "***3210" in audit["data"]
    assert "secret-token" not in json.dumps(inserted)


@patch.object(channels, "_visible_ticket", return_value=(TICKET, None))
@patch.object(channels, "_require_helpdesk", return_value=None)
def test_phone_activity_escapes_summary_and_is_idempotent(_, __):
    mocked = _frappe()
    inserted = []

    def get_list(doctype, **kwargs):
        if doctype == "Contact":
            return [{"name": "CONT-001", "mobile_no": "+919876543210", "phone": ""}]
        return []

    class FakeDoc:
        def __init__(self, payload):
            self.payload = payload
            self.name = "COMM-PHONE"

        def insert(self, ignore_permissions=False):
            inserted.append(self.payload)
            return self

    mocked.get_list.side_effect = get_list
    mocked.get_doc.side_effect = FakeDoc
    with patch.object(channels, "frappe", mocked):
        result = channels.log_phone_activity(
            "HD-0001",
            "outbound",
            90,
            "Called <script>alert(1)</script>",
            "call-123",
        )

    assert result["ok"] is True
    communication = next(row for row in inserted if row["doctype"] == "Communication")
    assert communication["communication_medium"] == "Phone"
    assert "<script>" not in communication["content"]
    assert "&lt;script&gt;" in communication["content"]


def test_provider_endpoint_must_be_https_without_embedded_credentials():
    assert channels._secure_endpoint("https://provider.example/send") is True
    assert channels._secure_endpoint("http://provider.example/send") is False
    assert channels._secure_endpoint("https://user:pass@provider.example/send") is False
