"""Grouped admin.notifications endpoints: notification_devices."""

from ._notifications_shared import *  # noqa: F401,F403

def register_device(token: str, device_id: str, platform: str | None = None) -> dict:
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    user = _user()
    if not user:
        return auth_expired()

    token = (token or "").strip()
    device_id = (device_id or "").strip()
    if not token or not device_id:
        return failure("token and device_id are required.", code="VALIDATION_REQUIRED")

    devices = _devices(user)
    devices[device_id] = {
        "token": token,
        "platform": (platform or "").strip() or None,
        "last_seen": frappe.utils.now(),
    }
    _cache_set(_devices_key(user), devices)
    _upsert_registry_device(user, device_id, devices[device_id])
    return success({"device_id": device_id, "registered": True})

def unregister_device(device_id: str | None = None) -> dict:
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    user = _user()
    if not user:
        return auth_expired()

    devices = _devices(user)
    clean = (device_id or "").strip()
    if clean:
        devices.pop(clean, None)
        _remove_registry_device(user, clean)
    else:
        devices.clear()
        _remove_registry_user(user)
    _cache_set(_devices_key(user), devices)
    return success({"remaining": len(devices)})

def list_registered_devices() -> list[dict]:
    """Return admin-visible device registrations from the cache index."""
    registry = _cache_get(_registry_key())
    if not isinstance(registry, dict):
        return []
    rows = []
    for user, devices in registry.items():
        if not isinstance(devices, dict):
            continue
        for device_id, data in devices.items():
            if not isinstance(data, dict):
                continue
            rows.append({
                "user": user,
                "device_id": device_id,
                "platform": data.get("platform"),
                "last_seen": data.get("last_seen"),
                "token_preview": _token_preview(data.get("token")),
            })
    return sorted(rows, key=lambda row: (row.get("user") or "", row.get("device_id") or ""))

def revoke_registered_device(user: str, device_id: str) -> bool:
    """Remove a device from both the per-user token cache and the admin index."""
    user = (user or "").strip()
    device_id = (device_id or "").strip()
    if not user or not device_id:
        return False
    devices = _devices(user)
    removed = device_id in devices
    devices.pop(device_id, None)
    _cache_set(_devices_key(user), devices)
    _remove_registry_device(user, device_id)
    return removed
