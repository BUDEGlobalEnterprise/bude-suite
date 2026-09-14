import base64
import csv
import io
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bude_api.api import hr as hr_api
from bude_api.services.hr import exports


def _wire(mock_frappe, roles=None):
    mock_frappe.session.user = "employee@example.com"
    mock_frappe.get_roles.return_value = roles or ["Employee"]
    mock_frappe.db.exists.return_value = True


def _employee_row():
    return {
        "name": "EMP-001",
        "employee_name": "Alice Employee",
        "company": "Bude",
        "department": "Operations",
        "designation": "Associate",
        "user_id": "employee@example.com",
    }


def _lists(mock_frappe, rows):
    """First get_list resolves the employee, the second returns export rows."""
    mock_frappe.get_list.side_effect = [[_employee_row()], rows]


def _rows_of(result):
    text = base64.b64decode(result["data"]["content"]).decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


@patch("bude_api.api.hr.frappe")
def test_attendance_export_returns_a_header_and_one_row_per_record(mock_frappe):
    _wire(mock_frappe)
    _lists(
        mock_frappe,
        [
            {
                "attendance_date": "2026-07-01",
                "status": "Present",
                "working_hours": 8.5,
                "in_time": "2026-07-01 09:00:00",
                "out_time": "2026-07-01 17:30:00",
                "late_entry": 0,
                "early_exit": 1,
                "shift": "Day",
            }
        ],
    )

    result = hr_api.export_history("attendance", "2026-07-01", "2026-07-31")

    assert result["ok"] is True
    assert result["data"]["mime"] == "text/csv"
    assert result["data"]["file_name"] == "attendance-2026-07-01-to-2026-07-31.csv"
    assert result["data"]["row_count"] == 1
    header, row = _rows_of(result)
    assert header[0] == "Date"
    assert row[:3] == ["2026-07-01", "Present", "8.5"]


@patch("bude_api.api.hr.frappe")
def test_export_is_filtered_to_the_signed_in_employee(mock_frappe):
    _wire(mock_frappe)
    _lists(mock_frappe, [])

    hr_api.export_history("leave", "2026-01-01", "2026-06-30")

    filters = mock_frappe.get_list.call_args_list[-1].kwargs["filters"]
    assert ["employee", "=", "EMP-001"] in filters
    assert ["from_date", ">=", "2026-01-01"] in filters
    assert ["to_date", "<=", "2026-06-30"] not in filters  # only the start field


@patch("bude_api.api.hr.frappe")
def test_salary_slip_export_excludes_drafts(mock_frappe):
    _wire(mock_frappe)
    _lists(mock_frappe, [])

    hr_api.export_history("salary_slips")

    filters = mock_frappe.get_list.call_args_list[-1].kwargs["filters"]
    assert ["docstatus", "=", 1] in filters


@patch("bude_api.api.hr.frappe")
def test_an_empty_period_still_produces_a_readable_file(mock_frappe):
    _wire(mock_frappe)
    _lists(mock_frappe, [])

    result = hr_api.export_history("checkins", "2026-07-01", "2026-07-31")

    assert result["data"]["row_count"] == 0
    assert _rows_of(result) == [["Time", "Type", "Reference"]]


@patch("bude_api.api.hr.frappe")
def test_booleans_read_as_words_not_as_zero_and_one(mock_frappe):
    _wire(mock_frappe)
    _lists(
        mock_frappe,
        [
            {
                "attendance_date": "2026-07-01",
                "status": "Present",
                "working_hours": 8,
                "in_time": None,
                "out_time": None,
                "late_entry": True,
                "early_exit": False,
                "shift": None,
            }
        ],
    )

    row = _rows_of(hr_api.export_history("attendance"))[1]

    assert row[5:8] == ["Yes", "No", ""]


@patch("bude_api.api.hr.frappe")
def test_unknown_kind_is_rejected_before_any_query(mock_frappe):
    _wire(mock_frappe)

    result = hr_api.export_history("everything")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_EXPORT_KIND"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.hr.frappe")
def test_a_range_longer_than_a_year_is_refused(mock_frappe):
    _wire(mock_frappe)
    _lists(mock_frappe, [])

    result = hr_api.export_history("attendance", "2024-01-01", "2026-01-01")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_RANGE_TOO_LONG"


@patch("bude_api.api.hr.frappe")
def test_a_backwards_range_is_refused(mock_frappe):
    _wire(mock_frappe)
    _lists(mock_frappe, [])

    result = hr_api.export_history("attendance", "2026-07-31", "2026-07-01")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_DATE_RANGE"


@patch("bude_api.api.hr.frappe")
def test_export_requires_an_hr_role(mock_frappe):
    _wire(mock_frappe, roles=["Stock User"])

    result = hr_api.export_history("attendance")

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.hr.frappe")
def test_a_user_with_no_employee_record_gets_no_rows(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = []

    result = hr_api.export_history("attendance")

    assert result["ok"] is False
    assert result["code"] == "HR_EMPLOYEE_NOT_FOUND"


@patch("bude_api.api.hr.frappe")
def test_excel_format_goes_through_frappes_own_xlsx_writer(mock_frappe, monkeypatch):
    _wire(mock_frappe)
    _lists(mock_frappe, [])
    make_xlsx = MagicMock(return_value=io.BytesIO(b"PK\x03\x04 fake"))
    monkeypatch.setitem(
        sys.modules,
        "frappe.utils.xlsxutils",
        SimpleNamespace(make_xlsx=make_xlsx),
    )

    result = hr_api.export_history("leave", "2026-01-01", "2026-01-31", format="xlsx")

    assert result["data"]["file_name"].endswith(".xlsx")
    assert result["data"]["mime"].startswith("application/vnd.openxmlformats")
    assert base64.b64decode(result["data"]["content"]) == b"PK\x03\x04 fake"
    # The same table the CSV writer would have received.
    assert make_xlsx.call_args.args[0][0][0] == "From"


@pytest.mark.parametrize("kind", exports.EXPORT_KINDS)
@patch("bude_api.api.hr.frappe")
def test_every_advertised_kind_actually_exports(mock_frappe, kind):
    _wire(mock_frappe)
    _lists(mock_frappe, [])

    assert hr_api.export_history(kind, "2026-01-01", "2026-01-31")["ok"] is True
