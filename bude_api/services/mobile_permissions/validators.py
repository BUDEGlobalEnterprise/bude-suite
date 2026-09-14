"""Validation helpers shared by the permission DocType controllers.

Kept Frappe-free where possible so the window logic is unit-testable.
"""


def validity_window_ok(valid_from, valid_until) -> bool:
    """True unless both bounds are set and ``valid_until`` is not after
    ``valid_from``."""
    if valid_from and valid_until:
        return valid_until > valid_from
    return True


def permission_code_for(app_key: str, screen_key: str) -> str:
    return f"{app_key}.{screen_key}"
