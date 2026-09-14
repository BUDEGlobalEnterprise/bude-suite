from unittest.mock import MagicMock, patch

from bude_api.api import hr as hr_api


class _FakePermissionError(Exception):
    pass


class _FakeValidationError(Exception):
    pass


def _wire(mock_frappe, roles=None):
    mock_frappe.PermissionError = _FakePermissionError
    mock_frappe.ValidationError = _FakeValidationError
    mock_frappe.session.user = "employee@example.com"
    mock_frappe.get_roles.return_value = roles or ["Employee"]


def _employee():
    return {
        "name": "EMP-001",
        "employee_name": "Alice Employee",
        "company": "Bude",
        "department": "Operations",
        "designation": "Associate",
        "user_id": "employee@example.com",
    }


@patch("bude_api.api.hr.frappe")
def test_profile_requires_hr_role(mock_frappe):
    _wire(mock_frappe, roles=["Stock User"])

    result = hr_api.profile()

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.hr.frappe")
def test_profile_returns_linked_employee(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [_employee()]

    result = hr_api.profile()

    assert result["ok"] is True
    assert result["data"]["name"] == "EMP-001"


@patch("bude_api.api.hr.frappe")
def test_profile_scoped_to_current_employee(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [_employee()]

    hr_api.profile()

    # The detail fetch must be filtered to the signed-in employee's record.
    employee_detail_calls = [
        call
        for call in mock_frappe.get_list.call_args_list
        if call.args and call.args[0] == "Employee"
    ]
    detail_call = next(
        call
        for call in employee_detail_calls
        if ["name", "=", "EMP-001"] in call.kwargs["filters"]
    )
    kwargs = detail_call.kwargs
    assert "employee_number" in kwargs["fields"]
    assert "branch" in kwargs["fields"]
    assert "current_address" in kwargs["fields"]
    assert "contract_end_date" in kwargs["fields"]
    assert "scheduled_confirmation_date" in kwargs["fields"]
    assert "final_confirmation_date" in kwargs["fields"]
    assert "date_of_retirement" in kwargs["fields"]
    assert "resignation_letter_date" in kwargs["fields"]
    assert "relieving_date" in kwargs["fields"]


@patch("bude_api.api.hr.frappe")
def test_profile_returns_privacy_safe_standard_career_history(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.side_effect = lambda doctype, name=None: (
        name
        if doctype == "DocType"
        and name
        in {
            "Employee Education",
            "Employee Internal Work History",
            "Employee External Work History",
        }
        else False
    )

    def get_list(doctype, **kwargs):
        if doctype == "Employee":
            return [_employee()]
        if doctype == "Employee Education":
            return [
                {
                    "school_univ": "State University",
                    "qualification": "BSc",
                    "year_of_passing": 2020,
                }
            ]
        if doctype == "Employee Internal Work History":
            return [
                {
                    "department": "Operations",
                    "designation": "Associate",
                    "from_date": "2024-01-01",
                }
            ]
        if doctype == "Employee External Work History":
            return [
                {
                    "company_name": "Previous Co",
                    "designation": "Analyst",
                    "total_experience": "2 years",
                    "salary": 1000,
                    "address": "Private",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = hr_api.profile()

    assert result["ok"] is True
    assert result["data"]["education"][0]["qualification"] == "BSc"
    external = result["data"]["external_work_history"][0]
    assert external["company_name"] == "Previous Co"
    assert "salary" not in external
    assert "address" not in external
    external_call = [
        call
        for call in mock_frappe.get_list.call_args_list
        if call.args[0] == "Employee External Work History"
    ][0]
    assert "salary" not in external_call.kwargs["fields"]
    assert "address" not in external_call.kwargs["fields"]


@patch("bude_api.api.hr.frappe")
def test_salary_slips_scoped_to_current_employee(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [
            {
                "name": "SAL-001",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
                "net_pay": 1000,
            }
        ],
    ]

    hr_api.salary_slips()

    _, kwargs = mock_frappe.get_list.call_args
    assert ["employee", "=", "EMP-001"] in kwargs["filters"]


@patch("bude_api.api.hr.frappe")
def test_employee_documents_scoped_to_current_employee(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [
            {
                "name": "FILE-001",
                "file_name": "contract.pdf",
                "file_url": "/private/files/contract.pdf",
                "is_private": 1,
            }
        ],
    ]

    result = hr_api.employee_documents()

    assert result["ok"] is True
    assert result["data"][0]["file_name"] == "contract.pdf"
    assert result["data"][0]["is_private"] is True
    # Documents must be scoped to the signed-in employee's record.
    _, kwargs = mock_frappe.get_list.call_args
    assert ["attached_to_name", "=", "EMP-001"] in kwargs["filters"]


@patch("bude_api.api.hr.frappe")
def test_attendance_status_uses_latest_checkin(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.utils.now_datetime.return_value = "2026-07-01 09:05:00"
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"name": "CHK-001", "time": "2026-07-01 09:00:00", "log_type": "IN"}],
        [{"time": "2026-07-01 09:00:00"}],
        [{"time": "2026-06-30 18:00:00"}],
    ]

    result = hr_api.attendance_status()

    assert result["ok"] is True
    assert result["data"]["checked_in"] is True
    assert result["data"]["last_check_in"] == "2026-07-01 09:00:00"
    assert result["data"]["last_check_out"] == "2026-06-30 18:00:00"
    assert result["data"]["latest_checkin_id"] == "CHK-001"
    assert result["data"]["last_log_type"] == "IN"
    assert result["data"]["server_time"] == "2026-07-01 09:05:00"


@patch("bude_api.api.hr.frappe")
def test_attendance_status_reports_checked_out_after_latest_out(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.utils.now_datetime.return_value = "2026-07-01 17:05:00"
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"name": "CHK-002", "time": "2026-07-01 17:00:00", "log_type": "OUT"}],
        [{"time": "2026-07-01 09:00:00"}],
        [{"time": "2026-07-01 17:00:00"}],
    ]

    result = hr_api.attendance_status()

    assert result["ok"] is True
    assert result["data"]["checked_in"] is False
    assert result["data"]["latest_checkin_id"] == "CHK-002"
    assert result["data"]["last_log_type"] == "OUT"


@patch("bude_api.api.hr.frappe")
def test_attendance_history_returns_employee_checkins(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [
            {"name": "CHK-002", "time": "2026-07-01 17:00:00", "log_type": "OUT"},
            {"name": "CHK-001", "time": "2026-07-01 09:00:00", "log_type": "IN"},
        ],
    ]

    result = hr_api.attendance_history(limit=2)

    assert result["ok"] is True
    assert result["data"][0]["name"] == "CHK-002"
    assert result["data"][0]["log_type"] == "OUT"


@patch("bude_api.api.hr.frappe")
def test_attendance_summary_aggregates_standard_attendance_fields(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Employee":
            return [_employee()]
        if doctype == "Attendance":
            return [
                {
                    "attendance_date": "2026-07-16",
                    "status": "Present",
                    "working_hours": 8,
                    "late_entry": 1,
                    "early_exit": 0,
                },
                {
                    "attendance_date": "2026-07-15",
                    "status": "Present",
                    "working_hours": 7,
                    "late_entry": 0,
                    "early_exit": 1,
                },
                {
                    "attendance_date": "2026-07-14",
                    "status": "On Leave",
                    "working_hours": 0,
                    "late_entry": 0,
                    "early_exit": 0,
                },
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = hr_api.attendance_summary(30)

    assert result["ok"] is True
    assert result["data"]["recorded_days"] == 3
    assert result["data"]["status_counts"] == {"Present": 2, "On Leave": 1}
    assert result["data"]["average_working_hours"] == 7.5
    assert result["data"]["late_entries"] == 1
    assert result["data"]["early_exits"] == 1


@patch("bude_api.api.hr.frappe")
def test_attendance_summary_returns_empty_when_attendance_is_unavailable(
    mock_frappe,
):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = False
    mock_frappe.get_list.return_value = [_employee()]

    result = hr_api.attendance_summary()

    assert result["ok"] is True
    assert result["data"]["recorded_days"] == 0
    assert result["data"]["status_counts"] == {}


@patch("bude_api.api.hr.frappe")
def test_attendance_calendar_is_month_bounded_and_employee_scoped(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [
            {
                "name": "ATT-001",
                "attendance_date": "2026-08-11",
                "status": "Present",
                "working_hours": 8.25,
                "in_time": "2026-08-11 09:00:00",
                "out_time": "2026-08-11 17:15:00",
                "late_entry": 1,
                "early_exit": 0,
                "shift": "General",
            }
        ],
    ]

    result = hr_api.attendance_calendar("2026-08")

    assert result["ok"] is True
    assert result["data"][0]["name"] == "ATT-001"
    assert result["data"][0]["date"] == "2026-08-11"
    attendance_call = mock_frappe.get_list.call_args_list[-1]
    assert attendance_call.args[0] == "Attendance"
    assert ["employee", "=", "EMP-001"] in attendance_call.kwargs["filters"]
    assert ["attendance_date", ">=", "2026-08-01"] in attendance_call.kwargs["filters"]
    assert ["attendance_date", "<=", "2026-08-31"] in attendance_call.kwargs["filters"]


@patch("bude_api.api.hr.frappe")
def test_check_in_inserts_employee_checkin_with_permissions(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [_employee()]
    mock_frappe.utils.now_datetime.return_value = "2026-07-01 09:00:00"
    doc = MagicMock()
    doc.name = "CHK-001"
    mock_frappe.get_doc.return_value = doc

    result = hr_api.check_in("IN", latitude=25.2048, longitude=55.2708)

    assert result["ok"] is True
    assert result["data"]["log_type"] == "IN"
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["latitude"] == 25.2048
    assert payload["longitude"] == 55.2708
    doc.insert.assert_called_once_with(ignore_permissions=False)
    mock_frappe.db.commit.assert_called_once()


@patch("bude_api.api.hr.frappe")
def test_check_in_accepts_out_type(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [_employee()]
    mock_frappe.utils.now_datetime.return_value = "2026-07-01 17:00:00"
    doc = MagicMock()
    doc.name = "CHK-002"
    mock_frappe.get_doc.return_value = doc

    result = hr_api.check_in("OUT")

    assert result["ok"] is True
    assert result["data"]["log_type"] == "OUT"
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["log_type"] == "OUT"
    doc.insert.assert_called_once_with(ignore_permissions=False)
    mock_frappe.db.commit.assert_called_once()


def test_check_in_rejects_unknown_type():
    with patch("bude_api.api.hr.frappe") as mock_frappe:
        _wire(mock_frappe)
        mock_frappe.get_list.return_value = [_employee()]

        result = hr_api.check_in("BREAK")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_BAD_TYPE"


@patch("bude_api.api.hr.frappe")
def test_attendance_requests_scoped_to_employee(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [
            {
                "name": "ATT-REQ-001",
                "from_date": "2026-07-01",
                "to_date": "2026-07-01",
                "reason": "Work From Home",
                "explanation": "Network issue",
                "docstatus": 0,
            }
        ],
    ]

    result = hr_api.attendance_requests()

    assert result["ok"] is True
    assert result["data"][0]["name"] == "ATT-REQ-001"
    _, kwargs = mock_frappe.get_list.call_args
    assert ["employee", "=", "EMP-001"] in kwargs["filters"]


@patch("bude_api.api.hr.frappe")
def test_apply_attendance_request_inserts_owned_request(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [_employee()]
    doc = MagicMock()
    doc.name = "ATT-REQ-001"
    mock_frappe.get_doc.return_value = doc

    result = hr_api.apply_attendance_request(
        from_date="2026-07-01",
        to_date="2026-07-01",
        reason="Work From Home",
        explanation="Client visit",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "Attendance Request"
    assert payload["employee"] == "EMP-001"
    doc.insert.assert_called_once_with(ignore_permissions=False)


@patch("bude_api.api.hr.frappe")
def test_apply_employee_advance_inserts_owned_request(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [_employee()]
    mock_frappe.utils.today.return_value = "2026-07-05"
    doc = MagicMock()
    doc.name = "ADV-001"
    doc.get.return_value = "Draft"
    mock_frappe.get_doc.return_value = doc

    result = hr_api.apply_employee_advance(amount=1000, purpose="Travel")

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "Employee Advance"
    assert payload["employee"] == "EMP-001"
    assert payload["advance_amount"] == 1000


@patch("bude_api.api.hr.frappe")
def test_missing_optional_hrms_doctype_returns_json_failure(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = None
    mock_frappe.get_list.return_value = [_employee()]

    result = hr_api.attendance_requests()

    assert result["ok"] is False
    assert result["code"] == "HR_DOCTYPE_UNAVAILABLE"
    assert result["data"]["doctype"] == "Attendance Request"


@patch("bude_api.api.hr.frappe")
def test_leave_balances_merges_allocations_and_used_days(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"leave_type": "Annual Leave", "total_leaves_allocated": 20}],
        [{"leave_type": "Annual Leave", "total_leave_days": 3}],
    ]

    result = hr_api.leave_balances()

    assert result["ok"] is True
    assert result["data"] == [
        {
            "leave_type": "Annual Leave",
            "allocated": 20.0,
            "new_allocated": 0.0,
            "carried_forward": 0.0,
            "encashed": 0.0,
            "from_date": "",
            "to_date": "",
            "used": 3.0,
            "available": 17.0,
            "usage_percent": 15.0,
        }
    ]


@patch("bude_api.api.hr.frappe")
def test_apply_leave_inserts_leave_application(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [_employee()]
    doc = MagicMock()
    doc.name = "LV-001"
    doc.get.return_value = "Open"
    mock_frappe.get_doc.return_value = doc

    result = hr_api.apply_leave(
        leave_type="Annual Leave",
        from_date="2026-07-10",
        to_date="2026-07-11",
        half_day=True,
        half_day_date="2026-07-10",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["half_day"] == 1
    assert payload["half_day_date"] == "2026-07-10"
    doc.insert.assert_called_once_with(ignore_permissions=False)
    mock_frappe.db.commit.assert_called_once()


def _leave_application(**overrides):
    row = {
        "name": "LV-001",
        "leave_type": "Annual Leave",
        "from_date": "2026-07-10",
        "to_date": "2026-07-11",
        "status": "Open",
        "total_leave_days": 2,
        "description": "Trip",
        "docstatus": 1,
    }
    row.update(overrides)
    return row


@patch("bude_api.api.hr.frappe")
def test_leave_requests_lists_employee_applications(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [_leave_application()],
    ]

    result = hr_api.leave_requests()

    assert result["ok"] is True
    assert result["data"][0]["name"] == "LV-001"
    assert result["data"][0]["cancellable"] is True


@patch("bude_api.api.hr.frappe")
def test_leave_request_detail_returns_owned_application(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [_leave_application()],
    ]

    result = hr_api.leave_request_detail("LV-001")

    assert result["ok"] is True
    assert result["data"]["leave_type"] == "Annual Leave"


@patch("bude_api.api.hr.frappe")
def test_leave_request_detail_hides_foreign_application(mock_frappe):
    _wire(mock_frappe)
    # Second get_list (name + employee filter) returns nothing → not owned.
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [],
    ]

    result = hr_api.leave_request_detail("LV-999")

    assert result["ok"] is False
    assert result["code"] == "HR_LEAVE_NOT_FOUND"


@patch("bude_api.api.hr.frappe")
def test_cancel_leave_cancels_submitted_application(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [_leave_application()],
    ]
    doc = MagicMock()
    mock_frappe.get_doc.return_value = doc

    result = hr_api.cancel_leave("LV-001")

    assert result["ok"] is True
    assert result["data"]["status"] == "Cancelled"
    doc.cancel.assert_called_once()
    mock_frappe.db.commit.assert_called_once()


@patch("bude_api.api.hr.frappe")
def test_cancel_leave_rejects_non_cancellable_application(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [_leave_application(docstatus=0, status="Open")],
    ]

    result = hr_api.cancel_leave("LV-001")

    assert result["ok"] is False
    assert result["code"] == "HR_LEAVE_NOT_CANCELLABLE"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.hr.frappe")
def test_expense_types_lists_claim_types(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [{"name": "Travel"}, {"name": "Food"}]

    result = hr_api.expense_types()

    assert result["ok"] is True
    assert result["data"] == ["Travel", "Food"]


@patch("bude_api.api.hr.frappe")
def test_expense_claim_detail_returns_owned_claim_with_lines(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [
            {
                "name": "EXP-001",
                "status": "Draft",
                "approval_status": "Draft",
                "posting_date": "2026-07-01",
                "total_claimed_amount": 100,
                "total_sanctioned_amount": 0,
            }
        ],
        [
            {
                "expense_type": "Travel",
                "amount": 100,
                "sanctioned_amount": 0,
                "description": "Taxi",
            }
        ],
    ]

    result = hr_api.expense_claim_detail("EXP-001")

    assert result["ok"] is True
    assert result["data"]["name"] == "EXP-001"
    assert result["data"]["expenses"][0]["expense_type"] == "Travel"


@patch("bude_api.api.hr.frappe")
def test_expense_claim_detail_hides_foreign_claim(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [],
    ]

    result = hr_api.expense_claim_detail("EXP-999")

    assert result["ok"] is False
    assert result["code"] == "HR_EXPENSE_NOT_FOUND"


@patch("bude_api.api.hr.frappe")
def test_submit_expense_claim_sets_optional_posting_date(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [_employee()]
    doc = MagicMock()
    doc.name = "EXP-001"
    doc.get.return_value = "Draft"
    mock_frappe.get_doc.return_value = doc

    result = hr_api.submit_expense_claim(
        expense_type="Travel",
        amount=100,
        posting_date="2026-07-02",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["posting_date"] == "2026-07-02"
    doc.insert.assert_called_once_with(ignore_permissions=False)


@patch("bude_api.api.hr.frappe")
def test_salary_slips_returns_success_envelope(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [
            {
                "name": "SAL-001",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
                "net_pay": 1000,
            }
        ],
    ]

    result = hr_api.salary_slips()

    assert result["ok"] is True
    assert result["data"][0]["name"] == "SAL-001"


@patch("bude_api.api.hr.frappe")
def test_salary_slip_detail_returns_owned_slip_with_components(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [
            {
                "name": "SAL-001",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
                "gross_pay": 1200,
                "total_deduction": 200,
                "net_pay": 1000,
            }
        ],
        [
            {"parentfield": "earnings", "salary_component": "Basic", "amount": 1200},
            {"parentfield": "deductions", "salary_component": "Tax", "amount": 200},
        ],
    ]

    result = hr_api.salary_slip_detail("SAL-001")

    assert result["ok"] is True
    assert result["data"]["net_pay"] == 1000.0
    assert result["data"]["earnings"][0]["component"] == "Basic"
    assert result["data"]["deductions"][0]["component"] == "Tax"


@patch("bude_api.api.hr.frappe")
def test_salary_slip_detail_hides_foreign_slip(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [[_employee()], []]

    result = hr_api.salary_slip_detail("SAL-999")

    assert result["ok"] is False
    assert result["code"] == "HR_SALARY_NOT_FOUND"


@patch("bude_api.api.hr.frappe")
def test_salary_slip_pdf_url_returns_owned_print_url(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"name": "SAL-001"}],
    ]
    mock_frappe.utils.get_url.side_effect = lambda path: f"https://erp.test{path}"

    result = hr_api.salary_slip_pdf_url("SAL-001")

    assert result["ok"] is True
    assert result["data"]["name"] == "SAL-001"
    assert "download_pdf" in result["data"]["url"]
    assert "Salary%20Slip" in result["data"]["url"]


@patch("bude_api.api.hr.frappe")
def test_salary_slip_pdf_url_hides_foreign_slip(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [[_employee()], []]

    result = hr_api.salary_slip_pdf_url("SAL-999")

    assert result["ok"] is False
    assert result["code"] == "HR_SALARY_NOT_FOUND"


@patch("bude_api.api.hr.frappe")
def test_manager_direct_reports_returns_active_reports(mock_frappe):
    _wire(mock_frappe, roles=["HR Manager"])
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [
            {
                "name": "EMP-002",
                "employee_name": "Bob Employee",
                "department": "Operations",
                "designation": "Technician",
                "company_email": "bob@bude.example",
                "cell_number": "+971500000001",
            }
        ],
    ]

    result = hr_api.manager_direct_reports()

    assert result["ok"] is True
    assert result["data"][0]["employee"] == "EMP-002"
    assert result["data"][0]["employee_name"] == "Bob Employee"
    _, kwargs = mock_frappe.get_list.call_args
    assert ["reports_to", "=", "EMP-001"] in kwargs["filters"]
    assert ["status", "=", "Active"] in kwargs["filters"]


@patch("bude_api.api.hr.frappe")
def test_notifications_lists_only_current_user_logs(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [
        {
            "name": "NOTIF-001",
            "subject": "Leave approval pending",
            "email_content": "Read the new policy.",
            "read": 0,
            "creation": "2026-07-01",
            "document_type": "Leave Application",
            "document_name": "LV-001",
        }
    ]

    result = hr_api.notifications()

    assert result["ok"] is True
    assert result["data"][0]["title"] == "Leave approval pending"
    assert result["data"][0]["read"] is False
    assert result["data"][0]["reference_type"] == "Leave Application"
    assert result["data"][0]["reference_name"] == "LV-001"
    assert result["data"][0]["category"] == "approvals"
    assert result["data"][0]["route"] == "/manager?tab=leave&focus=LV-001"
    # Notifications must be scoped to the signed-in user.
    _, kwargs = mock_frappe.get_list.call_args
    assert ["for_user", "=", "employee@example.com"] in kwargs["filters"]
    assert "name" in kwargs["fields"]
    assert "creation" in kwargs["fields"]


@patch("bude_api.services.hr._mobile_shared.frappe")
def test_existing_fields_keeps_frappe_standard_columns(mock_frappe):
    meta = MagicMock()
    meta.has_field.return_value = False
    mock_frappe.get_meta.return_value = meta

    fields = hr_api._existing_fields(
        "Notification Log", ["name", "creation", "subject", "missing"]
    )

    assert fields == ["name", "creation"]


def test_notification_route_sends_approval_results_to_requests():
    category, route = hr_api._notification_category_route(
        "Leave Application",
        "LV-001",
        "Leave request approved",
        "Your leave request has been approved.",
    )

    assert category == "requests"
    assert route == "/requests"


@patch("bude_api.api.hr.frappe")
def test_mark_notification_read_sets_read_flag(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [
        {
            "name": "NOTIF-001",
            "subject": "Policy update",
            "email_content": "Read it.",
            "read": 0,
            "creation": "2026-07-01",
        }
    ]

    result = hr_api.mark_notification_read("NOTIF-001")

    assert result["ok"] is True
    assert result["data"]["read"] is True
    mock_frappe.db.set_value.assert_called_once_with("Notification Log", "NOTIF-001", "read", 1)


@patch("bude_api.api.hr.frappe")
def test_register_push_token_inserts_owned_device_token(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True
    mock_frappe.get_list.side_effect = [[_employee()], []]
    doc = MagicMock()
    doc.name = "PUSH-001"
    mock_frappe.get_doc.return_value = doc

    result = hr_api.register_push_token(
        token="fcm-token",
        platform="android",
        device_id="device-1",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "Bude HR Push Token"
    assert payload["user"] == "employee@example.com"
    assert payload["employee"] == "EMP-001"
    assert payload["token"] == "fcm-token"
    assert payload["enabled"] == 1
    doc.insert.assert_called_once_with(ignore_permissions=False)


@patch("bude_api.api.hr.frappe")
def test_clear_push_token_only_disables_current_user_token(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True
    mock_frappe.get_list.return_value = [{"name": "PUSH-001"}]

    result = hr_api.clear_push_token(token="fcm-token")

    assert result["ok"] is True
    assert result["data"]["cleared"] == 1
    _, kwargs = mock_frappe.get_list.call_args
    assert ["user", "=", "employee@example.com"] in kwargs["filters"]
    assert ["token", "=", "fcm-token"] in kwargs["filters"]
    mock_frappe.db.set_value.assert_called_once_with("Bude HR Push Token", "PUSH-001", "enabled", 0)


# Every HR endpoint plus the args needed to reach its permission guard.
_HR_ENDPOINTS = [
    ("profile", (), {}),
    ("employee_documents", (), {}),
    ("attendance_status", (), {}),
    ("attendance_history", (), {}),
    ("check_in", ("IN",), {}),
    ("leave_balances", (), {}),
    ("holidays", (), {}),
    ("apply_leave", ("Annual Leave", "2026-07-10", "2026-07-11"), {}),
    ("leave_requests", (), {}),
    ("leave_request_detail", ("LV-001",), {}),
    ("upload_leave_attachment", ("LV-001", "medical.jpg", "aGVsbG8="), {}),
    ("leave_attachments", ("LV-001",), {}),
    ("cancel_leave", ("LV-001",), {}),
    ("expense_claims", (), {}),
    ("expense_types", (), {}),
    ("expense_claim_detail", ("EXP-001",), {}),
    ("submit_expense_claim", ("Travel", 10), {}),
    ("upload_expense_attachment", ("EXP-001", "receipt.jpg", "aGVsbG8="), {}),
    ("expense_attachments", ("EXP-001",), {}),
    ("salary_slips", (), {}),
    ("salary_slip_detail", ("SAL-001",), {}),
    ("salary_slip_pdf_url", ("SAL-001",), {}),
    ("notifications", (), {}),
    ("notification_detail", ("NOTIF-001",), {}),
    ("mark_notification_read", ("NOTIF-001",), {}),
    ("register_push_token", ("fcm-token",), {}),
    ("clear_push_token", ("fcm-token",), {}),
    ("manager_pending_leaves", (), {}),
    ("manager_pending_expenses", (), {}),
    ("manager_summary", (), {}),
    ("manager_direct_reports", (), {}),
    ("manager_team_attendance_exceptions", (), {}),
    ("decide_leave", ("LV-001", True), {}),
    ("decide_expense", ("EXP-001", True), {}),
]


def test_every_hr_endpoint_denies_non_hr_role():
    for name, args, kwargs in _HR_ENDPOINTS:
        with patch("bude_api.api.hr.frappe") as mock_frappe:
            _wire(mock_frappe, roles=["Stock User"])

            result = getattr(hr_api, name)(*args, **kwargs)

            assert result["ok"] is False, f"{name} should deny non-HR roles"
            assert result["code"] == "PERMISSION_DENIED", f"{name} wrong code"
            # No data access should happen once permission is denied.
            mock_frappe.get_list.assert_not_called()
            mock_frappe.get_doc.assert_not_called()


_MANAGER_ENDPOINTS = [
    ("manager_pending_leaves", (), {}),
    ("manager_pending_expenses", (), {}),
    ("manager_summary", (), {}),
    ("manager_team_attendance_exceptions", (), {}),
    ("decide_leave", ("LV-001", True), {}),
    ("decide_expense", ("EXP-001", True), {}),
]


def test_manager_endpoints_deny_plain_employee():
    for name, args, kwargs in _MANAGER_ENDPOINTS:
        with patch("bude_api.api.hr.frappe") as mock_frappe:
            _wire(mock_frappe, roles=["Employee"])

            result = getattr(hr_api, name)(*args, **kwargs)

            assert result["ok"] is False, f"{name} should deny plain employees"
            assert result["code"] == "PERMISSION_DENIED", f"{name} wrong code"
            mock_frappe.get_list.assert_not_called()
            mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.hr.frappe")
def test_manager_pending_leaves_scoped_to_approver(mock_frappe):
    _wire(mock_frappe, roles=["HR Manager"])
    mock_frappe.session.user = "manager@example.com"
    mock_frappe.get_list.return_value = [
        {
            "name": "LV-001",
            "employee": "EMP-002",
            "employee_name": "Bob",
            "leave_type": "Annual Leave",
            "from_date": "2026-07-10",
            "to_date": "2026-07-11",
            "total_leave_days": 2,
        }
    ]

    result = hr_api.manager_pending_leaves()

    assert result["ok"] is True
    assert result["data"][0]["employee_name"] == "Bob"
    _, kwargs = mock_frappe.get_list.call_args
    assert ["leave_approver", "=", "manager@example.com"] in kwargs["filters"]


@patch("bude_api.api.hr.frappe")
def test_decide_leave_approves_assigned_request(mock_frappe):
    _wire(mock_frappe, roles=["HR Manager"])
    mock_frappe.session.user = "manager@example.com"
    mock_frappe.get_list.return_value = [{"name": "LV-001"}]
    doc = MagicMock()
    mock_frappe.get_doc.return_value = doc

    result = hr_api.decide_leave("LV-001", approved=True, comment="Looks fine")

    assert result["ok"] is True
    assert result["data"]["status"] == "Approved"
    assert doc.status == "Approved"
    doc.add_comment.assert_called_once_with("Comment", "Looks fine")
    doc.save.assert_called_once_with(ignore_permissions=False)


@patch("bude_api.api.hr.frappe")
def test_decide_leave_treats_string_false_as_rejection(mock_frappe):
    _wire(mock_frappe, roles=["HR Manager"])
    mock_frappe.get_list.return_value = [{"name": "LV-001"}]
    doc = MagicMock()
    mock_frappe.get_doc.return_value = doc

    # HTTP delivers booleans as strings; "false" must reject, not approve.
    result = hr_api.decide_leave("LV-001", approved="false")

    assert result["ok"] is True
    assert result["data"]["status"] == "Rejected"
    assert doc.status == "Rejected"


@patch("bude_api.api.hr.frappe")
def test_decide_expense_hides_unassigned_claim(mock_frappe):
    _wire(mock_frappe, roles=["HR Manager"])
    mock_frappe.get_list.return_value = []

    result = hr_api.decide_expense("EXP-999", approved=True)

    assert result["ok"] is False
    assert result["code"] == "HR_APPROVAL_NOT_FOUND"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.hr.frappe")
def test_upload_expense_attachment_rejects_bad_extension(mock_frappe):
    _wire(mock_frappe)

    result = hr_api.upload_expense_attachment("EXP-001", "malware.exe", "aGVsbG8=")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.hr.frappe")
def test_upload_leave_attachment_rejects_bad_extension(mock_frappe):
    _wire(mock_frappe)

    result = hr_api.upload_leave_attachment("LV-001", "malware.exe", "aGVsbG8=")

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.hr.frappe")
def test_upload_leave_attachment_hides_foreign_application(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [],
    ]

    result = hr_api.upload_leave_attachment("LV-999", "medical.jpg", "aGVsbG8=")

    assert result["ok"] is False
    assert result["code"] == "HR_LEAVE_NOT_FOUND"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.hr.frappe")
def test_upload_leave_attachment_creates_private_file(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"name": "LV-001"}],
    ]
    doc = MagicMock()
    doc.name = "FILE-001"
    doc.get.return_value = "/private/files/medical.jpg"
    mock_frappe.get_doc.return_value = doc

    result = hr_api.upload_leave_attachment("LV-001", "medical.jpg", "aGVsbG8=")

    assert result["ok"] is True
    assert result["data"]["file_url"] == "/private/files/medical.jpg"
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "File"
    assert payload["attached_to_doctype"] == "Leave Application"
    assert payload["attached_to_name"] == "LV-001"
    assert payload["is_private"] == 1
    assert payload["decode"] is True
    doc.insert.assert_called_once_with(ignore_permissions=False)
    mock_frappe.db.commit.assert_called_once()


@patch("bude_api.api.hr.frappe")
def test_leave_attachments_scoped_to_owned_application(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"name": "LV-001"}],
        [
            {
                "name": "FILE-001",
                "file_name": "medical.jpg",
                "file_url": "/private/files/medical.jpg",
                "is_private": 1,
            }
        ],
    ]

    result = hr_api.leave_attachments("LV-001")

    assert result["ok"] is True
    assert result["data"][0]["file_name"] == "medical.jpg"
    assert result["data"][0]["is_private"] is True
    _, kwargs = mock_frappe.get_list.call_args
    assert ["attached_to_doctype", "=", "Leave Application"] in kwargs["filters"]
    assert ["attached_to_name", "=", "LV-001"] in kwargs["filters"]


@patch("bude_api.api.hr.frappe")
def test_upload_expense_attachment_rejects_oversized_content(mock_frappe):
    _wire(mock_frappe)
    oversized = "a" * (hr_api.MAX_ATTACHMENT_BASE64_LENGTH + 1)

    result = hr_api.upload_expense_attachment("EXP-001", "receipt.jpg", oversized)

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_REQUIRED"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.hr.frappe")
def test_upload_expense_attachment_hides_foreign_claim(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [],
    ]

    result = hr_api.upload_expense_attachment("EXP-999", "receipt.jpg", "aGVsbG8=")

    assert result["ok"] is False
    assert result["code"] == "HR_EXPENSE_NOT_FOUND"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.hr.frappe")
def test_upload_expense_attachment_creates_private_file(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"name": "EXP-001"}],
    ]
    doc = MagicMock()
    doc.name = "FILE-001"
    doc.get.return_value = "/private/files/receipt.jpg"
    mock_frappe.get_doc.return_value = doc

    result = hr_api.upload_expense_attachment("EXP-001", "receipt.jpg", "aGVsbG8=")

    assert result["ok"] is True
    assert result["data"]["file_url"] == "/private/files/receipt.jpg"
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["doctype"] == "File"
    assert payload["attached_to_doctype"] == "Expense Claim"
    assert payload["attached_to_name"] == "EXP-001"
    assert payload["is_private"] == 1
    assert payload["decode"] is True
    doc.insert.assert_called_once_with(ignore_permissions=False)


@patch("bude_api.api.hr.frappe")
def test_expense_attachments_scoped_to_owned_claim(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"name": "EXP-001"}],
        [
            {
                "name": "FILE-001",
                "file_name": "receipt.jpg",
                "file_url": "/private/files/receipt.jpg",
                "is_private": 1,
            }
        ],
    ]

    result = hr_api.expense_attachments("EXP-001")

    assert result["ok"] is True
    assert result["data"][0]["file_name"] == "receipt.jpg"
    assert result["data"][0]["is_private"] is True
    _, kwargs = mock_frappe.get_list.call_args
    assert ["attached_to_name", "=", "EXP-001"] in kwargs["filters"]


@patch("bude_api.api.hr.frappe")
def test_holidays_returns_employee_holiday_list(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"holiday_list": "2026 Holidays", "company": "Bude"}],
        [],
    ]
    mock_frappe.get_all.return_value = [
        {"holiday_date": "2026-07-04", "description": "Founders Day", "weekly_off": 0},
        {"holiday_date": "2026-07-05", "description": "Sunday", "weekly_off": 1},
    ]

    result = hr_api.holidays()

    assert result["ok"] is True
    assert result["data"][0]["description"] == "Founders Day"
    assert result["data"][0]["weekly_off"] is False
    assert result["data"][1]["weekly_off"] is True
    # Holidays must be scoped to the employee's assigned holiday list.
    _, kwargs = mock_frappe.get_all.call_args
    assert ["parent", "=", "2026 Holidays"] in kwargs["filters"]


@patch("bude_api.api.hr.frappe")
def test_holidays_falls_back_to_company_default(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"holiday_list": None, "company": "Bude"}],
        [],
        [{"default_holiday_list": "Company Default"}],
    ]
    mock_frappe.get_all.return_value = [
        {"holiday_date": "2026-12-25", "description": "Holiday", "weekly_off": 0},
    ]

    result = hr_api.holidays()

    assert result["ok"] is True
    _, kwargs = mock_frappe.get_all.call_args
    assert ["parent", "=", "Company Default"] in kwargs["filters"]


@patch("bude_api.api.hr.frappe")
def test_holidays_empty_when_no_list_resolves(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"holiday_list": None, "company": "Bude"}],
        [],
        [{"default_holiday_list": None}],
    ]

    result = hr_api.holidays()

    assert result["ok"] is True
    assert result["data"] == []
    # No Holiday query should run when no list resolves.
    assert mock_frappe.get_list.call_count == 4


