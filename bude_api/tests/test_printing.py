import base64
import io
import os
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import quote

import pytest

from bude_api.services.common import printing


class _Frappe(SimpleNamespace):
    """Minimal frappe stand-in: a logged-in session plus permission control."""

    def __init__(self, user="operator@bude.test", allowed=True, base="https://erp.test"):
        super().__init__(
            session=SimpleNamespace(user=user),
            utils=SimpleNamespace(get_url=lambda path: f"{base}{path}"),
        )
        self.has_permission = MagicMock(return_value=allowed)


@pytest.fixture
def frappe_stub(monkeypatch):
    stub = _Frappe()
    monkeypatch.setattr(printing, "frappe", stub)
    return stub


def test_returns_origin_relative_download_url(frappe_stub):
    result = printing.document_pdf_url("Salary Slip", "SAL-0001")

    assert result["ok"] is True
    url = result["data"]["url"]
    assert url.startswith("/api/method/frappe.utils.print_format.download_pdf")
    assert "doctype=Salary%20Slip" in url
    assert "name=SAL-0001" in url
    assert "format=Standard" in url
    assert "no_letterhead=0" in url
    assert result["data"]["file_name"] == "SAL-0001.pdf"


def test_custom_print_format_and_no_letterhead(frappe_stub):
    result = printing.document_pdf_url(
        "Sales Invoice", "SINV-0007", print_format="Bude Tax Invoice", letterhead=False
    )

    url = result["data"]["url"]
    assert "format=Bude%20Tax%20Invoice" in url
    assert "no_letterhead=1" in url


def test_slashes_in_document_name_do_not_break_the_filename(frappe_stub):
    result = printing.document_pdf_url("Sales Order", "SO/2026/0001")

    assert result["data"]["file_name"] == "SO-2026-0001.pdf"
    assert "name=SO%2F2026%2F0001" in result["data"]["url"]


def test_doctype_outside_the_allowlist_is_denied(frappe_stub):
    result = printing.document_pdf_url("User", "Administrator")

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    frappe_stub.has_permission.assert_not_called()


def test_guest_session_is_auth_expired(monkeypatch):
    monkeypatch.setattr(printing, "frappe", _Frappe(user="Guest"))

    result = printing.document_pdf_url("Salary Slip", "SAL-0001")

    assert result["ok"] is False
    assert result["code"] == "AUTH_EXPIRED"


def test_permission_denied_when_user_cannot_read_the_document(monkeypatch):
    monkeypatch.setattr(printing, "frappe", _Frappe(allowed=False))

    result = printing.document_pdf_url("Salary Slip", "SAL-0001")

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"


def test_falls_back_to_read_permission_when_print_permtype_raises(monkeypatch):
    stub = _Frappe()
    stub.has_permission = MagicMock(side_effect=[Exception("no ptype"), True])
    monkeypatch.setattr(printing, "frappe", stub)

    assert printing.document_pdf_url("Salary Slip", "SAL-0001")["ok"] is True


@pytest.mark.parametrize("doctype,name", [("", "SAL-0001"), ("Salary Slip", "  ")])
def test_missing_arguments_fail(frappe_stub, doctype, name):
    assert printing.document_pdf_url(doctype, name)["ok"] is False


@pytest.mark.parametrize(
    "doctype",
    [
        "Appraisal",
        "Attendance",
        "Attendance Request",
        "Compensatory Leave Request",
        "Employee Advance",
        "Employee Grievance",
        "Employee Tax Exemption Declaration",
        "Expense Claim",
        "Leave Application",
        "Salary Slip",
        "Shift Request",
        "Timesheet",
        "Travel Request",
    ],
)
def test_every_hr_document_an_employee_raises_is_printable(frappe_stub, doctype):
    """The HR app offers "download as PDF" on each of its request types, so the
    allowlist has to cover all of them — a missing entry is a dead button."""
    result = printing.document_pdf_url(doctype, "HR-0001")

    assert result["ok"] is True
    assert f"doctype={quote(doctype, safe='')}" in result["data"]["url"]


def test_without_frappe_installed_it_fails_cleanly(monkeypatch):
    monkeypatch.setattr(printing, "frappe", None)

    result = printing.document_pdf_url("Salary Slip", "SAL-0001")

    assert result["ok"] is False


# --- bulk downloads ---------------------------------------------------------


