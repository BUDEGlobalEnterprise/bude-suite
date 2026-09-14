"""Device-independent notification plumbing.

Firebase delivery is intentionally isolated from this module. These endpoints
cover the parts we can test without a Firebase project or device: device token
registration, per-user category preferences, and routeable payload generation
from standard Frappe `Notification Log` rows.
"""

try:
    import json
    from urllib import request
    from urllib.parse import quote

    import frappe
except ImportError:
    json = None
    request = None
    frappe = None

from ...utils.pagination import Page, parse_page

from ...utils.response import failure, success

from ..common.permissions import auth_expired

_CATEGORIES = {
    "low_stock": "/alerts",
    "po_arrival": "/receipt",
    "approval_pending": "/sync",
    "sync_failure": "/sync",
    "lead_assignment": "/leads",
    "task_due": "/crm-tasks",
    "sla_breach": "/leads?stale=1",
    "deal_stage": "/pipeline",
    "quotation_expiry": "/sell",
    "helpdesk_escalation": "/agent/pulse",
    "helpdesk_digest": "/admin/automation",
}

_DEFAULT_PREFS = {category: True for category in _CATEGORIES}

def route_for_category(category: str) -> str:
    return _CATEGORIES.get(category, "/")

def _route_for_log(row: dict, category: str) -> str:
    """Return the most specific mobile route supported by the sales app."""
    name = str(row.get("document_name") or "").strip()
    doctype = str(row.get("document_type") or "").strip()
    if name and doctype in {"Lead", "CRM Lead"}:
        return f"/leads/{quote(name, safe='')}"
    if name and doctype in {"Opportunity", "CRM Deal"}:
        return f"/deals/{quote(name, safe='')}"
    return route_for_category(category)

def _whitelist():
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=False, methods=["GET", "POST"])

def _payload_for_log(row: dict, category: str) -> dict:
    return {
        "notification": {
            "title": row.get("subject") or category.replace("_", " ").title(),
            "body": row.get("email_content") or "",
        },
        "data": {
            "category": category,
            "route": _route_for_log(row, category),
            "notification_log": row.get("name") or "",
            "ref_doctype": row.get("document_type") or "",
            "ref_name": row.get("document_name") or "",
        },
    }

def _category_for(row: dict) -> str:
    doctype = str(row.get("document_type") or "").strip()
    text = " ".join(
        str(row.get(key) or "").lower()
        for key in ("subject", "email_content", "document_type")
    )
    if doctype == "HD Ticket":
        return "helpdesk_escalation"
    if "helpdesk escalation digest" in text:
        return "helpdesk_digest"
    if "sla" in text or "response overdue" in text:
        return "sla_breach"
    if doctype in {"Lead", "CRM Lead"}:
        return "lead_assignment"
    if doctype in {"ToDo", "CRM Task"}:
        return "task_due"
    if doctype in {"Opportunity", "CRM Deal"}:
        return "deal_stage"
    if doctype == "Quotation" and any(
        word in text for word in ("expir", "follow up", "follow-up")
    ):
        return "quotation_expiry"
    if "low stock" in text or "reorder" in text:
        return "low_stock"
    if "purchase order" in text or row.get("document_type") == "Purchase Order":
        return "po_arrival"
    if "approval" in text or row.get("document_type") == "Workflow Action":
        return "approval_pending"
    if "sync" in text:
        return "sync_failure"
    return "approval_pending"

def _user() -> str | None:
    user = getattr(getattr(frappe, "session", None), "user", None)
    if not user or user == "Guest":
        return None
    return user

def _devices_key(user: str) -> str:
    return f"bude_api:notifications:devices:{user}"

def _prefs_key(user: str) -> str:
    return f"bude_api:notifications:prefs:{user}"

def _registry_key() -> str:
    return "bude_api:notifications:device_registry"

def _sent_logs_key() -> str:
    return "bude_api:notifications:fcm_sent_logs"

def _devices(user: str) -> dict:
    cached = _cache_get(_devices_key(user))
    return cached if isinstance(cached, dict) else {}

def _preferences(user: str) -> dict:
    cached = _cache_get(_prefs_key(user))
    if not isinstance(cached, dict):
        return dict(_DEFAULT_PREFS)
    result = dict(_DEFAULT_PREFS)
    for key, value in cached.items():
        if key in result:
            result[key] = bool(value)
    return result

def _sent_logs() -> set[str]:
    cached = _cache_get(_sent_logs_key())
    if isinstance(cached, dict):
        names = cached.get("names")
        if isinstance(names, list):
            return {str(name) for name in names}
    if isinstance(cached, list):
        return {str(name) for name in cached}
    return set()

def _token_preview(token: str | None) -> str | None:
    clean = (token or "").strip()
    if not clean:
        return None
    if len(clean) <= 10:
        return clean
    return f"{clean[:6]}...{clean[-4:]}"

def _upsert_registry_device(user: str, device_id: str, device: dict) -> None:
    registry = _cache_get(_registry_key())
    if not isinstance(registry, dict):
        registry = {}
    user_devices = registry.get(user)
    if not isinstance(user_devices, dict):
        user_devices = {}
    user_devices[device_id] = dict(device)
    registry[user] = user_devices
    _cache_set(_registry_key(), registry)