@patch("bude_api.api.hr.frappe")
def test_holidays_prefers_current_holiday_list_assignment(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"holiday_list": "Legacy Holidays", "company": "Bude"}],
        [{"holiday_list": "Assigned Holidays"}],
    ]
    mock_frappe.get_all.return_value = [
        {
            "holiday_date": "2026-10-20",
            "description": "Diwali",
            "weekly_off": 0,
        }
    ]

    result = hr_api.holidays(from_date="2026-10-01")

    assert result["ok"] is True
    assert result["data"][0]["description"] == "Diwali"
    _, kwargs = mock_frappe.get_all.call_args
    assert ["parent", "=", "Assigned Holidays"] in kwargs["filters"]


@patch("bude_api.api.hr.frappe")
def test_manager_team_attendance_exceptions_scoped_to_reports(mock_frappe):
    _wire(mock_frappe, roles=["HR Manager"])
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"name": "EMP-002"}, {"name": "EMP-003"}],
        [
            {
                "name": "ATT-001",
                "employee": "EMP-002",
                "employee_name": "Bob",
                "attendance_date": "2026-07-01",
                "status": "Absent",
            }
        ],
    ]

    result = hr_api.manager_team_attendance_exceptions()

    assert result["ok"] is True
    assert result["data"][0]["status"] == "Absent"
    _, kwargs = mock_frappe.get_list.call_args
    assert ["employee", "in", ["EMP-002", "EMP-003"]] in kwargs["filters"]
    assert ["status", "in", ["Absent", "Half Day", "On Leave"]] in kwargs["filters"]


