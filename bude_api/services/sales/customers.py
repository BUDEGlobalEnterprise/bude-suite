"""Grouped mobile endpoints: customers."""

from datetime import date, timedelta

from ._mobile_shared import *  # noqa: F401,F403


def customers(
    search: str | None = None,
    territory: str | None = None,
    assigned_to_me: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> dict:
    denied = require_sales_role(frappe)
    if denied:
        return denied
    page = _page(limit, offset)
    if not isinstance(page, Page):
        return page
    filters = []
    if search:
        filters.append(["customer_name", "like", f"%{search.strip()}%"])
    if territory:
        filters.append(["territory", "=", territory])
    if assigned_to_me in (True, 1, "1", "true", "True") and not _is_sales_manager():
        filters.append(["owner", "=", _current_user()])
    fields = _existing_fields(
        "Customer",
        [
            "name",
            "customer_name",
            "customer_group",
            "territory",
            "mobile_no",
            "email_id",
            "customer_type",
            "disabled",
        ],
    )
    rows = frappe.get_list(
        "Customer",
        filters=filters,
        fields=fields,
        order_by="customer_name asc",
        limit_start=page.offset,
        limit_page_length=page.limit,
    )
    _add_customer_locations(rows)
    return success(
        {
            "customers": rows,
            "total": _count("Customer", filters),
            "limit": page.limit,
            "offset": page.offset,
        }
    )


def _add_customer_locations(rows: list[dict]) -> None:
    """Attach the first geocoded Address without introducing custom fields."""
    names = [row.get("name") for row in rows if row.get("name")]
    if not names:
        return
    try:
        # Dynamic Link is a child DocType; get_list() on Frappe v16 returns
        # only its name and drops parent/link_name even when requested.
        links = frappe.get_all(
            "Dynamic Link",
            filters=[
                ["link_doctype", "=", "Customer"],
                ["link_name", "in", names],
                ["parenttype", "=", "Address"],
            ],
            fields=["parent", "link_name"],
            limit_page_length=min(len(names) * 3, 600),
        )
        address_names = list({link.get("parent") for link in links if link.get("parent")})
        if not address_names:
            return
        fields = _existing_fields(
            "Address",
            [
                "name",
                "address_title",
                "address_line1",
                "city",
                "state",
                "country",
                "latitude",
                "longitude",
            ],
        )
        addresses = frappe.get_list(
            "Address",
            filters=[["name", "in", address_names]],
            fields=fields,
            limit_page_length=len(address_names),
        )
    except Exception:
        return
    address_by_name = {row.get("name"): row for row in addresses}
    location_by_customer = {}
    for link in links:
        address = address_by_name.get(link.get("parent"))
        if not address or link.get("link_name") in location_by_customer:
            continue
        location_by_customer[link.get("link_name")] = address
    for row in rows:
        address = location_by_customer.get(row.get("name"), {})
        row["latitude"] = _float_or_none(address.get("latitude"))
        row["longitude"] = _float_or_none(address.get("longitude"))
        row["address"] = ", ".join(
            str(address.get(field) or "").strip()
            for field in ("address_line1", "city", "state", "country")
            if str(address.get(field) or "").strip()
        )


def _float_or_none(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def customer_detail(customer: str) -> dict:
    denied = require_sales_role(frappe)
    if denied:
        return denied
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    fields = _existing_fields(
        "Customer",
        [
            "name",
            "customer_name",
            "customer_group",
            "territory",
            "mobile_no",
            "email_id",
            "customer_type",
            "default_price_list",
            "default_currency",
            "payment_terms",
            "tax_id",
            "tax_category",
            "customer_primary_address",
            "customer_primary_contact",
            "website",
            "industry",
            "market_segment",
            "disabled",
        ],
    )
    rows = frappe.get_list(
        "Customer",
        filters=[["name", "=", customer]],
        fields=fields,
        limit_page_length=1,
    )
    if not rows:
        return failure("Customer not found.", code="VALIDATION_UNKNOWN_CUSTOMER")
    return success(
        {
            **rows[0],
            "contacts": _linked_contacts(customer),
            "addresses": _linked_addresses(customer),
            "recent_orders": _recent_docs("Sales Order", customer),
            "recent_invoices": _recent_docs("Sales Invoice", customer),
            "outstanding": _outstanding(customer),
            "credit_limits": _customer_credit_limits(customer),
            "receivable_aging": _receivable_aging(customer),
        }
    )


def customer_buying_history(customer: str, limit: int = 5) -> dict:
    """Summarize recent submitted invoice items for a customer by currency."""
    denied = require_sales_role(frappe)
    if denied:
        return denied
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if limit < 1 or limit > 20:
        return failure("limit must be between 1 and 20.", code="VALIDATION_BAD_LIMIT")
    if not _optional_doctype_exists("Sales Invoice") or not _optional_doctype_exists(
        "Sales Invoice Item"
    ):
        return success(_empty_buying_history())

    customer_rows = frappe.get_list(
        "Customer",
        filters=[["name", "=", customer]],
        fields=["name"],
        limit_page_length=1,
    )
    if not customer_rows:
        return failure("Customer not found.", code="VALIDATION_UNKNOWN_CUSTOMER")
    try:
        invoices = frappe.get_list(
            "Sales Invoice",
            filters=[["customer", "=", customer], ["docstatus", "=", 1]],
            fields=_existing_fields(
                "Sales Invoice",
                ["name", "posting_date", "currency", "status"],
            ),
            order_by="posting_date desc, creation desc",
            limit_page_length=51,
        )
    except Exception:
        return success(_empty_buying_history())
    truncated = len(invoices) > 50
    invoices = invoices[:50]
    invoice_names = [row.get("name") for row in invoices if row.get("name")]
    if not invoice_names:
        return success(_empty_buying_history())
    item_fields = _existing_fields(
        "Sales Invoice Item",
        ["parent", "item_code", "item_name", "qty", "uom", "net_amount"],
    )
    if not {"parent", "item_code"}.issubset(item_fields):
        return success(_empty_buying_history())
    try:
        item_rows = frappe.get_list(
            "Sales Invoice Item",
            filters=[["parent", "in", invoice_names]],
            fields=item_fields,
            limit_page_length=5000,
        )
    except Exception:
        return success(_empty_buying_history())

    invoice_by_name = {row.get("name"): row for row in invoices}
    grouped: dict[str, dict[tuple[str, str], dict]] = {}
    for row in item_rows:
        invoice = invoice_by_name.get(row.get("parent"), {})
        currency = str(invoice.get("currency") or "Company Currency")
        item_code = str(row.get("item_code") or "")
        if not item_code:
            continue
        key = (item_code, str(row.get("uom") or ""))
        bucket = grouped.setdefault(currency, {})
        item = bucket.setdefault(
            key,
            {
                "item_code": item_code,
                "item_name": row.get("item_name") or item_code,
                "uom": row.get("uom") or "",
                "quantity": 0.0,
                "net_amount": 0.0,
                "invoice_names": set(),
                "last_invoice": "",
                "last_purchase_date": "",
            },
        )
        item["quantity"] += float(row.get("qty") or 0)
        item["net_amount"] += float(row.get("net_amount") or 0)
        item["invoice_names"].add(row.get("parent"))
        posting_date = str(invoice.get("posting_date") or "")
        if posting_date >= item["last_purchase_date"]:
            item["last_purchase_date"] = posting_date
            item["last_invoice"] = row.get("parent") or ""

    currencies = []
    for currency, buckets in sorted(grouped.items()):
        items = []
        for item in buckets.values():
            items.append(
                {
                    **{key: value for key, value in item.items() if key != "invoice_names"},
                    "invoice_count": len(item["invoice_names"]),
                }
            )
        items.sort(
            key=lambda item: (
                -item["net_amount"],
                -item["quantity"],
                item["item_code"],
            )
        )
        currencies.append({"currency": currency, "items": items[:limit]})
    return success(
        {
            "currencies": currencies,
            "scanned_invoices": len(invoices),
            "truncated": truncated,
        }
    )


def customer_fulfillment(customer: str, limit: int = 10) -> dict:
    """Return delivery progress for recent submitted Sales Orders."""
    denied = require_sales_role(frappe)
    if denied:
        return denied
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if limit < 1 or limit > 20:
        return failure("limit must be between 1 and 20.", code="VALIDATION_BAD_LIMIT")
    empty = {"orders": [], "recent_deliveries": [], "open_orders": 0, "overdue_orders": 0}
    if not _optional_doctype_exists("Sales Order"):
        return success(empty)
    customers = frappe.get_list(
        "Customer",
        filters=[["name", "=", customer]],
        fields=["name"],
        limit_page_length=1,
    )
    if not customers:
        return failure("Customer not found.", code="VALIDATION_UNKNOWN_CUSTOMER")
    order_fields = _existing_fields(
        "Sales Order",
        [
            "name",
            "transaction_date",
            "delivery_date",
            "currency",
            "grand_total",
            "status",
            "per_delivered",
            "per_billed",
        ],
    )
    try:
        rows = frappe.get_list(
            "Sales Order",
            filters=[["customer", "=", customer], ["docstatus", "=", 1]],
            fields=order_fields,
            order_by="transaction_date desc, creation desc",
            limit_page_length=limit,
        )
    except Exception:
        return success(empty)
    today = date.today()
    orders = []
    overdue_orders = 0
    for row in rows:
        delivered = float(row.get("per_delivered") or 0)
        delivery_date = _date_value(row.get("delivery_date"))
        overdue = bool(delivery_date and delivery_date < today and delivered < 100)
        overdue_orders += int(overdue)
        orders.append(
            {
                "name": row.get("name") or "",
                "transaction_date": str(row.get("transaction_date") or ""),
                "delivery_date": str(row.get("delivery_date") or ""),
                "currency": row.get("currency") or "",
                "grand_total": float(row.get("grand_total") or 0),
                "status": row.get("status") or "",
                "per_delivered": delivered,
                "per_billed": float(row.get("per_billed") or 0),
                "overdue": overdue,
            }
        )
    deliveries = []
    if _optional_doctype_exists("Delivery Note"):
        try:
            deliveries = frappe.get_list(
                "Delivery Note",
                filters=[["customer", "=", customer], ["docstatus", "=", 1]],
                fields=_existing_fields(
                    "Delivery Note",
                    [
                        "name",
                        "posting_date",
                        "currency",
                        "grand_total",
                        "status",
                        "per_billed",
                    ],
                ),
                order_by="posting_date desc, creation desc",
                limit_page_length=min(limit, 5),
            )
        except Exception:
            deliveries = []
    return success(
        {
            "orders": orders,
            "recent_deliveries": [
                {
                    **row,
                    "posting_date": str(row.get("posting_date") or ""),
                    "grand_total": float(row.get("grand_total") or 0),
                    "per_billed": float(row.get("per_billed") or 0),
                }
                for row in deliveries
            ],
            "open_orders": sum(
                1 for order in orders if order["per_delivered"] < 100
            ),
            "overdue_orders": overdue_orders,
        }
    )


def customer_quotation_guidance(customer: str, limit: int = 10) -> dict:
    """Classify recent standard Quotations by their next practical action."""
    denied = require_sales_role(frappe)
    if denied:
        return denied
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if limit < 1 or limit > 20:
        return failure("limit must be between 1 and 20.", code="VALIDATION_BAD_LIMIT")
    empty = {
        "quotations": [],
        "open": 0,
        "expiring_soon": 0,
        "expired": 0,
        "ordered": 0,
        "lost": 0,
    }
    if not _optional_doctype_exists("Quotation"):
        return success(empty)
    customers = frappe.get_list(
        "Customer",
        filters=[["name", "=", customer]],
        fields=["name"],
        limit_page_length=1,
    )
    if not customers:
        return failure("Customer not found.", code="VALIDATION_UNKNOWN_CUSTOMER")
    try:
        rows = frappe.get_list(
            "Quotation",
            filters=[
                ["quotation_to", "=", "Customer"],
                ["party_name", "=", customer],
                ["docstatus", "=", 1],
            ],
            fields=_existing_fields(
                "Quotation",
                [
                    "name",
                    "transaction_date",
                    "valid_till",
                    "status",
                    "currency",
                    "grand_total",
                    "order_type",
                ],
            ),
            order_by="transaction_date desc, creation desc",
            limit_page_length=limit,
        )
    except Exception:
        return success(empty)

    today = date.today()
    counts = {
        key: 0
        for key in ("open", "expiring_soon", "expired", "ordered", "lost")
    }
    quotations = []
    for row in rows:
        status = str(row.get("status") or "")
        status_key = status.lower()
        valid_till = _date_value(row.get("valid_till"))
        days_to_expiry = (valid_till - today).days if valid_till else None
        expired = bool(valid_till and valid_till < today) or status_key == "expired"
        expiring = bool(
            not expired
            and days_to_expiry is not None
            and 0 <= days_to_expiry <= 7
            and status_key not in {"ordered", "lost", "cancelled"}
        )
        if status_key == "ordered":
            category, action = "ordered", "none"
        elif status_key == "lost":
            category, action = "lost", "none"
        elif expired:
            category, action = "expired", "renew"
        elif expiring:
            category, action = "expiring_soon", "follow_up"
        else:
            category, action = "open", "convert"
        counts[category] += 1
        quotations.append(
            {
                "name": row.get("name") or "",
                "transaction_date": str(row.get("transaction_date") or ""),
                "valid_till": str(row.get("valid_till") or ""),
                "status": status,
                "currency": row.get("currency") or "",
                "grand_total": float(row.get("grand_total") or 0),
                "order_type": row.get("order_type") or "",
                "days_to_expiry": days_to_expiry,
                "category": category,
                "recommended_action": action,
            }
        )
    return success({"quotations": quotations, **counts})


def customer_item_pricing(customer: str, limit: int = 10) -> dict:
    """Return customer-specific standard Item Price records and validity."""
    denied = require_sales_role(frappe)
    if denied:
        return denied
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if limit < 1 or limit > 50:
        return failure("limit must be between 1 and 50.", code="VALIDATION_BAD_LIMIT")
    empty = {"prices": [], "active": 0, "upcoming": 0, "expired": 0}
    if not _optional_doctype_exists("Item Price"):
        return success(empty)
    customers = frappe.get_list(
        "Customer",
        filters=[["name", "=", customer]],
        fields=["name"],
        limit_page_length=1,
    )
    if not customers:
        return failure("Customer not found.", code="VALIDATION_UNKNOWN_CUSTOMER")
    fields = _existing_fields(
        "Item Price",
        [
            "name",
            "item_code",
            "item_name",
            "price_list",
            "currency",
            "price_list_rate",
            "uom",
            "packing_unit",
            "valid_from",
            "valid_upto",
            "lead_time_days",
        ],
    )
    if not {"item_code", "price_list_rate"}.issubset(fields):
        return success(empty)
    try:
        rows = frappe.get_list(
            "Item Price",
            filters=[["customer", "=", customer], ["selling", "=", 1]],
            fields=fields,
            order_by="valid_from desc, modified desc",
            limit_page_length=limit,
        )
    except Exception:
        return success(empty)
    today = date.today()
    counts = {"active": 0, "upcoming": 0, "expired": 0}
    prices = []
    for row in rows:
        valid_from = _date_value(row.get("valid_from"))
        valid_upto = _date_value(row.get("valid_upto"))
        if valid_from and valid_from > today:
            status = "upcoming"
        elif valid_upto and valid_upto < today:
            status = "expired"
        else:
            status = "active"
        counts[status] += 1
        prices.append(
            {
                "name": row.get("name") or "",
                "item_code": row.get("item_code") or "",
                "item_name": row.get("item_name") or row.get("item_code") or "",
                "price_list": row.get("price_list") or "",
                "currency": row.get("currency") or "",
                "rate": float(row.get("price_list_rate") or 0),
                "uom": row.get("uom") or "",
                "packing_unit": int(row.get("packing_unit") or 0),
                "valid_from": str(row.get("valid_from") or ""),
                "valid_upto": str(row.get("valid_upto") or ""),
                "lead_time_days": int(row.get("lead_time_days") or 0),
                "status": status,
            }
        )
    return success({"prices": prices, **counts})


def customer_opportunities(customer: str, limit: int = 10) -> dict:
    """Return the standard Opportunity pipeline for a customer."""
    denied = require_sales_role(frappe)
    if denied:
        return denied
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if limit < 1 or limit > 50:
        return failure("limit must be between 1 and 50.", code="VALIDATION_BAD_LIMIT")
    empty = {
        "opportunities": [],
        "open": 0,
        "converted": 0,
        "lost": 0,
        "overdue": 0,
        "weighted_by_currency": [],
        "truncated": False,
    }
    if not _optional_doctype_exists("Opportunity"):
        return success(empty)
    customers = frappe.get_list(
        "Customer",
        filters=[["name", "=", customer]],
        fields=["name"],
        limit_page_length=1,
    )
    if not customers:
        return failure("Customer not found.", code="VALIDATION_UNKNOWN_CUSTOMER")
    try:
        rows = frappe.get_list(
            "Opportunity",
            filters=[
                ["opportunity_from", "=", "Customer"],
                ["party_name", "=", customer],
                ["docstatus", "!=", 2],
            ],
            fields=_existing_fields(
                "Opportunity",
                [
                    "name",
                    "title",
                    "transaction_date",
                    "status",
                    "opportunity_type",
                    "sales_stage",
                    "expected_closing",
                    "probability",
                    "currency",
                    "opportunity_amount",
                    "opportunity_owner",
                ],
            ),
            order_by="expected_closing asc, transaction_date desc",
            limit_page_length=501,
        )
    except Exception:
        return success(empty)
    truncated = len(rows) > 500
    rows = rows[:500]
    today = date.today()
    counts = {"open": 0, "converted": 0, "lost": 0, "overdue": 0}
    weighted: dict[str, float] = {}
    opportunities = []
    for row in rows:
        status = str(row.get("status") or "")
        status_key = status.lower()
        if status_key == "converted":
            counts["converted"] += 1
        elif status_key == "lost":
            counts["lost"] += 1
        elif status_key not in {"closed"}:
            counts["open"] += 1
        closing = _date_value(row.get("expected_closing"))
        overdue = bool(
            closing
            and closing < today
            and status_key not in {"converted", "lost", "closed"}
        )
        counts["overdue"] += int(overdue)
        amount = float(row.get("opportunity_amount") or 0)
        probability = float(row.get("probability") or 0)
        currency = str(row.get("currency") or "Company Currency")
        if status_key not in {"lost", "closed"}:
            weighted[currency] = weighted.get(currency, 0) + (
                amount * probability / 100
            )
        opportunities.append(
            {
                "name": row.get("name") or "",
                "title": row.get("title") or row.get("name") or "",
                "transaction_date": str(row.get("transaction_date") or ""),
                "status": status,
                "opportunity_type": row.get("opportunity_type") or "",
                "sales_stage": row.get("sales_stage") or "",
                "expected_closing": str(row.get("expected_closing") or ""),
                "probability": probability,
                "currency": row.get("currency") or "",
                "amount": amount,
                "owner": row.get("opportunity_owner") or "",
                "overdue": overdue,
            }
        )
    return success(
        {
            "opportunities": opportunities[:limit],
            **counts,
            "weighted_by_currency": [
                {"currency": currency, "amount": round(amount, 2)}
                for currency, amount in sorted(weighted.items())
            ],
            "truncated": truncated,
        }
    )


def customer_account_team(customer: str) -> dict:
    """Return privacy-safe standard Sales Team ownership for a Customer."""
    denied = require_sales_role(frappe)
    if denied:
        return denied
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    if not _optional_doctype_exists("Sales Team"):
        return success({"members": [], "allocated_percentage": 0.0})
    customers = frappe.get_list(
        "Customer",
        filters=[["name", "=", customer]],
        fields=["name"],
        limit_page_length=1,
    )
    if not customers:
        return failure("Customer not found.", code="VALIDATION_UNKNOWN_CUSTOMER")
    try:
        rows = frappe.get_list(
            "Sales Team",
            filters=[
                ["parent", "=", customer],
                ["parenttype", "=", "Customer"],
            ],
            fields=_existing_fields(
                "Sales Team",
                ["sales_person", "contact_no", "allocated_percentage"],
            ),
            order_by="idx asc",
            limit_page_length=100,
        )
    except Exception:
        rows = []
    members = [
        {
            "sales_person": row.get("sales_person") or "",
            "contact_no": row.get("contact_no") or "",
            "allocated_percentage": float(row.get("allocated_percentage") or 0),
        }
        for row in rows
    ]
    return success(
        {
            "members": members,
            "allocated_percentage": sum(
                row["allocated_percentage"] for row in members
            ),
        }
    )


def customer_returns(customer: str, limit: int = 10) -> dict:
    """Return submitted standard credit notes grouped by currency."""
    denied = require_sales_role(frappe)
    if denied:
        return denied
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    customers = frappe.get_list(
        "Customer",
        filters=[["name", "=", customer]],
        fields=["name"],
        limit_page_length=1,
    )
    if not customers:
        return failure("Customer not found.", code="VALIDATION_UNKNOWN_CUSTOMER")
    if not _optional_doctype_exists("Sales Invoice"):
        return success({"returns": [], "totals": [], "truncated": False})
    try:
        rows = frappe.get_list(
            "Sales Invoice",
            filters=[
                ["customer", "=", customer],
                ["docstatus", "=", 1],
                ["is_return", "=", 1],
            ],
            fields=_existing_fields(
                "Sales Invoice",
                [
                    "name",
                    "posting_date",
                    "return_against",
                    "company",
                    "currency",
                    "grand_total",
                    "rounded_total",
                    "outstanding_amount",
                    "status",
                    "remarks",
                ],
            ),
            order_by="posting_date desc, creation desc",
            limit_page_length=501,
        )
    except Exception:
        rows = []
    truncated = len(rows) > 500
    rows = rows[:500]
    totals: dict[str, dict] = {}
    returns = []
    for row in rows:
        currency = str(row.get("currency") or "Company Currency")
        raw_total = row.get("rounded_total")
        if raw_total in (None, 0, 0.0):
            raw_total = row.get("grand_total")
        amount = abs(float(raw_total or 0))
        summary = totals.setdefault(currency, {"amount": 0.0, "count": 0})
        summary["amount"] += amount
        summary["count"] += 1
        returns.append(
            {
                "name": row.get("name") or "",
                "posting_date": str(row.get("posting_date") or ""),
                "return_against": row.get("return_against") or "",
                "company": row.get("company") or "",
                "currency": row.get("currency") or "",
                "amount": amount,
                "outstanding_amount": abs(
                    float(row.get("outstanding_amount") or 0)
                ),
                "status": row.get("status") or "",
                "remarks": row.get("remarks") or "",
            }
        )
    return success(
        {
            "returns": returns[:limit],
            "totals": [
                {
                    "currency": currency,
                    "amount": round(summary["amount"], 2),
                    "count": summary["count"],
                }
                for currency, summary in sorted(totals.items())
            ],
            "truncated": truncated,
        }
    )


def customer_receipts(customer: str, limit: int = 10) -> dict:
    """Return submitted customer receipts and invoice allocations by currency."""
    denied = require_sales_role(frappe)
    if denied:
        return denied
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    customers = frappe.get_list(
        "Customer",
        filters=[["name", "=", customer]],
        fields=["name"],
        limit_page_length=1,
    )
    if not customers:
        return failure("Customer not found.", code="VALIDATION_UNKNOWN_CUSTOMER")
    empty = {"receipts": [], "totals": [], "truncated": False}
    if not _optional_doctype_exists("Payment Entry"):
        return success(empty)

    try:
        rows = frappe.get_list(
            "Payment Entry",
            filters=[
                ["party_type", "=", "Customer"],
                ["party", "=", customer],
                ["payment_type", "=", "Receive"],
                ["docstatus", "=", 1],
            ],
            fields=_existing_fields(
                "Payment Entry",
                [
                    "name",
                    "posting_date",
                    "company",
                    "mode_of_payment",
                    "paid_from_account_currency",
                    "paid_amount",
                    "received_amount",
                    "unallocated_amount",
                    "reference_no",
                    "reference_date",
                    "clearance_date",
                    "status",
                    "remarks",
                ],
            ),
            order_by="posting_date desc, creation desc",
            limit_page_length=501,
        )
    except Exception:
        return success(empty)
    truncated = len(rows) > 500
    rows = rows[:500]
    visible_rows = rows[:limit]
    payment_names = [str(row.get("name") or "") for row in visible_rows]
    references_by_payment: dict[str, list[dict]] = {}
    if (
        payment_names
        and _optional_doctype_exists("Payment Entry Reference")
    ):
        try:
            references = frappe.get_list(
                "Payment Entry Reference",
                filters=[
                    ["parent", "in", payment_names],
                    ["parenttype", "=", "Payment Entry"],
                    ["reference_doctype", "=", "Sales Invoice"],
                ],
                fields=_existing_fields(
                    "Payment Entry Reference",
                    [
                        "parent",
                        "reference_doctype",
                        "reference_name",
                        "allocated_amount",
                    ],
                ),
                order_by="parent asc, idx asc",
                limit_page_length=500,
            )
        except Exception:
            references = []
        for row in references:
            parent = str(row.get("parent") or "")
            references_by_payment.setdefault(parent, []).append(
                {
                    "doctype": row.get("reference_doctype") or "",
                    "name": row.get("reference_name") or "",
                    "allocated_amount": float(
                        row.get("allocated_amount") or 0
                    ),
                }
            )

    totals: dict[str, dict] = {}
    for row in rows:
        currency = str(
            row.get("paid_from_account_currency") or "Company Currency"
        )
        amount = float(row.get("paid_amount") or row.get("received_amount") or 0)
        summary = totals.setdefault(currency, {"amount": 0.0, "count": 0})
        summary["amount"] += amount
        summary["count"] += 1

    receipts = []
    for row in visible_rows:
        name = str(row.get("name") or "")
        receipts.append(
            {
                "name": name,
                "posting_date": str(row.get("posting_date") or ""),
                "company": row.get("company") or "",
                "mode_of_payment": row.get("mode_of_payment") or "",
                "currency": row.get("paid_from_account_currency") or "",
                "amount": float(
                    row.get("paid_amount")
                    or row.get("received_amount")
                    or 0
                ),
                "unallocated_amount": float(
                    row.get("unallocated_amount") or 0
                ),
                "reference_no": row.get("reference_no") or "",
                "reference_date": str(row.get("reference_date") or ""),
                "clearance_date": str(row.get("clearance_date") or ""),
                "status": row.get("status") or "",
                "remarks": row.get("remarks") or "",
                "references": references_by_payment.get(name, []),
            }
        )
    return success(
        {
            "receipts": receipts,
            "totals": [
                {
                    "currency": currency,
                    "amount": round(summary["amount"], 2),
                    "count": summary["count"],
                }
                for currency, summary in sorted(totals.items())
            ],
            "truncated": truncated,
        }
    )


def customer_loyalty(customer: str, limit: int = 20) -> dict:
    """Return standard loyalty balances and upcoming expiries by program."""
    denied = require_sales_role(frappe)
    if denied:
        return denied
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if not frappe.get_list(
        "Customer",
        filters=[["name", "=", customer]],
        fields=["name"],
        limit_page_length=1,
    ):
        return failure("Customer not found.", code="VALIDATION_UNKNOWN_CUSTOMER")
    empty = {"programs": [], "entries": [], "truncated": False}
    if not _optional_doctype_exists("Loyalty Point Entry"):
        return success(empty)
    fields = _existing_fields(
        "Loyalty Point Entry",
        [
            "name",
            "loyalty_program",
            "loyalty_program_tier",
            "loyalty_points",
            "purchase_amount",
            "expiry_date",
            "posting_date",
            "company",
            "invoice_type",
            "invoice",
        ],
    )
    try:
        rows = frappe.get_list(
            "Loyalty Point Entry",
            filters=[["customer", "=", customer]],
            fields=fields,
            order_by="posting_date desc, creation desc",
            limit_page_length=501,
        )
    except Exception:
        return success(empty)
    truncated = len(rows) > 500
    rows = rows[:500]
    today = date.today()
    programs: dict[tuple[str, str], dict] = {}
    for row in rows:
        expiry = _date_value(row.get("expiry_date"))
        # Match ERPNext's own loyalty balance query, which only includes
        # entries whose standard expiry date is still current.
        active = expiry is not None and expiry >= today
        key = (
            str(row.get("loyalty_program") or ""),
            str(row.get("company") or ""),
        )
        summary = programs.setdefault(
            key,
            {
                "loyalty_program": key[0],
                "company": key[1],
                "tier": row.get("loyalty_program_tier") or "",
                "balance": 0,
                "expiring_points": 0,
                "next_expiry_date": "",
            },
        )
        points = int(row.get("loyalty_points") or 0)
        if active:
            summary["balance"] += points
        if points > 0 and expiry and today <= expiry <= today + timedelta(
            days=365
        ):
            summary["expiring_points"] += points
            current = summary["next_expiry_date"]
            if not current or str(expiry) < current:
                summary["next_expiry_date"] = str(expiry)
    entries = [
        {
            "name": row.get("name") or "",
            "program": row.get("loyalty_program") or "",
            "tier": row.get("loyalty_program_tier") or "",
            "points": int(row.get("loyalty_points") or 0),
            "purchase_amount": float(row.get("purchase_amount") or 0),
            "posting_date": str(row.get("posting_date") or ""),
            "expiry_date": str(row.get("expiry_date") or ""),
            "expired": bool(
                _date_value(row.get("expiry_date"))
                and _date_value(row.get("expiry_date")) < today
            ),
            "company": row.get("company") or "",
            "invoice_type": row.get("invoice_type") or "",
            "invoice": row.get("invoice") or "",
        }
        for row in rows[:limit]
    ]
    return success(
        {
            "programs": sorted(
                programs.values(),
                key=lambda row: (row["loyalty_program"], row["company"]),
            ),
            "entries": entries,
            "truncated": truncated,
        }
    )


def customer_dunnings(customer: str, limit: int = 10) -> dict:
    """Return submitted standard Dunning notices and invoice references."""
    denied = require_sales_role(frappe)
    if denied:
        return denied
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if not frappe.get_list(
        "Customer",
        filters=[["name", "=", customer]],
        fields=["name"],
        limit_page_length=1,
    ):
        return failure("Customer not found.", code="VALIDATION_UNKNOWN_CUSTOMER")
    empty = {
        "dunnings": [],
        "totals": [],
        "unresolved_count": 0,
        "truncated": False,
    }
    if not _optional_doctype_exists("Dunning"):
        return success(empty)
    try:
        rows = frappe.get_list(
            "Dunning",
            filters=[["customer", "=", customer], ["docstatus", "=", 1]],
            fields=_existing_fields(
                "Dunning",
                [
                    "name",
                    "posting_date",
                    "company",
                    "currency",
                    "status",
                    "dunning_type",
                    "rate_of_interest",
                    "dunning_fee",
                    "total_interest",
                    "total_outstanding",
                    "dunning_amount",
                ],
            ),
            order_by="posting_date desc, creation desc",
            limit_page_length=501,
        )
    except Exception:
        return success(empty)
    truncated = len(rows) > 500
    rows = rows[:500]
    visible = rows[:limit]
    invoices_by_dunning: dict[str, list[dict]] = {}
    if visible and _optional_doctype_exists("Overdue Payment"):
        names = [str(row.get("name") or "") for row in visible]
        try:
            payments = frappe.get_list(
                "Overdue Payment",
                filters=[
                    ["parent", "in", names],
                    ["parenttype", "=", "Dunning"],
                ],
                fields=_existing_fields(
                    "Overdue Payment",
                    [
                        "parent",
                        "sales_invoice",
                        "due_date",
                        "outstanding",
                        "overdue_days",
                        "interest",
                        "dunning_level",
                    ],
                ),
                order_by="parent asc, due_date asc, idx asc",
                limit_page_length=500,
            )
        except Exception:
            payments = []
        for row in payments:
            invoices_by_dunning.setdefault(
                str(row.get("parent") or ""), []
            ).append(
                {
                    "invoice": row.get("sales_invoice") or "",
                    "due_date": str(row.get("due_date") or ""),
                    "outstanding": float(row.get("outstanding") or 0),
                    "overdue_days": int(float(row.get("overdue_days") or 0)),
                    "interest": float(row.get("interest") or 0),
                    "level": int(row.get("dunning_level") or 0),
                }
            )
    totals: dict[str, dict] = {}
    for row in rows:
        currency = str(row.get("currency") or "Company Currency")
        summary = totals.setdefault(
            currency,
            {"outstanding": 0.0, "dunning_amount": 0.0, "count": 0},
        )
        summary["outstanding"] += float(row.get("total_outstanding") or 0)
        summary["dunning_amount"] += float(row.get("dunning_amount") or 0)
        summary["count"] += 1
    return success(
        {
            "dunnings": [
                {
                    "name": row.get("name") or "",
                    "posting_date": str(row.get("posting_date") or ""),
                    "company": row.get("company") or "",
                    "currency": row.get("currency") or "",
                    "status": row.get("status") or "",
                    "type": row.get("dunning_type") or "",
                    "interest_rate": float(
                        row.get("rate_of_interest") or 0
                    ),
                    "fee": float(row.get("dunning_fee") or 0),
                    "interest": float(row.get("total_interest") or 0),
                    "outstanding": float(
                        row.get("total_outstanding") or 0
                    ),
                    "amount": float(row.get("dunning_amount") or 0),
                    "invoices": invoices_by_dunning.get(
                        str(row.get("name") or ""), []
                    ),
                }
                for row in visible
            ],
            "totals": [
                {"currency": currency, **summary}
                for currency, summary in sorted(totals.items())
            ],
            "unresolved_count": sum(
                str(row.get("status") or "") == "Unresolved" for row in rows
            ),
            "truncated": truncated,
        }
    )


def customer_maintenance(customer: str, limit: int = 10) -> dict:
    """Return submitted standard Maintenance Schedule obligations."""
    denied = require_sales_role(frappe)
    if denied:
        return denied
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if not frappe.get_list(
        "Customer",
        filters=[["name", "=", customer]],
        fields=["name"],
        limit_page_length=1,
    ):
        return failure("Customer not found.", code="VALIDATION_UNKNOWN_CUSTOMER")
    empty = {
        "schedules": [],
        "pending_visits": 0,
        "overdue_visits": 0,
        "completed_visits": 0,
        "truncated": False,
    }
    required = ["Maintenance Schedule", "Maintenance Schedule Detail"]
    if any(not _optional_doctype_exists(row) for row in required):
        return success(empty)
    try:
        rows = frappe.get_list(
            "Maintenance Schedule",
            filters=[["customer", "=", customer], ["docstatus", "=", 1]],
            fields=_existing_fields(
                "Maintenance Schedule",
                [
                    "name",
                    "status",
                    "transaction_date",
                    "customer_name",
                    "company",
                    "contact_person",
                    "territory",
                ],
            ),
            order_by="modified desc",
            limit_page_length=201,
        )
    except Exception:
        return success(empty)
    truncated = len(rows) > 200
    rows = rows[:200]
    names = [str(row.get("name") or "") for row in rows if row.get("name")]
    if not names:
        return success(empty)
    try:
        detail_rows = frappe.get_list(
            "Maintenance Schedule Detail",
            filters=[
                ["parent", "in", names],
                ["parenttype", "=", "Maintenance Schedule"],
            ],
            fields=_existing_fields(
                "Maintenance Schedule Detail",
                [
                    "parent",
                    "item_code",
                    "item_name",
                    "scheduled_date",
                    "actual_date",
                    "sales_person",
                    "serial_no",
                    "completion_status",
                ],
            ),
            order_by="scheduled_date asc, idx asc",
            limit_page_length=5001,
        )
    except Exception:
        return success(empty)
    truncated = truncated or len(detail_rows) > 5000
    detail_rows = detail_rows[:5000]
    today = date.today()
    details_by_parent: dict[str, list[dict]] = {}
    pending_visits = 0
    overdue_visits = 0
    completed_visits = 0
    for detail in detail_rows:
        status = str(detail.get("completion_status") or "Pending")
        completed = status == "Fully Completed"
        scheduled = _date_value(detail.get("scheduled_date"))
        overdue = bool(not completed and scheduled and scheduled < today)
        pending_visits += int(not completed)
        overdue_visits += int(overdue)
        completed_visits += int(completed)
        parent = str(detail.get("parent") or "")
        details_by_parent.setdefault(parent, []).append(
            {
                "item_code": detail.get("item_code") or "",
                "item_name": detail.get("item_name") or "",
                "scheduled_date": str(detail.get("scheduled_date") or ""),
                "actual_date": str(detail.get("actual_date") or ""),
                "sales_person": detail.get("sales_person") or "",
                "serial_no": detail.get("serial_no") or "",
                "status": status,
                "overdue": overdue,
            }
        )
    schedules = []
    for row in rows:
        name = str(row.get("name") or "")
        visits = details_by_parent.get(name, [])
        if not visits:
            continue
        incomplete = [
            visit
            for visit in visits
            if visit["status"] != "Fully Completed"
        ]
        schedules.append(
            {
                "name": name,
                "status": row.get("status") or "",
                "transaction_date": str(row.get("transaction_date") or ""),
                "company": row.get("company") or "",
                "contact": row.get("contact_person") or "",
                "territory": row.get("territory") or "",
                "next_visit": next(
                    (
                        visit["scheduled_date"]
                        for visit in incomplete
                        if visit["scheduled_date"]
                    ),
                    "",
                ),
                "pending_visits": len(incomplete),
                "overdue_visits": sum(
                    visit["overdue"] for visit in visits
                ),
                "visits": visits,
            }
        )
    schedules.sort(
        key=lambda row: (
            row["pending_visits"] == 0,
            row["next_visit"] or "9999-12-31",
            row["name"],
        )
    )
    return success(
        {
            "schedules": schedules[:limit],
            "pending_visits": pending_visits,
            "overdue_visits": overdue_visits,
            "completed_visits": completed_visits,
            "truncated": truncated or len(schedules) > limit,
        }
    )


def customer_warranty_claims(customer: str, limit: int = 10) -> dict:
    """Return standard Warranty Claims for a sales-visible customer."""
    denied = require_sales_role(frappe)
    if denied:
        return denied
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        return failure("limit must be an integer.", code="VALIDATION_BAD_LIMIT")
    if not frappe.get_list(
        "Customer",
        filters=[["name", "=", customer]],
        fields=["name"],
        limit_page_length=1,
    ):
        return failure("Customer not found.", code="VALIDATION_UNKNOWN_CUSTOMER")
    empty = {
        "claims": [],
        "open_count": 0,
        "resolved_count": 0,
        "under_coverage_count": 0,
        "truncated": False,
    }
    if not _optional_doctype_exists("Warranty Claim"):
        return success(empty)
    try:
        rows = frappe.get_list(
            "Warranty Claim",
            filters=[
                ["customer", "=", customer],
                ["status", "!=", "Cancelled"],
            ],
            fields=_existing_fields(
                "Warranty Claim",
                [
                    "name",
                    "status",
                    "complaint_date",
                    "serial_no",
                    "item_code",
                    "item_name",
                    "warranty_amc_status",
                    "warranty_expiry_date",
                    "amc_expiry_date",
                    "complaint",
                    "resolution_date",
                    "resolved_by",
                    "resolution_details",
                    "contact_person",
                    "territory",
                    "company",
                ],
            ),
            order_by="complaint_date desc, creation desc",
            limit_page_length=101,
        )
    except Exception:
        return success(empty)
    truncated = len(rows) > 100
    rows = rows[:100]
    closed_statuses = {"Closed", "Cancelled"}
    covered_statuses = {"Under Warranty", "Under AMC"}
    return success(
        {
            "claims": [
                {
                    "name": row.get("name") or "",
                    "status": row.get("status") or "",
                    "complaint_date": str(row.get("complaint_date") or ""),
                    "serial_no": row.get("serial_no") or "",
                    "item_code": row.get("item_code") or "",
                    "item_name": row.get("item_name") or "",
                    "coverage": row.get("warranty_amc_status") or "",
                    "warranty_expiry_date": str(
                        row.get("warranty_expiry_date") or ""
                    ),
                    "amc_expiry_date": str(
                        row.get("amc_expiry_date") or ""
                    ),
                    "complaint": row.get("complaint") or "",
                    "resolution_date": str(
                        row.get("resolution_date") or ""
                    ),
                    "resolved_by": row.get("resolved_by") or "",
                    "resolution": row.get("resolution_details") or "",
                    "contact": row.get("contact_person") or "",
                    "territory": row.get("territory") or "",
                    "company": row.get("company") or "",
                }
                for row in rows[:limit]
            ],
            "open_count": sum(
                str(row.get("status") or "") not in closed_statuses
                for row in rows
            ),
            "resolved_count": sum(
                str(row.get("status") or "") == "Closed" for row in rows
            ),
            "under_coverage_count": sum(
                str(row.get("warranty_amc_status") or "")
                in covered_statuses
                for row in rows
            ),
            "truncated": truncated or len(rows) > limit,
        }
    )


def _empty_buying_history() -> dict:
    return {"currencies": [], "scanned_invoices": 0, "truncated": False}


def _optional_doctype_exists(doctype: str) -> bool:
    try:
        exists = frappe.db.exists("DocType", doctype)
    except Exception:
        return False
    return isinstance(exists, bool | str) and bool(exists)


def _date_value(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except (TypeError, ValueError):
        return None
