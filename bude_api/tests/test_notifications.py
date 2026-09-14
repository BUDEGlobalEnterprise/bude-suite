from unittest.mock import patch

from bude_api.api import notifications as notifications_api


def _login(mock_frappe):
    mock_frappe.session.user = "operator@example.com"
    mock_frappe.utils.now.return_value = "2026-07-07 10:00:00"


def _cache_store(mock_frappe):
    store = {}
    cache = mock_frappe.cache.return_value
    cache.get_value.side_effect = lambda key: store.get(key)
    cache.set_value.side_effect = lambda key, value: store.__setitem__(key, value)
    return store


@patch("bude_api.api.notifications.frappe")
def test_register_and_unregister_device_token(mock_frappe):
    _login(mock_frappe)
    store = _cache_store(mock_frappe)

    result = notifications_api.register_device(
        token=" fcm-token ",
        device_id=" device-1 ",
        platform="android",
    )

    assert result["ok"] is True
    devices = store["bude_api:notifications:devices:operator@example.com"]
    assert devices["device-1"]["token"] == "fcm-token"

    result = notifications_api.unregister_device("device-1")

    assert result["ok"] is True
    assert result["data"]["remaining"] == 0


@patch("bude_api.api.notifications.frappe")
def test_registered_device_registry_lists_and_revokes_admin_view(mock_frappe):
    _login(mock_frappe)
    store = _cache_store(mock_frappe)

    notifications_api.register_device(
        token="abcdef1234567890",
        device_id="device-1",
        platform="android",
    )

    rows = notifications_api.list_registered_devices()

    assert rows == [
        {
            "user": "operator@example.com",
            "device_id": "device-1",
            "platform": "android",
            "last_seen": "2026-07-07 10:00:00",
            "token_preview": "abcdef...7890",
        }
    ]

    removed = notifications_api.revoke_registered_device(
        "operator@example.com",
        "device-1",
    )

    assert removed is True
    assert notifications_api.list_registered_devices() == []
    assert store["bude_api:notifications:devices:operator@example.com"] == {}


@patch("bude_api.api.notifications.frappe")
def test_unregister_without_device_clears_tokens_on_logout(mock_frappe):
    _login(mock_frappe)
    store = _cache_store(mock_frappe)
    notifications_api.register_device("token-a", "device-a")
    notifications_api.register_device("token-b", "device-b")

    result = notifications_api.unregister_device()

    assert result["ok"] is True
    assert result["data"]["remaining"] == 0
    assert store["bude_api:notifications:devices:operator@example.com"] == {}


@patch("bude_api.api.notifications.frappe")
def test_preferences_update_validates_categories(mock_frappe):
    _login(mock_frappe)
    _cache_store(mock_frappe)

    result = notifications_api.update_preferences({"low_stock": False})

    assert result["ok"] is True
    assert result["data"]["low_stock"] is False
    assert result["data"]["po_arrival"] is True

    bad = notifications_api.update_preferences({"unknown": True})
    assert bad["ok"] is False
    assert bad["code"] == "VALIDATION_UNKNOWN_CATEGORY"


@patch("bude_api.api.notifications.frappe")
def test_payloads_route_notification_logs_to_enabled_categories(mock_frappe):
    _login(mock_frappe)
    _cache_store(mock_frappe)
    notifications_api.register_device("token-a", "device-a")
    notifications_api.update_preferences({"sync_failure": False})

    mock_frappe.get_list.return_value = [
        {
            "name": "LOG-LOW",
            "subject": "Low stock digest",
            "email_content": "Items below reorder point",
            "document_type": "Item",
            "document_name": "ITEM-001",
        },
        {
            "name": "LOG-SYNC",
            "subject": "Sync failure",
            "email_content": "Queued work failed",
            "document_type": None,
            "document_name": None,
        },
    ]

    result = notifications_api.payloads(limit=10)

    assert result["ok"] is True
    assert result["data"]["total"] == 1
    payload = result["data"]["payloads"][0]
    assert payload["notification_log"] == "LOG-LOW"
    assert payload["category"] == "low_stock"
    assert payload["route"] == "/alerts"
    assert payload["tokens"] == ["token-a"]
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["limit_page_length"] == 10


@patch("bude_api.api.notifications.frappe")
def test_crm_notification_categories_use_record_aware_mobile_routes(mock_frappe):
    _login(mock_frappe)
    _cache_store(mock_frappe)
    notifications_api.register_device("token-a", "device-a")
    mock_frappe.get_list.return_value = [
        {
            "name": "LOG-LEAD",
            "subject": "A lead was assigned to you",
            "email_content": "Please make first contact",
            "document_type": "CRM Lead",
            "document_name": "LEAD / 001",
        },
        {
            "name": "LOG-DEAL",
            "subject": "Deal stage changed",
            "email_content": "Moved to negotiation",
            "document_type": "CRM Deal",
            "document_name": "DEAL-001",
        },
        {
            "name": "LOG-TASK",
            "subject": "Task is overdue",
            "email_content": "Call the customer",
            "document_type": "CRM Task",
            "document_name": "TASK-001",
        },
    ]

    result = notifications_api.payloads(limit=10)

    rows = result["data"]["payloads"]
    assert [(row["category"], row["route"]) for row in rows] == [
        ("lead_assignment", "/leads/LEAD%20%2F%20001"),
        ("deal_stage", "/deals/DEAL-001"),
        ("task_due", "/crm-tasks"),
    ]


