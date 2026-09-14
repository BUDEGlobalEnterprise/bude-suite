"""Public API wrappers for `printing.py`.

Business logic lives in `bude_api.services.common.printing`.
Endpoint names stay here for Frappe/mobile compatibility.
"""
try:
    import frappe
except ImportError:
    frappe = None

from ..services.common import printing as _service


def _whitelist(methods=None, allow_guest: bool = False):
    if frappe is None:
        def decorator(fn):
            return fn
        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=methods or ["GET", "POST"])


def _call(name, *args, **kwargs):
    _service.frappe = frappe
    return getattr(_service, name)(*args, **kwargs)


@_whitelist(["GET", "POST"])
def document_pdf_url(
    doctype: str,
    name: str,
    print_format: str | None = None,
    letterhead: bool = True,
):
    return _call("document_pdf_url", doctype, name, print_format, letterhead)


@_whitelist(["GET", "POST"])
def documents_pdf_url(
    doctype: str,
    names,
    bundle: str = "merged",
    print_format: str | None = None,
    letterhead: bool = True,
):
    return _call("documents_pdf_url", doctype, names, bundle, print_format, letterhead)
