from unittest.mock import MagicMock, patch

from bude_api.api import sales as sales_api


class _FakeValidationError(Exception):
    pass


class _FakePermissionError(Exception):
    pass


def _grant_sales_role(mock_frappe):
    mock_frappe.session.user = "sales.user@example.com"
    mock_frappe.get_roles.return_value = ["Sales User"]
    mock_frappe.ValidationError = _FakeValidationError
    mock_frappe.PermissionError = _FakePermissionError


@patch("bude_api.api.sales.frappe")
def test_sales_endpoints_require_sales_role(mock_frappe):
    mock_frappe.session.user = "stock.user@example.com"
    mock_frappe.get_roles.return_value = ["Stock User"]

    results = [
        sales_api.item_price("ITEM-001"),
        sales_api.list_customers(),
        sales_api.create_order("CUST-001", [{"item_code": "ITEM-001", "qty": 1}]),
        sales_api.my_orders(),
        sales_api.create_invoice("CUST-001", [{"item_code": "ITEM-001", "qty": 1}]),
        sales_api.record_payment("CUST-001", 10, "Cash"),
    ]

    assert all(result["ok"] is False for result in results)
    assert all(result["code"] == "PERMISSION_DENIED" for result in results)
    mock_frappe.get_list.assert_not_called()
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.sales.frappe")
def test_item_price_returns_rate_and_available_qty(mock_frappe):
    _grant_sales_role(mock_frappe)

    def get_list(doctype, **kwargs):
        if doctype == "Item Price":
            return [{
                "price_list": "Retail",
                "price_list_rate": 99.5,
                "currency": "INR",
                "uom": "Nos",
            }]
        if doctype == "Bin":
            return [
                {"warehouse": "Stores - A", "actual_qty": 3, "projected_qty": 4},
                {"warehouse": "Stores - B", "actual_qty": 2, "projected_qty": 2},
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = sales_api.item_price("ITEM-001", price_list="Retail")

    assert result["ok"] is True
    assert result["data"]["rate"] == 99.5
    assert result["data"]["available_qty"] == 5.0
    assert result["data"]["projected_qty"] == 6.0


@patch("bude_api.api.sales.frappe")
def test_list_customers_paginates_and_searches(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.get_list.return_value = [
        {
            "name": "CUST-001",
            "customer_name": "Acme",
            "customer_group": "Commercial",
            "territory": "India",
        }
    ]
    mock_frappe.db.count.return_value = 3

    result = sales_api.list_customers(search="ac", limit=25, offset=5)

    assert result["ok"] is True
    assert result["data"]["customers"][0]["name"] == "CUST-001"
    assert result["data"]["total"] == 3
    _, kwargs = mock_frappe.get_list.call_args
    assert kwargs["limit_start"] == 5
    assert kwargs["limit_page_length"] == 25
    assert ["customer_name", "like", "%ac%"] in kwargs["filters"]
    mock_frappe.db.count.assert_called_once_with(
        "Customer",
        filters=[["customer_name", "like", "%ac%"]],
    )


@patch("bude_api.api.sales.frappe")
def test_list_customers_rejects_over_cap_limit(mock_frappe):
    _grant_sales_role(mock_frappe)

    result = sales_api.list_customers(limit=201)

    assert result["ok"] is False
    assert result["code"] == "PAGINATION_LIMIT_EXCEEDED"


@patch("bude_api.api.sales.frappe")
def test_create_order_inserts_standard_sales_order(mock_frappe):
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
    doc.docstatus = 0
    mock_frappe.get_doc.return_value = doc

    result = sales_api.create_order(
        customer="CUST-001",
        delivery_date="2026-07-08",
        company="Company A",
        price_list="Retail",
        items=[{"item_code": "ITEM-001", "qty": 2, "rate": 99, "warehouse": "Stores - A"}],
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "Sales Order"
    assert payload["customer"] == "CUST-001"
    assert payload["company"] == "Company A"
    assert payload["selling_price_list"] == "Retail"
    assert payload["items"] == [
        {"item_code": "ITEM-001", "qty": 2.0, "rate": 99.0, "warehouse": "Stores - A"}
    ]
    doc.insert.assert_called_once_with(ignore_permissions=False)
    doc.submit.assert_not_called()


@patch("bude_api.api.sales.frappe")
def test_my_orders_scopes_to_current_user(mock_frappe):
    _grant_sales_role(mock_frappe)
    mock_frappe.get_list.return_value = [{"name": "SO-001", "status": "Draft"}]
    mock_frappe.db.count.return_value = 7

    result = sales_api.my_orders(limit=10, offset=3)

    assert result["ok"] is True
    assert result["data"]["total"] == 7
    _, kwargs = mock_frappe.get_list.call_args
    assert ["owner", "=", "sales.user@example.com"] in kwargs["filters"]
    assert kwargs["limit_start"] == 3
    assert kwargs["limit_page_length"] == 10
    mock_frappe.db.count.assert_called_once()


@patch("bude_api.api.sales.frappe")
def test_create_invoice_inserts_and_submits_sales_invoice(mock_frappe):
    _grant_sales_role(mock_frappe)
    doc = MagicMock()
    doc.name = "SINV-001"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = sales_api.create_invoice(
        customer="CUST-001",
        sales_order="SO-001",
        items=[{"item_code": "ITEM-001", "qty": 1, "rate": 50}],
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "Sales Invoice"
    assert payload["items"][0]["sales_order"] == "SO-001"
    doc.insert.assert_called_once_with(ignore_permissions=False)
    doc.submit.assert_called_once()


@patch("bude_api.api.sales.frappe")
def test_record_payment_inserts_and_submits_payment_entry(mock_frappe):
    _grant_sales_role(mock_frappe)
    doc = MagicMock()
    doc.name = "PAY-001"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = sales_api.record_payment(
        party="CUST-001",
        paid_amount="125.50",
        mode_of_payment="Cash",
        reference_no="UPI-REF",
        reference_date="2026-07-06",
        sales_invoice="SINV-001",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "Payment Entry"
    assert payload["payment_type"] == "Receive"
    assert payload["paid_amount"] == 125.5
    assert payload["references"][0] == {
        "reference_doctype": "Sales Invoice",
        "reference_name": "SINV-001",
        "allocated_amount": 125.5,
    }
    doc.insert.assert_called_once_with(ignore_permissions=False)
    doc.submit.assert_called_once()
