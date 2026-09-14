from unittest.mock import MagicMock, patch

from bude_api.api import sales_orders as so_api


class _FakeValidationError(Exception):
    pass


class _FakePermissionError(Exception):
    pass


def _so_doc(status="To Deliver and Bill", company="Company A"):
    return {
        "name": "SO-001",
        "customer": "Acme",
        "transaction_date": "2026-06-01",
        "delivery_date": "2026-06-10",
        "status": status,
        "company": company,
    }


def _so_lines():
    return [
        {
            "parent": "SO-001",
            "name": "SOI-1",
            "item_code": "ITEM-1",
            "item_name": "Item 1",
            "qty": 5,
            "delivered_qty": 2,
            "stock_uom": "Nos",
            "warehouse": "Stores - A",
        },
        {
            "parent": "SO-001",
            "name": "SOI-2",
            "item_code": "ITEM-2",
            "item_name": "Item 2",
            "qty": 1,
            "delivered_qty": 0,
            "stock_uom": "Nos",
            "warehouse": "Stores - A",
        },
    ]


def _dispatch_items():
    return [
        {"sales_order_item": "SOI-1", "item_code": "ITEM-1", "qty": 3},
        {"sales_order_item": "SOI-2", "item_code": "ITEM-2", "qty": 1},
    ]


def _grant_stock_role(mock_frappe):
    mock_frappe.get_roles.return_value = ["Stock User"]
    mock_frappe.session.user = "warehouse.user@example.com"


def _get_list_side_effect(lines=None, sales_order=None):
    lines = lines or _so_lines()
    sales_order = sales_order or _so_doc()

    def get_list(doctype, **kwargs):
        if doctype == "Sales Order":
            return [sales_order]
        if doctype == "Sales Order Item":
            return lines
        if doctype == "Warehouse":
            filters = kwargs.get("filters") or []
            name = filters[0][2]
            parent = "Stores - A" if name == "Rack 1 - A" else None
            return [{"name": name, "company": "Company A", "parent_warehouse": parent}]
        if doctype == "Item":
            filters = kwargs.get("filters") or []
            codes = filters[0][2] if filters else []
            return [
                {
                    "item_code": code,
                    "has_batch_no": 0,
                    "has_serial_no": 0,
                    "create_new_batch": 0,
                }
                for code in codes
            ]
        return []

    return get_list


@patch("bude_api.api.sales_orders.frappe")
def test_list_open_filters_and_returns_pending_summary(mock_frappe):
    mock_frappe.get_list.side_effect = _get_list_side_effect()

    result = so_api.list_open(company="Company A", limit=10, offset=20)

    assert result["ok"] is True
    assert result["data"][0]["name"] == "SO-001"
    assert result["data"][0]["item_count"] == 2
    assert result["data"][0]["pending_qty"] == 4.0
    sales_order_call = [
        call for call in mock_frappe.get_list.call_args_list
        if call.args[0] == "Sales Order"
    ][0]
    _, kwargs = sales_order_call
    assert ["company", "=", "Company A"] in kwargs["filters"]
    assert kwargs["limit_start"] == 20
    assert kwargs["limit_page_length"] == 10


@patch("bude_api.api.sales_orders.frappe")
def test_list_open_rejects_bad_limit(mock_frappe):
    result = so_api.list_open(limit="bad")
    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_LIMIT"


@patch("bude_api.api.sales_orders.frappe")
def test_get_returns_only_pending_lines(mock_frappe):
    mock_frappe.get_list.side_effect = _get_list_side_effect(
        _so_lines()
        + [
            {
                "name": "SOI-DONE",
                "item_code": "DONE",
                "qty": 2,
                "delivered_qty": 2,
            }
        ]
    )

    result = so_api.get("SO-001")

    assert result["ok"] is True
    assert len(result["data"]["items"]) == 2
    assert result["data"]["items"][0]["sales_order_item"] == "SOI-1"
    assert result["data"]["items"][0]["pending_qty"] == 3.0


