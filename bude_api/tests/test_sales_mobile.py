from unittest.mock import MagicMock, patch

from bude_api.api import sales_mobile as sales_api


class _FakeValidationError(Exception):
    pass


class _FakePermissionError(Exception):
    pass


def _grant_sales_role(mock_frappe, roles=None, user="sales.user@example.com"):
    mock_frappe.session.user = user
    mock_frappe.get_roles.return_value = roles or ["Sales User"]
    mock_frappe.ValidationError = _FakeValidationError
    mock_frappe.PermissionError = _FakePermissionError


@patch("bude_api.api.sales_mobile.frappe")
def test_mobile_sales_endpoints_require_sales_role(mock_frappe):
    mock_frappe.session.user = "stock.user@example.com"
    mock_frappe.get_roles.return_value = ["Stock User"]

    results = [
        sales_api.masters(),
        sales_api.dashboard(),
        sales_api.customers(),
        sales_api.items(),
        sales_api.create_visit("CUST-001"),
        sales_api.create_quotation("CUST-001", [{"item_code": "ITEM-001", "qty": 1}]),
        sales_api.create_order("CUST-001", [{"item_code": "ITEM-001", "qty": 1}]),
    ]

    assert all(result["ok"] is False for result in results)
    assert all(result["code"] == "PERMISSION_DENIED" for result in results)
    mock_frappe.get_list.assert_not_called()
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.sales_mobile.frappe")
def test_masters_returns_standard_sales_masters(mock_frappe):
    _grant_sales_role(mock_frappe, roles=["Sales Manager"])

    def get_list(doctype, **kwargs):
        if doctype == "Sales Person":
            return [{"name": "SP-001", "sales_person_name": "Asha", "employee": "EMP-001"}]
        return [{"name": f"{doctype}-001"}]

    mock_frappe.get_list.side_effect = get_list

    result = sales_api.masters()

    assert result["ok"] is True
    assert result["data"]["companies"] == ["Company-001"]
    assert result["data"]["territories"] == ["Territory-001"]
    assert result["data"]["sales_persons"][0]["name"] == "SP-001"
    assert result["data"]["is_manager"] is True


