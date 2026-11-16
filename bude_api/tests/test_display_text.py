"""Text the apps show as-is must be readable: no HTML, no internal codes."""

from bude_api.services.analytics.exceptions import _parse_todo
from bude_api.services.hr._mobile_shared import _plain_text


def test_notification_subject_html_becomes_plain_text():
    raw = "<strong>Administrator</strong> assigned a new task <strong>HD Ticket</strong> &amp; more"
    assert _plain_text(raw) == "Administrator assigned a new task HD Ticket & more"
    assert _plain_text(None) == ""


def test_exception_todo_gets_label_subject_and_note():
    row = {
        "name": "TODO-1",
        "description": "Exception: blocked_stock\nItem: SAF-3003\nBarcode: \nWarehouse: Stores - KS\nNote: Held for QC",
    }
    parsed = _parse_todo(row)
    assert parsed["title"] == "Stock on hold · SAF-3003"
    assert parsed["kind"] == "blocked_stock"
    assert parsed["note"] == "Held for QC"
    assert _parse_todo({"description": "Exception: unknown_scan\nBarcode: 890\nNote: "})["title"] == "Unknown barcode · 890"
