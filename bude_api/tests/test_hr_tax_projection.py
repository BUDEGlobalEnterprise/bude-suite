from unittest.mock import patch

from bude_api.api import hr as hr_api


def _wire(mock_frappe, roles=None):
    mock_frappe.session.user = "employee@example.com"
    mock_frappe.get_roles.return_value = roles or ["Employee"]
    mock_frappe.db.exists.return_value = True


def _employee_row():
    return {
        "name": "EMP-001",
        "employee_name": "Alice Employee",
        "company": "Bude",
        "department": "Operations",
        "designation": "Associate",
        "user_id": "employee@example.com",
    }


def _slip(month: int, gross: float):
    return {
        "name": f"SAL-{month:02d}",
        "start_date": f"2026-{month:02d}-01",
        "gross_pay": gross,
        "total_deduction": 0,
        "net_pay": gross,
        "currency": "AED",
    }


def _wire_lists(
    mock_frappe,
    slips,
    *,
    period=None,
    declarations=None,
    slab="Slab A",
):
    """Feed the five get_list calls the projection makes, in order."""
    period_rows = [period] if period else []
    mock_frappe.get_list.side_effect = [
        [_employee_row()],
        period_rows,
        slips,
        declarations if declarations is not None else [],
        [{"income_tax_slab": slab}],
    ]


@patch("bude_api.api.hr.frappe")
def test_projects_the_year_from_the_months_already_paid(mock_frappe):
    _wire(mock_frappe)
    _wire_lists(
        mock_frappe,
        [_slip(1, 10000), _slip(2, 10000), _slip(3, 10000)],
        period={
            "name": "2026 Payroll",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
        declarations=[{"total_exemption_amount": 5000}],
    )
    mock_frappe.get_all.return_value = [{"amount": 500}] * 3

    result = hr_api.salary_tax_projection(2026)

    data = result["data"]
    assert data["slips_paid"] == 3
    assert data["gross_ytd"] == 30000
    assert data["tax_deducted_ytd"] == 1500
    # Three months of 10000 across a twelve-month period.
    assert data["projected_annual_gross"] == 120000
    assert data["projected_annual_tax"] == 6000
    assert data["declared_exemption"] == 5000
    assert data["income_tax_slab"] == "Slab A"
    assert data["payroll_period"] == "2026 Payroll"
    assert data["currency"] == "AED"


@patch("bude_api.api.hr.frappe")
def test_only_income_tax_components_count_as_tax(mock_frappe):
    _wire(mock_frappe)
    _wire_lists(mock_frappe, [_slip(1, 10000)])
    mock_frappe.get_all.return_value = [{"amount": 500}]

    hr_api.salary_tax_projection(2026)

    # A loan repayment is a deduction too — filtering on the tax flag is what
    # keeps it out of the projection.
    filters = mock_frappe.get_all.call_args.kwargs["filters"]
    assert filters["is_income_tax_component"] == 1
    assert filters["parentfield"] == "deductions"


@patch("bude_api.api.hr.frappe")
def test_a_year_with_no_slips_projects_zero_rather_than_dividing_by_zero(
    mock_frappe,
):
    _wire(mock_frappe)
    _wire_lists(mock_frappe, [])

    data = hr_api.salary_tax_projection(2026)["data"]

    assert data["slips_paid"] == 0
    assert data["projected_annual_gross"] == 0
    assert data["projected_annual_tax"] == 0
    assert data["currency"] == ""


@patch("bude_api.api.hr.frappe")
def test_a_site_without_a_payroll_period_falls_back_to_the_calendar_year(
    mock_frappe,
):
    _wire(mock_frappe)
    _wire_lists(mock_frappe, [_slip(1, 1000)])
    mock_frappe.get_all.return_value = []

    data = hr_api.salary_tax_projection(2026)["data"]

    assert data["payroll_period"] == ""
    assert data["start_date"] == "2026-01-01"
    assert data["end_date"] == "2026-12-31"
    assert data["months_in_period"] == 12


@patch("bude_api.api.hr.frappe")
def test_a_short_payroll_period_projects_over_its_own_length(mock_frappe):
    # A company that started mid-year has a six-month first period; projecting
    # over twelve months would double its numbers.
    _wire(mock_frappe)
    _wire_lists(
        mock_frappe,
        [_slip(7, 10000), _slip(8, 10000)],
        period={
            "name": "2026 H2",
            "start_date": "2026-07-01",
            "end_date": "2026-12-31",
        },
    )
    mock_frappe.get_all.return_value = []

    data = hr_api.salary_tax_projection(2026)["data"]

    assert data["months_in_period"] == 6
    assert data["projected_annual_gross"] == 60000


@patch("bude_api.api.hr.frappe")
def test_only_submitted_slips_of_this_employee_are_read(mock_frappe):
    _wire(mock_frappe)
    _wire_lists(mock_frappe, [])

    hr_api.salary_tax_projection(2026)

    slip_call = mock_frappe.get_list.call_args_list[2]
    assert slip_call.args[0] == "Salary Slip"
    assert ["employee", "=", "EMP-001"] in slip_call.kwargs["filters"]
    assert ["docstatus", "=", 1] in slip_call.kwargs["filters"]


@patch("bude_api.api.hr.frappe")
def test_projection_requires_an_hr_role(mock_frappe):
    _wire(mock_frappe, roles=["Stock User"])

    result = hr_api.salary_tax_projection()

    assert result["ok"] is False
    assert result["code"] == "PERMISSION_DENIED"
    mock_frappe.get_list.assert_not_called()


@patch("bude_api.api.hr.frappe")
def test_a_site_without_salary_slips_says_so_instead_of_crashing(mock_frappe):
    _wire(mock_frappe)
    mock_frappe.get_list.return_value = [_employee_row()]
    mock_frappe.db.exists.return_value = False

    result = hr_api.salary_tax_projection()

    assert result["ok"] is False
    assert result["code"] == "HR_DOCTYPE_UNAVAILABLE"
