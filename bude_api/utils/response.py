"""Standard envelope for API responses returned by `bude_api` endpoints."""

from typing import Any


def success(data: Any = None, message: str | None = None) -> dict:
    return {"ok": True, "data": data, "message": message}


def failure(message: str, code: str | None = None, data: Any = None) -> dict:
    return {"ok": False, "data": data, "message": message, "code": code}
