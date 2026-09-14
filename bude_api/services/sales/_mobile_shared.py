"""Mobile sales endpoints for the standalone Bude Sales app.

All reads and writes use standard ERPNext/Frappe DocTypes only. No custom
DocTypes are introduced here.
"""

from __future__ import annotations

from datetime import date

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.pagination import Page, parse_page

from ...utils.response import failure, success

from ..common.permissions import has_any_role, permission_denied, require_sales_role

SALES_MANAGER_ROLES = {"Sales Manager", "System Manager"}

ACCOUNTS_ROLES = {"Accounts User", "Accounts Manager", "System Manager"}

DEFAULT_LIMIT = 50

MAX_LIMIT = 200

CLOSED_STATUSES = {"Closed", "Completed", "Cancelled"}


def _whitelist(methods=None, allow_guest: bool = False):
    if frappe is None:

        def decorator(fn):
            return fn

        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=methods or ["GET", "POST"])


def _current_user() -> str | None:
    return getattr(getattr(frappe, "session", None), "user", None)


def _is_sales_manager() -> bool:
    return has_any_role(frappe, SALES_MANAGER_ROLES)


def _has_accounts_role() -> bool:
    return has_any_role(frappe, ACCOUNTS_ROLES)


def _require_accounts_or_manager() -> dict | None:
    denied = require_sales_role(frappe)
    if denied:
        return denied
    if _has_accounts_role() or _is_sales_manager():
        return None
    return permission_denied("An accounts or sales manager role is required for this action.")


def _page(limit, offset) -> Page | dict:
    return parse_page(limit, offset, default_limit=DEFAULT_LIMIT, max_limit=MAX_LIMIT)


def _existing_fields(doctype: str, fields: list[str]) -> list[str]:
    """Keep mobile reads compatible across ERPNext schema versions."""
    try:
        meta = frappe.get_meta(doctype)
        has_field = getattr(meta, "has_field", None)
        if callable(has_field):
            return [field for field in fields if field == "name" or has_field(field)]
    except Exception:
        pass
    return fields


def _names(doctype: str, filters: list | None = None) -> list[str]:
    return [
        row.get("name")
        for row in frappe.get_list(
            doctype, filters=filters or [], fields=["name"], limit_page_length=MAX_LIMIT
        )
    ]


def _sales_persons() -> list[dict]:
    return frappe.get_list(
        "Sales Person",
        filters=[["enabled", "=", 1]],
        fields=["name", "sales_person_name", "employee"],
        order_by="sales_person_name asc",
        limit_page_length=MAX_LIMIT,
    )


def _doc_date_filters(doctype: str, from_date: str | None, to_date: str | None) -> list:
    field = "posting_date" if doctype in {"Sales Invoice", "Payment Entry"} else "transaction_date"
    filters = []
    if from_date:
        filters.append([field, ">=", from_date])
    if to_date:
        filters.append([field, "<=", to_date])
    return filters


def _append_sales_person_filter(filters: list, parenttype: str, sales_person: str) -> None:
    parents = frappe.get_list(
        "Sales Team",
        filters=[["parenttype", "=", parenttype], ["sales_person", "=", sales_person]],
        fields=["parent"],
        limit_page_length=5000,
    )
    names = [row["parent"] for row in parents]
    filters.append(["name", "in", names or ["__none__"]])


def _sales_people_for_docs(parenttype: str, names: list[str]) -> dict[str, str]:
    if not names:
        return {}
    rows = frappe.get_list(
        "Sales Team",
        filters=[["parenttype", "=", parenttype], ["parent", "in", names]],
        fields=["parent", "sales_person"],
        limit_page_length=5000,
    )
    return {row["parent"]: row["sales_person"] for row in rows if row.get("sales_person")}