@patch("bude_api.api.notifications.frappe")
def test_helpdesk_automation_notifications_use_helpdesk_routes(mock_frappe):
    _login(mock_frappe)
    _cache_store(mock_frappe)
    notifications_api.register_device("token-a", "device-a")
    mock_frappe.get_list.return_value = [
        {
            "name": "LOG-TICKET",
            "subject": "Helpdesk SLA breach: HD-0001",
            "email_content": "Ticket HD-0001 needs attention",
            "document_type": "HD Ticket",
            "document_name": "HD-0001",
        },
        {
            "name": "LOG-DIGEST",
            "subject": "Bude Helpdesk escalation digest",
            "email_content": "Current automation matches",
            "document_type": None,
            "document_name": None,
        },
    ]

    result = notifications_api.payloads(limit=10)

    rows = result["data"]["payloads"]
    assert [(row["category"], row["route"]) for row in rows] == [
        ("helpdesk_escalation", "/agent/pulse"),
        ("helpdesk_digest", "/admin/automation"),
    ]


@patch("bude_api.api.notifications._send_fcm_message")
@patch("bude_api.api.notifications.frappe")
def test_fan_out_notification_logs_sends_registered_enabled_categories(
    mock_frappe,
    mock_send,
):
    _login(mock_frappe)
    _cache_store(mock_frappe)
    notifications_api.register_device("token-a", "device-a")
    mock_frappe.get_list.return_value = [
        {
            "name": "LOG-LOW",
            "for_user": "operator@example.com",
            "subject": "Low stock digest",
            "email_content": "Items below reorder",
            "document_type": "Item",
            "document_name": "ITEM-001",
        }
    ]

    result = notifications_api.fan_out_notification_logs(limit=10)

    assert result["ok"] is True
    assert result["data"]["delivered"] == 1
    mock_send.assert_called_once()
    token, payload = mock_send.call_args.args
    assert token == "token-a"
    assert payload["data"]["category"] == "low_stock"
    assert payload["data"]["route"] == "/alerts"


@patch("bude_api.api.notifications._send_fcm_message")
@patch("bude_api.api.notifications.frappe")
def test_fan_out_notification_logs_skips_disabled_category_and_sent_logs(
    mock_frappe,
    mock_send,
):
    _login(mock_frappe)
    store = _cache_store(mock_frappe)
    notifications_api.register_device("token-a", "device-a")
    notifications_api.update_preferences({"sync_failure": False})
    store["bude_api:notifications:fcm_sent_logs"] = {"names": ["LOG-SENT"]}
    mock_frappe.get_list.return_value = [
        {
            "name": "LOG-SYNC",
            "for_user": "operator@example.com",
            "subject": "Sync failure",
            "email_content": "Queued work failed",
            "document_type": None,
            "document_name": None,
        },
        {
            "name": "LOG-SENT",
            "for_user": "operator@example.com",
            "subject": "Low stock digest",
            "email_content": "Items below reorder",
            "document_type": "Item",
            "document_name": "ITEM-001",
        },
    ]

    result = notifications_api.fan_out_notification_logs(limit=10)

    assert result["ok"] is True
    assert result["data"]["delivered"] == 0
    assert result["data"]["skipped"] == 2
    mock_send.assert_not_called()


@patch("bude_api.api.notifications._send_fcm_message")
@patch("bude_api.api.notifications.frappe")
def test_fan_out_notification_logs_dry_run_does_not_send(mock_frappe, mock_send):
    _login(mock_frappe)
    _cache_store(mock_frappe)
    notifications_api.register_device("token-a", "device-a")
    mock_frappe.get_list.return_value = [
        {
            "name": "LOG-PO",
            "for_user": "operator@example.com",
            "subject": "Purchase Order arrived",
            "email_content": "PO ready",
            "document_type": "Purchase Order",
            "document_name": "PO-001",
        }
    ]

    result = notifications_api.fan_out_notification_logs(limit=10, dry_run=True)

    assert result["ok"] is True
    assert result["data"]["delivered"] == 1
    assert result["data"]["attempts"][0]["token"] == "token-a"
    mock_send.assert_not_called()


@patch("bude_api.api.notifications.frappe")
def test_payloads_rejects_over_cap_limit(mock_frappe):
    _login(mock_frappe)
    _cache_store(mock_frappe)

    result = notifications_api.payloads(limit=201)

    assert result["ok"] is False
    assert result["code"] == "PAGINATION_LIMIT_EXCEEDED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.notifications.frappe")
def test_guest_session_returns_auth_expired(mock_frappe):
    mock_frappe.session.user = "Guest"

    result = notifications_api.preferences()

    assert result["ok"] is False
    assert result["code"] == "AUTH_EXPIRED"


def test_fcm_v1_body_wraps_message_and_stringifies_data():
    from bude_api.services.admin._notifications_shared import _fcm_v1_body

    body = _fcm_v1_body(
        "tok-123",
        {
            "notification": {"title": "Low stock", "body": "5 items"},
            "data": {"category": "low_stock", "route": "/alerts", "count": 5},
        },
    )

    assert body == {
        "message": {
            "token": "tok-123",
            "notification": {"title": "Low stock", "body": "5 items"},
            # v1 requires all data values to be strings (note count: 5 -> "5").
            "data": {"category": "low_stock", "route": "/alerts", "count": "5"},
        }
    }


def test_fcm_v1_body_omits_absent_notification_and_data():
    from bude_api.services.admin._notifications_shared import _fcm_v1_body

    assert _fcm_v1_body("tok", {}) == {"message": {"token": "tok"}}
