"""Centralized configuration access for the Bude API app.

Reads from (in order):
1. Frappe site_config.json (via frappe.conf)
2. Process environment variables
3. Hardcoded defaults
"""

import os
from typing import Any

try:
    import frappe
except ImportError:
    frappe = None


_DEFAULTS: dict[str, Any] = {
    "bude_api_token_expiry_hours": 24,
    "bude_api_default_warehouse": None,
    "bude_api_log_level": "INFO",
}


def get(key: str, default: Any = None) -> Any:
    if frappe is not None:
        value = frappe.conf.get(key)
        if value is not None:
            return value

    env_key = key.upper()
    if env_key in os.environ:
        return os.environ[env_key]

    if key in _DEFAULTS:
        return _DEFAULTS[key]

    return default


def require(key: str) -> Any:
    value = get(key)
    if value is None:
        raise RuntimeError(f"Required configuration key '{key}' is not set.")
    return value