def _linked_contacts(customer: str) -> list[dict]:
    # Dynamic Link is a child DocType.  Frappe v16's permission-aware
    # ``get_list`` strips child-table fields and returns only ``name``, which
    # made the customer detail endpoint fail with KeyError("parent").  The
    # customer itself has already passed the permission-filtered lookup, and
    # these rows are constrained to that exact customer, so read the child
    # table directly.
    links = frappe.get_all(
        "Dynamic Link",
        filters=[
            ["link_doctype", "=", "Customer"],
            ["link_name", "=", customer],
            ["parenttype", "=", "Contact"],
        ],
        fields=["parent"],
        limit_page_length=50,
    )
    names = [row["parent"] for row in links]
    if not names:
        return []
    return frappe.get_list(
        "Contact",
        filters=[["name", "in", names]],
        fields=["name", "first_name", "last_name", "email_id", "mobile_no"],
        limit_page_length=50,
    )


def _linked_addresses(customer: str) -> list[dict]:
    links = frappe.get_all(
        "Dynamic Link",
        filters=[
            ["link_doctype", "=", "Customer"],
            ["link_name", "=", customer],
            ["parenttype", "=", "Address"],
        ],
        fields=["parent"],
        limit_page_length=50,
    )
    names = [row["parent"] for row in links]
    if not names:
        return []
    return frappe.get_list(
        "Address",
        filters=[["name", "in", names]],
        fields=["name", "address_title", "address_line1", "city", "state", "country", "pincode"],
        limit_page_length=50,
    )


def _recent_docs(doctype: str, customer: str) -> list[dict]:
    date_field = "posting_date" if doctype == "Sales Invoice" else "transaction_date"
    return frappe.get_list(
        doctype,
        filters=[["customer", "=", customer]],
        fields=["name", date_field, "status", "grand_total", "docstatus"],
        order_by="modified desc",
        limit_page_length=5,
    )


def _outstanding(customer: str) -> float:
    rows = frappe.get_list(
        "Sales Invoice",
        filters=[
            ["customer", "=", customer],
            ["docstatus", "=", 1],
            ["outstanding_amount", ">", 0],
        ],
        fields=["outstanding_amount"],
        limit_page_length=1000,
    )
    return sum(float(row.get("outstanding_amount") or 0) for row in rows)


def _customer_credit_limits(customer: str) -> list[dict]:
    try:
        exists = frappe.db.exists("DocType", "Customer Credit Limit")
    except Exception:
        return []
    if not isinstance(exists, (bool, str)) or not exists:
        return []
    fields = _existing_fields(
        "Customer Credit Limit",
        ["company", "credit_limit", "bypass_credit_limit_check"],
    )
    if not fields:
        return []
    try:
        rows = frappe.get_list(
            "Customer Credit Limit",
            filters=[
                ["parent", "=", customer],
                ["parenttype", "=", "Customer"],
            ],
            fields=fields,
            order_by="idx asc",
            limit_page_length=100,
        )
    except Exception:
        return []
    return [
        {
            "company": row.get("company") or "",
            "credit_limit": float(row.get("credit_limit") or 0),
            "bypass_credit_limit_check": bool(row.get("bypass_credit_limit_check")),
        }
        for row in rows
    ]