@patch("bude_api.api.hr.frappe")
def test_manager_team_attendance_exceptions_empty_without_reports(mock_frappe):
    _wire(mock_frappe, roles=["HR Manager"])
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [],
    ]

    result = hr_api.manager_team_attendance_exceptions()

    assert result["ok"] is True
    assert result["data"] == []
    # No Attendance query should run when there are no direct reports.
    assert mock_frappe.get_list.call_count == 2


@patch("bude_api.api.hr.frappe")
def test_profile_returns_auth_expired_for_guest_session(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.session.user = "Guest"

    result = hr_api.profile()

    assert result["ok"] is False
    assert result["code"] == "AUTH_EXPIRED"
    mock_frappe.get_roles.assert_not_called()


@patch("bude_api.api.hr.frappe")
def test_shift_requests_are_scoped_and_paginated(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [
            {
                "name": "SHIFT-REQ-001",
                "employee": "EMP-001",
                "employee_name": "Alice Employee",
                "shift_type": "Night",
                "from_date": "2026-07-10",
                "to_date": "2026-07-12",
                "status": "Open",
                "reason": "Swap",
                "docstatus": 0,
            }
        ],
    ]

    result = hr_api.shift_requests(limit=999, offset=5)

    assert result["ok"] is True
    assert result["data"][0]["name"] == "SHIFT-REQ-001"
    _, kwargs = mock_frappe.get_list.call_args
    assert ["employee", "=", "EMP-001"] in kwargs["filters"]
    assert kwargs["limit_start"] == 5
    assert kwargs["limit_page_length"] == 100


@patch("bude_api.api.hr.frappe")
def test_apply_shift_request_inserts_with_permissions(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [_employee()]
    doc = MagicMock()
    doc.name = "SHIFT-REQ-001"
    doc.get.return_value = "Open"
    mock_frappe.get_doc.return_value = doc

    result = hr_api.apply_shift_request(
        shift_type="Night",
        from_date="2026-07-10",
        to_date="2026-07-12",
        reason="Swap",
    )

    assert result["ok"] is True
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["employee"] == "EMP-001"
    assert payload["shift_type"] == "Night"
    doc.insert.assert_called_once_with(ignore_permissions=False)


@patch("bude_api.api.hr.frappe")
def test_salary_ytd_sums_owned_salary_slips(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [
            {"gross_pay": 1000, "total_deduction": 100, "net_pay": 900},
            {"gross_pay": 1500, "total_deduction": 200, "net_pay": 1300},
        ],
    ]

    result = hr_api.salary_ytd(year=2026)

    assert result["ok"] is True
    assert result["data"]["gross_pay"] == 2500
    assert result["data"]["total_deduction"] == 300
    assert result["data"]["net_pay"] == 2200
    _, kwargs = mock_frappe.get_list.call_args
    assert ["employee", "=", "EMP-001"] in kwargs["filters"]


@patch("bude_api.api.hr.frappe")
def test_upload_checkin_selfie_checks_owned_checkin(mock_frappe):
    _wire(mock_frappe)
    doc = MagicMock()
    doc.name = "FILE-001"
    doc.get.return_value = "/private/files/selfie.jpg"
    mock_frappe.get_doc.return_value = doc
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"name": "CHK-001"}],
    ]

    result = hr_api.upload_checkin_selfie(
        checkin_name="CHK-001",
        file_name="selfie.jpg",
        content_base64="aGVsbG8=",
    )

    assert result["ok"] is True
    _, kwargs = mock_frappe.get_list.call_args
    assert ["name", "=", "CHK-001"] in kwargs["filters"]
    assert ["employee", "=", "EMP-001"] in kwargs["filters"]
    payload = mock_frappe.get_doc.call_args.args[0]
    assert payload["attached_to_doctype"] == "Employee Checkin"
    assert payload["is_private"] == 1
    doc.insert.assert_called_once_with(ignore_permissions=False)


