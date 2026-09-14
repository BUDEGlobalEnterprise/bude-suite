from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from bude_api.services.sales_crm import reminders


def _configured(mock_frappe):
    mock_frappe.conf.get.side_effect = lambda key: {
        "bude_sales_crm_enabled": 1,
        "bude_sales_crm_provider": "erpnext",
    }.get(key)
    mock_frappe.utils.now_datetime.return_value = datetime(2026, 8, 4, 9, 0)
    mock_frappe.get_meta.return_value.has_field.return_value = True
    mock_frappe.cache.return_value.get_value.return_value = None
    mock_frappe.db.exists.side_effect = lambda doctype, value: (
        True if doctype == "DocType" else False
    )


@patch("bude_api.services.sales_crm.reminders.fan_out_notification_logs")
@patch("bude_api.services.sales_crm.reminders.frappe")
def test_scheduler_creates_due_task_once_and_runs_delivery(mock_frappe, mock_fanout):
    _configured(mock_frappe)
    mock_frappe.get_list.side_effect = lambda doctype, **kwargs: (
        [
            {
                "name": "TODO-001",
                "description": "Call Asha",
                "allocated_to": "rep@example.com",
                "date": "2026-08-04",
                "status": "Open",
                "reference_type": "Lead",
                "reference_name": "LEAD-001",
            }
        ]
        if doctype == "ToDo"
        else []
    )
    notification = MagicMock(name="notification")
    mock_frappe.get_doc.return_value = notification
    mock_fanout.return_value = {"ok": True, "data": {"delivered": 1}}

    result = reminders.run_crm_reminders()

    assert result["created"] == 1
    notification.insert.assert_called_once_with(ignore_permissions=True)
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "Notification Log"
    assert payload["for_user"] == "rep@example.com"
    assert payload["document_type"] == "Lead"
    assert payload["document_name"] == "LEAD-001"
    mock_fanout.assert_called_once_with(limit=200)


@patch("bude_api.services.sales_crm.reminders.frappe")
def test_assignment_and_stage_changes_notify_new_owner(mock_frappe):
    _configured(mock_frappe)
    before = {"lead_owner": "old@example.com", "status": "Open"}
    doc = SimpleNamespace(
        doctype="Lead",
        name="LEAD-001",
        get=lambda field: {
            "lead_owner": "new@example.com",
            "status": "Interested",
        }.get(field),
        get_doc_before_save=lambda: before,
    )
    inserted = []

    def get_doc(payload):
        record = MagicMock()
        record.insert.side_effect = lambda **kwargs: inserted.append(payload)
        return record

    mock_frappe.get_doc.side_effect = get_doc

    reminders.on_crm_record_update(doc)

    assert len(inserted) == 2
    assert {row["subject"] for row in inserted} == {
        "Lead assigned: LEAD-001",
        "Lead stage changed: Interested",
    }
    assert all(row["for_user"] == "new@example.com" for row in inserted)


@patch("bude_api.services.sales_crm.reminders.frappe")
def test_disabled_site_does_not_query_or_send(mock_frappe):
    mock_frappe.conf.get.return_value = 0

    result = reminders.run_crm_reminders()

    assert result == {"created": 0, "skipped": 0, "delivery": None}
    mock_frappe.get_list.assert_not_called()
