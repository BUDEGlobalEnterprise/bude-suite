from ...utils.response import failure, success
from .permissions import permission_denied


def erpnext_message(exc: Exception) -> str:
    msg = (str(exc) or '').strip() or 'ERPNext rejected the document.'
    try:
        from frappe.utils import strip_html_tags
        msg = strip_html_tags(msg).strip() or msg
    except Exception:
        pass
    return msg