@patch("bude_api.api.hr.frappe")
def test_manager_pending_shift_requests_direct_report_scoped(mock_frappe):
    _wire(mock_frappe, roles=["HR Manager"])
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"name": "EMP-002"}],
        [
            {
                "name": "SHIFT-REQ-001",
                "employee": "EMP-002",
                "employee_name": "Bob",
                "shift_type": "Night",
                "from_date": "2026-07-10",
                "to_date": "2026-07-12",
                "status": "Open",
                "reason": "Swap",
                "docstatus": 0,
            }
        ],
    ]

    result = hr_api.manager_pending_shift_requests()

    assert result["ok"] is True
    _, kwargs = mock_frappe.get_list.call_args
    assert ["employee", "in", ["EMP-002"]] in kwargs["filters"]
    assert ["docstatus", "=", 0] in kwargs["filters"]


@patch("bude_api.api.hr.frappe")
def test_attendance_anomalies_flags_absent_late_and_missing_checkout(mock_frappe):
    _wire(mock_frappe, roles=["HR Manager"])
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"name": "EMP-002"}],
        [
            {
                "name": "ATT-ABS",
                "employee": "EMP-002",
                "employee_name": "Bob",
                "attendance_date": "2026-07-01",
                "status": "Absent",
                "late_entry": 0,
                "in_time": None,
                "out_time": None,
            },
            {
                "name": "ATT-LATE",
                "employee": "EMP-002",
                "employee_name": "Bob",
                "attendance_date": "2026-07-02",
                "status": "Present",
                "late_entry": 1,
                "in_time": "2026-07-02 09:45:00",
                "out_time": "2026-07-02 18:00:00",
            },
            {
                "name": "ATT-OUT",
                "employee": "EMP-002",
                "employee_name": "Bob",
                "attendance_date": "2026-07-03",
                "status": "Present",
                "late_entry": 0,
                "in_time": "2026-07-03 09:00:00",
                "out_time": None,
            },
        ],
    ]

    result = hr_api.attendance_anomalies(
        from_date="2026-07-01",
        to_date="2026-07-03",
        limit=2,
        offset=1,
    )

    assert result["ok"] is True
    assert [row["type"] for row in result["data"]] == ["late", "missing_checkout"]
    _, kwargs = mock_frappe.get_list.call_args
    assert ["employee", "in", ["EMP-002"]] in kwargs["filters"]