def _remove_registry_device(user: str, device_id: str) -> None:
    registry = _cache_get(_registry_key())
    if not isinstance(registry, dict):
        return
    devices = registry.get(user)
    if not isinstance(devices, dict):
        return
    devices.pop(device_id, None)
    if devices:
        registry[user] = devices
    else:
        registry.pop(user, None)
    _cache_set(_registry_key(), registry)

def _remove_registry_user(user: str) -> None:
    registry = _cache_get(_registry_key())
    if not isinstance(registry, dict):
        return
    registry.pop(user, None)
    _cache_set(_registry_key(), registry)

def _conf_value(name: str):
    conf = getattr(frappe, "conf", None)
    if conf is None:
        return None
    value = getattr(conf, name, None)
    if value is None and isinstance(conf, dict):
        value = conf.get(name)
    return value


def _service_account() -> dict | None:
    """The Firebase service account for FCM HTTP v1, from site config.

    Accepts either an inline dict (`fcm_service_account`) or a path to the JSON
    (`fcm_service_account_path`). Returns None when neither is configured, so
    the legacy path can act as a fallback.
    """
    inline = _conf_value("fcm_service_account")
    if isinstance(inline, dict) and inline.get("private_key") and inline.get("client_email"):
        return inline
    path = _conf_value("fcm_service_account_path")
    if path and json is not None:
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return None
        if isinstance(data, dict) and data.get("private_key") and data.get("client_email"):
            return data
    return None


def _fcm_v1_body(token: str, payload: dict) -> dict:
    """Wrap a legacy `{notification, data}` payload into the FCM HTTP v1 shape.

    v1 requires every `data` value to be a string.
    """
    message: dict = {"token": token}
    notification = payload.get("notification")
    if isinstance(notification, dict):
        message["notification"] = notification
    data = payload.get("data")
    if isinstance(data, dict):
        message["data"] = {str(key): str(value) for key, value in data.items()}
    return {"message": message}


def _fcm_access_token(service_account: dict) -> str:
    """Mint (and cache) a short-lived OAuth2 access token for FCM HTTP v1."""
    import time
    from urllib.parse import urlencode

    email = service_account.get("client_email")
    cache_key = f"bude_api:notifications:fcm_token:{email}"
    now = int(time.time())
    cached = _cache_get(cache_key)
    if isinstance(cached, dict) and cached.get("token") and int(cached.get("exp", 0)) > now + 60:
        return cached["token"]

    try:
        import jwt  # PyJWT — present on a Frappe bench (needs `cryptography`).
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError(
            "PyJWT is required for FCM HTTP v1; install it or set fcm_server_key."
        ) from exc

    token_uri = service_account.get("token_uri", "https://oauth2.googleapis.com/token")
    assertion = jwt.encode(
        {
            "iss": email,
            "scope": "https://www.googleapis.com/auth/firebase.messaging",
            "aud": token_uri,
            "iat": now,
            "exp": now + 3600,
        },
        service_account["private_key"],
        algorithm="RS256",
    )
    if isinstance(assertion, bytes):  # PyJWT 1.x returns bytes, 2.x returns str
        assertion = assertion.decode("ascii")
    body = urlencode(
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }
    ).encode("utf-8")
    req = request.Request(
        token_uri,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    response = json.loads(request.urlopen(req, timeout=10).read().decode("utf-8"))
    access_token = response.get("access_token")
    if not access_token:
        raise RuntimeError("FCM token exchange did not return an access_token.")
    _cache_set(cache_key, {"token": access_token, "exp": now + int(response.get("expires_in", 3600))})
    return access_token


def _send_fcm_message(token: str, payload: dict) -> None:
    if json is None or request is None:
        raise RuntimeError("Python JSON/URL libraries are not available.")

    service_account = _service_account()
    if service_account:
        # FCM HTTP v1 (service-account OAuth2) — Google's current, supported API.
        access_token = _fcm_access_token(service_account)
        project_id = service_account.get("project_id")
        body = json.dumps(_fcm_v1_body(token, payload)).encode("utf-8")
        req = request.Request(
            f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
            data=body,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        request.urlopen(req, timeout=10).read()
        return

    # Legacy FCM (shut down by Google in 2024); only a fallback for benches
    # still configured with a server key.
    server_key = _conf_value("fcm_server_key")
    if not server_key:
        raise RuntimeError(
            "No FCM credentials configured (set fcm_service_account or fcm_server_key)."
        )
    body = json.dumps({"to": token, **payload}).encode("utf-8")
    req = request.Request(
        "https://fcm.googleapis.com/fcm/send",
        data=body,
        headers={
            "Authorization": f"key={server_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    request.urlopen(req, timeout=10).read()

def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)

def _cache_get(key: str):
    try:
        cache = frappe.cache()
        getter = getattr(cache, "get_value", None) or getattr(cache, "get", None)
        return getter(key) if getter else None
    except Exception:
        return None

def _cache_set(key: str, value: dict) -> None:
    try:
        cache = frappe.cache()
        setter = getattr(cache, "set_value", None)
        if setter:
            setter(key, value)
            return
        setter = getattr(cache, "set", None)
        if setter:
            setter(key, value)
    except Exception:
        pass

__all__ = [name for name in globals() if not name.startswith("__")]