def _receivable_aging(customer: str) -> dict:
    fields = _existing_fields(
        "Sales Invoice",
        [
            "name",
            "posting_date",
            "due_date",
            "currency",
            "grand_total",
            "outstanding_amount",
            "status",
        ],
    )
    required = {"name", "outstanding_amount"}
    if not required.issubset(fields):
        return _empty_receivable_aging()
    try:
        rows = frappe.get_list(
            "Sales Invoice",
            filters=[
                ["customer", "=", customer],
                ["docstatus", "=", 1],
                ["outstanding_amount", ">", 0],
            ],
            fields=fields,
            order_by="due_date asc, posting_date asc",
            limit_page_length=501,
        )
    except Exception:
        return _empty_receivable_aging()

    truncated = len(rows) > 500
    scanned = rows[:500]
    today = _today_date()
    totals: dict[str, dict] = {}
    overdue = []
    for row in scanned:
        currency = str(row.get("currency") or "Company Currency")
        amount = float(row.get("outstanding_amount") or 0)
        bucket = totals.setdefault(
            currency,
            {
                "currency": currency,
                "current": 0.0,
                "days_1_30": 0.0,
                "days_31_60": 0.0,
                "days_61_90": 0.0,
                "days_91_plus": 0.0,
                "total": 0.0,
            },
        )
        due_date = _parse_date(row.get("due_date") or row.get("posting_date"))
        days_overdue = max((today - due_date).days, 0) if due_date else 0
        if days_overdue == 0:
            key = "current"
        elif days_overdue <= 30:
            key = "days_1_30"
        elif days_overdue <= 60:
            key = "days_31_60"
        elif days_overdue <= 90:
            key = "days_61_90"
        else:
            key = "days_91_plus"
        bucket[key] += amount
        bucket["total"] += amount
        if days_overdue > 0:
            overdue.append(
                {
                    "name": row.get("name") or "",
                    "posting_date": str(row.get("posting_date") or ""),
                    "due_date": str(row.get("due_date") or ""),
                    "currency": currency,
                    "grand_total": float(row.get("grand_total") or 0),
                    "outstanding_amount": amount,
                    "status": row.get("status") or "",
                    "days_overdue": days_overdue,
                }
            )
    overdue.sort(
        key=lambda row: (
            -row["days_overdue"],
            row["due_date"],
            row["name"],
        )
    )
    return {
        "currencies": sorted(totals.values(), key=lambda row: row["currency"]),
        "overdue_invoices": overdue[:10],
        "scanned_count": len(scanned),
        "truncated": truncated,
    }


def _empty_receivable_aging() -> dict:
    return {
        "currencies": [],
        "overdue_invoices": [],
        "scanned_count": 0,
        "truncated": False,
    }


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _today_date() -> date:
    try:
        return date.fromisoformat(str(frappe.utils.nowdate())[:10])
    except Exception:
        return date.today()


def _price_by_item(item_codes: list[str], price_list: str) -> dict:
    if not item_codes:
        return {}
    rows = frappe.get_list(
        "Item Price",
        filters=[
            ["item_code", "in", item_codes],
            ["price_list", "=", price_list],
            ["selling", "=", 1],
        ],
        fields=["item_code", "price_list_rate", "currency"],
        limit_page_length=500,
    )
    return {
        row["item_code"]: {
            "rate": float(row.get("price_list_rate") or 0),
            "currency": row.get("currency"),
        }
        for row in rows
    }


def _stock_by_item(item_codes: list[str], warehouse: str | None) -> dict:
    if not item_codes:
        return {}
    filters = [["item_code", "in", item_codes]]
    if warehouse:
        filters.append(["warehouse", "=", warehouse])
    rows = frappe.get_list(
        "Bin", filters=filters, fields=["item_code", "actual_qty"], limit_page_length=1000
    )
    result: dict[str, float] = {}
    for row in rows:
        result[row["item_code"]] = result.get(row["item_code"], 0) + float(
            row.get("actual_qty") or 0
        )
    return result


def _visit_description(notes: str | None, latitude, longitude) -> str:
    parts = [(notes or "").strip()]
    if latitude not in (None, "") and longitude not in (None, ""):
        parts.append(f"Location: {latitude}, {longitude}")
    return "\n".join(part for part in parts if part)


