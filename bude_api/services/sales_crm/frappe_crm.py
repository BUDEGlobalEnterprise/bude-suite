"""Frappe CRM implementation of the normalized CRM provider."""

from __future__ import annotations

from .erpnext import _doc_dict, _items
from .provider import CrmProvider, ProviderConfig, _serial, normalize_permissions


class FrappeCrmProvider(CrmProvider):
    config = ProviderConfig(
        key="frappe_crm",
        lead_doctype="CRM Lead",
        deal_doctype="CRM Deal",
        task_doctype="CRM Task",
        note_doctype="FCRM Note",
        call_doctype="CRM Call Log",
        lead_email_field="email",
        lead_phone_field="mobile_no",
        lead_organization_field="organization",
        lead_owner_field="lead_owner",
        deal_owner_field="deal_owner",
        deal_stage_field="status",
    )

    def lead_fields(self) -> list[str]:
        return [
            "name", "lead_name", "first_name", "last_name", "organization", "status", "email",
            "mobile_no", "phone", "source", "territory", "lead_owner", "owner", "job_title",
            "industry", "website", "converted", "sla_status", "response_by", "modified", "creation",
            "do_not_contact",
        ]

    def deal_fields(self) -> list[str]:
        return [
            "name", "organization", "organization_name", "lead", "lead_name", "status", "deal_owner",
            "owner", "probability", "expected_deal_value", "deal_value", "currency", "expected_closure_date",
            "closed_date", "next_step", "email", "mobile_no", "source", "territory", "sla_status",
            "response_by", "lost_reason", "lost_notes", "modified", "creation",
        ]

    def normalize_lead(self, row: dict) -> dict:
        title = row.get("lead_name") or " ".join(
            part for part in [row.get("first_name"), row.get("last_name")] if part
        ) or row.get("organization") or row.get("name") or ""
        return {
            "provider": self.config.key,
            "kind": "lead",
            "name": row.get("name") or "",
            "title": title,
            "organization": row.get("organization") or "",
            "status": row.get("status") or "New",
            "stage": row.get("status") or "New",
            "email": row.get("email") or "",
            "phone": row.get("mobile_no") or row.get("phone") or "",
            "source": row.get("source") or "",
            "territory": row.get("territory") or "",
            "owner": row.get("lead_owner") or row.get("owner") or "",
            "next_action": _serial(row.get("response_by")),
            "sla_status": row.get("sla_status") or "",
            "do_not_contact": bool(row.get("do_not_contact")) or row.get("status") == "Do Not Contact",
            "modified": _serial(row.get("modified")),
            "created": _serial(row.get("creation")),
            "details": {key: value for key, value in row.items() if key != "name"},
            "permissions": normalize_permissions(),
        }

    def normalize_deal(self, row: dict) -> dict:
        amount = float(row.get("expected_deal_value") or row.get("deal_value") or 0)
        probability = float(row.get("probability") or 0)
        return {
            "provider": self.config.key,
            "kind": "deal",
            "name": row.get("name") or "",
            "title": row.get("organization_name") or row.get("organization") or row.get("lead_name") or row.get("name") or "",
            "organization": row.get("organization") or row.get("organization_name") or "",
            "status": row.get("status") or "Qualification",
            "stage": row.get("status") or "Qualification",
            "owner": row.get("deal_owner") or row.get("owner") or "",
            "value": amount,
            "currency": row.get("currency") or "",
            "probability": probability,
            "weighted_value": round(amount * probability / 100, 2),
            "expected_close": _serial(row.get("expected_closure_date")),
            "next_action": row.get("next_step") or "",
            "source": row.get("source") or "",
            "email": row.get("email") or "",
            "phone": row.get("mobile_no") or "",
            "sla_status": row.get("sla_status") or "",
            "modified": _serial(row.get("modified")),
            "created": _serial(row.get("creation")),
            "details": {key: value for key, value in row.items() if key != "name"},
            "permissions": normalize_permissions(),
        }

    def lead_payload(self, payload: dict) -> dict:
        first = str(payload.get("first_name") or payload.get("title") or "").strip()
        data = {
            "first_name": first,
            "last_name": payload.get("last_name"),
            "organization": payload.get("organization"),
            "email": payload.get("email"),
            "mobile_no": payload.get("phone"),
            "status": payload.get("status") or ("Do Not Contact" if payload.get("do_not_contact") else "New"),
            "do_not_contact": payload.get("do_not_contact"),
            "source": payload.get("source"),
            "territory": payload.get("territory"),
            "lead_owner": payload.get("owner"),
            "job_title": payload.get("job_title"),
            "industry": payload.get("industry"),
            "website": payload.get("website"),
            "campaign": payload.get("campaign"),
            "utm_source": payload.get("utm_source"),
            "utm_medium": payload.get("utm_medium"),
            "utm_campaign": payload.get("utm_campaign"),
            "external_id": payload.get("external_id"),
            "received_at": payload.get("received_at"),
        }
        data.update(payload.get("custom_fields") or {})
        return self.writable_payload(self.config.lead_doctype, data)

    def deal_payload(self, payload: dict) -> dict:
        data = {
            "status": payload.get("stage") or payload.get("status"),
            "deal_owner": payload.get("owner"),
            "expected_deal_value": payload.get("value"),
            "probability": payload.get("probability"),
            "currency": payload.get("currency"),
            "expected_closure_date": payload.get("expected_close"),
            "next_step": payload.get("next_action"),
            "source": payload.get("source"),
        }
        data.update(payload.get("custom_fields") or {})
        return self.writable_payload(self.config.deal_doctype, data)

    def convert_lead(self, lead: str, payload: dict) -> dict:
        doc = self.frappe.get_doc("CRM Lead", lead)
        deal_args = {
            "status": payload.get("stage") or "Qualification",
            "deal_owner": payload.get("owner"),
            "expected_deal_value": payload.get("value"),
            "probability": payload.get("probability"),
            "currency": payload.get("currency"),
            "expected_closure_date": payload.get("expected_close"),
            "next_step": payload.get("next_action"),
            "products": payload.get("products") or [],
        }
        deal_args = {key: value for key, value in deal_args.items() if value not in (None, "", [])}
        try:
            converter = self.frappe.get_attr("crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal")
            result = converter(
                lead=lead,
                deal=deal_args,
                existing_contact=payload.get("existing_contact"),
                existing_organization=payload.get("existing_organization"),
            )
        except (AttributeError, ImportError):
            # Older compatible CRM 1.x builds expose only the document method.
            result = doc.convert_to_deal(deal_args)
        deal = result if hasattr(result, "as_dict") else self.frappe.get_doc("CRM Deal", result)
        return self.normalize_deal(_doc_dict(deal, self.deal_fields()))

    def quotation_payload(self, deal_doc, payload: dict) -> dict:
        source = _doc_dict(deal_doc, self.deal_fields())
        products = payload.get("items") or getattr(deal_doc, "products", [])
        return {
            "doctype": "Quotation",
            "quotation_to": "CRM Deal",
            "party_name": source.get("name"),
            "crm_deal": source.get("name"),
            "company": payload.get("company"),
            "currency": payload.get("currency") or source.get("currency"),
            "selling_price_list": payload.get("price_list"),
            "valid_till": payload.get("valid_till"),
            "items": _items(products),
        }
