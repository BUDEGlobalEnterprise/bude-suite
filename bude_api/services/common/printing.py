"""Print-format PDF URLs for any standard ERPNext document.

Frappe already renders a PDF for every DocType through
`frappe.utils.print_format.download_pdf`. This module adds the only thing the
mobile apps are missing: a permission check plus an absolute URL they can
download with their session token. One endpoint therefore covers Salary Slip,
Expense Claim, Leave Application, Sales Order, Sales Invoice, Delivery Note,
Purchase Receipt, Stock Entry and HD Ticket — no per-doctype code.
"""

import base64
import io
import json
import zipfile
from urllib.parse import quote

try:
    import frappe
except ImportError:  # pragma: no cover - frappe is absent in unit tests
    frappe = None

from ...utils.response import failure, success
from .permissions import auth_expired, permission_denied

# DocTypes the mobile apps are allowed to print. An allowlist keeps the generic
# endpoint from turning into "download any document in the system as PDF".
#
# A doctype listed here but absent from a given site is harmless: `_can_print`
# fails closed and the caller gets a clean PERMISSION_DENIED rather than a 500.
PRINTABLE_DOCTYPES = {
    # Stock / selling / buying
    "Delivery Note",
    "Material Request",
    "Payment Entry",
    "Purchase Order",
    "Purchase Receipt",
    "Quotation",
    "Sales Invoice",
    "Sales Order",
    "Stock Entry",
    "Stock Reconciliation",
    # Helpdesk
    "HD Ticket",
    "Issue",
    # HR — every document an employee can raise about themselves, so the HR
    # app can offer "download as PDF" on each of its request types.
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
}

# Rendering a print format is a full HTML->PDF pass per document, so a bulk
# download is slow long before it is large. 50 keeps the request inside a
# normal gunicorn timeout.
MAX_BULK_DOCUMENTS = 50

# A zip is returned inline as base64, which inflates it by a third. 10 MB raw
# is about as much as a phone should be asked to hold in memory.
MAX_BUNDLE_BYTES = 10 * 1024 * 1024


def document_pdf_url(
    doctype: str,
    name: str,
    print_format: str | None = None,
    letterhead: bool = True,
) -> dict:
    """Return an absolute, downloadable print-format URL for one document."""
    doctype = (doctype or "").strip()
    name = (name or "").strip()
    if not doctype or not name:
        return failure("A document type and name are required.")
    if doctype not in PRINTABLE_DOCTYPES:
        return permission_denied(f"{doctype} cannot be printed from mobile.")
    if frappe is None:
        return failure("ERPNext is not available.")

    user = getattr(getattr(frappe, "session", None), "user", None)
    if user is None or user == "Guest":
        return auth_expired()

    if not _can_print(doctype, name):
        return permission_denied("You do not have permission to print this document.")

    return success(
        {
            "doctype": doctype,
            "name": name,
            "file_name": f"{name}.pdf".replace("/", "-"),
            "url": _print_url(doctype, name, print_format, letterhead),
        }
    )


def documents_pdf_url(
    doctype: str,
    names,
    bundle: str = "merged",
    print_format: str | None = None,
    letterhead: bool = True,
) -> dict:
    """Bundle many documents of one type into a single download.

    `bundle="merged"` returns a URL to Frappe's own `download_multi_pdf`, which
    re-checks print permission per document as it renders — the same
    delegate-to-core shape as `document_pdf_url`. `bundle="zip"` returns the
    archive inline, because core has no multi-file endpoint to point at.
    """
    doctype = (doctype or "").strip()
    if not doctype:
        return failure("A document type is required.")
    if doctype not in PRINTABLE_DOCTYPES:
        return permission_denied(f"{doctype} cannot be printed from mobile.")
    if frappe is None:
        return failure("ERPNext is not available.")

    user = getattr(getattr(frappe, "session", None), "user", None)
    if user is None or user == "Guest":
        return auth_expired()

    requested = _name_list(names)
    if not requested:
        return failure("At least one document name is required.")
    if len(requested) > MAX_BULK_DOCUMENTS:
        return failure(
            f"Select at most {MAX_BULK_DOCUMENTS} documents to download at once.",
            code="VALIDATION_TOO_MANY_DOCUMENTS",
        )

    # Never trust the client's list: anything the caller cannot read is dropped
    # silently, so the response never confirms that a foreign document exists.
    allowed = [name for name in requested if _can_print(doctype, name)]
    if not allowed:
        return permission_denied("You do not have permission to print these documents.")

    if str(bundle or "").strip().lower() == "zip":
        return _zip_bundle(doctype, allowed, print_format, letterhead)
    return success(
        {
            "doctype": doctype,
            "bundle": "merged",
            "count": len(allowed),
            "file_name": f"{doctype}.pdf".replace("/", "-"),
            "url": _multi_print_url(doctype, allowed, print_format, letterhead),
        }
    )


