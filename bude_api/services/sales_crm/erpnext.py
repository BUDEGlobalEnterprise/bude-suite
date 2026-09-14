"""ERPNext Lead/Opportunity implementation of the CRM contract."""

from __future__ import annotations

from .provider import CrmProvider, ProviderConfig, _serial, normalize_permissions


class ErpnextCrmProvider(CrmProvider):
    config = ProviderConfig(
        key="erpnext",
        lead_doctype="Lead",
        deal_doctype="Opportunity",
        task_doctype="ToDo",
        note_doctype="Comment",
        call_doctype=None,
        lead_email_field="email_id",
        lead_phone_field="mobile_no",
        lead_organization_field="company_name",
        lead_owner_field="lead_owner",
        deal_owner_field="opportunity_owner",
        deal_stage_field="sales_stage",
    )

    def lead_fields(self) -> list[str]:
        return [
            "name", "lead_name", "first_name", "last_name", "company_name", "status",
            "email_id", "mobile_no", "phone", "source", "territory", "lead_owner",
            "owner", "job_title", "industry", "market_segment", "website", "notes",
            "modified", "creation",
            "do_not_contact",
        ]

    def deal_fields(self) -> list[str]:
        return [
            "name", "title", "opportunity_from", "party_name", "customer_name", "status",
            "sales_stage", "probability", "opportunity_amount", "currency", "expected_closing",
            "next_contact_date", "contact_email", "contact_mobile", "opportunity_owner", "owner",
            "source", "modified", "creation",
        ]

    def normalize_lead(self, row: dict) -> dict:
        title = row.get("lead_name") or " ".join(
            part for part in [row.get("first_name"), row.get("last_name")] if part
        ) or row.get("company_name") or row.get("name") or ""
        return {
            "provider": self.config.key,
            "kind": "lead",
            "name": row.get("name") or "",
            "title": title,
            "organization": row.get("company_name") or "",
            "status": row.get("status") or "Lead",
            "stage": row.get("status") or "Lead",
            "email": row.get("email_id") or "",
            "phone": row.get("mobile_no") or row.get("phone") or "",
            "source": row.get("source") or "",
            "territory": row.get("territory") or "",
            "owner": row.get("lead_owner") or row.get("owner") or "",
            "next_action": "",
            "do_not_contact": bool(row.get("do_not_contact")) or row.get("status") == "Do Not Contact",
            "modified": _serial(row.get("modified")),
            "created": _serial(row.get("creation")),
            "details": {key: value for key, value in row.items() if key not in {"name"}},
            "permissions": normalize_permissions(),
        }

    def normalize_deal(self, row: dict) -> dict:
        amount = float(row.get("opportunity_amount") or 0)
        probability = float(row.get("probability") or 0)
        return {
            "provider": self.config.key,
            "kind": "deal",
            "name": row.get("name") or "",
            "title": row.get("title") or row.get("customer_name") or row.get("party_name") or row.get("name") or "",
            "organization": row.get("customer_name") or row.get("party_name") or "",
            "status": row.get("status") or "Open",
            "stage": row.get("sales_stage") or row.get("status") or "Open",
            "owner": row.get("opportunity_owner") or row.get("owner") or "",
            "value": amount,
            "currency": row.get("currency") or "",
            "probability": probability,
            "weighted_value": round(amount * probability / 100, 2),
            "expected_close": _serial(row.get("expected_closing")),
            "next_action": _serial(row.get("next_contact_date")),
            "source": row.get("source") or "",
            "email": row.get("contact_email") or "",
            "phone": row.get("contact_mobile") or "",
            "modified": _serial(row.get("modified")),
            "created": _serial(row.get("creation")),
            "details": {key: value for key, value in row.items() if key not in {"name"}},
            "permissions": normalize_permissions(),
        }

    def lead_payload(self, payload: dict) -> dict:
        first = str(payload.get("first_name") or payload.get("title") or "").strip()
        last = str(payload.get("last_name") or "").strip()
        data = {
            "first_name": first,
            "last_name": last,
            "lead_name": " ".join(part for part in [first, last] if part),
            "company_name": payload.get("organization"),
            "email_id": payload.get("email"),
            "mobile_no": payload.get("phone"),
            "status": payload.get("status") or ("Do Not Contact" if payload.get("do_not_contact") else "Lead"),
            "do_not_contact": payload.get("do_not_contact"),
            "source": payload.get("source"),
            "territory": payload.get("territory"),
            "lead_owner": payload.get("owner"),
            "notes": payload.get("notes"),
            "job_title": payload.get("job_title"),
            "industry": payload.get("industry"),
            "website": payload.get("website"),
            "campaign_name": payload.get("campaign"),
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
            "sales_stage": payload.get("stage"),
            "status": payload.get("status"),
            "opportunity_owner": payload.get("owner"),
            "opportunity_amount": payload.get("value"),
            "probability": payload.get("probability"),
            "currency": payload.get("currency"),
            "expected_closing": payload.get("expected_close"),
            "next_contact_date": payload.get("next_action"),
            "source": payload.get("source"),
        }
        data.update(payload.get("custom_fields") or {})
        return self.writable_payload(self.config.deal_doctype, data)

    def convert_lead(self, lead: str, payload: dict) -> dict:
        lead_row = self.frappe.db.get_value(
            "Lead", lead, ["lead_name", "company_name", "email_id", "mobile_no"], as_dict=True
        ) or {}
        opportunity = {
            "doctype": "Opportunity",
            "opportunity_from": "Lead",
            "party_name": lead,
            "title": payload.get("title") or lead_row.get("company_name") or lead_row.get("lead_name") or lead,
            "opportunity_type": payload.get("opportunity_type") or "Sales",
            "sales_stage": payload.get("stage"),
            "opportunity_owner": payload.get("owner"),
            "opportunity_amount": payload.get("value"),
            "probability": payload.get("probability"),
            "currency": payload.get("currency"),
            "expected_closing": payload.get("expected_close"),
            "source": payload.get("source"),
            "items": _items(payload.get("products")),
        }
        opportunity = {key: value for key, value in opportunity.items() if value not in (None, "", [])}
        doc = self.frappe.get_doc(opportunity)
        doc.insert(ignore_permissions=False)
        return self.normalize_deal(_doc_dict(doc, self.deal_fields()))

    def quotation_payload(self, deal_doc, payload: dict) -> dict:
        source = _doc_dict(deal_doc, self.deal_fields())
        party_type = source.get("opportunity_from") or "Lead"
        party = source.get("party_name")
        return {
            "doctype": "Quotation",
            "quotation_to": party_type,
            "party_name": party,
            "opportunity": source.get("name"),
            "company": payload.get("company"),
            "currency": payload.get("currency") or source.get("currency"),
            "selling_price_list": payload.get("price_list"),
            "valid_till": payload.get("valid_till"),
            "items": _items(payload.get("items") or _doc_items(deal_doc)),
        }


def _items(values) -> list[dict]:
    result = []
    for row in values or []:
        if not isinstance(row, dict):
            row = row.as_dict() if hasattr(row, "as_dict") else vars(row)
        item_code = row.get("item_code") or row.get("product")
        if not item_code:
            continue
        item = {"item_code": item_code, "qty": float(row.get("qty") or row.get("quantity") or 1)}
        if row.get("rate") is not None:
            item["rate"] = float(row.get("rate") or 0)
        if row.get("discount_percentage") is not None:
            item["discount_percentage"] = float(row.get("discount_percentage") or 0)
        result.append(item)
    return result


def _doc_items(doc) -> list[dict]:
    return [row.as_dict() if hasattr(row, "as_dict") else vars(row) for row in getattr(doc, "items", [])]


def _doc_dict(doc, fields: list[str]) -> dict:
    if hasattr(doc, "as_dict"):
        return dict(doc.as_dict())
    return {field: getattr(doc, field, None) for field in fields}
