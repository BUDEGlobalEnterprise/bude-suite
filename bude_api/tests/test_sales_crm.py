import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from bude_api.api import sales_crm as crm_api


class _ValidationError(Exception):
    pass


class _PermissionError(Exception):
    pass


def _grant(mock_frappe, *, roles=None, provider="erpnext", installed=None):
    mock_frappe.session.user = "rep@example.com"
    mock_frappe.get_roles.return_value = roles or ["Sales User"]
    mock_frappe.get_installed_apps.return_value = installed or ["frappe", "erpnext"]
    mock_frappe.conf.get.side_effect = lambda key: {
        "bude_sales_crm_provider": provider,
        "bude_sales_crm_enabled": 1,
    }.get(key)
    mock_frappe.ValidationError = _ValidationError
    mock_frappe.PermissionError = _PermissionError
    mock_frappe.db.exists.return_value = True
    mock_frappe.db.count.return_value = 0
    mock_frappe.has_permission.return_value = True
    meta = MagicMock()
    meta.has_field.return_value = True
    meta.fields = []
    mock_frappe.get_meta.return_value = meta


@patch("bude_api.api.sales_crm.frappe")
def test_crm_requires_sales_role(mock_frappe):
    mock_frappe.session.user = "stock@example.com"
    mock_frappe.get_roles.return_value = ["Stock User"]

    result = crm_api.list_leads()

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.sales_crm.frappe")
def test_bootstrap_defaults_to_erpnext_and_returns_normalized_capabilities(mock_frappe):
    _grant(mock_frappe, roles=["Sales Manager"])
    mock_frappe.get_list.return_value = []

    result = crm_api.bootstrap()

    assert result["ok"] is True
    assert result["data"]["provider"] == "erpnext"
    assert result["data"]["is_manager"] is True
    assert result["data"]["capabilities"]["leads"] is True
    assert result["data"]["capabilities"]["offline_capture"] is True


@patch("bude_api.api.sales_crm.frappe")
def test_bootstrap_selects_optional_frappe_crm_provider(mock_frappe):
    _grant(mock_frappe, provider="frappe_crm", installed=["frappe", "erpnext", "crm"])
    mock_frappe.get_list.return_value = []

    result = crm_api.bootstrap()

    assert result["ok"] is True
    assert result["data"]["provider"] == "frappe_crm"
    assert result["data"]["capabilities"]["calls"] is True
    assert "frappe_crm" in result["data"]["available_providers"]


@patch("bude_api.api.sales_crm.frappe")
def test_setup_doctor_reports_pilot_readiness_without_secrets(mock_frappe):
    _grant(mock_frappe, roles=["Sales Manager"])
    mock_frappe.conf.get.side_effect = lambda key: {
        "bude_sales_crm_provider": "erpnext",
        "bude_sales_crm_enabled": 1,
        "bude_sales_intake_secret": "never-return-this",
        "bude_sales_plan": "managed",
        "bude_sales_entitlement_status": "active",
    }.get(key)
    mock_frappe.get_versions.return_value = {
        "frappe": {"version": "16.2.0"},
        "erpnext": {"version": "16.1.0"},
    }
    mock_frappe.db.count.return_value = 1
    mock_frappe.utils.scheduler.is_scheduler_inactive.return_value = False

    result = crm_api.setup_doctor()

    assert result["ok"] is True
    assert result["data"]["healthy"] is True
    assert result["data"]["entitlement"]["plan"] == "managed"
    assert "never-return-this" not in json.dumps(result)
    assert {row["key"] for row in result["data"]["checks"]} >= {
        "provider",
        "versions",
        "scheduler",
        "price_list",
    }


