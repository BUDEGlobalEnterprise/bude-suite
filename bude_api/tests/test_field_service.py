from unittest.mock import MagicMock, patch

from bude_api.api import field_service as fs_api


class _FakePermissionError(Exception):
    pass


class _FakeValidationError(Exception):
    pass


TECH = "tech@example.com"


def _wire(mock_fs, mock_hd=None, roles=None, user=TECH, missing_doctypes=()):
    modules = [mock_fs] + ([mock_hd] if mock_hd is not None else [])
    for module in modules:
        module.PermissionError = _FakePermissionError
        module.ValidationError = _FakeValidationError
        module.session.user = user
        module.get_roles.return_value = roles or ["Agent"]
        module.db.exists.side_effect = (
            lambda doctype, name=None: (name or doctype) not in missing_doctypes
        )


def _route_get_list(mock_frappe, mapping):
    def router(doctype, **kwargs):
        return list(mapping.get(doctype, []))

    mock_frappe.get_list.side_effect = router


def _ticket(contact="", customer=""):
    return {
        "name": "0091",
        "subject": "AC not cooling",
        "status": "Open",
        "contact": contact,
        "customer": customer,
        "raised_by": "someone@example.com",
    }


def _employee():
    return {"name": "EMP-007", "employee_name": "Tech Person", "company": "Bude"}


def _visit_row(log_type, time="2026-07-11 09:00:00"):
    return {
        "name": f"CHK-{log_type}",
        "log_type": log_type,
        "time": time,
        "latitude": 10.0,
        "longitude": 76.0,
    }


# --- job_site ---


@patch("bude_api.api.helpdesk.frappe")
@patch("bude_api.api.field_service.frappe")
def test_job_site_requires_agent_role(mock_fs, mock_hd):
    _wire(mock_fs, mock_hd, roles=["Employee"])

    result = fs_api.job_site("0091")

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_fs.get_list.assert_not_called()


@patch("bude_api.api.helpdesk.frappe")
@patch("bude_api.api.field_service.frappe")
def test_job_site_ticket_not_found(mock_fs, mock_hd):
    _wire(mock_fs, mock_hd)
    _route_get_list(mock_fs, {"HD Ticket": []})

    result = fs_api.job_site("0091")

    assert result["ok"] is False
    assert result["code"] == "TICKET_NOT_FOUND"


@patch("bude_api.api.helpdesk.frappe")
@patch("bude_api.api.field_service.frappe")
def test_job_site_resolves_contact_and_visits(mock_fs, mock_hd):
    _wire(mock_fs, mock_hd)
    _route_get_list(
        mock_fs,
        {
            "HD Ticket": [_ticket(contact="CON-1", customer="HDC-1")],
            "Contact": [
                {
                    "name": "CON-1",
                    "full_name": "Site Contact",
                    "mobile_no": "12345",
                    "phone": "",
                    "email_id": "c@example.com",
                    "address": "ADDR-1",
                }
            ],
            "Employee": [_employee()],
            "Employee Checkin": [_visit_row("IN")],
        },
    )
    mock_fs.db.get_value.return_value = "CUST-1"
    mock_fs.get_attr.return_value = lambda name: "12 Main Street, Kochi"

    result = fs_api.job_site("0091")

    assert result["ok"] is True
    data = result["data"]
    assert data["contact"]["phone"] == "12345"
    assert data["address"] == "12 Main Street, Kochi"
    assert data["erpnext_customer"] == "CUST-1"
    assert data["checked_in"] is True
    assert data["has_employee"] is True
    assert data["visits"][0]["log_type"] == "IN"


@patch("bude_api.api.helpdesk.frappe")
@patch("bude_api.api.field_service.frappe")
def test_job_site_without_employee_hides_visits(mock_fs, mock_hd):
    _wire(mock_fs, mock_hd)
    _route_get_list(mock_fs, {"HD Ticket": [_ticket()], "Employee": []})

    result = fs_api.job_site("0091")

    assert result["ok"] is True
    assert result["data"]["has_employee"] is False
    assert result["data"]["visits"] == []
    assert result["data"]["checked_in"] is False


# --- check-in / check-out ---


@patch("bude_api.api.helpdesk.frappe")
@patch("bude_api.api.field_service.frappe")
def test_check_in_requires_employee(mock_fs, mock_hd):
    _wire(mock_fs, mock_hd)
    _route_get_list(mock_fs, {"HD Ticket": [_ticket()], "Employee": []})

    result = fs_api.job_check_in("0091", latitude=10.0, longitude=76.0)

    assert result["ok"] is False
    assert result["code"] == "FS_EMPLOYEE_REQUIRED"
    mock_fs.get_doc.assert_not_called()


@patch("bude_api.api.helpdesk.frappe")
@patch("bude_api.api.field_service.frappe")
def test_check_in_reports_missing_hrms(mock_fs, mock_hd):
    _wire(mock_fs, mock_hd, missing_doctypes={"Employee Checkin"})

    result = fs_api.job_check_in("0091")

    assert result["ok"] is False
    assert result["code"] == "FS_HRMS_NOT_INSTALLED"


@patch("bude_api.api.helpdesk.frappe")
@patch("bude_api.api.field_service.frappe")
def test_check_in_blocks_double_entry(mock_fs, mock_hd):
    _wire(mock_fs, mock_hd)
    _route_get_list(
        mock_fs,
        {
            "HD Ticket": [_ticket()],
            "Employee": [_employee()],
            "Employee Checkin": [_visit_row("IN")],
        },
    )

    result = fs_api.job_check_in("0091")

    assert result["ok"] is False
    assert result["code"] == "FS_ALREADY_CHECKED_IN"