@patch("bude_api.api.sales_mobile.frappe")
def test_customers_paginates_searches_and_counts(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.get_list.return_value = [{"name": "CUST-001", "customer_name": "Acme"}]
    mock_frappe.db.count.return_value = 4

    result = sales_api.customers(
        search="ac", territory="India", assigned_to_me=True, limit=25, offset=5
    )

    assert result["ok"] is True
    assert result["data"]["customers"][0]["name"] == "CUST-001"
    assert result["data"]["total"] == 4
    customer_call = next(
        call for call in mock_frappe.get_list.call_args_list if call.args[0] == "Customer"
    )
    _, kwargs = customer_call
    assert ["customer_name", "like", "%ac%"] in kwargs["filters"]
    assert ["territory", "=", "India"] in kwargs["filters"]
    assert ["owner", "=", "sales.user@example.com"] in kwargs["filters"]
    assert kwargs["limit_start"] == 5
    assert kwargs["limit_page_length"] == 25
    assert "customer_type" in kwargs["fields"]
    assert "disabled" in kwargs["fields"]


@patch("bude_api.api.sales_mobile.frappe")
def test_field_day_builds_offline_pack_from_standard_records(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.count.return_value = 1
    mock_frappe.db.exists.return_value = True
    mock_frappe.utils.now_datetime.return_value = "2026-08-04 08:00:00"

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [{"name": "CUST-001", "customer_name": "Acme", "territory": "South"}]
        if doctype == "Item":
            return [
                {
                    "name": "ITEM-001",
                    "item_code": "ITEM-001",
                    "item_name": "Widget",
                    "stock_uom": "Nos",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = sales_api.field_day("2026-08-04", "South")

    assert result["ok"] is True, result
    assert result["data"]["day"] == "2026-08-04"
    assert result["data"]["customers"][0]["name"] == "CUST-001"
    assert result["data"]["customers"][0]["suggested_sequence"] == 1
    assert result["data"]["items"][0]["item_code"] == "ITEM-001"


@patch("bude_api.api.sales_mobile.frappe")
def test_visit_check_in_records_accuracy_and_verification(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.exists.return_value = True
    mock_frappe.conf.get.side_effect = lambda key: {
        "bude_sales_visit_max_accuracy_m": 100,
        "bude_sales_visit_geofence_m": 250,
    }.get(key)
    mock_frappe.get_list.side_effect = lambda doctype, **kwargs: (
        [{"name": "CUST-001"}] if doctype == "Customer" else []
    )
    mock_frappe.utils.now_datetime.return_value = "2026-08-04 09:15:00"
    event = MagicMock()
    event.name = "EVENT-001"
    event.docstatus = 0
    mock_frappe.get_doc.return_value = event

    result = sales_api.visit_check_in("CUST-001", 12.9716, 77.5946, 12)

    assert result["ok"] is True, result
    assert result["data"]["event"] == "EVENT-001"
    assert result["data"]["verified"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "Event"
    assert "accuracy=12m" in payload["description"]
    event.insert.assert_called_once_with(ignore_permissions=False)


@patch("bude_api.api.sales_mobile.frappe")
def test_order_retry_with_same_request_id_creates_exactly_one_document(mock_frappe):
    _grant_sales_role(mock_frappe)
    stored_requests = []

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [{"name": "CUST-001"}]
        if doctype == "Item":
            return [{"item_code": "ITEM-001"}]
        if doctype == "Integration Request":
            return list(stored_requests)
        return []

    order = MagicMock()
    order.name = "SO-001"
    order.docstatus = 0

    def get_doc(value, *args):
        if isinstance(value, dict) and value.get("doctype") == "Sales Order":
            return order
        log = MagicMock()
        log.insert.side_effect = lambda **kwargs: stored_requests.append(
            {"output": value["output"]}
        )
        return log

    mock_frappe.get_list.side_effect = get_list
    mock_frappe.get_doc.side_effect = get_doc
    payload = [{"item_code": "ITEM-001", "qty": 2}]

    first = sales_api.create_order(
        "CUST-001", payload, client_request_id="offline-order-1"
    )
    replay = sales_api.create_order(
        "CUST-001", payload, client_request_id="offline-order-1"
    )

    assert first["data"]["name"] == "SO-001"
    assert replay["data"]["name"] == "SO-001"
    order.insert.assert_called_once_with(ignore_permissions=False)


@patch("bude_api.api.sales_mobile.frappe")
def test_collections_queue_scopes_rep_and_calculates_overdue(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.count.return_value = 1
    mock_frappe.get_list.return_value = [
        {
            "name": "SINV-001",
            "customer": "CUST-001",
            "customer_name": "Acme",
            "due_date": "2020-01-01",
            "currency": "USD",
            "outstanding_amount": 125,
            "grand_total": 200,
        }
    ]

    result = sales_api.collections_queue(overdue_only=True)

    assert result["ok"] is True
    assert result["data"]["invoices"][0]["overdue"] is True
    assert result["data"]["totals"][0]["outstanding"] == 125
    invoice_call = mock_frappe.get_list.call_args_list[0]
    assert ["owner", "=", "sales.user@example.com"] in invoice_call.kwargs["filters"]


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_detail_returns_standard_commercial_fields(mock_frappe):
    _grant_sales_role(mock_frappe)

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [
                {
                    "name": "CUST-001",
                    "customer_name": "Acme",
                    "default_currency": "INR",
                    "payment_terms": "Net 30",
                    "tax_id": "GST-1",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = sales_api.customer_detail("CUST-001")

    assert result["ok"] is True
    assert result["data"]["default_currency"] == "INR"
    customer_call = [
        call for call in mock_frappe.get_list.call_args_list if call.args[0] == "Customer"
    ][0]
    assert "payment_terms" in customer_call.kwargs["fields"]
    assert "customer_primary_address" in customer_call.kwargs["fields"]
    assert "market_segment" in customer_call.kwargs["fields"]


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_detail_reads_dynamic_link_child_fields_directly(mock_frappe):
    """Frappe v16 get_list() strips parent from Dynamic Link child rows."""
    _grant_sales_role(mock_frappe)

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [{"name": "CUST-001", "customer_name": "Acme"}]
        if doctype == "Contact":
            return [{"name": "CONTACT-001", "first_name": "Asha"}]
        if doctype == "Address":
            return [{"name": "ADDRESS-001", "city": "Kovai"}]
        return []

    def get_all(doctype, **kwargs):
        assert doctype == "Dynamic Link"
        parenttype = next(
            value for field, operator, value in kwargs["filters"] if field == "parenttype"
        )
        return [{"parent": f"{parenttype.upper()}-001"}]

    mock_frappe.get_list.side_effect = get_list
    mock_frappe.get_all.side_effect = get_all

    result = sales_api.customer_detail("CUST-001")

    assert result["ok"] is True
    assert result["data"]["contacts"][0]["name"] == "CONTACT-001"
    assert result["data"]["addresses"][0]["name"] == "ADDRESS-001"
    assert mock_frappe.get_all.call_count == 2


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_detail_returns_credit_limits_and_currency_aging(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.utils.nowdate.return_value = "2026-07-17"
    mock_frappe.db.exists.side_effect = lambda doctype, name=None: (
        name if doctype == "DocType" and name == "Customer Credit Limit" else False
    )

    def get_list(doctype, **kwargs):
        fields = kwargs.get("fields", [])
        if doctype == "Customer":
            return [{"name": "CUST-001", "customer_name": "Acme"}]
        if doctype == "Customer Credit Limit":
            return [
                {
                    "company": "Bude",
                    "credit_limit": 10000,
                    "bypass_credit_limit_check": 0,
                }
            ]
        if doctype == "Sales Invoice" and "due_date" in fields:
            return [
                {
                    "name": "SINV-CURRENT",
                    "due_date": "2026-07-20",
                    "currency": "INR",
                    "outstanding_amount": 100,
                },
                {
                    "name": "SINV-30",
                    "due_date": "2026-07-01",
                    "currency": "INR",
                    "outstanding_amount": 200,
                },
                {
                    "name": "SINV-90",
                    "due_date": "2026-05-01",
                    "currency": "USD",
                    "outstanding_amount": 50,
                },
                {
                    "name": "SINV-OLD",
                    "due_date": "2026-01-01",
                    "currency": "INR",
                    "outstanding_amount": 300,
                },
            ]
        if doctype == "Sales Invoice" and fields == ["outstanding_amount"]:
            return [{"outstanding_amount": 650}]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = sales_api.customer_detail("CUST-001")

    assert result["ok"] is True
    assert result["data"]["credit_limits"][0]["credit_limit"] == 10000
    aging = result["data"]["receivable_aging"]
    inr = next(row for row in aging["currencies"] if row["currency"] == "INR")
    usd = next(row for row in aging["currencies"] if row["currency"] == "USD")
    assert inr["current"] == 100
    assert inr["days_1_30"] == 200
    assert inr["days_91_plus"] == 300
    assert usd["days_61_90"] == 50
    assert aging["overdue_invoices"][0]["name"] == "SINV-OLD"
    assert aging["truncated"] is False


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_detail_flags_receivable_scan_truncation(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.utils.nowdate.return_value = "2026-07-17"

    def get_list(doctype, **kwargs):
        fields = kwargs.get("fields", [])
        if doctype == "Customer":
            return [{"name": "CUST-001", "customer_name": "Acme"}]
        if doctype == "Sales Invoice" and "due_date" in fields:
            return [
                {
                    "name": f"SINV-{index:04d}",
                    "due_date": "2026-07-20",
                    "currency": "INR",
                    "outstanding_amount": 1,
                }
                for index in range(501)
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = sales_api.customer_detail("CUST-001")

    aging = result["data"]["receivable_aging"]
    assert aging["scanned_count"] == 500
    assert aging["truncated"] is True
    assert aging["currencies"][0]["total"] == 500


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_buying_history_groups_items_by_currency(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [{"name": "CUST-001"}]
        if doctype == "Sales Invoice":
            return [
                {
                    "name": "SINV-002",
                    "posting_date": "2026-07-15",
                    "currency": "USD",
                    "status": "Paid",
                },
                {
                    "name": "SINV-001",
                    "posting_date": "2026-07-01",
                    "currency": "EUR",
                    "status": "Paid",
                },
            ]
        if doctype == "Sales Invoice Item":
            return [
                {
                    "parent": "SINV-002",
                    "item_code": "ITEM-1",
                    "item_name": "Widget",
                    "qty": 2,
                    "uom": "Nos",
                    "net_amount": 100,
                },
                {
                    "parent": "SINV-002",
                    "item_code": "ITEM-1",
                    "item_name": "Widget",
                    "qty": 1,
                    "uom": "Nos",
                    "net_amount": 50,
                },
                {
                    "parent": "SINV-001",
                    "item_code": "ITEM-2",
                    "item_name": "Cable",
                    "qty": 4,
                    "uom": "Nos",
                    "net_amount": 80,
                },
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = sales_api.customer_buying_history("CUST-001")

    assert result["ok"] is True
    usd = next(row for row in result["data"]["currencies"] if row["currency"] == "USD")
    assert usd["items"][0]["quantity"] == 3
    assert usd["items"][0]["net_amount"] == 150
    assert usd["items"][0]["invoice_count"] == 1
    assert result["data"]["scanned_invoices"] == 2


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_buying_history_is_empty_when_optional_schema_is_missing(
    mock_frappe,
):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.exists.return_value = False

    result = sales_api.customer_buying_history("CUST-001")

    assert result["ok"] is True
    assert result["data"]["currencies"] == []
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_fulfillment_returns_delivery_progress(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [{"name": "CUST-001"}]
        if doctype == "Sales Order":
            return [
                {
                    "name": "SO-001",
                    "transaction_date": "2026-07-01",
                    "delivery_date": "2020-07-10",
                    "currency": "USD",
                    "grand_total": 1000,
                    "status": "To Deliver and Bill",
                    "per_delivered": 40,
                    "per_billed": 20,
                },
                {
                    "name": "SO-002",
                    "transaction_date": "2026-07-05",
                    "delivery_date": "2026-08-10",
                    "currency": "USD",
                    "grand_total": 500,
                    "status": "Completed",
                    "per_delivered": 100,
                    "per_billed": 100,
                },
            ]
        if doctype == "Delivery Note":
            return [
                {
                    "name": "DN-001",
                    "posting_date": "2026-07-16",
                    "currency": "USD",
                    "grand_total": 400,
                    "status": "Completed",
                    "per_billed": 50,
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = sales_api.customer_fulfillment("CUST-001")

    assert result["ok"] is True
    assert result["data"]["open_orders"] == 1
    assert result["data"]["overdue_orders"] == 1
    assert result["data"]["orders"][0]["overdue"] is True
    assert result["data"]["recent_deliveries"][0]["name"] == "DN-001"


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_fulfillment_is_empty_when_sales_orders_are_unavailable(
    mock_frappe,
):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.exists.return_value = False

    result = sales_api.customer_fulfillment("CUST-001")

    assert result["ok"] is True
    assert result["data"]["orders"] == []
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.sales_mobile.frappe")
def test_items_adds_price_and_stock(mock_frappe):
    _grant_sales_role(mock_frappe)

    def get_list(doctype, **kwargs):
        if doctype == "Item":
            return [
                {
                    "item_code": "ITEM-001",
                    "item_name": "Widget",
                    "item_group": "Products",
                    "stock_uom": "Nos",
                }
            ]
        if doctype == "Item Price":
            return [{"item_code": "ITEM-001", "price_list_rate": 99.5, "currency": "INR"}]
        if doctype == "Bin":
            return [
                {"item_code": "ITEM-001", "actual_qty": 3},
                {"item_code": "ITEM-001", "actual_qty": 2},
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    mock_frappe.db.count.return_value = 1

    result = sales_api.items(search="wid", price_list="Retail", warehouse="Stores - A")

    assert result["ok"] is True
    item = result["data"]["items"][0]
    assert item["rate"] == 99.5
    assert item["currency"] == "INR"
    assert item["available_qty"] == 5.0


@patch("bude_api.api.sales_mobile.frappe")
def test_create_visit_inserts_event_and_followup(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.get_list.return_value = [{"name": "CUST-001"}]
    mock_frappe.utils.now_datetime.return_value = "2026-07-12 10:00:00"
    event = MagicMock(name="event")
    event.name = "EV-001"
    event.docstatus = 0
    todo = MagicMock(name="todo")
    todo.name = "TODO-001"
    todo.docstatus = 0
    mock_frappe.get_doc.side_effect = [event, todo]

    result = sales_api.create_visit(
        customer="CUST-001",
        notes="Met buyer",
        next_follow_up="2026-07-15",
        latitude=11.1,
        longitude=77.2,
    )

    assert result["ok"] is True
    event_payload = mock_frappe.get_doc.call_args_list[0].args[0]
    todo_payload = mock_frappe.get_doc.call_args_list[1].args[0]
    assert event_payload["doctype"] == "Event"
    assert event_payload["event_participants"][0]["reference_docname"] == "CUST-001"
    assert "Location: 11.1, 77.2" in event_payload["description"]
    assert todo_payload["doctype"] == "ToDo"
    assert todo_payload["reference_name"] == "CUST-001"
    event.insert.assert_called_once_with(ignore_permissions=False)
    todo.insert.assert_called_once_with(ignore_permissions=False)


@patch("bude_api.api.sales_mobile.frappe")
def test_create_order_maps_to_standard_sales_order_and_submits_when_requested(mock_frappe):
    _grant_sales_role(mock_frappe)

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [{"name": "CUST-001"}]
        if doctype == "Item":
            return [{"item_code": "ITEM-001"}]
        return []

    mock_frappe.get_list.side_effect = get_list
    doc = MagicMock()
    doc.name = "SO-001"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = sales_api.create_order(
        customer="CUST-001",
        delivery_date="2026-07-20",
        company="Company A",
        price_list="Retail",
        submit=True,
        items=[{"item_code": "ITEM-001", "qty": 2, "rate": 50, "warehouse": "Stores - A"}],
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "Sales Order"
    assert payload["customer"] == "CUST-001"
    assert payload["delivery_date"] == "2026-07-20"
    assert payload["selling_price_list"] == "Retail"
    assert payload["items"][0] == {
        "item_code": "ITEM-001",
        "qty": 2.0,
        "rate": 50.0,
        "warehouse": "Stores - A",
    }
    doc.insert.assert_called_once_with(ignore_permissions=False)
    doc.submit.assert_called_once()


@patch("bude_api.api.sales_mobile.frappe")
def test_invoice_and_payment_require_accounts_or_manager_role(mock_frappe):
    _grant_sales_role(mock_frappe, roles=["Sales User"])

    invoice = sales_api.create_invoice("CUST-001", [{"item_code": "ITEM-001", "qty": 1}])
    payment = sales_api.record_payment("CUST-001", 10, "Cash")

    assert invoice["ok"] is False
    assert invoice["code"] == "PERMISSION_DENIED"
    assert payment["ok"] is False
    assert payment["code"] == "PERMISSION_DENIED"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.sales_mobile.frappe")
def test_record_payment_maps_to_standard_payment_entry(mock_frappe):
    _grant_sales_role(mock_frappe, roles=["Accounts User"])
    doc = MagicMock()
    doc.name = "PAY-001"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = sales_api.record_payment(
        customer="CUST-001",
        amount="125.50",
        mode_of_payment="Cash",
        reference_no="UPI-REF",
        reference_date="2026-07-12",
        invoice="SINV-001",
        company="Company A",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "Payment Entry"
    assert payload["payment_type"] == "Receive"
    assert payload["party"] == "CUST-001"
    assert payload["paid_amount"] == 125.5
    assert payload["references"][0]["reference_name"] == "SINV-001"
    doc.insert.assert_called_once_with(ignore_permissions=False)
    doc.submit.assert_called_once()


@patch("bude_api.api.sales_mobile.frappe")
def test_team_summary_requires_manager_and_groups_by_sales_team(mock_frappe):
    _grant_sales_role(mock_frappe, roles=["Sales Manager"])

    def get_list(doctype, **kwargs):
        if doctype == "Sales Order":
            return [
                {"name": "SO-001", "owner": "rep1@example.com", "grand_total": 100},
                {"name": "SO-002", "owner": "rep2@example.com", "grand_total": 50},
            ]
        if doctype == "Sales Team":
            return [
                {"parent": "SO-001", "sales_person": "Rep One"},
                {"parent": "SO-002", "sales_person": "Rep Two"},
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = sales_api.team_summary(from_date="2026-07-01", to_date="2026-07-31")

    assert result["ok"] is True
    assert result["data"]["rows"] == [
        {"sales_person": "Rep One", "orders": 1, "order_value": 100.0},
        {"sales_person": "Rep Two", "orders": 1, "order_value": 50.0},
    ]


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_quotation_guidance_classifies_next_actions(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [{"name": "CUST-001"}]
        if doctype == "Quotation":
            return [
                {
                    "name": "QTN-OPEN",
                    "transaction_date": "2026-07-01",
                    "valid_till": "2099-12-31",
                    "status": "Open",
                    "currency": "INR",
                    "grand_total": 100,
                },
                {
                    "name": "QTN-OLD",
                    "transaction_date": "2026-06-01",
                    "valid_till": "2000-01-01",
                    "status": "Open",
                    "currency": "INR",
                    "grand_total": 50,
                },
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = sales_api.customer_quotation_guidance("CUST-001")

    assert result["ok"] is True
    assert result["data"]["open"] == 1
    assert result["data"]["expired"] == 1
    assert result["data"]["quotations"][0]["recommended_action"] == "convert"
    assert result["data"]["quotations"][1]["recommended_action"] == "renew"
@patch("bude_api.api.sales_mobile.frappe")
def test_customer_item_pricing_classifies_validity(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [{"name": "CUST-001"}]
        if doctype == "Item Price":
            return [
                {
                    "name": "PRICE-1",
                    "item_code": "ITEM-1",
                    "item_name": "Widget",
                    "price_list": "Standard Selling",
                    "currency": "USD",
                    "price_list_rate": 25,
                    "uom": "Nos",
                    "valid_from": "2026-01-01",
                    "valid_upto": "2099-12-31",
                },
                {
                    "name": "PRICE-2",
                    "item_code": "ITEM-2",
                    "price_list_rate": 30,
                    "valid_upto": "2020-01-01",
                },
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = sales_api.customer_item_pricing("CUST-001")

    assert result["ok"] is True
    assert result["data"]["active"] == 1
    assert result["data"]["expired"] == 1
    assert result["data"]["prices"][0]["rate"] == 25


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_opportunities_returns_weighted_pipeline(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [{"name": "CUST-001"}]
        if doctype == "Opportunity":
            return [
                {
                    "name": "OPP-001",
                    "title": "Warehouse rollout",
                    "status": "Open",
                    "sales_stage": "Qualification",
                    "expected_closing": "2099-08-01",
                    "probability": 50,
                    "currency": "USD",
                    "opportunity_amount": 10000,
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = sales_api.customer_opportunities("CUST-001")

    assert result["ok"] is True
    assert result["data"]["open"] == 1
    assert result["data"]["weighted_by_currency"] == [
        {"currency": "USD", "amount": 5000.0}
    ]


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_account_team_returns_privacy_safe_allocations(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [{"name": "CUST-001"}]
        if doctype == "Sales Team":
            return [
                {
                    "sales_person": "Territory Lead",
                    "contact_no": "+91 555 0100",
                    "allocated_percentage": 60,
                    "commission_rate": 25,
                    "incentives": 1000,
                },
                {
                    "sales_person": "Account Executive",
                    "allocated_percentage": 40,
                },
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = sales_api.customer_account_team("CUST-001")

    assert result["ok"] is True
    assert result["data"]["allocated_percentage"] == 100
    assert result["data"]["members"][0]["sales_person"] == "Territory Lead"
    assert "commission_rate" not in result["data"]["members"][0]
    assert "incentives" not in result["data"]["members"][0]


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_returns_groups_submitted_credit_notes_by_currency(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [{"name": "CUST-001"}]
        if doctype == "Sales Invoice":
            return [
                {
                    "name": "SINV-RET-001",
                    "posting_date": "2026-07-18",
                    "return_against": "SINV-001",
                    "company": "Bude",
                    "currency": "USD",
                    "grand_total": -120,
                    "outstanding_amount": -20,
                    "status": "Return",
                },
                {
                    "name": "SINV-RET-002",
                    "posting_date": "2026-07-17",
                    "currency": "EUR",
                    "rounded_total": -80,
                    "status": "Return",
                },
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = sales_api.customer_returns("CUST-001")

    assert result["ok"] is True
    assert result["data"]["returns"][0]["amount"] == 120
    assert result["data"]["returns"][0]["outstanding_amount"] == 20
    assert result["data"]["totals"] == [
        {"currency": "EUR", "amount": 80.0, "count": 1},
        {"currency": "USD", "amount": 120.0, "count": 1},
    ]
    invoice_call = next(
        call
        for call in mock_frappe.get_list.call_args_list
        if call.args and call.args[0] == "Sales Invoice"
    )
    assert ["is_return", "=", 1] in invoice_call.kwargs["filters"]
    assert ["docstatus", "=", 1] in invoice_call.kwargs["filters"]


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_receipts_groups_currency_and_invoice_allocations(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [{"name": "CUST-001"}]
        if doctype == "Payment Entry":
            return [
                {
                    "name": "PAY-001",
                    "posting_date": "2026-07-18",
                    "company": "Bude",
                    "mode_of_payment": "Bank Transfer",
                    "paid_from_account_currency": "USD",
                    "paid_amount": 125,
                    "unallocated_amount": 25,
                    "reference_no": "BANK-001",
                    "status": "Submitted",
                },
                {
                    "name": "PAY-002",
                    "posting_date": "2026-07-17",
                    "paid_from_account_currency": "EUR",
                    "paid_amount": 80,
                },
            ]
        if doctype == "Payment Entry Reference":
            return [
                {
                    "parent": "PAY-001",
                    "reference_doctype": "Sales Invoice",
                    "reference_name": "SINV-001",
                    "allocated_amount": 100,
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = sales_api.customer_receipts("CUST-001")

    assert result["ok"] is True
    assert result["data"]["totals"] == [
        {"currency": "EUR", "amount": 80.0, "count": 1},
        {"currency": "USD", "amount": 125.0, "count": 1},
    ]
    receipt = result["data"]["receipts"][0]
    assert receipt["unallocated_amount"] == 25
    assert receipt["references"] == [
        {
            "doctype": "Sales Invoice",
            "name": "SINV-001",
            "allocated_amount": 100,
        }
    ]
    payment_call = next(
        call
        for call in mock_frappe.get_list.call_args_list
        if call.args and call.args[0] == "Payment Entry"
    )
    assert ["payment_type", "=", "Receive"] in payment_call.kwargs["filters"]
    assert ["docstatus", "=", 1] in payment_call.kwargs["filters"]


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_loyalty_excludes_expired_points_from_balance(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [{"name": "CUST-001"}]
        if doctype == "Loyalty Point Entry":
            return [
                {
                    "name": "LP-001",
                    "loyalty_program": "Gold",
                    "loyalty_program_tier": "Gold",
                    "loyalty_points": 120,
                    "posting_date": "2026-07-01",
                    "expiry_date": "2099-12-31",
                    "company": "Bude",
                    "invoice_type": "Sales Invoice",
                    "invoice": "SINV-001",
                },
                {
                    "name": "LP-OLD",
                    "loyalty_program": "Gold",
                    "loyalty_points": 40,
                    "posting_date": "2020-01-01",
                    "expiry_date": "2020-12-31",
                    "company": "Bude",
                },
                {
                    "name": "LP-REDEEM",
                    "loyalty_program": "Gold",
                    "loyalty_points": -20,
                    "posting_date": "2026-07-02",
                    "expiry_date": "2099-12-31",
                    "company": "Bude",
                },
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = sales_api.customer_loyalty("CUST-001")

    assert result["ok"] is True
    assert result["data"]["programs"][0]["balance"] == 100
    assert result["data"]["entries"][1]["points"] == 40
    assert result["data"]["entries"][1]["expired"] is True


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_dunnings_return_currency_totals_and_invoices(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [{"name": "CUST-001"}]
        if doctype == "Dunning":
            return [
                {
                    "name": "DUNN-001",
                    "posting_date": "2026-07-18",
                    "currency": "USD",
                    "status": "Unresolved",
                    "dunning_type": "Second Notice",
                    "rate_of_interest": 12,
                    "dunning_fee": 10,
                    "total_interest": 5,
                    "total_outstanding": 200,
                    "dunning_amount": 215,
                }
            ]
        if doctype == "Overdue Payment":
            return [
                {
                    "parent": "DUNN-001",
                    "sales_invoice": "SINV-001",
                    "due_date": "2026-06-01",
                    "outstanding": 200,
                    "overdue_days": "47",
                    "interest": 5,
                    "dunning_level": 2,
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = sales_api.customer_dunnings("CUST-001")

    assert result["ok"] is True
    assert result["data"]["unresolved_count"] == 1
    assert result["data"]["totals"] == [
        {
            "currency": "USD",
            "outstanding": 200.0,
            "dunning_amount": 215.0,
            "count": 1,
        }
    ]
    assert result["data"]["dunnings"][0]["invoices"][0]["invoice"] == "SINV-001"


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_maintenance_reports_overdue_standard_visits(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [{"name": "CUST-001"}]
        if doctype == "Maintenance Schedule":
            return [
                {
                    "name": "MAT-MSH-2026-00001",
                    "status": "Submitted",
                    "transaction_date": "2026-01-01",
                    "company": "Bude",
                }
            ]
        if doctype == "Maintenance Schedule Detail":
            return [
                {
                    "parent": "MAT-MSH-2026-00001",
                    "item_code": "ASSET-SERVICE",
                    "item_name": "Annual service",
                    "scheduled_date": "2020-01-01",
                    "completion_status": "Pending",
                    "serial_no": "SN-001",
                },
                {
                    "parent": "MAT-MSH-2026-00001",
                    "item_code": "ASSET-SERVICE",
                    "scheduled_date": "2020-02-01",
                    "actual_date": "2020-02-01",
                    "completion_status": "Fully Completed",
                },
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = sales_api.customer_maintenance("CUST-001")

    assert result["ok"] is True
    assert result["data"]["pending_visits"] == 1
    assert result["data"]["overdue_visits"] == 1
    assert result["data"]["completed_visits"] == 1
    schedule = result["data"]["schedules"][0]
    assert schedule["next_visit"] == "2020-01-01"
    assert schedule["visits"][0]["overdue"] is True
    assert schedule["visits"][0]["serial_no"] == "SN-001"


@patch("bude_api.api.sales_mobile.frappe")
def test_customer_warranty_claims_return_coverage_and_resolution(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Customer":
            return [{"name": "CUST-001"}]
        if doctype == "Warranty Claim":
            return [
                {
                    "name": "SER-WRN-2026-00001",
                    "status": "Work In Progress",
                    "complaint_date": "2026-07-18",
                    "serial_no": "SN-001",
                    "item_code": "ITEM-001",
                    "item_name": "Display",
                    "warranty_amc_status": "Under Warranty",
                    "warranty_expiry_date": "2027-01-01",
                    "complaint": "Screen flickers",
                    "company": "Bude",
                },
                {
                    "name": "SER-WRN-2026-00002",
                    "status": "Closed",
                    "complaint_date": "2026-07-01",
                    "warranty_amc_status": "Out of Warranty",
                    "resolution_date": "2026-07-02 10:00:00",
                    "resolved_by": "support@example.com",
                    "resolution_details": "Cable replaced",
                },
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = sales_api.customer_warranty_claims("CUST-001")

    assert result["ok"] is True
    assert result["data"]["open_count"] == 1
    assert result["data"]["resolved_count"] == 1
    assert result["data"]["under_coverage_count"] == 1
    claim = result["data"]["claims"][0]
    assert claim["coverage"] == "Under Warranty"
    assert claim["serial_no"] == "SN-001"
    assert claim["warranty_expiry_date"] == "2027-01-01"
