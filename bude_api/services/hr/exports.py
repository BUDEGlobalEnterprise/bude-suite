"""Period exports of an employee's own HR history as CSV or Excel.

Lives in `services/hr` rather than `services/common` on purpose: every query
here goes through `_employee_or_failure()` and filters on that employee, so an
export can never return another person's rows. A generic "export any doctype"
endpoint could not make that promise.
"""

import base64
import csv
import io

from ._mobile_shared import *  # noqa: F401,F403

# A year plus a leap day. Longer ranges are a reporting job, not a phone
# download — and an unbounded range is an easy way to melt the site.
MAX_EXPORT_DAYS = 366

MAX_EXPORT_ROWS = 2000

# kind -> (doctype, date field, columns as (fieldname, header)).
_EXPORTS = {
    "attendance": (
        "Attendance",
        "attendance_date",
        [
            ("attendance_date", "Date"),
            ("status", "Status"),
            ("working_hours", "Working Hours"),
            ("in_time", "In"),
            ("out_time", "Out"),
            ("late_entry", "Late Entry"),
            ("early_exit", "Early Exit"),
            ("shift", "Shift"),
        ],
    ),
    "checkins": (
        "Employee Checkin",
        "time",
        [("time", "Time"), ("log_type", "Type"), ("name", "Reference")],
    ),
    "expense_claims": (
        "Expense Claim",
        "posting_date",
        [
            ("posting_date", "Date"),
            ("name", "Claim"),
            ("total_claimed_amount", "Claimed"),
            ("total_sanctioned_amount", "Sanctioned"),
            ("status", "Status"),
            ("approval_status", "Approval"),
        ],
    ),
    "leave": (
        "Leave Application",
        "from_date",
        [
            ("from_date", "From"),
            ("to_date", "To"),
            ("leave_type", "Leave Type"),
            ("total_leave_days", "Days"),
            ("status", "Status"),
            ("name", "Reference"),
        ],
    ),
    "salary_slips": (
        "Salary Slip",
        "start_date",
        [
            ("start_date", "From"),
            ("end_date", "To"),
            ("gross_pay", "Gross"),
            ("total_deduction", "Deductions"),
            ("net_pay", "Net"),
            ("name", "Reference"),
        ],
    ),
}

EXPORT_KINDS = sorted(_EXPORTS)


def export_history(
    kind: str,
    from_date: str | None = None,
    to_date: str | None = None,
    format: str = "csv",
) -> dict:
    """Return the caller's own rows for one history kind as a downloadable file."""
    spec = _EXPORTS.get(str(kind or "").strip().lower())
    if not spec:
        return failure(
            f"Unknown export. Choose one of: {', '.join(EXPORT_KINDS)}.",
            code="VALIDATION_BAD_EXPORT_KIND",
        )
    doctype, date_field, columns = spec

    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes(doctype)
    if missing:
        return missing

    start, end, error = _export_window(from_date, to_date)
    if error:
        return error

    filters = [
        ["employee", "=", employee["name"]],
        [date_field, ">=", start.isoformat()],
        [date_field, "<=", end.isoformat()],
    ]
    if doctype == "Salary Slip":
        filters.append(["docstatus", "=", 1])
    rows = frappe.get_list(
        doctype,
        filters=filters,
        fields=[field for field, _ in columns],
        order_by=f"{date_field} asc",
        limit_page_length=MAX_EXPORT_ROWS,
    )

    table = [[header for _, header in columns]]
    table += [[_cell(row.get(field)) for field, _ in columns] for row in rows]
    stem = f"{kind}-{start.isoformat()}-to-{end.isoformat()}"
    if str(format or "csv").strip().lower() in {"xlsx", "excel"}:
        content, file_name, mime = _xlsx(table, stem, kind)
    else:
        content, file_name, mime = _csv(table, stem)
    return success(
        {
            "kind": kind,
            "from_date": start.isoformat(),
            "to_date": end.isoformat(),
            "row_count": len(rows),
            "file_name": file_name,
            "mime": mime,
            "content": base64.b64encode(content).decode("ascii"),
        }
    )


def _export_window(from_date, to_date):
    end = _date_or_none(to_date) or date.today()
    start = _date_or_none(from_date) or date(end.year, 1, 1)
    if start > end:
        return None, None, failure(
            "The start date must not be after the end date.",
            code="VALIDATION_BAD_DATE_RANGE",
        )
    if (end - start).days + 1 > MAX_EXPORT_DAYS:
        return None, None, failure(
            f"Exports cover at most {MAX_EXPORT_DAYS} days.",
            code="VALIDATION_RANGE_TOO_LONG",
        )
    return start, end, None


def _cell(value) -> str:
    if value is None:
        return ""
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return str(value)


def _csv(table: list[list[str]], stem: str) -> tuple[bytes, str, str]:
    buffer = io.StringIO(newline="")
    csv.writer(buffer).writerows(table)
    # utf-8-sig so Excel opens accented names and Arabic correctly on a
    # double-click instead of showing mojibake.
    return buffer.getvalue().encode("utf-8-sig"), f"{stem}.csv", "text/csv"


def _xlsx(table: list[list[str]], stem: str, sheet: str) -> tuple[bytes, str, str]:
    # Frappe ships openpyxl and this wrapper for its own report exports.
    from frappe.utils.xlsxutils import make_xlsx

    content = make_xlsx(table, sheet[:31]).getvalue()
    return (
        content,
        f"{stem}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
