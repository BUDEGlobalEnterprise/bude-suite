"""Common CRM provider contract and normalization helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class ProviderConfig:
    key: str
    lead_doctype: str
    deal_doctype: str
    task_doctype: str
    note_doctype: str
    call_doctype: str | None
    lead_email_field: str
    lead_phone_field: str
    lead_organization_field: str
    lead_owner_field: str
    deal_owner_field: str
    deal_stage_field: str


class CrmProvider(ABC):
    """Small stable surface implemented by ERPNext and Frappe CRM."""

    config: ProviderConfig

    def __init__(self, frappe_module):
        self.frappe = frappe_module

    @abstractmethod
    def lead_fields(self) -> list[str]: ...

    @abstractmethod
    def deal_fields(self) -> list[str]: ...

    @abstractmethod
    def normalize_lead(self, row: dict) -> dict: ...

    @abstractmethod
    def normalize_deal(self, row: dict) -> dict: ...

    @abstractmethod
    def lead_payload(self, payload: dict) -> dict: ...

    @abstractmethod
    def deal_payload(self, payload: dict) -> dict: ...

    @abstractmethod
    def convert_lead(self, lead: str, payload: dict) -> dict: ...

    @abstractmethod
    def quotation_payload(self, deal_doc, payload: dict) -> dict: ...

    def existing_fields(self, doctype: str, fields: list[str]) -> list[str]:
        try:
            meta = self.frappe.get_meta(doctype)
            has_field = getattr(meta, "has_field", None)
            if callable(has_field):
                return [field for field in fields if field == "name" or has_field(field)]
        except Exception:
            pass
        return fields

    def writable_payload(self, doctype: str, payload: dict) -> dict:
        """Drop transport-only and unsupported fields without bypassing validation."""
        ignored = {
            "name",
            "provider",
            "kind",
            "modified",
            "base_modified",
            "client_request_id",
            "next_follow_up",
            "notes",
            "custom_fields",
        }
        allowed = set(self.existing_fields(doctype, list(payload)))
        result = {
            key: value
            for key, value in payload.items()
            if key not in ignored and key in allowed and value is not None
        }
        custom = payload.get("custom_fields")
        if isinstance(custom, dict):
            custom_allowed = set(self.existing_fields(doctype, list(custom)))
            result.update(
                {
                    key: value
                    for key, value in custom.items()
                    if key in custom_allowed and value is not None
                }
            )
        return result

    def normalize_task(self, row: dict) -> dict:
        due = row.get("due_date") or row.get("date") or ""
        return {
            "provider": self.config.key,
            "kind": "task",
            "name": row.get("name") or "",
            "title": row.get("title") or row.get("description") or "Follow up",
            "description": row.get("description") or "",
            "status": row.get("status") or "Open",
            "priority": row.get("priority") or "Medium",
            "assigned_to": row.get("assigned_to") or row.get("allocated_to") or "",
            "due_date": _serial(due),
            "reference_kind": _kind(row.get("reference_doctype")),
            "reference_name": row.get("reference_docname") or row.get("reference_name") or "",
            "modified": _serial(row.get("modified")),
        }

    def reference_doctype(self, kind: str) -> str:
        return self.config.lead_doctype if kind == "lead" else self.config.deal_doctype


def normalize_permissions(*, can_read=True, can_write=True, can_assign=False, can_delete=False):
    return {
        "read": bool(can_read),
        "write": bool(can_write),
        "assign": bool(can_assign),
        "delete": bool(can_delete),
    }


def normalized_ref(provider: str, kind: str, name: str) -> dict:
    return {"provider": provider, "kind": kind, "name": name}


def _serial(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, date | datetime):
        return value.isoformat()
    return str(value)


def _kind(doctype: Any) -> str:
    value = str(doctype or "").lower()
    if "lead" in value:
        return "lead"
    if "deal" in value or "opportunity" in value:
        return "deal"
    return ""
