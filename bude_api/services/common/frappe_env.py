try:
    import frappe
except ImportError:
    frappe = None


def current_user(frappe_module=None):
    module = frappe_module or frappe
    return getattr(getattr(module, 'session', None), 'user', None)


def is_available(frappe_module=None):
    return (frappe_module or frappe) is not None