@patch("bude_api.api.helpdesk.frappe")
@patch("bude_api.api.field_service.frappe")
def test_check_out_requires_open_checkin(mock_fs, mock_hd):
    _wire(mock_fs, mock_hd)
    _route_get_list(
        mock_fs,
        {"HD Ticket": [_ticket()], "Employee": [_employee()], "Employee Checkin": []},
    )

    result = fs_api.job_check_out("0091")

    assert result["ok"] is False
    assert result["code"] == "FS_NOT_CHECKED_IN"


@patch("bude_api.api.helpdesk.frappe")
@patch("bude_api.api.field_service.frappe")
def test_check_in_writes_tagged_geo_checkin(mock_fs, mock_hd):
    _wire(mock_fs, mock_hd)
    _route_get_list(
        mock_fs,
        {"HD Ticket": [_ticket()], "Employee": [_employee()], "Employee Checkin": []},
    )
    doc = MagicMock()
    doc.name = "CHK-NEW"
    doc.get.return_value = "2026-07-11 09:00:00"
    mock_fs.get_doc.return_value = doc

    result = fs_api.job_check_in("0091", latitude="10.01", longitude="76.02")

    assert result["ok"] is True
    assert result["data"]["log_type"] == "IN"
    (payload,), _ = mock_fs.get_doc.call_args
    assert payload["doctype"] == "Employee Checkin"
    assert payload["employee"] == "EMP-007"
    assert payload["device_id"] == "HD Ticket 0091"
    assert payload["skip_auto_attendance"] == 1
    assert payload["latitude"] == 10.01
    assert payload["longitude"] == 76.02
    doc.insert.assert_called_once_with(ignore_permissions=True)


# --- complete_visit ---


@patch("bude_api.api.helpdesk.frappe")
@patch("bude_api.api.field_service.frappe")
def test_complete_visit_validates_inputs(mock_fs, mock_hd):
    _wire(mock_fs, mock_hd)

    missing = fs_api.complete_visit("0091", work_done="")
    bad_status = fs_api.complete_visit("0091", work_done="x", completion_status="Done")
    bad_type = fs_api.complete_visit("0091", work_done="x", maintenance_type="Magic")

    assert missing["code"] == "VALIDATION_REQUIRED"
    assert bad_status["code"] == "FS_COMPLETION_STATUS_INVALID"
    assert bad_type["code"] == "FS_MAINTENANCE_TYPE_INVALID"


@patch("bude_api.api.helpdesk.frappe")
@patch("bude_api.api.field_service.frappe")
def test_complete_visit_without_customer_records_comment_only(mock_fs, mock_hd):
    _wire(mock_fs, mock_hd)
    _route_get_list(mock_fs, {"HD Ticket": [_ticket()], "Employee": [_employee()]})
    comment = MagicMock()
    comment.name = "COMMENT-1"
    mock_fs.get_doc.return_value = comment

    result = fs_api.complete_visit("0091", work_done="Cleaned filters")

    assert result["ok"] is True
    assert result["data"]["maintenance_visit"] is None
    assert result["data"]["visit_skipped_reason"] == "NO_ERPNEXT_CUSTOMER"
    assert result["data"]["comment"] == "COMMENT-1"
    (payload,), _ = mock_fs.get_doc.call_args
    assert payload["doctype"] == "HD Ticket Comment"
    assert "Cleaned filters" in payload["content"]


@patch("bude_api.api.helpdesk.frappe")
@patch("bude_api.api.field_service.frappe")
def test_complete_visit_creates_maintenance_visit_and_resolves(mock_fs, mock_hd):
    _wire(mock_fs, mock_hd)
    _route_get_list(
        mock_fs,
        {
            "HD Ticket": [_ticket(customer="HDC-1")],
            "Employee": [_employee()],
            "Sales Person": [{"name": "SP-TECH"}],
        },
    )
    mock_fs.db.get_value.return_value = "CUST-1"
    mock_fs.utils.today.return_value = "2026-07-11"
    docs = []

    def _make_doc(payload):
        doc = MagicMock()
        doc.name = f"DOC-{len(docs)}"
        docs.append((payload, doc))
        return doc

    mock_fs.get_doc.side_effect = _make_doc
    _route_get_list(mock_hd, {"HD Ticket": [_ticket(customer="HDC-1")]})
    mock_hd.get_doc.return_value = MagicMock()

    result = fs_api.complete_visit(
        "0091", work_done="Replaced compressor", resolve_ticket=True
    )

    assert result["ok"] is True
    assert result["data"]["maintenance_visit"] == "DOC-1"
    assert result["data"]["ticket_status"] == "Resolved"
    visit_payload, visit_doc = docs[1]
    assert visit_payload["doctype"] == "Maintenance Visit"
    assert visit_payload["customer"] == "CUST-1"
    assert visit_payload["company"] == "Bude"
    assert visit_payload["completion_status"] == "Fully Completed"
    purpose = visit_payload["purposes"][0]
    assert purpose["service_person"] == "SP-TECH"
    assert purpose["work_done"] == "Replaced compressor"
    visit_doc.submit.assert_called_once()


@patch("bude_api.api.helpdesk.frappe")
@patch("bude_api.api.field_service.frappe")
def test_complete_visit_rolls_back_on_validation_error(mock_fs, mock_hd):
    _wire(mock_fs, mock_hd)
    _route_get_list(mock_fs, {"HD Ticket": [_ticket()], "Employee": [_employee()]})
    failing = MagicMock()
    failing.insert.side_effect = _FakeValidationError("bad data")
    mock_fs.get_doc.return_value = failing

    result = fs_api.complete_visit("0091", work_done="x")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_ERPNEXT"
    mock_fs.db.rollback.assert_called_once()