def _name_list(names) -> list[str]:
    """Accept a real list, a JSON array, or a comma-separated string.

    Whitelisted arguments arrive as strings over HTTP, so a Dart `List<String>`
    reaches us as JSON text.
    """
    if isinstance(names, str):
        text = names.strip()
        if text.startswith("["):
            try:
                names = json.loads(text)
            except ValueError:
                return []
        else:
            names = text.split(",")
    if not isinstance(names, (list, tuple)):
        return []
    seen: list[str] = []
    for value in names:
        name = str(value or "").strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def _multi_print_url(
    doctype: str,
    names: list[str],
    print_format: str | None,
    letterhead: bool,
) -> str:
    path = (
        "/api/method/frappe.utils.print_format.download_multi_pdf"
        f"?doctype={quote(doctype, safe='')}"
        f"&name={quote(json.dumps(names), safe='')}"
        f"&format={quote(print_format or 'Standard', safe='')}"
        f"&no_letterhead={0 if letterhead else 1}"
    )
    # Keep this origin-relative. A bench often sits behind a tunnel/reverse
    # proxy and its configured host_name may be a private address. The mobile
    # client resolves this path against the site it actually signed in to, so
    # internal IPs can never leak into a download URL.
    return path


def _zip_bundle(
    doctype: str,
    names: list[str],
    print_format: str | None,
    letterhead: bool,
) -> dict:
    buffer = io.BytesIO()
    rendered = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            try:
                pdf = frappe.get_print(
                    doctype,
                    name,
                    print_format or "Standard",
                    as_pdf=True,
                    no_letterhead=0 if letterhead else 1,
                )
            except Exception:
                # One unprintable document must not lose the whole archive, and
                # the reason belongs in the server log, not in the response.
                continue
            archive.writestr(f"{name}.pdf".replace("/", "-"), pdf)
            rendered += 1
            if buffer.tell() > MAX_BUNDLE_BYTES:
                return failure(
                    "That selection is too large to download as a zip. "
                    "Choose fewer documents or use the merged PDF.",
                    code="VALIDATION_BUNDLE_TOO_LARGE",
                )
    if not rendered:
        return failure("None of those documents could be printed.", code="PRINT_FAILED")
    return success(
        {
            "doctype": doctype,
            "bundle": "zip",
            "count": rendered,
            "file_name": f"{doctype}.zip".replace("/", "-"),
            "mime": "application/zip",
            "content": base64.b64encode(buffer.getvalue()).decode("ascii"),
        }
    )


def _can_print(doctype: str, name: str) -> bool:
    """Reject anything the session user cannot read.

    `print` is the precise permtype, but not every site grants it explicitly, so
    fall back to `read` — Frappe's own download_pdf enforces the real check
    again server-side when the URL is fetched.
    """
    try:
        if frappe.has_permission(doctype, "print", doc=name):
            return True
    except Exception:
        pass
    try:
        return bool(frappe.has_permission(doctype, "read", doc=name))
    except Exception:
        return False


def _print_url(
    doctype: str,
    name: str,
    print_format: str | None,
    letterhead: bool,
) -> str:
    # safe='' so that a document name like SO/2026/0001 stays one query value.
    path = (
        "/api/method/frappe.utils.print_format.download_pdf"
        f"?doctype={quote(doctype, safe='')}&name={quote(name, safe='')}"
        f"&format={quote(print_format or 'Standard', safe='')}"
        f"&no_letterhead={0 if letterhead else 1}"
    )
    return path
