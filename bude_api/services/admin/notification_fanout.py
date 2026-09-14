"""Grouped admin.notifications endpoints: notification_fanout."""

from ._notifications_shared import *  # noqa: F401,F403

def fan_out_notification_logs(limit: int | None = None, dry_run: bool = False) -> dict:
    """Send routeable Notification Log rows to registered FCM device tokens.

    This is intentionally isolated behind `_send_fcm_message` so unit tests do
    not need a Firebase project. Production benches provide `fcm_server_key`
    through `site_config.json` or monkey-patch the sender to a service-account
    implementation.
    """
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    page = parse_page(limit, 0, default_limit=100, max_limit=200)
    if not isinstance(page, Page):
        return page

    rows = frappe.get_list(
        "Notification Log",
        fields=[
            "name",
            "for_user",
            "subject",
            "email_content",
            "document_type",
            "document_name",
        ],
        order_by="creation desc",
        limit_page_length=page.limit,
    )
    sent = _sent_logs()
    delivered = 0
    failed = 0
    skipped = 0
    attempts = []
    for row in rows:
        name = row.get("name")
        user = row.get("for_user")
        if not name or not user or name in sent:
            skipped += 1
            continue
        category = _category_for(row)
        if not _preferences(user).get(category, True):
            skipped += 1
            continue
        tokens = [
            device.get("token")
            for device in _devices(user).values()
            if (device.get("token") or "").strip()
        ]
        if not tokens:
            skipped += 1
            continue
        payload = _payload_for_log(row, category)
        log_failed = False
        for token in tokens:
            attempts.append({"notification_log": name, "token": _token_preview(token)})
            if not _as_bool(dry_run):
                try:
                    _send_fcm_message(token, payload)
                except Exception:
                    failed += 1
                    log_failed = True
                    continue
            delivered += 1
        if not log_failed:
            sent.add(name)
    if not _as_bool(dry_run):
        _cache_set(_sent_logs_key(), {"names": sorted(sent)})
    return success({
        "delivered": delivered,
        "failed": failed,
        "skipped": skipped,
        "attempts": attempts,
        "dry_run": _as_bool(dry_run),
    })
