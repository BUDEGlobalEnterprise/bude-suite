"""Grouped admin.notifications endpoints: notification_preferences."""

from ._notifications_shared import *  # noqa: F401,F403

def preferences() -> dict:
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    user = _user()
    if not user:
        return auth_expired()
    return success(_preferences(user))

def update_preferences(preferences: dict) -> dict:
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    user = _user()
    if not user:
        return auth_expired()
    if not isinstance(preferences, dict):
        return failure("preferences must be an object.", code="VALIDATION_BAD_SHAPE")

    current = _preferences(user)
    for category, enabled in preferences.items():
        if category not in _CATEGORIES:
            return failure(
                f"Unknown notification category: {category}.",
                code="VALIDATION_UNKNOWN_CATEGORY",
            )
        current[category] = bool(enabled)
    _cache_set(_prefs_key(user), current)
    return success(current)