@patch("bude_api.api.sales_crm.frappe")
def test_telemetry_is_opt_in_and_redacts_customer_fields(mock_frappe):
    _grant(mock_frappe)
    mock_frappe.conf.get.side_effect = lambda key: {
        "bude_sales_crm_enabled": 1,
        "bude_sales_telemetry_enabled": 1,
    }.get(key)
    mock_frappe.db.exists.side_effect = lambda doctype, value: (
        False if doctype == "Integration Request" else True
    )
    log = MagicMock()
    mock_frappe.get_doc.return_value = log

    result = crm_api.telemetry(
        "lead_created",
        {"provider": "erpnext", "offline": True, "email": "asha@example.com", "lead": "LEAD-1"},
        "event-1",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert json.loads(payload["data"]) == {"provider": "erpnext", "offline": True}
    log.insert.assert_called_once_with(ignore_permissions=True)


@patch("bude_api.api.sales_crm.frappe")
def test_signed_quotation_link_records_customer_acceptance_once(mock_frappe):
    _grant(mock_frappe)
    mock_frappe.conf.get.side_effect = lambda key: {
        "bude_sales_crm_provider": "erpnext",
        "bude_sales_crm_enabled": 1,
        "bude_sales_quote_response_secret": "quote-secret",
    }.get(key)
    mock_frappe.utils.get_url.return_value = "https://erp.example.com"
    mock_frappe.has_permission.return_value = True

    link = crm_api.quotation_response_link("QTN-001", 7)

    assert link["ok"] is True
    assert link["data"]["url"].startswith(
        "https://erp.example.com/bude-quotation-response?"
    )
    expires = link["data"]["expires"]
    signature = link["data"]["url"].split("signature=")[1]
    mock_frappe.get_list.return_value = []
    comment = MagicMock()
    notification = MagicMock()
    mock_frappe.get_doc.side_effect = [comment, notification]
    mock_frappe.db.get_value.return_value = "rep@example.com"

    response = crm_api.quotation_response(
        "QTN-001", "accept", expires, signature, "Please deliver Friday"
    )

    assert response["ok"] is True
    assert response["data"]["response"] == "accepted"
    comment_payload = mock_frappe.get_doc.call_args_list[0].args[0]
    assert "ACCEPTED" in comment_payload["content"]
    assert "deliver Friday" in comment_payload["content"]
    comment.insert.assert_called_once_with(ignore_permissions=True)
    notification.insert.assert_called_once_with(ignore_permissions=True)


@patch("bude_api.api.sales_crm.frappe")
def test_manager_dashboard_returns_outcomes_and_recommendations(mock_frappe):
    _grant(mock_frappe, roles=["Sales Manager"])
    mock_frappe.get_list.return_value = []
    mock_frappe.db.count.return_value = 0

    result = crm_api.manager_dashboard(30)
    templates = crm_api.playbooks()

    assert result["ok"] is True
    assert result["data"]["quotation"]["conversion_rate"] == 0
    assert result["data"]["recommendations"][0]["severity"] == "info"
    assert templates["ok"] is True
    assert {row["key"] for row in templates["data"]["templates"]} >= {
        "new_lead_3_touch",
        "quotation_follow_up",
    }


@patch("bude_api.api.sales_crm.frappe")
def test_list_leads_normalizes_erpnext_fields_and_scopes_to_rep(mock_frappe):
    _grant(mock_frappe)
    mock_frappe.get_list.return_value = [
        {
            "name": "LEAD-001",
            "lead_name": "Asha Rao",
            "company_name": "Acme",
            "status": "Open",
            "email_id": "asha@example.com",
            "mobile_no": "+91 99999 00000",
            "lead_owner": "rep@example.com",
            "modified": "2026-08-04 10:00:00",
        }
    ]
    mock_frappe.db.count.return_value = 1

    result = crm_api.list_leads(search="asha")

    assert result["ok"] is True
    assert result["data"]["leads"][0]["title"] == "Asha Rao"
    assert result["data"]["leads"][0]["organization"] == "Acme"
    _, kwargs = mock_frappe.get_list.call_args
    assert ["lead_owner", "=", "rep@example.com"] in kwargs["filters"]
    assert kwargs["or_filters"]


@patch("bude_api.api.sales_crm.frappe")
def test_create_lead_writes_provider_doc_and_idempotency_record(mock_frappe):
    _grant(mock_frappe)
    mock_frappe.get_list.return_value = []
    lead = MagicMock()
    lead.name = "LEAD-001"
    lead.as_dict.return_value = {
        "name": "LEAD-001",
        "lead_name": "Asha Rao",
        "company_name": "Acme",
        "status": "Lead",
        "email_id": "asha@example.com",
        "lead_owner": "rep@example.com",
    }
    request_log = MagicMock()
    request_log.name = "INT-001"
    mock_frappe.get_doc.side_effect = [lead, request_log]

    result = crm_api.create_lead(
        {
            "first_name": "Asha",
            "last_name": "Rao",
            "organization": "Acme",
            "email": "asha@example.com",
            "owner": "rep@example.com",
        },
        "mobile-123",
    )

    assert result["ok"] is True
    assert result["data"]["lead"]["name"] == "LEAD-001"
    lead_payload = mock_frappe.get_doc.call_args_list[0].args[0]
    assert lead_payload["doctype"] == "Lead"
    assert lead_payload["company_name"] == "Acme"
    assert lead_payload["email_id"] == "asha@example.com"
    log_payload = mock_frappe.get_doc.call_args_list[1].args[0]
    assert log_payload["doctype"] == "Integration Request"
    assert log_payload["request_id"] == "mobile-123"


@patch("bude_api.api.sales_crm.frappe")
def test_manager_can_merge_duplicate_leads_with_audit_note(mock_frappe):
    _grant(mock_frappe, roles=["Sales Manager"])
    source = {
        "name": "LEAD-DUPLICATE",
        "lead_name": "Asha duplicate",
        "email_id": "asha@example.com",
        "status": "Lead",
    }
    target = {
        "name": "LEAD-PRIMARY",
        "lead_name": "Asha Rao",
        "company_name": "Acme",
        "status": "Open",
        "modified": "2026-08-04 12:00:00",
    }
    mock_frappe.get_list.side_effect = [[source], [target], [target]]
    target_doc = MagicMock()
    note_doc = MagicMock()
    note_doc.name = "COMMENT-001"
    mock_frappe.get_doc.side_effect = [target_doc, note_doc]

    result = crm_api.merge_leads(
        "LEAD-DUPLICATE",
        "LEAD-PRIMARY",
        {"email": "asha@example.com"},
    )

    assert result["ok"] is True
    assert result["data"]["lead"]["name"] == "LEAD-PRIMARY"
    assert target_doc.email_id == "asha@example.com"
    target_doc.save.assert_called_once()
    mock_frappe.rename_doc.assert_called_once_with(
        "Lead", "LEAD-DUPLICATE", "LEAD-PRIMARY", merge=True
    )
    note_payload = mock_frappe.get_doc.call_args_list[1].args[0]
    assert note_payload["doctype"] == "Comment"
    assert "LEAD-DUPLICATE" in note_payload["content"]


@patch("bude_api.api.sales_crm.frappe")
def test_rep_cannot_merge_duplicate_leads(mock_frappe):
    _grant(mock_frappe, roles=["Sales User"])

    result = crm_api.merge_leads("LEAD-002", "LEAD-001")

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.rename_doc.assert_not_called()


@patch("bude_api.api.sales_crm.frappe")
def test_update_rejects_stale_revision(mock_frappe):
    _grant(mock_frappe)
    mock_frappe.db.get_value.return_value = "2026-08-04 11:00:00"

    result = crm_api.update_lead(
        "LEAD-001",
        {"status": "Open"},
        base_modified="2026-08-04 10:00:00",
    )

    assert result["ok"] is False
    assert result["code"] == "CONFLICT"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.sales_crm.frappe")
def test_convert_erpnext_lead_creates_linked_opportunity(mock_frappe):
    _grant(mock_frappe)
    mock_frappe.db.get_value.return_value = {
        "lead_name": "Asha Rao",
        "company_name": "Acme",
        "email_id": "asha@example.com",
        "mobile_no": "9999900000",
    }
    opportunity = MagicMock()
    opportunity.name = "OPP-001"
    opportunity.as_dict.return_value = {
        "name": "OPP-001",
        "title": "Acme",
        "opportunity_from": "Lead",
        "party_name": "LEAD-001",
        "status": "Open",
        "sales_stage": "Qualification",
        "opportunity_amount": 25000,
        "probability": 25,
    }
    mock_frappe.get_doc.return_value = opportunity

    result = crm_api.convert_lead(
        "LEAD-001",
        {"stage": "Qualification", "value": 25000, "probability": 25},
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "Opportunity"
    assert payload["party_name"] == "LEAD-001"
    assert result["data"]["deal"]["weighted_value"] == 6250


@patch("bude_api.api.sales_crm.frappe")
def test_convert_frappe_crm_lead_uses_native_conversion_contract(mock_frappe):
    _grant(mock_frappe, provider="frappe_crm", installed=["frappe", "erpnext", "crm"])
    lead_doc = MagicMock()
    deal_doc = MagicMock()
    deal_doc.as_dict.return_value = {
        "name": "CRM-DEAL-001",
        "organization_name": "Acme",
        "status": "Qualification",
        "expected_deal_value": 12000,
        "probability": 50,
    }
    mock_frappe.get_doc.side_effect = [lead_doc, deal_doc]
    converter = MagicMock(return_value="CRM-DEAL-001")
    mock_frappe.get_attr.return_value = converter

    result = crm_api.convert_lead(
        "CRM-LEAD-001",
        {
            "stage": "Qualification",
            "value": 12000,
            "existing_contact": "CONTACT-001",
            "existing_organization": "CRM-ORG-001",
        },
    )

    assert result["ok"] is True
    converter.assert_called_once_with(
        lead="CRM-LEAD-001",
        deal={"status": "Qualification", "expected_deal_value": 12000},
        existing_contact="CONTACT-001",
        existing_organization="CRM-ORG-001",
    )
    assert result["data"]["deal"]["weighted_value"] == 6000


@patch("bude_api.api.sales_crm.frappe")
def test_signed_intake_rejects_duplicate_and_returns_existing_lead(mock_frappe):
    _grant(mock_frappe)
    secret = "test-secret"
    mock_frappe.conf.get.side_effect = lambda key: {
        "bude_sales_crm_provider": "erpnext",
        "bude_sales_crm_enabled": 1,
        "bude_sales_intake_secret": secret,
    }.get(key)
    mock_frappe.get_list.return_value = [
        {
            "name": "LEAD-001",
            "lead_name": "Asha",
            "email_id": "asha@example.com",
            "status": "Open",
        }
    ]
    payload = {"name": "Asha", "email": "asha@example.com"}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), f"{timestamp}.{raw}".encode(), hashlib.sha256).hexdigest()
    mock_frappe.cache.return_value.incr.return_value = 1
    mock_frappe.local = SimpleNamespace(request_ip="127.0.0.1")

    result = crm_api.capture_intake("api", payload, timestamp, signature, "external-1")

    assert result["ok"] is True
    assert result["data"]["created"] is False
    assert result["data"]["matched"] is True
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.sales_crm.frappe")
def test_won_deal_requires_an_explicit_customer_choice(mock_frappe):
    _grant(mock_frappe)
    mock_frappe.conf.get.side_effect = lambda key: {
        "bude_sales_crm_provider": "erpnext",
        "bude_sales_crm_enabled": 1,
    }.get(key)

    result = crm_api.close_deal("OPP-001", "won")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_CUSTOMER"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.sales_crm.frappe")