@patch("bude_api.api.sales_orders.frappe")
def test_create_delivery_note_requires_stock_role(mock_frappe):
    mock_frappe.get_roles.return_value = ["Sales User"]
    mock_frappe.session.user = "sales.user@example.com"

    result = so_api.create_delivery_note(
        sales_order="SO-001",
        source_warehouse="Stores - A",
        items=_dispatch_items(),
    )

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.sales_orders.frappe")
def test_create_delivery_note_maps_sales_order_lines(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.ValidationError = _FakeValidationError
    mock_frappe.get_list.side_effect = _get_list_side_effect()
    doc = MagicMock()
    doc.name = "DN-001"
    doc.docstatus = 1
    mock_frappe.get_doc.return_value = doc

    result = so_api.create_delivery_note(
        sales_order="SO-001",
        source_warehouse="Stores - A",
        source_location="Rack 1 - A",
        items=_dispatch_items(),
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args[0][0]
    assert payload["doctype"] == "Delivery Note"
    assert payload["customer"] == "Acme"
    assert payload["company"] == "Company A"
    assert payload["items"][0]["warehouse"] == "Rack 1 - A"
    assert payload["items"][0]["against_sales_order"] == "SO-001"
    assert payload["items"][0]["so_detail"] == "SOI-1"
    doc.insert.assert_called_once()
    doc.submit.assert_called_once()


@patch("bude_api.api.sales_orders.frappe")
def test_create_delivery_note_attaches_pod_files_to_delivery_note(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.ValidationError = _FakeValidationError
    mock_frappe.PermissionError = _FakePermissionError
    mock_frappe.get_list.side_effect = _get_list_side_effect()
    delivery_note = MagicMock()
    delivery_note.name = "DN-001"
    delivery_note.docstatus = 1
    photo_file = MagicMock()
    signature_file = MagicMock()
    mock_frappe.get_doc.side_effect = [delivery_note, photo_file, signature_file]

    result = so_api.create_delivery_note(
        sales_order="SO-001",
        source_warehouse="Stores - A",
        items=_dispatch_items(),
        pod_attachments=[
            {
                "type": "photo",
                "file_name": "delivery-photo.jpg",
                "content_base64": "cGhvdG8=",
            },
            {
                "type": "signature",
                "file_name": "signature.png",
                "content_base64": "c2lnbmF0dXJl",
            },
        ],
    )

    assert result["ok"] is True
    assert result["data"]["pod_attachments"] == 2
    file_payloads = [call.args[0] for call in mock_frappe.get_doc.call_args_list[1:]]
    assert file_payloads[0]["doctype"] == "File"
    assert file_payloads[0]["attached_to_doctype"] == "Delivery Note"
    assert file_payloads[0]["attached_to_name"] == "DN-001"
    assert file_payloads[0]["decode"] is True
    photo_file.insert.assert_called_once_with(ignore_permissions=False)
    signature_file.insert.assert_called_once_with(ignore_permissions=False)


@patch("bude_api.api.sales_orders.frappe")
def test_create_delivery_note_rejects_invalid_pod_base64_before_insert(mock_frappe):
    _grant_stock_role(mock_frappe)

    result = so_api.create_delivery_note(
        sales_order="SO-001",
        source_warehouse="Stores - A",
        items=_dispatch_items(),
        pod_attachments=[
            {
                "type": "photo",
                "file_name": "delivery-photo.jpg",
                "content_base64": "not base64!",
            }
        ],
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_FILE"
    mock_frappe.get_list.assert_not_called()
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.sales_orders.frappe")
def test_create_delivery_note_rejects_closed_sales_order(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = _get_list_side_effect(
        sales_order=_so_doc(status="Closed")
    )

    result = so_api.create_delivery_note(
        sales_order="SO-001",
        source_warehouse="Stores - A",
        items=_dispatch_items(),
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_SALES_ORDER_CLOSED"


@patch("bude_api.api.sales_orders.frappe")
def test_create_delivery_note_rejects_company_mismatch(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = _get_list_side_effect(
        sales_order=_so_doc(company="Company B")
    )

    result = so_api.create_delivery_note(
        sales_order="SO-001",
        source_warehouse="Stores - A",
        company="Company A",
        items=_dispatch_items(),
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_SO_COMPANY_MISMATCH"


@patch("bude_api.api.sales_orders.frappe")
def test_create_delivery_note_rejects_under_or_over_pick(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = _get_list_side_effect()

    result = so_api.create_delivery_note(
        sales_order="SO-001",
        source_warehouse="Stores - A",
        items=[
            {"sales_order_item": "SOI-1", "item_code": "ITEM-1", "qty": 2},
            {"sales_order_item": "SOI-2", "item_code": "ITEM-2", "qty": 1},
        ],
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_EXACT_QTY_REQUIRED"


@patch("bude_api.api.sales_orders.frappe")
def test_create_delivery_note_rejects_missing_line(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.get_list.side_effect = _get_list_side_effect()

    result = so_api.create_delivery_note(
        sales_order="SO-001",
        source_warehouse="Stores - A",
        items=[{"sales_order_item": "SOI-1", "item_code": "ITEM-1", "qty": 3}],
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_MISSING_SO_LINES"


@patch("bude_api.api.sales_orders.frappe")
def test_create_delivery_note_rejects_bad_location_scope(mock_frappe):
    _grant_stock_role(mock_frappe)
    def get_list(doctype, **kwargs):
        if doctype == "Sales Order":
            return [_so_doc()]
        if doctype == "Sales Order Item":
            return _so_lines()
        if doctype == "Warehouse":
            name = kwargs["filters"][0][2]
            parent = "Other - A" if name == "Rack 1 - A" else None
            return [{"name": name, "company": "Company A", "parent_warehouse": parent}]
        if doctype == "Item":
            return []
        return []

    mock_frappe.get_list.side_effect = get_list

    result = so_api.create_delivery_note(
        sales_order="SO-001",
        source_warehouse="Stores - A",
        source_location="Rack 1 - A",
        items=_dispatch_items(),
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_LOCATION_SCOPE"


@patch("bude_api.api.sales_orders.frappe")
def test_create_delivery_note_converts_erpnext_validation_error(mock_frappe):
    _grant_stock_role(mock_frappe)
    mock_frappe.ValidationError = _FakeValidationError
    mock_frappe.get_list.side_effect = _get_list_side_effect()
    doc = MagicMock()
    doc.submit.side_effect = _FakeValidationError("No stock")
    mock_frappe.get_doc.return_value = doc

    result = so_api.create_delivery_note(
        sales_order="SO-001",
        source_warehouse="Stores - A",
        items=_dispatch_items(),
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_ERPNEXT"
    mock_frappe.db.rollback.assert_called_once()