def test_merged_bundle_points_at_frappes_own_multi_pdf_endpoint(frappe_stub):
    result = printing.documents_pdf_url("Salary Slip", ["SAL-0001", "SAL-0002"])

    assert result["ok"] is True
    assert result["data"]["bundle"] == "merged"
    assert result["data"]["count"] == 2
    url = result["data"]["url"]
    assert url.startswith("/api/method/frappe.utils.print_format.download_multi_pdf")
    assert quote('["SAL-0001", "SAL-0002"]', safe="") in url


def test_names_arriving_as_json_text_are_parsed(frappe_stub):
    # Whitelisted args come over HTTP as strings, so a Dart list is JSON text.
    result = printing.documents_pdf_url("Salary Slip", '["SAL-0001","SAL-0002"]')

    assert result["data"]["count"] == 2


def test_duplicate_names_are_collapsed(frappe_stub):
    result = printing.documents_pdf_url("Salary Slip", ["SAL-0001", "SAL-0001"])

    assert result["data"]["count"] == 1


def test_documents_the_caller_cannot_read_are_dropped_silently(frappe_stub):
    frappe_stub.has_permission = MagicMock(
        side_effect=lambda doctype, ptype, doc=None: doc == "SAL-0001"
    )

    result = printing.documents_pdf_url("Salary Slip", ["SAL-0001", "SAL-0009"])

    # SAL-0009 belongs to someone else: it is absent from the URL, and the
    # response never says it exists.
    assert result["data"]["count"] == 1
    assert "SAL-0009" not in result["data"]["url"]


def test_a_selection_of_only_foreign_documents_is_denied(frappe_stub):
    frappe_stub.has_permission = MagicMock(return_value=False)

    result = printing.documents_pdf_url("Salary Slip", ["SAL-0009"])

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"


def test_too_many_documents_is_rejected_before_any_rendering(frappe_stub):
    names = [f"SAL-{index:04d}" for index in range(printing.MAX_BULK_DOCUMENTS + 1)]

    result = printing.documents_pdf_url("Salary Slip", names)

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_TOO_MANY_DOCUMENTS"
    frappe_stub.has_permission.assert_not_called()


def test_empty_selection_is_rejected(frappe_stub):
    assert printing.documents_pdf_url("Salary Slip", []) ["ok"] is False


def test_bulk_download_honours_the_allowlist(frappe_stub):
    result = printing.documents_pdf_url("User", ["Administrator"])

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"


def test_zip_bundle_returns_one_pdf_per_document(frappe_stub):
    frappe_stub.get_print = MagicMock(return_value=b"%PDF-1.4 fake")

    result = printing.documents_pdf_url(
        "Salary Slip", ["SAL-0001", "SAL/2026/0002"], bundle="zip"
    )

    assert result["data"]["mime"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(result["data"]["content"])))
    # The slash in a document name must not create a folder inside the zip.
    assert archive.namelist() == ["SAL-0001.pdf", "SAL-2026-0002.pdf"]
    assert archive.read("SAL-0001.pdf") == b"%PDF-1.4 fake"


def test_one_unprintable_document_does_not_lose_the_archive(frappe_stub):
    frappe_stub.get_print = MagicMock(
        side_effect=lambda doctype, name, *args, **kwargs: (
            b"%PDF" if name == "SAL-0001" else _boom()
        )
    )

    result = printing.documents_pdf_url(
        "Salary Slip", ["SAL-0001", "SAL-0002"], bundle="zip"
    )

    assert result["ok"] is True
    assert result["data"]["count"] == 1


def test_a_zip_where_nothing_renders_is_an_error_not_an_empty_file(frappe_stub):
    frappe_stub.get_print = MagicMock(side_effect=RuntimeError("no wkhtmltopdf"))

    result = printing.documents_pdf_url("Salary Slip", ["SAL-0001"], bundle="zip")

    assert result["ok"] is False
    assert result["code"] == "PRINT_FAILED"


def test_an_oversized_zip_is_refused_rather_than_streamed(frappe_stub):
    # Incompressible payload, so the archive really does grow past the cap.
    frappe_stub.get_print = MagicMock(
        return_value=os.urandom(printing.MAX_BUNDLE_BYTES + 1)
    )

    result = printing.documents_pdf_url("Salary Slip", ["SAL-0001"], bundle="zip")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BUNDLE_TOO_LARGE"


def _boom():
    raise RuntimeError("render failed")