def test_attachment_upload_is_private_bounded_and_linked(mock_frappe):
    _grant(mock_frappe)
    mock_frappe.get_list.return_value = []
    saved = SimpleNamespace(
        name="FILE-001",
        file_name="card.pdf",
        file_url="/private/files/card.pdf",
    )
    save_file = MagicMock(return_value=saved)
    mock_frappe.get_attr.return_value = save_file

    result = crm_api.upload_attachment(
        "lead",
        "LEAD-001",
        "card.pdf",
        "aGVsbG8=",
        "upload-1",
    )

    assert result["ok"] is True
    save_file.assert_called_once_with(
        "card.pdf",
        b"hello",
        "Lead",
        "LEAD-001",
        is_private=1,
    )
    assert result["data"]["attachment"]["file_url"].startswith("/private/")


@patch("bude_api.api.sales_crm.frappe")
def test_send_email_respects_do_not_contact(mock_frappe):
    _grant(mock_frappe)
    mock_frappe.get_list.return_value = [
        {
            "name": "LEAD-001",
            "lead_name": "Asha Rao",
            "email_id": "asha@example.com",
            "status": "Do Not Contact",
            "do_not_contact": 1,
        }
    ]

    result = crm_api.send_email(
        "lead",
        "LEAD-001",
        "asha@example.com",
        "Follow up",
        "Hello Asha",
    )

    assert result["ok"] is False
    assert result["code"] == "DO_NOT_CONTACT"
    mock_frappe.sendmail.assert_not_called()


@patch("bude_api.api.sales_crm.frappe")
def test_send_email_links_communication_to_provider_record(mock_frappe):
    _grant(mock_frappe)
    mock_frappe.get_list.return_value = [
        {
            "name": "LEAD-001",
            "lead_name": "Asha Rao",
            "email_id": "asha@example.com",
            "status": "Open",
        }
    ]

    result = crm_api.send_email(
        "lead",
        "LEAD-001",
        "asha@example.com, owner@example.com",
        " Follow up ",
        " Hello Asha ",
    )

    assert result["ok"] is True
    mock_frappe.sendmail.assert_called_once_with(
        recipients=["asha@example.com", "owner@example.com"],
        subject="Follow up",
        message="Hello Asha",
        reference_doctype="Lead",
        reference_name="LEAD-001",
        now=True,
    )
