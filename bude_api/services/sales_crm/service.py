"""Provider-neutral CRM application service.

The service deliberately writes only provider-native or standard Frappe/
ERPNext records.  It owns permission checks, normalization, optimistic
concurrency and durable request idempotency; provider classes only map fields.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta

from ...utils.pagination import parse_page
from ...utils.response import failure, success
from ..common.permissions import has_any_role, permission_denied, require_sales_role
from .erpnext import ErpnextCrmProvider, _doc_dict
from .frappe_crm import FrappeCrmProvider
from .provider import CrmProvider, _serial

SALES_MANAGER_ROLES = {"Sales Manager", "System Manager"}
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
FALSE_VALUES = {False, 0, "0", "false", "False", "no", "off"}


class SalesCrmService:
    def __init__(self, frappe_module):
        self.frappe = frappe_module

    # ---- capability and provider selection ---------------------------------

    def bootstrap(self) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        provider_or_error = self._provider()
        if isinstance(provider_or_error, dict):
            return provider_or_error
        provider = provider_or_error
        installed = self._installed_apps()
        return success(
            {
                "enabled": self._enabled(),
                "provider": provider.config.key,
                "provider_label": "Frappe CRM" if provider.config.key == "frappe_crm" else "ERPNext CRM",
                "available_providers": ["erpnext"] + (["frappe_crm"] if "crm" in installed else []),
                "roles": list(self._roles()),
                "is_manager": self._is_manager(),
                "capabilities": self._capabilities(provider, installed),
                "lead_statuses": self._statuses(provider, "lead"),
                "deal_stages": self._statuses(provider, "deal"),
                "sources": self._names("CRM Lead Source" if provider.config.key == "frappe_crm" else "Lead Source"),
                "territories": self._names("CRM Territory" if provider.config.key == "frappe_crm" else "Territory"),
                "loss_reasons": self._names("CRM Lost Reason" if provider.config.key == "frappe_crm" else "Opportunity Lost Reason"),
                "users": self._sales_users(),
                "lead_fields": self._form_fields(provider.config.lead_doctype),
                "deal_fields": self._form_fields(provider.config.deal_doctype),
                "connector_health": self._connector_health(provider, installed),
            }
        )

    # ---- leads --------------------------------------------------------------

    def list_leads(
        self,
        search: str | None = None,
        status: str | None = None,
        source: str | None = None,
        territory: str | None = None,
        assigned_to_me: bool = True,
        stale_days: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        page = parse_page(limit, offset, default_limit=DEFAULT_LIMIT, max_limit=MAX_LIMIT)
        if isinstance(page, dict):
            return page
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        filters: list = []
        if status:
            filters.append(["status", "=", status])
        if source:
            filters.append(["source", "=", source])
        if territory:
            filters.append(["territory", "=", territory])
        if assigned_to_me and not self._is_manager():
            filters.append([provider.config.lead_owner_field, "=", self._user()])
        elif assigned_to_me:
            filters.append([provider.config.lead_owner_field, "=", self._user()])
        if stale_days:
            filters.append(["modified", "<", self._days_ago(stale_days)])
        or_filters = []
        term = (search or "").strip()
        if term:
            for field in self._searchable_fields(
                provider.config.lead_doctype,
                ["lead_name", "first_name", provider.config.lead_organization_field, provider.config.lead_email_field, provider.config.lead_phone_field],
            ):
                or_filters.append([field, "like", f"%{term}%"])
        fields = provider.existing_fields(provider.config.lead_doctype, provider.lead_fields())
        rows = self.frappe.get_list(
            provider.config.lead_doctype,
            filters=filters,
            or_filters=or_filters or None,
            fields=fields,
            order_by="modified desc",
            limit_start=page.offset,
            limit_page_length=page.limit,
        )
        total = self._count(provider.config.lead_doctype, filters, or_filters)
        return success(
            {
                "provider": provider.config.key,
                "leads": [provider.normalize_lead(dict(row)) for row in rows],
                "total": total,
                "limit": page.limit,
                "offset": page.offset,
            }
        )

    def get_lead(self, lead: str) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        row = self._read_row(provider.config.lead_doctype, lead, provider.lead_fields())
        if row is None:
            return failure("Lead not found or not permitted.", code="NOT_FOUND")
        data = provider.normalize_lead(row)
        data["tasks"] = self._task_rows(provider, "lead", lead, limit=10)
        data["timeline"] = self._timeline_rows(provider, "lead", lead, limit=30)
        data["attachments"] = self._attachment_rows(provider, "lead", lead)
        data["duplicates"] = self._duplicate_rows(provider, data.get("email"), data.get("phone"), data.get("title"), data.get("organization"), exclude=lead)
        return success(data)

    def check_duplicates(
        self,
        email: str | None = None,
        phone: str | None = None,
        name: str | None = None,
        organization: str | None = None,
    ) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        rows = self._duplicate_rows(provider, email, phone, name, organization)
        return success({"duplicates": rows, "exact": any(row["match"] == "exact" for row in rows)})

    def merge_leads(
        self,
        source: str,
        target: str,
        payload: dict | str | None = None,
        client_request_id: str | None = None,
    ) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        if not self._is_manager():
            return permission_denied("Sales Manager access is required to merge leads.")
        source = str(source or "").strip()
        target = str(target or "").strip()
        if not source or not target or source == target:
            return failure("Choose two different leads to merge.", code="VALIDATION_LEADS")
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        source_row = self._read_row(provider.config.lead_doctype, source, provider.lead_fields())
        target_row = self._read_row(provider.config.lead_doctype, target, provider.lead_fields())
        if source_row is None or target_row is None:
            return failure("A lead was not found or is not permitted.", code="NOT_FOUND")
        requested = self._payload(payload or {})

        def action():
            target_doc = self.frappe.get_doc(provider.config.lead_doctype, target)
            field_map = {
                "title": "lead_name",
                "organization": provider.config.lead_organization_field,
                "email": provider.config.lead_email_field,
                "phone": provider.config.lead_phone_field,
                "source": "source",
                "territory": "territory",
                "owner": provider.config.lead_owner_field,
                "status": "status",
                "do_not_contact": "do_not_contact",
            }
            mapped = {
                field_map[key]: value
                for key, value in requested.items()
                if key in field_map and value is not None
            }
            custom_fields = requested.get("custom_fields")
            if isinstance(custom_fields, dict):
                mapped.update(custom_fields)
            mapped = provider.writable_payload(provider.config.lead_doctype, mapped)
            for field, value in mapped.items():
                setattr(target_doc, field, value)
            if mapped:
                target_doc.save()
            self.frappe.rename_doc(
                provider.config.lead_doctype,
                source,
                target,
                merge=True,
            )
            self._insert_note(
                provider,
                "lead",
                target,
                f"Merged duplicate lead {source} into this record by {self._user()}.",
                title="Duplicate merged",
            )
            row = self._read_row(provider.config.lead_doctype, target, provider.lead_fields())
            return {"lead": provider.normalize_lead(row or target_row), "merged": source}

        return self._idempotent("merge_leads", client_request_id, action)

    def conversion_options(self, lead: str) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        row = self._read_row(provider.config.lead_doctype, lead, provider.lead_fields())
        if not row:
            return failure("Lead not found or not permitted.", code="NOT_FOUND")
        normalized = provider.normalize_lead(row)
        contact_names = set()
        if normalized.get("email"):
            contact_names.update(
                item.get("parent")
                for item in self._safe_list(
                    "Contact Email",
                    ["parent"],
                    filters=[["email_id", "=", normalized["email"]]],
                    limit=20,
                )
                if item.get("parent")
            )
        if normalized.get("phone"):
            phone_digits = _phone(normalized["phone"])
            contact_names.update(
                item.get("parent")
                for item in self._safe_list(
                    "Contact Phone",
                    ["parent"],
                    filters=[["phone", "like", f"%{phone_digits[-10:]}%"]],
                    limit=20,
                )
                if item.get("parent")
            )
        contacts = self._parent_documents(
            "Contact", sorted(contact_names), ["name", "full_name", "company_name", "email_id", "mobile_no"]
        )
        organization_name = str(normalized.get("organization") or "").strip()
        organizations = []
        if provider.config.key == "frappe_crm" and organization_name:
            organizations = self._safe_list(
                "CRM Organization",
                ["name", "organization_name", "website", "territory"],
                filters=[["organization_name", "like", f"%{organization_name}%"]],
                limit=20,
            )
        customers = []
        if organization_name:
            customers = self._safe_list(
                "Customer",
                ["name", "customer_name", "customer_type", "territory"],
                filters=[["customer_name", "like", f"%{organization_name}%"]],
                limit=20,
            )
        return success(
            {
                "lead": normalized,
                "contacts": contacts,
                "organizations": organizations,
                "customers": customers,
            }
        )

    def create_lead(self, payload: dict | str, client_request_id: str | None = None) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        data = self._payload(payload)
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        first_name = str(data.get("first_name") or data.get("title") or "").strip()
        if not first_name:
            return failure("first_name is required.", code="VALIDATION_REQUIRED")
        duplicate_rows = self._duplicate_rows(
            provider, data.get("email"), data.get("phone"), first_name, data.get("organization")
        )
        exact = next((row for row in duplicate_rows if row["match"] == "exact"), None)
        if exact and not data.get("allow_duplicate"):
            return failure("A lead with this email or phone already exists.", code="DUPLICATE", data={"duplicate": exact})
        if exact and data.get("allow_duplicate") and not self._is_manager():
            return permission_denied("Only a Sales Manager can override an exact lead duplicate.")

        def action():
            values = provider.lead_payload(data)
            values["doctype"] = provider.config.lead_doctype
            doc = self.frappe.get_doc(values)
            doc.insert(ignore_permissions=False)
            record = provider.normalize_lead(_doc_dict(doc, provider.lead_fields()))
            if data.get("notes"):
                self._insert_note(provider, "lead", doc.name, str(data["notes"]))
            if data.get("next_follow_up"):
                self._insert_task(
                    provider,
                    {
                        "title": f"Follow up with {record['title']}",
                        "description": str(data.get("notes") or ""),
                        "assigned_to": data.get("owner") or self._user(),
                        "due_date": data["next_follow_up"],
                        "reference_kind": "lead",
                        "reference_name": doc.name,
                        "priority": "Medium",
                    },
                )
            return {"lead": record, "queued": False}

        return self._idempotent("create_lead", client_request_id or data.get("client_request_id"), action)

    def update_lead(
        self,
        lead: str,
        payload: dict | str,
        base_modified: str | None = None,
        client_request_id: str | None = None,
    ) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        data = self._payload(payload)
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        conflict = self._conflict(provider.config.lead_doctype, lead, base_modified or data.get("base_modified"))
        if conflict:
            return conflict

        def action():
            doc = self._writable_doc(provider.config.lead_doctype, lead)
            if isinstance(doc, dict):
                return doc
            for key, value in provider.lead_payload(data).items():
                setattr(doc, key, value)
            doc.save(ignore_permissions=False)
            return {"lead": provider.normalize_lead(_doc_dict(doc, provider.lead_fields()))}

        return self._idempotent("update_lead", client_request_id or data.get("client_request_id"), action)

    def convert_lead(self, lead: str, payload: dict | str, client_request_id: str | None = None) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        data = self._payload(payload)
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        conflict = self._conflict(provider.config.lead_doctype, lead, data.get("base_modified"))
        if conflict:
            return conflict

        def action():
            if not self._has_permission(provider.config.lead_doctype, "write", lead):
                return permission_denied("You cannot convert this lead.")
            deal = provider.convert_lead(lead, data)
            return {"deal": deal, "lead": lead}

        return self._idempotent("convert_lead", client_request_id or data.get("client_request_id"), action)

    # ---- deals --------------------------------------------------------------

    def list_deals(
        self,
        search: str | None = None,
        stage: str | None = None,
        assigned_to_me: bool = True,
        expected_from: str | None = None,
        expected_to: str | None = None,
        stale_days: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        page = parse_page(limit, offset, default_limit=DEFAULT_LIMIT, max_limit=MAX_LIMIT)
        if isinstance(page, dict):
            return page
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        filters: list = []
        if stage:
            filters.append([provider.config.deal_stage_field, "=", stage])
        if assigned_to_me:
            filters.append([provider.config.deal_owner_field, "=", self._user()])
        close_field = "expected_closure_date" if provider.config.key == "frappe_crm" else "expected_closing"
        if expected_from:
            filters.append([close_field, ">=", expected_from])
        if expected_to:
            filters.append([close_field, "<=", expected_to])
        if stale_days:
            filters.append(["modified", "<", self._days_ago(stale_days)])
        term = (search or "").strip()
        or_filters = []
        if term:
            candidates = ["title", "organization", "organization_name", "party_name", "customer_name", "lead_name", "email"]
            for field in self._searchable_fields(provider.config.deal_doctype, candidates):
                or_filters.append([field, "like", f"%{term}%"])
        rows = self.frappe.get_list(
            provider.config.deal_doctype,
            filters=filters,
            or_filters=or_filters or None,
            fields=provider.existing_fields(provider.config.deal_doctype, provider.deal_fields()),
            order_by="modified desc",
            limit_start=page.offset,
            limit_page_length=page.limit,
        )
        normalized = [provider.normalize_deal(dict(row)) for row in rows]
        return success(
            {
                "provider": provider.config.key,
                "deals": normalized,
                "total": self._count(provider.config.deal_doctype, filters, or_filters),
                "value": round(sum(row["value"] for row in normalized), 2),
                "weighted_value": round(sum(row["weighted_value"] for row in normalized), 2),
                "limit": page.limit,
                "offset": page.offset,
            }
        )

    def get_deal(self, deal: str) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        row = self._read_row(provider.config.deal_doctype, deal, provider.deal_fields())
        if row is None:
            return failure("Deal not found or not permitted.", code="NOT_FOUND")
        data = provider.normalize_deal(row)
        data["tasks"] = self._task_rows(provider, "deal", deal, limit=10)
        data["timeline"] = self._timeline_rows(provider, "deal", deal, limit=30)
        data["products"] = self._child_rows(provider, deal)
        data["documents"] = self._documents(provider, deal, row)
        data["attachments"] = self._attachment_rows(provider, "deal", deal)
        return success(data)

    def create_deal(self, payload: dict | str, client_request_id: str | None = None) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        data = self._payload(payload)
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider

        def action():
            values = provider.deal_payload(data)
            values["doctype"] = provider.config.deal_doctype
            if provider.config.key == "erpnext":
                values.update(
                    {
                        "opportunity_from": data.get("party_type") or "Customer",
                        "party_name": data.get("party"),
                        "opportunity_type": data.get("opportunity_type") or "Sales",
                        "title": data.get("title") or data.get("organization"),
                        "items": data.get("products") or [],
                    }
                )
            else:
                values.update(
                    {
                        "organization": data.get("organization"),
                        "first_name": data.get("first_name"),
                        "email": data.get("email"),
                        "mobile_no": data.get("phone"),
                        "products": data.get("products") or [],
                    }
                )
            values = {key: value for key, value in values.items() if value not in (None, "", [])}
            doc = self.frappe.get_doc(values)
            doc.insert(ignore_permissions=False)
            return {"deal": provider.normalize_deal(_doc_dict(doc, provider.deal_fields()))}

        return self._idempotent("create_deal", client_request_id or data.get("client_request_id"), action)

    def update_deal(
        self,
        deal: str,
        payload: dict | str,
        base_modified: str | None = None,
        client_request_id: str | None = None,
    ) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        data = self._payload(payload)
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        conflict = self._conflict(provider.config.deal_doctype, deal, base_modified or data.get("base_modified"))
        if conflict:
            return conflict

        def action():
            doc = self._writable_doc(provider.config.deal_doctype, deal)
            if isinstance(doc, dict):
                return doc
            for key, value in provider.deal_payload(data).items():
                setattr(doc, key, value)
            if data.get("lost_reason"):
                doc.lost_reason = data["lost_reason"]
                doc.lost_notes = data.get("lost_notes") or ""
            doc.save(ignore_permissions=False)
            return {"deal": provider.normalize_deal(_doc_dict(doc, provider.deal_fields()))}

        return self._idempotent("update_deal", client_request_id or data.get("client_request_id"), action)

    def close_deal(
        self,
        deal: str,
        outcome: str,
        reason: str | None = None,
        notes: str | None = None,
        client_request_id: str | None = None,
        customer: str | None = None,
        create_customer: bool = False,
    ) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        outcome = (outcome or "").strip().lower()
        if outcome not in {"won", "lost"}:
            return failure("outcome must be won or lost.", code="VALIDATION_OUTCOME")
        if outcome == "lost" and not (reason or "").strip():
            return failure("A loss reason is required.", code="VALIDATION_LOSS_REASON")
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        linked_customer = None
        if outcome == "won":
            linked_customer = self._ensure_customer(provider, deal, customer, create_customer)
            if isinstance(linked_customer, dict):
                return linked_customer
        stage = ("Won" if outcome == "won" else "Lost") if provider.config.key == "frappe_crm" else ("Converted" if outcome == "won" else "Lost")
        result = self.update_deal(
            deal,
            {"stage": stage, "status": stage, "lost_reason": reason, "lost_notes": notes},
            client_request_id=client_request_id,
        )
        if result.get("ok") and linked_customer:
            result["data"]["customer"] = linked_customer
        return result

    def create_quotation(self, deal: str, payload: dict | str, client_request_id: str | None = None) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        data = self._payload(payload)
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider

        def action():
            source = self._writable_doc(provider.config.deal_doctype, deal, permission="read")
            if isinstance(source, dict):
                return source
            values = provider.quotation_payload(source, data)
            values = {key: value for key, value in values.items() if value not in (None, "", [])}
            if not values.get("items"):
                return failure("At least one product is required to create a quotation.", code="VALIDATION_ITEMS")
            doc = self.frappe.get_doc(values)
            doc.insert(ignore_permissions=False)
            return {"quotation": {"name": doc.name, "docstatus": getattr(doc, "docstatus", 0), "deal": deal}}

        return self._idempotent("create_quotation", client_request_id or data.get("client_request_id"), action)

    def create_sales_order(self, quotation: str, client_request_id: str | None = None) -> dict:
        """Use ERPNext's standard mapper so quotation/item references survive."""
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        if not self._has_permission("Quotation", "read", quotation):
            return permission_denied("You do not have permission to read this quotation.")
        if not self._has_permission("Sales Order", "create"):
            return permission_denied("You do not have permission to create Sales Orders.")
        existing = self._linked_parents("Sales Order Item", "prevdoc_docname", [quotation])
        if existing:
            return success(
                {
                    "sales_order": {
                        "name": existing[0],
                        "quotation": quotation,
                        "existing": True,
                    }
                },
                message="This quotation already has a linked Sales Order.",
            )

        def action():
            mapper = self.frappe.get_attr("erpnext.selling.doctype.quotation.quotation.make_sales_order")
            order = mapper(quotation)
            order.insert(ignore_permissions=False)
            return {
                "sales_order": {
                    "name": order.name,
                    "docstatus": getattr(order, "docstatus", 0),
                    "quotation": quotation,
                }
            }

        return self._idempotent("create_sales_order", client_request_id, action)

    # ---- tasks and activity -------------------------------------------------

    def list_tasks(
        self,
        status: str | None = None,
        assigned_to_me: bool = True,
        overdue_only: bool = False,
        reference_kind: str | None = None,
        reference_name: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        page = parse_page(limit, offset, default_limit=DEFAULT_LIMIT, max_limit=MAX_LIMIT)
        if isinstance(page, dict):
            return page
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        filters = []
        if status:
            filters.append(["status", "=", status])
        elif provider.config.key == "erpnext":
            filters.append(["status", "!=", "Closed"])
        else:
            filters.append(["status", "not in", ["Done", "Cancelled"]])
        assigned_field = "assigned_to" if provider.config.key == "frappe_crm" else "allocated_to"
        due_field = "due_date" if provider.config.key == "frappe_crm" else "date"
        if assigned_to_me:
            filters.append([assigned_field, "=", self._user()])
        if overdue_only:
            filters.append([due_field, "<", self._today()])
        if reference_kind and reference_name:
            filters.extend(
                [
                    ["reference_doctype" if provider.config.key == "frappe_crm" else "reference_type", "=", provider.reference_doctype(reference_kind)],
                    ["reference_docname" if provider.config.key == "frappe_crm" else "reference_name", "=", reference_name],
                ]
            )
        fields = [
            "name", "title", "description", "status", "priority", assigned_field, due_field,
            "reference_doctype" if provider.config.key == "frappe_crm" else "reference_type",
            "reference_docname" if provider.config.key == "frappe_crm" else "reference_name", "modified",
        ]
        rows = self.frappe.get_list(
            provider.config.task_doctype,
            filters=filters,
            fields=provider.existing_fields(provider.config.task_doctype, fields),
            order_by=f"{due_field} asc",
            limit_start=page.offset,
            limit_page_length=page.limit,
        )
        return success(
            {
                "tasks": [provider.normalize_task(dict(row)) for row in rows],
                "total": self._count(provider.config.task_doctype, filters, []),
                "limit": page.limit,
                "offset": page.offset,
            }
        )

    def create_task(self, payload: dict | str, client_request_id: str | None = None) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        data = self._payload(payload)
        if not str(data.get("title") or "").strip():
            return failure("title is required.", code="VALIDATION_REQUIRED")
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        return self._idempotent(
            "create_task",
            client_request_id or data.get("client_request_id"),
            lambda: {"task": self._insert_task(provider, data)},
        )

    def update_task(
        self,
        task: str,
        payload: dict | str,
        base_modified: str | None = None,
        client_request_id: str | None = None,
    ) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        data = self._payload(payload)
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        conflict = self._conflict(provider.config.task_doctype, task, base_modified or data.get("base_modified"))
        if conflict:
            return conflict

        def action():
            doc = self._writable_doc(provider.config.task_doctype, task)
            if isinstance(doc, dict):
                return doc
            mapping = {
                "title": "title" if provider.config.key == "frappe_crm" else "description",
                "description": "description",
                "status": "status",
                "priority": "priority",
                "assigned_to": "assigned_to" if provider.config.key == "frappe_crm" else "allocated_to",
                "due_date": "due_date" if provider.config.key == "frappe_crm" else "date",
            }
            for source, target in mapping.items():
                if source in data:
                    setattr(doc, target, data[source])
            doc.save(ignore_permissions=False)
            return {"task": provider.normalize_task(_doc_dict(doc, list(mapping.values()) + ["name", "modified"]))}

        return self._idempotent("update_task", client_request_id or data.get("client_request_id"), action)

    def timeline(self, kind: str, name: str, limit: int = 50) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        if kind not in {"lead", "deal"}:
            return failure("kind must be lead or deal.", code="VALIDATION_KIND")
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        return success({"timeline": self._timeline_rows(provider, kind, name, min(max(int(limit), 1), 100))})

    def add_note(self, kind: str, name: str, content: str, title: str | None = None, client_request_id: str | None = None) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        if kind not in {"lead", "deal"} or not (content or "").strip():
            return failure("kind and content are required.", code="VALIDATION_REQUIRED")
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        return self._idempotent(
            "add_note", client_request_id, lambda: {"activity": self._insert_note(provider, kind, name, content, title)}
        )

    def upload_attachment(
        self,
        kind: str,
        name: str,
        file_name: str,
        content_base64: str,
        client_request_id: str | None = None,
    ) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        if kind not in {"lead", "deal"}:
            return failure("kind must be lead or deal.", code="VALIDATION_KIND")
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        doctype = provider.reference_doctype(kind)
        if not self._has_permission(doctype, "write", name):
            return permission_denied("You cannot attach files to this record.")
        safe_name = re.split(r"[\\/]", str(file_name or ""))[-1].strip()
        extension = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
        allowed = {"pdf", "png", "jpg", "jpeg", "webp", "heic", "txt", "csv", "doc", "docx", "xls", "xlsx"}
        if not safe_name or extension not in allowed:
            return failure("This attachment type is not supported.", code="VALIDATION_FILE_TYPE")
        try:
            content = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError, TypeError):
            return failure("Attachment content is invalid.", code="VALIDATION_FILE")
        if not content or len(content) > 8 * 1024 * 1024:
            return failure("Attachments must be between 1 byte and 8 MB.", code="VALIDATION_FILE_SIZE")

        def action():
            save_file = self.frappe.get_attr("frappe.utils.file_manager.save_file")
            file_doc = save_file(safe_name, content, doctype, name, is_private=1)
            return {
                "attachment": {
                    "name": file_doc.name,
                    "file_name": getattr(file_doc, "file_name", safe_name),
                    "file_url": getattr(file_doc, "file_url", ""),
                    "is_private": True,
                }
            }

        return self._idempotent("upload_attachment", client_request_id, action)

    def delete_attachment(self, kind: str, name: str, attachment: str) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        if kind not in {"lead", "deal"}:
            return failure("kind must be lead or deal.", code="VALIDATION_KIND")
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        doctype = provider.reference_doctype(kind)
        if not self._has_permission(doctype, "write", name):
            return permission_denied("You cannot remove files from this record.")
        rows = self._safe_list(
            "File",
            ["name"],
            filters=[
                ["name", "=", attachment],
                ["attached_to_doctype", "=", doctype],
                ["attached_to_name", "=", name],
            ],
            limit=1,
        )
        if not rows:
            return failure("Attachment not found.", code="NOT_FOUND")
        try:
            self.frappe.get_doc("File", attachment).delete(ignore_permissions=False)
        except Exception as exc:
            return self._exception(exc)
        return success({"deleted": attachment})

    def log_activity(self, payload: dict | str, client_request_id: str | None = None) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        data = self._payload(payload)
        kind = data.get("reference_kind")
        name = data.get("reference_name")
        activity_type = str(data.get("type") or "note").lower()
        if kind not in {"lead", "deal"} or not name:
            return failure("A lead or deal reference is required.", code="VALIDATION_REFERENCE")
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider

        def action():
            reference_doctype = provider.reference_doctype(kind)
            if activity_type == "note":
                return {"activity": self._insert_note(provider, kind, name, str(data.get("notes") or data.get("content") or ""), data.get("title"))}
            if activity_type == "call" and provider.config.call_doctype:
                values = {
                    "doctype": provider.config.call_doctype,
                    "type": data.get("direction") or "Outgoing",
                    "status": data.get("status") or "Completed",
                    "from": data.get("from"),
                    "to": data.get("to") or data.get("phone"),
                    "duration": data.get("duration") or 0,
                    "start_time": data.get("started_at") or self._now(),
                    "reference_doctype": reference_doctype,
                    "reference_docname": name,
                }
            else:
                values = {
                    "doctype": "Event",
                    "subject": data.get("title") or f"{activity_type.title()} - {name}",
                    "event_type": "Private",
                    "event_category": "Call" if activity_type == "call" else "Meeting",
                    "description": data.get("notes") or "",
                    "starts_on": data.get("started_at") or self._now(),
                    "ends_on": data.get("ended_at"),
                    "event_participants": [{"reference_doctype": reference_doctype, "reference_docname": name}],
                }
            values = {key: value for key, value in values.items() if value not in (None, "")}
            doc = self.frappe.get_doc(values)
            doc.insert(ignore_permissions=False)
            if data.get("next_follow_up"):
                self._insert_task(
                    provider,
                    {
                        "title": data.get("next_step") or f"Follow up after {activity_type}",
                        "assigned_to": data.get("assigned_to") or self._user(),
                        "due_date": data["next_follow_up"],
                        "reference_kind": kind,
                        "reference_name": name,
                        "priority": data.get("priority") or "Medium",
                    },
                )
            return {"activity": {"name": doc.name, "type": activity_type, "created": self._now()}}

        return self._idempotent("log_activity", client_request_id or data.get("client_request_id"), action)

    def send_email(
        self,
        kind: str,
        name: str,
        recipients: str | list,
        subject: str,
        content: str,
        client_request_id: str | None = None,
    ) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        if kind not in {"lead", "deal"}:
            return failure("kind must be lead or deal.", code="VALIDATION_KIND")
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        doctype = provider.reference_doctype(kind)
        fields = provider.lead_fields() if kind == "lead" else provider.deal_fields()
        row = self._read_row(doctype, name, fields)
        if not row:
            return failure("Record not found or not permitted.", code="NOT_FOUND")
        normalized = provider.normalize_lead(row) if kind == "lead" else provider.normalize_deal(row)
        if normalized.get("do_not_contact"):
            return failure("Outbound messages are blocked by Do Not Contact.", code="DO_NOT_CONTACT")
        recipient_list = recipients if isinstance(recipients, list) else [part.strip() for part in str(recipients or "").split(",")]
        recipient_list = [item for item in recipient_list if item]
        if not recipient_list or not str(subject or "").strip() or not str(content or "").strip():
            return failure("Recipient, subject, and message are required.", code="VALIDATION_REQUIRED")

        def action():
            self.frappe.sendmail(
                recipients=recipient_list,
                subject=str(subject).strip(),
                message=str(content).strip(),
                reference_doctype=doctype,
                reference_name=name,
                now=True,
            )
            return {"sent": True, "recipients": recipient_list, "subject": str(subject).strip()}

        return self._idempotent("send_email", client_request_id, action)

    # ---- intake and analytics ----------------------------------------------

    def capture_intake(
        self,
        channel: str,
        payload: dict | str,
        timestamp: str,
        signature: str,
        external_id: str | None = None,
    ) -> dict:
        data = self._payload(payload)
        raw = json.dumps(data, sort_keys=True, separators=(",", ":"))
        if len(raw.encode("utf-8")) > 32768:
            return failure("Payload is too large.", code="PAYLOAD_TOO_LARGE")
        secret = self._conf_string("bude_sales_intake_secret")
        if not secret:
            return failure("Lead intake is not configured.", code="INTAKE_NOT_CONFIGURED")
        try:
            sent_at = int(timestamp)
        except (TypeError, ValueError):
            return failure("Invalid timestamp.", code="SIGNATURE_INVALID")
        if abs(int(time.time()) - sent_at) > 300:
            return failure("Request timestamp expired.", code="SIGNATURE_EXPIRED")
        expected = hmac.new(secret.encode(), f"{timestamp}.{raw}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(signature or "")):
            return failure("Invalid signature.", code="SIGNATURE_INVALID")
        limited = self._rate_limit(channel)
        if limited:
            return limited
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        data["source"] = data.get("source") or channel.replace("_", " ").title()
        data["owner"] = data.get("owner") or self._default_sales_owner()
        request_id = external_id or data.get("external_id") or hashlib.sha256(f"{channel}:{raw}".encode()).hexdigest()
        data["external_id"] = external_id or data.get("external_id")
        data["received_at"] = data.get("received_at") or self._now()
        data["channel"] = channel
        duplicates = self._duplicate_rows(provider, data.get("email"), data.get("phone"), data.get("first_name") or data.get("name"), data.get("organization"))
        exact = next((row for row in duplicates if row["match"] == "exact"), None)
        if exact:
            return success({"lead": exact["lead"], "created": False, "matched": True})
        data["first_name"] = data.get("first_name") or data.get("name")
        def action():
            values = provider.lead_payload(data)
            values["doctype"] = provider.config.lead_doctype
            doc = self.frappe.get_doc(values)
            # This is the only permission bypass in the CRM service. It is
            # reached only after the timestamp, HMAC, payload-size and rate
            # limit checks above, allowing a Guest webhook to create a lead
            # without granting Guest general Lead permissions.
            doc.insert(ignore_permissions=True)
            record = provider.normalize_lead(_doc_dict(doc, provider.lead_fields()))
            if data.get("notes"):
                self._insert_note(provider, "lead", doc.name, str(data["notes"]), ignore_permissions=True)
            attribution = [
                ("Channel", data.get("channel")),
                ("External ID", data.get("external_id")),
                ("Campaign", data.get("campaign")),
                ("UTM source", data.get("utm_source")),
                ("UTM medium", data.get("utm_medium")),
                ("UTM campaign", data.get("utm_campaign")),
                ("Received", data.get("received_at")),
            ]
            details = "; ".join(f"{label}: {value}" for label, value in attribution if value)
            if details:
                self._insert_note(
                    provider,
                    "lead",
                    doc.name,
                    details,
                    title="Lead attribution",
                    ignore_permissions=True,
                )
            if data.get("next_follow_up"):
                self._insert_task(
                    provider,
                    {
                        "title": f"Follow up with {record['title']}",
                        "description": str(data.get("notes") or ""),
                        "assigned_to": data.get("owner") or self._default_sales_owner(),
                        "due_date": data["next_follow_up"],
                        "reference_kind": "lead",
                        "reference_name": doc.name,
                        "priority": "Medium",
                    },
                    ignore_permissions=True,
                )
            return {"lead": record, "queued": False}

        result = self._idempotent(
            "capture_intake",
            f"intake:{channel}:{request_id}",
            action,
            ignore_permissions=True,
        )
        if result.get("ok"):
            replayed = result.get("message") == "Request already completed."
            result["data"]["created"] = not replayed
            result["data"]["matched"] = replayed
            result["data"]["channel"] = channel
        return result

    def analytics(self, scope: str = "mine") -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        provider = self._provider_or_return()
        if isinstance(provider, dict):
            return provider
        mine = scope != "team" or not self._is_manager()
        lead_filters = [[provider.config.lead_owner_field, "=", self._user()]] if mine else []
        deal_filters = [[provider.config.deal_owner_field, "=", self._user()]] if mine else []
        task_assignee = "assigned_to" if provider.config.key == "frappe_crm" else "allocated_to"
        task_due = "due_date" if provider.config.key == "frappe_crm" else "date"
        task_filters = [[task_assignee, "=", self._user()], [task_due, "<", self._today()]]
        open_task_status = ["status", "not in", ["Done", "Cancelled"]] if provider.config.key == "frappe_crm" else ["status", "!=", "Closed"]
        task_filters.append(open_task_status)
        new_status = "New" if provider.config.key == "frappe_crm" else "Lead"
        lead_new_filters = [*lead_filters, ["status", "=", new_status]]
        stale_lead_filters = [*lead_filters, ["modified", "<", self._days_ago(7)]]
        stale_deal_filters = [*deal_filters, ["modified", "<", self._days_ago(14)]]
        deals = self.frappe.get_list(
            provider.config.deal_doctype,
            filters=deal_filters,
            fields=provider.existing_fields(provider.config.deal_doctype, provider.deal_fields()),
            limit_page_length=5000,
        )
        normalized = [provider.normalize_deal(dict(row)) for row in deals]
        leads = self.frappe.get_list(
            provider.config.lead_doctype,
            filters=lead_filters,
            fields=provider.existing_fields(provider.config.lead_doctype, provider.lead_fields()),
            limit_page_length=5000,
        )
        normalized_leads = [provider.normalize_lead(dict(row)) for row in leads]
        by_stage: dict[str, dict] = {}
        by_owner: dict[str, dict] = {}
        by_source: dict[str, dict] = {}
        for row in normalized:
            bucket = by_stage.setdefault(row["stage"], {"stage": row["stage"], "count": 0, "value": 0.0, "weighted_value": 0.0})
            bucket["count"] += 1
            bucket["value"] += row["value"]
            bucket["weighted_value"] += row["weighted_value"]
            owner = row.get("owner") or "Unassigned"
            owner_bucket = by_owner.setdefault(owner, {"owner": owner, "count": 0, "value": 0.0, "weighted_value": 0.0})
            owner_bucket["count"] += 1
            owner_bucket["value"] += row["value"]
            owner_bucket["weighted_value"] += row["weighted_value"]
        for row in normalized_leads:
            source = row.get("source") or "Unspecified"
            source_bucket = by_source.setdefault(source, {"source": source, "count": 0, "converted": 0})
            source_bucket["count"] += 1
            if str(row.get("status") or "").lower() in {"converted", "opportunity", "quotation"}:
                source_bucket["converted"] += 1
        loss_reasons: dict[str, int] = {}
        for row in normalized:
            reason = str((row.get("details") or {}).get("lost_reason") or "").strip()
            if reason:
                loss_reasons[reason] = loss_reasons.get(reason, 0) + 1
        return success(
            {
                "scope": "mine" if mine else "team",
                "new_leads": self._count(provider.config.lead_doctype, lead_new_filters, []),
                "stale_leads": self._count(provider.config.lead_doctype, stale_lead_filters, []),
                "stale_deals": self._count(provider.config.deal_doctype, stale_deal_filters, []),
                "overdue_tasks": self._count(provider.config.task_doctype, task_filters, []),
                "pipeline_count": len(normalized),
                "pipeline_value": round(sum(row["value"] for row in normalized), 2),
                "weighted_value": round(sum(row["weighted_value"] for row in normalized), 2),
                "by_stage": sorted(by_stage.values(), key=lambda row: row["stage"]),
                "by_owner": sorted(by_owner.values(), key=lambda row: row["owner"]),
                "by_source": sorted(by_source.values(), key=lambda row: row["source"]),
                "loss_reasons": [{"reason": key, "count": value} for key, value in sorted(loss_reasons.items())],
                "sla_at_risk": sum(
                    1
                    for row in normalized_leads
                    if str((row.get("details") or {}).get("sla_status") or "").lower()
                    in {"failed", "breached", "at risk"}
                ),
            }
        )

    def bulk_update(self, kind: str, names: list | str, payload: dict | str) -> dict:
        denied = require_sales_role(self.frappe)
        if denied:
            return denied
        if not self._is_manager():
            return permission_denied("Sales Manager access is required for bulk changes.")
        if kind not in {"lead", "deal"}:
            return failure("kind must be lead or deal.", code="VALIDATION_KIND")
        if isinstance(names, str):
            try:
                names = json.loads(names)
            except ValueError:
                names = [names]
        records = [str(name) for name in (names or []) if str(name).strip()][:100]
        values = self._payload(payload)
        updated = []
        failed = []
        for name in records:
            result = self.update_lead(name, values) if kind == "lead" else self.update_deal(name, values)
            if result.get("ok"):
                updated.append(name)
            else:
                failed.append({"name": name, "code": result.get("code"), "message": result.get("message")})
        return success({"updated": updated, "failed": failed})

    # ---- internal -----------------------------------------------------------

    def _provider(self) -> CrmProvider | dict:
        configured = self._conf_string("bude_sales_crm_provider") or "erpnext"
        if configured not in {"erpnext", "frappe_crm"}:
            return failure("bude_sales_crm_provider must be erpnext or frappe_crm.", code="CRM_PROVIDER_CONFIG")
        if configured == "frappe_crm":
            if "crm" not in self._installed_apps() or not self._doctype_exists("CRM Lead"):
                return failure("Frappe CRM is selected but the crm app is not installed on this site.", code="CRM_PROVIDER_UNAVAILABLE")
            return FrappeCrmProvider(self.frappe)
        return ErpnextCrmProvider(self.frappe)

    def _provider_or_return(self):
        if not self._enabled():
            return failure("Bude Sales CRM is disabled on this site.", code="CRM_DISABLED")
        return self._provider()

    def _enabled(self) -> bool:
        try:
            value = self.frappe.conf.get("bude_sales_crm_enabled")
        except Exception:
            return False
        if value is None or not isinstance(value, str | int | bool):
            return False
        return value not in FALSE_VALUES

    def _capabilities(self, provider: CrmProvider, installed: set[str]) -> dict:
        return {
            "leads": True,
            "deals": True,
            "tasks": True,
            "notes": True,
            "calls": provider.config.call_doctype is not None,
            "email": self._doctype_exists("Communication"),
            "whatsapp": "frappe_whatsapp" in installed,
            "meta_intake": provider.config.key == "frappe_crm" or bool(self._conf_string("bude_meta_access_token")),
            "public_forms": self._doctype_exists("Web Form"),
            "data_import": self._doctype_exists("Data Import"),
            "forecasting": True,
            "sla": provider.config.key == "frappe_crm",
            "offline_capture": True,
            "quotation_handoff": self._doctype_exists("Quotation"),
        }

    def _statuses(self, provider: CrmProvider, kind: str) -> list[dict]:
        if provider.config.key == "frappe_crm":
            doctype = "CRM Lead Status" if kind == "lead" else "CRM Deal Status"
            fields = provider.existing_fields(doctype, ["name", "color", "position", "type", "probability"])
            try:
                rows = self.frappe.get_list(doctype, fields=fields, order_by="position asc", limit_page_length=100)
                return [
                    {
                        "key": row.get("name") or "",
                        "label": row.get("name") or "",
                        "color": row.get("color") or "",
                        "order": row.get("position") or index,
                        "type": row.get("type") or "open",
                        "probability": float(row.get("probability") or 0),
                    }
                    for index, row in enumerate(rows)
                ]
            except Exception:
                return []
        values = (
            ["Lead", "Open", "Replied", "Interested", "Opportunity", "Quotation", "Converted", "Do Not Contact"]
            if kind == "lead"
            else [row["name"] for row in self._safe_list("Sales Stage", ["name"], order_by="name asc")]
        )
        if not values and kind == "deal":
            values = ["Prospecting", "Qualification", "Proposal", "Negotiation", "Converted", "Lost"]
        return [
            {"key": value, "label": value, "color": "", "order": index, "type": _stage_type(value), "probability": 0}
            for index, value in enumerate(values)
        ]

    def _form_fields(self, doctype: str) -> list[dict]:
        try:
            meta = self.frappe.get_meta(doctype)
            fields = getattr(meta, "fields", [])
        except Exception:
            return []
        result = []
        supported = {"Data", "Small Text", "Text", "Select", "Link", "Date", "Datetime", "Int", "Float", "Currency", "Percent", "Check"}
        for field in fields:
            fieldtype = getattr(field, "fieldtype", None) or (field.get("fieldtype") if isinstance(field, dict) else None)
            if fieldtype not in supported:
                continue
            fieldname = getattr(field, "fieldname", None) or (field.get("fieldname") if isinstance(field, dict) else None)
            if not fieldname or fieldname.startswith("_"):
                continue
            result.append(
                {
                    "name": fieldname,
                    "label": getattr(field, "label", None) or (field.get("label") if isinstance(field, dict) else None) or fieldname.replace("_", " ").title(),
                    "type": fieldtype,
                    "required": bool(getattr(field, "reqd", 0) or (field.get("reqd") if isinstance(field, dict) else 0)),
                    "read_only": bool(getattr(field, "read_only", 0) or (field.get("read_only") if isinstance(field, dict) else 0)),
                    "options": getattr(field, "options", None) or (field.get("options") if isinstance(field, dict) else None) or "",
                    "custom": bool(getattr(field, "is_custom_field", 0) or (field.get("is_custom_field") if isinstance(field, dict) else 0)),
                }
            )
        return result

    def _connector_health(self, provider: CrmProvider, installed: set[str]) -> list[dict]:
        return [
            {"channel": "manual", "label": "Manual capture", "enabled": True, "status": "ready", "desk_path": ""},
            {"channel": "web_form", "label": "Web forms", "enabled": self._doctype_exists("Web Form"), "status": "ready" if self._doctype_exists("Web Form") else "unavailable", "desk_path": "/app/web-form"},
            {"channel": "api", "label": "Lead capture API", "enabled": bool(self._conf_string("bude_sales_intake_secret")), "status": "ready" if self._conf_string("bude_sales_intake_secret") else "setup_required", "desk_path": ""},
            {"channel": "email", "label": "Incoming email", "enabled": self._doctype_exists("Email Account"), "status": "configured" if self._safe_exists("Email Account", {"enable_incoming": 1}) else "setup_required", "desk_path": "/app/email-account"},
            {"channel": "meta", "label": "Meta leads", "enabled": provider.config.key == "frappe_crm" or bool(self._conf_string("bude_meta_access_token")), "status": "provider_managed" if provider.config.key == "frappe_crm" else "setup_required", "desk_path": "/crm/settings/integrations"},
            {"channel": "whatsapp", "label": "WhatsApp", "enabled": "frappe_whatsapp" in installed, "status": "provider_managed" if "frappe_whatsapp" in installed else "unavailable", "desk_path": "/app/whatsapp-settings"},
        ]

    def _duplicate_rows(self, provider, email, phone, name, organization, exclude=None) -> list[dict]:
        matches: dict[str, dict] = {}
        normalized_email = str(email or "").strip().lower()
        normalized_phone = _phone(phone)
        queries = []
        if normalized_email:
            queries.append((provider.config.lead_email_field, normalized_email, "exact"))
        if normalized_phone:
            queries.append((provider.config.lead_phone_field, ["like", f"%{normalized_phone[-10:]}"], "exact"))
        for field, value, match in queries:
            filters = [[field, "=", value]] if not isinstance(value, list) else [[field, value[0], value[1]]]
            for row in self._safe_list(provider.config.lead_doctype, provider.lead_fields(), filters=filters, limit=10):
                if row.get("name") == exclude:
                    continue
                matches[row["name"]] = {"match": match, "lead": provider.normalize_lead(row)}
        if name and organization:
            name_field = "lead_name"
            filters = [[name_field, "like", f"%{str(name).strip()}%"], [provider.config.lead_organization_field, "like", f"%{str(organization).strip()}%"]]
            for row in self._safe_list(provider.config.lead_doctype, provider.lead_fields(), filters=filters, limit=10):
                if row.get("name") == exclude or row.get("name") in matches:
                    continue
                matches[row["name"]] = {"match": "possible", "lead": provider.normalize_lead(row)}
        return list(matches.values())

    def _task_rows(self, provider, kind, name, limit=10) -> list[dict]:
        ref_type = "reference_doctype" if provider.config.key == "frappe_crm" else "reference_type"
        ref_name = "reference_docname" if provider.config.key == "frappe_crm" else "reference_name"
        fields = ["name", "title", "description", "status", "priority", "assigned_to", "allocated_to", "due_date", "date", ref_type, ref_name, "modified"]
        rows = self._safe_list(
            provider.config.task_doctype,
            provider.existing_fields(provider.config.task_doctype, fields),
            filters=[[ref_type, "=", provider.reference_doctype(kind)], [ref_name, "=", name]],
            order_by="modified desc",
            limit=limit,
        )
        return [provider.normalize_task(row) for row in rows]

    def _attachment_rows(self, provider, kind, name) -> list[dict]:
        rows = self._safe_list(
            "File",
            ["name", "file_name", "file_url", "file_size", "is_private", "creation", "owner"],
            filters=[
                ["attached_to_doctype", "=", provider.reference_doctype(kind)],
                ["attached_to_name", "=", name],
            ],
            order_by="creation desc",
            limit=100,
        )
        return [
            {
                "name": row.get("name") or "",
                "file_name": row.get("file_name") or "",
                "file_url": row.get("file_url") or "",
                "file_size": int(row.get("file_size") or 0),
                "is_private": bool(row.get("is_private")),
                "created": _serial(row.get("creation")),
                "owner": row.get("owner") or "",
            }
            for row in rows
        ]

    def _timeline_rows(self, provider, kind, name, limit=30) -> list[dict]:
        doctype = provider.reference_doctype(kind)
        activities = []
        specs = [
            ("Communication", "communication", "reference_doctype", "reference_name", ["name", "subject", "content", "sender", "communication_medium", "sent_or_received", "creation", "modified"]),
            ("Comment", "comment", "reference_doctype", "reference_name", ["name", "content", "comment_by", "creation", "modified"]),
        ]
        if self._doctype_exists("WhatsApp Message"):
            specs.append(
                (
                    "WhatsApp Message",
                    "whatsapp",
                    "reference_doctype",
                    "reference_name",
                    ["name", "message", "content", "from", "to", "type", "status", "creation", "modified"],
                )
            )
        if provider.config.key == "frappe_crm":
            specs.extend(
                [
                    ("FCRM Note", "note", "reference_doctype", "reference_docname", ["name", "title", "content", "owner", "creation", "modified"]),
                    ("CRM Call Log", "call", "reference_doctype", "reference_docname", ["name", "type", "status", "from", "to", "duration", "recording_url", "start_time", "creation", "modified"]),
                ]
            )
        for activity_doctype, activity_type, ref_type, ref_name, fields in specs:
            if not self._doctype_exists(activity_doctype):
                continue
            for row in self._safe_list(
                activity_doctype,
                fields,
                filters=[[ref_type, "=", doctype], [ref_name, "=", name]],
                order_by="creation desc",
                limit=limit,
            ):
                activities.append(
                    {
                        "name": row.get("name") or "",
                        "type": activity_type,
                        "title": row.get("subject") or row.get("title") or str(row.get("type") or activity_type).title(),
                        "content": row.get("content") or row.get("message") or row.get("status") or "",
                        "actor": row.get("sender") or row.get("comment_by") or row.get("owner") or row.get("from") or "",
                        "direction": row.get("sent_or_received") or row.get("type") or "",
                        "duration": float(row.get("duration") or 0),
                        "recording_url": row.get("recording_url") or "",
                        "created": _serial(row.get("start_time") or row.get("creation")),
                        "modified": _serial(row.get("modified")),
                    }
                )
        if self._doctype_exists("Event Participants"):
            participant_rows = self._safe_list(
                "Event Participants",
                ["parent"],
                filters=[
                    ["reference_doctype", "=", doctype],
                    ["reference_docname", "=", name],
                ],
                limit=limit,
            )
            event_names = [row.get("parent") for row in participant_rows if row.get("parent")]
            for row in self._parent_documents(
                "Event",
                event_names,
                ["name", "subject", "description", "starts_on", "ends_on", "owner", "event_category", "modified"],
            ):
                activities.append(
                    {
                        "name": row.get("name") or "",
                        "type": "meeting",
                        "title": row.get("subject") or "Meeting",
                        "content": row.get("description") or "",
                        "actor": row.get("owner") or "",
                        "direction": "",
                        "duration": 0,
                        "recording_url": "",
                        "created": _serial(row.get("starts_on")),
                        "modified": _serial(row.get("modified")),
                    }
                )
        activities.extend(
            {
                "name": task["name"],
                "type": "task",
                "title": task["title"],
                "content": task["status"],
                "actor": task["assigned_to"],
                "direction": "",
                "duration": 0,
                "recording_url": "",
                "created": task["modified"],
                "modified": task["modified"],
            }
            for task in self._task_rows(provider, kind, name, limit=limit)
        )
        activities.sort(key=lambda row: row.get("created") or "", reverse=True)
        return activities[:limit]

    def _insert_note(self, provider, kind, name, content, title=None, *, ignore_permissions=False) -> dict:
        if provider.config.key == "frappe_crm":
            values = {
                "doctype": "FCRM Note",
                "title": title or "Note",
                "content": content,
                "reference_doctype": provider.reference_doctype(kind),
                "reference_docname": name,
            }
        else:
            values = {
                "doctype": "Comment",
                "comment_type": "Comment",
                "content": content,
                "reference_doctype": provider.reference_doctype(kind),
                "reference_name": name,
            }
        doc = self.frappe.get_doc(values)
        doc.insert(ignore_permissions=ignore_permissions)
        return {"name": doc.name, "type": "note", "title": title or "Note", "content": content, "created": self._now()}

    def _insert_task(self, provider, data: dict, *, ignore_permissions=False) -> dict:
        kind = data.get("reference_kind") or "lead"
        reference = data.get("reference_name")
        if kind not in {"lead", "deal"} or not reference:
            raise ValueError("A lead or deal reference is required for a task.")
        if provider.config.key == "frappe_crm":
            values = {
                "doctype": "CRM Task",
                "title": data.get("title"),
                "description": data.get("description"),
                "status": data.get("status") or "Todo",
                "priority": data.get("priority") or "Medium",
                "assigned_to": data.get("assigned_to") or self._user(),
                "due_date": data.get("due_date"),
                "reference_doctype": provider.reference_doctype(kind),
                "reference_docname": reference,
            }
        else:
            values = {
                "doctype": "ToDo",
                "description": data.get("title") or data.get("description"),
                "status": "Closed" if data.get("status") in {"Done", "Closed"} else "Open",
                "priority": data.get("priority") or "Medium",
                "allocated_to": data.get("assigned_to") or self._user(),
                "date": data.get("due_date"),
                "reference_type": provider.reference_doctype(kind),
                "reference_name": reference,
            }
        values = {key: value for key, value in values.items() if value not in (None, "")}
        doc = self.frappe.get_doc(values)
        doc.insert(ignore_permissions=ignore_permissions)
        row = _doc_dict(doc, list(values) + ["name", "modified"])
        return provider.normalize_task(row)

    def _child_rows(self, provider, deal: str) -> list[dict]:
        child = "CRM Products" if provider.config.key == "frappe_crm" else "Opportunity Item"
        if not self._doctype_exists(child):
            return []
        fields = ["name", "item_code", "product", "item_name", "qty", "quantity", "rate", "amount", "discount_percentage"]
        return self._safe_list(child, fields, filters=[["parent", "=", deal]], order_by="idx asc", limit=100)

    def _documents(self, provider, deal: str, source: dict) -> dict:
        quote_ref = "crm_deal" if provider.config.key == "frappe_crm" else "opportunity"
        if quote_ref not in self._searchable_fields("Quotation", [quote_ref]):
            quote_ref = "party_name"
        quotations = self._safe_list(
            "Quotation",
            ["name", "status", "transaction_date", "valid_till", "currency", "grand_total", "docstatus", "modified"],
            filters=[[quote_ref, "=", deal]],
            order_by="modified desc",
            limit=50,
        )
        quote_names = [row["name"] for row in quotations]
        order_names = self._linked_parents("Sales Order Item", "prevdoc_docname", quote_names)
        orders = self._parent_documents(
            "Sales Order", order_names, ["name", "status", "transaction_date", "delivery_date", "currency", "grand_total", "per_delivered", "per_billed", "docstatus", "modified"]
        )
        delivery_names = self._linked_parents("Delivery Note Item", "against_sales_order", order_names)
        deliveries = self._parent_documents(
            "Delivery Note", delivery_names, ["name", "status", "posting_date", "currency", "grand_total", "per_billed", "docstatus", "modified"]
        )
        invoice_names = set(self._linked_parents("Sales Invoice Item", "sales_order", order_names))
        invoice_names.update(self._linked_parents("Sales Invoice Item", "delivery_note", delivery_names))
        invoices = self._parent_documents(
            "Sales Invoice", sorted(invoice_names), ["name", "status", "posting_date", "due_date", "currency", "grand_total", "outstanding_amount", "is_return", "docstatus", "modified"]
        )
        payment_names = self._linked_parents(
            "Payment Entry Reference", "reference_name", sorted(invoice_names), extra_filters=[["reference_doctype", "=", "Sales Invoice"]]
        )
        payments = self._parent_documents(
            "Payment Entry", payment_names, ["name", "status", "posting_date", "paid_amount", "received_amount", "paid_from_account_currency", "paid_to_account_currency", "docstatus", "modified"]
        )
        return {
            "quotations": quotations,
            "orders": orders,
            "deliveries": deliveries,
            "invoices": invoices,
            "payments": payments,
        }

    def _linked_parents(self, child_doctype, link_field, values, extra_filters=None):
        if not values:
            return []
        rows = self._safe_list(
            child_doctype,
            ["parent"],
            filters=[[link_field, "in", values], *(extra_filters or [])],
            limit=500,
        )
        return sorted({row.get("parent") for row in rows if row.get("parent")})

    def _parent_documents(self, doctype, names, fields):
        if not names:
            return []
        return self._safe_list(
            doctype,
            fields,
            filters=[["name", "in", names]],
            order_by="modified desc",
            limit=200,
        )

    def _ensure_customer(self, provider, deal, customer, create_customer):
        """Resolve the explicit Customer required before a deal can be Won."""
        customer = str(customer or "").strip()
        if customer:
            if not self._safe_exists("Customer", customer):
                return failure("The selected Customer does not exist.", code="VALIDATION_CUSTOMER")
        elif not create_customer:
            return failure(
                "Select an existing Customer or allow Customer creation before marking Won.",
                code="VALIDATION_CUSTOMER",
            )
        else:
            source = self._read_row(provider.config.deal_doctype, deal, provider.deal_fields())
            if not source:
                return failure("Deal not found or not permitted.", code="NOT_FOUND")
            normalized = provider.normalize_deal(source)
            customer_name = str(normalized.get("organization") or normalized.get("title") or "").strip()
            if not customer_name:
                return failure("A customer name is required to mark this deal Won.", code="VALIDATION_CUSTOMER")
            existing = self._safe_list(
                "Customer", ["name", "customer_name"], filters=[["customer_name", "=", customer_name]], limit=2
            )
            if len(existing) > 1:
                return failure(
                    "Multiple Customers match this deal. Select the correct Customer.",
                    code="DUPLICATE_CUSTOMER",
                    data={"customers": existing},
                )
            if existing:
                customer = existing[0]["name"]
            else:
                values = {
                    "doctype": "Customer",
                    "customer_name": customer_name,
                    "customer_type": "Company" if normalized.get("organization") else "Individual",
                }
                doc = self.frappe.get_doc(values)
                try:
                    doc.insert(ignore_permissions=False)
                except Exception as exc:
                    return self._exception(exc)
                customer = doc.name

        deal_doc = self._writable_doc(provider.config.deal_doctype, deal)
        if isinstance(deal_doc, dict):
            return deal_doc
        if provider.config.key == "erpnext":
            deal_doc.opportunity_from = "Customer"
            deal_doc.party_name = customer
        else:
            fields = set(provider.existing_fields(provider.config.deal_doctype, ["customer"]))
            if "customer" in fields:
                deal_doc.customer = customer
        deal_doc.save(ignore_permissions=False)
        self._insert_note(provider, "deal", deal, f"Linked ERPNext Customer: {customer}", title="Customer")
        return customer

    def _idempotent(
        self,
        action_name: str,
        request_id: str | None,
        action: Callable[[], dict],
        *,
        ignore_permissions: bool = False,
    ) -> dict:
        request_id = str(request_id or "").strip()
        if request_id:
            existing = self._safe_list(
                "Integration Request",
                ["name", "status", "output", "reference_doctype", "reference_docname"],
                filters=[["integration_request_service", "=", f"bude_sales_crm:{action_name}"], ["request_id", "=", request_id]],
                order_by="creation desc",
                limit=1,
            )
            if existing:
                output = existing[0].get("output")
                try:
                    data = json.loads(output) if isinstance(output, str) else output
                except (TypeError, ValueError):
                    data = None
                if isinstance(data, dict):
                    return success(data, message="Request already completed.")
        try:
            data = action()
        except Exception as exc:
            return self._exception(exc)
        if isinstance(data, dict) and data.get("ok") is False:
            return data
        if request_id:
            try:
                reference = _first_reference(data)
                log = self.frappe.get_doc(
                    {
                        "doctype": "Integration Request",
                        "integration_request_service": f"bude_sales_crm:{action_name}",
                        "status": "Completed",
                        "request_id": request_id,
                        "request_description": action_name,
                        "output": json.dumps(data, default=str),
                        "reference_doctype": reference[0] if reference else None,
                        "reference_docname": reference[1] if reference else None,
                    }
                )
                log.insert(ignore_permissions=ignore_permissions)
            except Exception:
                pass
        return success(data)

    def _read_row(self, doctype, name, fields):
        rows = self._safe_list(doctype, fields, filters=[["name", "=", name]], limit=1)
        return rows[0] if rows else None

    def _writable_doc(self, doctype, name, permission="write"):
        if not self._has_permission(doctype, permission, name):
            return permission_denied(f"You do not have {permission} permission for this record.")
        try:
            return self.frappe.get_doc(doctype, name)
        except Exception as exc:
            return self._exception(exc)

    def _conflict(self, doctype, name, base_modified):
        if not base_modified:
            return None
        try:
            current = self.frappe.db.get_value(doctype, name, "modified")
        except Exception:
            current = None
        if current and _serial(current) != _serial(base_modified):
            return failure(
                "This record changed on the server. Refresh before saving.",
                code="CONFLICT",
                data={"server_modified": _serial(current)},
            )
        return None

    def _has_permission(self, doctype, permission, name=None):
        try:
            result = self.frappe.has_permission(doctype, ptype=permission, doc=name)
            return bool(result) if isinstance(result, bool) else True
        except Exception:
            return True

    def _safe_list(self, doctype, fields, *, filters=None, order_by=None, limit=50):
        if not self._doctype_exists(doctype):
            return []
        try:
            kwargs = {
                "filters": filters or [],
                "fields": fields,
                "limit_page_length": limit,
            }
            if order_by:
                kwargs["order_by"] = order_by
            return [dict(row) for row in self.frappe.get_list(doctype, **kwargs)]
        except Exception:
            return []

    def _searchable_fields(self, doctype, fields):
        try:
            meta = self.frappe.get_meta(doctype)
            has_field = getattr(meta, "has_field", None)
            if callable(has_field):
                return [field for field in fields if has_field(field)]
        except Exception:
            pass
        return fields

    def _count(self, doctype, filters, or_filters):
        try:
            if or_filters:
                return len(
                    self.frappe.get_list(
                        doctype,
                        filters=filters,
                        or_filters=or_filters,
                        fields=["name"],
                        limit_page_length=5000,
                    )
                )
            return int(self.frappe.db.count(doctype, filters=filters) or 0)
        except Exception:
            return 0

    def _names(self, doctype):
        return [row["name"] for row in self._safe_list(doctype, ["name"], order_by="name asc", limit=500)]

    def _sales_users(self):
        rows = self._safe_list("Has Role", ["parent", "role"], filters=[["role", "in", ["Sales User", "Sales Manager"]]], limit=1000)
        names = sorted({row.get("parent") for row in rows if row.get("parent")})
        return [{"name": name, "label": name} for name in names]

    def _installed_apps(self) -> set[str]:
        try:
            apps = self.frappe.get_installed_apps()
            if isinstance(apps, list | tuple | set):
                return {str(app) for app in apps}
        except Exception:
            pass
        return {"frappe", "erpnext"}

    def _doctype_exists(self, doctype):
        try:
            result = self.frappe.db.exists("DocType", doctype)
            return bool(result) if isinstance(result, bool | int | str) else True
        except Exception:
            return True

    def _safe_exists(self, doctype, filters):
        try:
            result = self.frappe.db.exists(doctype, filters)
            return bool(result) if isinstance(result, bool | int | str) else False
        except Exception:
            return False

    def _roles(self):
        try:
            roles = self.frappe.get_roles()
            return {str(role) for role in roles} if roles else set()
        except Exception:
            return set()

    def _is_manager(self):
        return has_any_role(self.frappe, SALES_MANAGER_ROLES)

    def _user(self):
        return getattr(getattr(self.frappe, "session", None), "user", None)

    def _default_sales_owner(self):
        return self._conf_string("bude_sales_default_owner") or self._user()

    def _conf_string(self, key):
        try:
            value = self.frappe.conf.get(key)
        except Exception:
            return ""
        return value.strip() if isinstance(value, str) else ""

    def _today(self):
        try:
            return str(self.frappe.utils.nowdate())
        except Exception:
            return date.today().isoformat()

    def _now(self):
        try:
            return str(self.frappe.utils.now_datetime())
        except Exception:
            return datetime.now().isoformat()

    def _days_ago(self, days):
        try:
            value = int(days)
        except (TypeError, ValueError):
            value = 0
        return (datetime.now() - timedelta(days=max(value, 0))).isoformat(sep=" ", timespec="seconds")

    def _rate_limit(self, channel):
        try:
            cache = self.frappe.cache()
            key = f"bude_sales_intake:{channel}:{getattr(self.frappe.local, 'request_ip', 'unknown')}:{int(time.time()) // 60}"
            count = cache.incr(key)
            cache.expire(key, 120)
            if isinstance(count, int) and count > 60:
                return failure("Too many intake requests.", code="RATE_LIMITED")
        except Exception:
            pass
        return None

    def _payload(self, payload):
        if isinstance(payload, dict):
            return dict(payload)
        if isinstance(payload, str):
            try:
                value = json.loads(payload)
                return value if isinstance(value, dict) else {}
            except ValueError:
                return {}
        return {}

    def _exception(self, exc):
        validation = getattr(self.frappe, "ValidationError", ())
        permission = getattr(self.frappe, "PermissionError", ())
        if isinstance(validation, type) and isinstance(exc, validation):
            return failure(str(exc) or "ERPNext rejected the request.", code="VALIDATION_FAILED")
        if isinstance(permission, type) and isinstance(exc, permission):
            return permission_denied(str(exc) or "You do not have permission for this action.")
        return failure(str(exc) or "Unable to complete the CRM request.", code="CRM_ERROR")


def _phone(value) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _stage_type(value) -> str:
    lowered = str(value or "").lower()
    if lowered in {"won", "converted", "completed"}:
        return "won"
    if "lost" in lowered or lowered in {"closed", "do not contact"}:
        return "lost"
    return "open"


def _first_reference(data):
    if not isinstance(data, dict):
        return None
    for key, doctype in (("lead", "Lead"), ("deal", "Opportunity"), ("task", "ToDo"), ("quotation", "Quotation")):
        value = data.get(key)
        if isinstance(value, dict) and value.get("name"):
            return doctype, value["name"]
    return None