@patch("bude_api.api.hr.frappe")
def test_attendance_anomalies_rejects_wide_range(mock_frappe):
    _wire(mock_frappe, roles=["HR Manager"])
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"name": "EMP-002"}],
    ]

    result = hr_api.attendance_anomalies(
        from_date="2026-01-01",
        to_date="2026-04-01",
    )

    assert result["ok"] is False
    assert result["code"] == "VALIDATION_RANGE_TOO_WIDE"


@patch("bude_api.api.hr.frappe")
def test_onboarding_checklists_include_activity_ids(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [
            {
                "name": "ONB-001",
                "employee": "EMP-001",
                "employee_name": "Alice Employee",
                "boarding_status": "Pending",
                "docstatus": 1,
            }
        ],
        [
            {
                "name": "ACT-001",
                "activity_name": "Submit ID proof",
                "role": "Employee",
                "user": "employee@example.com",
                "status": "Open",
            }
        ],
        [],
    ]

    result = hr_api.onboarding_checklists()

    assert result["ok"] is True
    assert result["data"][0]["activities"][0]["name"] == "ACT-001"
    assert result["data"][0]["activities"][0]["activity_name"] == "Submit ID proof"


@patch("bude_api.api.hr.frappe")
def test_complete_onboarding_activity_saves_owned_parent_with_permissions(mock_frappe):
    _wire(mock_frappe)
    activity = MagicMock()
    activity.get.side_effect = lambda key: {
        "name": "ACT-001",
        "activity_name": "Submit ID proof",
        "status": activity.status,
    }.get(key)
    activity.status = "Open"
    doc = MagicMock()
    doc.get.return_value = [activity]
    mock_frappe.get_doc.return_value = doc
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [{"name": "ONB-001"}],
    ]

    result = hr_api.complete_onboarding_activity(
        parent_doctype="Employee Onboarding",
        parent_name="ONB-001",
        activity_name="ACT-001",
    )

    assert result["ok"] is True
    assert activity.status == "Completed"
    doc.save.assert_called_once_with(ignore_permissions=False)
    mock_frappe.db.commit.assert_called_once()