def _validate_customer_items(customer: str, items: list) -> dict | None:
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    if not _exists("Customer", customer):
        return failure("Customer not found.", code="VALIDATION_UNKNOWN_CUSTOMER")
    if not items:
        return failure("At least one item is required.", code="VALIDATION_REQUIRED")
    for row in items:
        if not isinstance(row, dict) or not row.get("item_code"):
            return failure("Each item needs an item_code.", code="VALIDATION_REQUIRED")
        try:
            qty = float(row.get("qty"))
        except (TypeError, ValueError):
            return failure(f"Invalid qty for {row.get('item_code')}.", code="VALIDATION_BAD_QTY")
        if qty <= 0:
            return failure(
                f"qty must be greater than zero for {row.get('item_code')}.",
                code="VALIDATION_BAD_QTY",
            )
    missing = _missing_items([row["item_code"] for row in items])
    if missing:
        return failure(f"Unknown item(s): {', '.join(missing)}", code="VALIDATION_UNKNOWN_ITEM")
    return None


def _selling_doc(doctype: str, customer: str, items: list, **kwargs) -> dict:
    doc = {
        "doctype": doctype,
        "customer": customer.strip(),
        "items": [
            {
                "item_code": row["item_code"],
                "qty": float(row["qty"]),
                **({"rate": float(row["rate"])} if row.get("rate") not in (None, "") else {}),
                **({"uom": row["uom"].strip()} if (row.get("uom") or "").strip() else {}),
                **(
                    {"warehouse": row["warehouse"].strip()}
                    if (row.get("warehouse") or "").strip()
                    else {}
                ),
                **({"sales_order": kwargs.get("sales_order")} if kwargs.get("sales_order") else {}),
            }
            for row in items
        ],
    }
    if kwargs.get("company"):
        doc["company"] = kwargs["company"]
    if kwargs.get("price_list"):
        doc["selling_price_list"] = kwargs["price_list"]
    if kwargs.get("delivery_date"):
        doc["delivery_date"] = kwargs["delivery_date"]
    if kwargs.get("valid_till"):
        doc["valid_till"] = kwargs["valid_till"]
    return doc


def _exists(doctype: str, name: str) -> bool:
    return bool(
        frappe.get_list(
            doctype, filters=[["name", "=", name]], fields=["name"], limit_page_length=1
        )
    )


def _missing_items(codes: list[str]) -> list[str]:
    rows = frappe.get_list(
        "Item",
        filters=[["item_code", "in", codes]],
        fields=["item_code"],
        limit_page_length=len(codes),
    )
    found = {row["item_code"] for row in rows}
    return [code for code in codes if code not in found]


def _count(doctype: str, filters: list) -> int:
    try:
        return int(frappe.db.count(doctype, filters=filters))
    except Exception:
        return len(
            frappe.get_list(doctype, filters=filters, fields=["name"], limit_page_length=5000)
        )


def _sum(doctype: str, field: str, filters: list) -> float:
    rows = frappe.get_list(doctype, filters=filters, fields=[field], limit_page_length=5000)
    return sum(float(row.get(field) or 0) for row in rows)


def _insert_doc(doc_data: dict) -> dict:
    doc = frappe.get_doc(doc_data)
    try:
        doc.insert(ignore_permissions=False)
        frappe.db.commit()
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(_erpnext_message(exc), code="VALIDATION_ERPNEXT")
    except frappe.PermissionError:
        frappe.db.rollback()
        return permission_denied()
    return success({"name": doc.name, "docstatus": doc.docstatus})


def _insert_and_maybe_submit(doc_data: dict, submit: bool) -> dict:
    doc = frappe.get_doc(doc_data)
    try:
        doc.insert(ignore_permissions=False)
        if submit:
            doc.submit()
        frappe.db.commit()
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(_erpnext_message(exc), code="VALIDATION_ERPNEXT")
    except frappe.PermissionError:
        frappe.db.rollback()
        return permission_denied()
    return success({"name": doc.name, "docstatus": doc.docstatus})


def _erpnext_message(exc: Exception) -> str:
    msg = (str(exc) or "").strip() or "ERPNext rejected the document."
    try:
        from frappe.utils import strip_html_tags

        msg = strip_html_tags(msg).strip() or msg
    except Exception:
        pass
    return msg


__all__ = [name for name in globals() if not name.startswith("__")]