@patch("bude_api.api.hr.frappe")
def test_complete_onboarding_activity_rejects_foreign_parent(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.side_effect = [
        [_employee()],
        [],
    ]

    result = hr_api.complete_onboarding_activity(
        parent_doctype="Employee Onboarding",
        parent_name="ONB-999",
        activity_name="ACT-001",
    )

    assert result["ok"] is False
    assert result["code"] == "HR_CHECKLIST_NOT_FOUND"
    mock_frappe.get_doc.assert_not_called()


@patch("bude_api.api.hr.frappe")
def test_profile_includes_optional_standard_employee_skills(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Employee":
            return [_employee()]
        if doctype == "Employee Skill Map":
            return [{"name": "EMP-001"}]
        if doctype == "Employee Skill":
            return [
                {
                    "skill": "Inventory Planning",
                    "proficiency": 0.8,
                    "evaluation_date": "2026-07-01",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list

    result = hr_api.profile()

    assert result["ok"] is True
    assert result["data"]["skills"] == [
        {
            "skill": "Inventory Planning",
            "proficiency": 0.8,
            "evaluation_date": "2026-07-01",
        }
    ]


@patch("bude_api.api.hr.frappe")
def test_profile_includes_optional_standard_employee_training(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Employee":
            return [_employee()]
        if doctype == "Employee Skill Map":
            return [{"name": "SKILL-MAP-001"}]
        if doctype == "Employee Training":
            return [
                {
                    "training": "Safe Warehouse Operations",
                    "training_date": "2026-07-01",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = hr_api.profile()

    assert result["ok"] is True
    assert result["data"]["trainings"] == [
        {
            "training": "Safe Warehouse Operations",
            "training_date": "2026-07-01",
        }
    ]


@patch("bude_api.api.hr.frappe")
def test_profile_includes_employee_scoped_upcoming_training(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Employee":
            return [_employee()]
        if doctype == "Training Event Employee":
            return [
                {
                    "parent": "Warehouse Safety",
                    "status": "Invited",
                    "is_mandatory": 1,
                }
            ]
        if doctype == "Training Event":
            return [
                {
                    "name": "Warehouse Safety",
                    "event_name": "Warehouse Safety",
                    "event_status": "Scheduled",
                    "type": "Workshop",
                    "location": "HQ",
                    "start_time": "2026-08-01 09:00:00",
                    "end_time": "2026-08-01 12:00:00",
                    "has_certificate": 1,
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = hr_api.profile()

    assert result["ok"] is True
    training = result["data"]["upcoming_training"][0]
    assert training["event_name"] == "Warehouse Safety"
    assert training["is_mandatory"] is True
    assert training["has_certificate"] is True


@patch("bude_api.api.hr.frappe")
def test_profile_includes_privacy_safe_current_appraisal(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Employee":
            return [_employee()]
        if doctype == "Appraisal":
            return [
                {
                    "name": "APP-001",
                    "appraisal_cycle": "FY 2026",
                    "start_date": "2026-04-01",
                    "end_date": "2027-03-31",
                    "goal_score_percentage": 75,
                    "self_score": 4,
                    "final_score": 3.5,
                    "salary": 999999,
                }
            ]
        if doctype == "Appraisal Goal":
            return [
                {
                    "kra": "Inventory accuracy",
                    "per_weightage": 40,
                    "score": 4,
                    "score_earned": 1.6,
                    "feedback": "private",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = hr_api.profile()

    assert result["ok"] is True
    appraisal = result["data"]["current_appraisal"]
    assert appraisal["appraisal_cycle"] == "FY 2026"
    assert appraisal["goals"][0]["goal"] == "Inventory accuracy"
    assert "salary" not in appraisal
    assert "feedback" not in appraisal["goals"][0]


@patch("bude_api.api.hr.frappe")
def test_profile_includes_only_privacy_safe_promotion_changes(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Employee":
            return [_employee()]
        if doctype == "Employee Promotion":
            return [
                {
                    "name": "HR-EMP-PRO-2026-00001",
                    "promotion_date": "2026-07-01",
                    "company": "Bude",
                    "current_ctc": 100000,
                    "revised_ctc": 120000,
                }
            ]
        if doctype == "Employee Property History":
            return [
                {
                    "property": "Designation",
                    "fieldname": "designation",
                    "current": "Associate",
                    "new": "Senior Associate",
                },
                {
                    "property": "CTC",
                    "fieldname": "ctc",
                    "current": "100000",
                    "new": "120000",
                },
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = hr_api.profile()

    assert result["ok"] is True
    promotion = result["data"]["promotions"][0]
    assert promotion["promotion_date"] == "2026-07-01"
    assert promotion["changes"] == [
        {
            "field": "designation",
            "label": "Designation",
            "from": "Associate",
            "to": "Senior Associate",
        }
    ]
    assert "current_ctc" not in promotion
    assert "revised_ctc" not in promotion


@patch("bude_api.api.hr.frappe")
def test_profile_includes_only_privacy_safe_transfer_changes(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Employee":
            return [_employee()]
        if doctype == "Employee Transfer":
            return [
                {
                    "name": "HR-EMP-TRN-2026-00001",
                    "transfer_date": "2026-07-15",
                    "company": "Bude India",
                    "new_company": "Bude UAE",
                    "new_employee_id": "EMP-UAE-001",
                }
            ]
        if doctype == "Employee Property History":
            parenttype = next(
                (
                    row[2]
                    for row in kwargs.get("filters", [])
                    if row[0] == "parenttype"
                ),
                "",
            )
            if parenttype == "Employee Transfer":
                return [
                    {
                        "property": "Department",
                        "fieldname": "department",
                        "current": "Operations",
                        "new": "Regional Operations",
                    },
                    {
                        "property": "Salary",
                        "fieldname": "salary",
                        "current": "100000",
                        "new": "150000",
                    },
                ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = hr_api.profile()

    assert result["ok"] is True
    transfer = result["data"]["transfers"][0]
    assert transfer["new_company"] == "Bude UAE"
    assert transfer["changes"] == [
        {
            "field": "department",
            "label": "Department",
            "from": "Operations",
            "to": "Regional Operations",
        }
    ]
    assert "salary" not in transfer


@patch("bude_api.api.hr.frappe")
def test_profile_separation_progress_excludes_interview_and_assignees(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Employee":
            return [_employee()]
        if doctype == "Employee Separation":
            return [
                {
                    "name": "SEP-001",
                    "resignation_letter_date": "2026-07-01",
                    "boarding_begins_on": "2026-07-15",
                    "boarding_status": "In Process",
                    "employee_separation_template": "Standard Exit",
                    "company": "Bude",
                    "exit_interview": "private interview",
                }
            ]
        if doctype == "Employee Boarding Activity":
            return [
                {
                    "activity_name": "Return equipment",
                    "task": "TASK-001",
                    "task_weight": 50,
                    "user": "manager@example.com",
                }
            ]
        if doctype == "Task":
            return [
                {
                    "name": "TASK-001",
                    "status": "Completed",
                    "progress": 100,
                    "exp_end_date": "2026-07-20",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = hr_api.profile()

    assert result["ok"] is True
    separation = result["data"]["separations"][0]
    assert separation["completed_activities"] == 1
    assert separation["activities"][0]["activity"] == "Return equipment"
    assert "exit_interview" not in separation
    assert "user" not in separation["activities"][0]


@patch("bude_api.api.hr.frappe")
def test_profile_employee_groups_expose_membership_and_count_only(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Employee":
            return [_employee()]
        if doctype == "Employee Group":
            return [
                {
                    "name": "Warehouse Safety Team",
                    "employee_group_name": "Warehouse Safety",
                }
            ]
        if doctype == "Employee Group Table":
            filters = kwargs.get("filters", [])
            if ["employee", "=", _employee()["name"]] in filters:
                return [
                    {
                        "parent": "Warehouse Safety Team",
                        "employee": _employee()["name"],
                    }
                ]
            return [
                {"parent": "Warehouse Safety Team", "employee": "EMP-001"},
                {
                    "parent": "Warehouse Safety Team",
                    "employee": "EMP-PRIVATE",
                    "employee_name": "Private Coworker",
                    "user_id": "private@example.com",
                },
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = hr_api.profile()

    assert result["ok"] is True
    assert result["data"]["employee_groups"] == [
        {
            "name": "Warehouse Safety Team",
            "group_name": "Warehouse Safety",
            "member_count": 2,
        }
    ]
    assert "employee_name" not in result["data"]["employee_groups"][0]
    assert "user_id" not in result["data"]["employee_groups"][0]


@patch("bude_api.api.hr.frappe")
def test_profile_leave_blocks_honor_department_and_user_allow_list(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.db.exists.return_value = True

    def get_list(doctype, **kwargs):
        if doctype == "Employee":
            return [_employee()]
        if doctype == "Leave Block List":
            filters = kwargs.get("filters", [])
            if ["name", "=", "Operations Freeze"] in filters:
                return [
                    {
                        "name": "Operations Freeze",
                        "leave_block_list_name": "Operations Freeze",
                        "leave_type": "Annual Leave",
                    }
                ]
            return [
                {
                    "name": "Company Freeze",
                    "leave_block_list_name": "Company Freeze",
                    "leave_type": "",
                }
            ]
        if doctype == "Department":
            return [
                {
                    "name": "Operations",
                    "leave_block_list": "Operations Freeze",
                }
            ]
        if doctype == "Leave Block List Allow":
            return [
                {
                    "parent": "Company Freeze",
                    "allow_user": "employee@example.com",
                }
            ]
        if doctype == "Leave Block List Date":
            return [
                {
                    "parent": "Operations Freeze",
                    "block_date": "2026-08-20",
                    "reason": "Year-end stock count",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    result = hr_api.profile()

    assert result["ok"] is True
    assert result["data"]["leave_blocks"] == [
        {
            "date": "2026-08-20",
            "reason": "Year-end stock count",
            "list": "Operations Freeze",
            "leave_type": "Annual Leave",
        }
    ]
    block_call = next(
        call
        for call in mock_frappe.get_list.call_args_list
        if call.args and call.args[0] == "Leave Block List Date"
    )
    assert ["parent", "in", ["Operations Freeze"]] in block_call.kwargs[
        "filters"
    ]
