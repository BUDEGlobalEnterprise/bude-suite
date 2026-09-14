"""Grouped mobile endpoints: payroll."""

from ._mobile_shared import *  # noqa: F401,F403

def salary_slips(limit: int = 24) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Salary Slip")
    if missing:
        return missing
    rows = frappe.get_list(
        "Salary Slip",
        filters=[["employee", "=", employee["name"]], ["docstatus", "=", 1]],
        fields=["name", "start_date", "end_date", "net_pay"],
        order_by="start_date desc",
        limit_page_length=max(1, min(int(limit), 60)),
    )
    return success(rows)

def salary_slip_detail(name: str) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Salary Slip", "Salary Detail")
    if missing:
        return missing
    rows = frappe.get_list(
        "Salary Slip",
        filters=[
            ["name", "=", name],
            ["employee", "=", employee["name"]],
            ["docstatus", "=", 1],
        ],
        fields=[
            "name",
            "start_date",
            "end_date",
            "gross_pay",
            "total_deduction",
            "net_pay",
        ],
        limit_page_length=1,
    )
    if not rows:
        return failure("Salary slip not found.", code="HR_SALARY_NOT_FOUND")
    slip = rows[0]
    components = frappe.get_list(
        "Salary Detail",
        filters=[["parent", "=", name]],
        fields=["parentfield", "salary_component", "amount"],
        limit_page_length=200,
    )

    def _by(field: str) -> list[dict]:
        return [
            {"component": row.get("salary_component"), "amount": float(row.get("amount") or 0)}
            for row in components
            if row.get("parentfield") == field
        ]

    return success(
        {
            "name": slip.get("name"),
            "start_date": str(slip.get("start_date") or ""),
            "end_date": str(slip.get("end_date") or ""),
            "gross_pay": float(slip.get("gross_pay") or 0),
            "total_deduction": float(slip.get("total_deduction") or 0),
            "net_pay": float(slip.get("net_pay") or 0),
            "earnings": _by("earnings"),
            "deductions": _by("deductions"),
        }
    )

def salary_slip_pdf_url(name: str, print_format: str = "Standard") -> dict:
    slip, error = _owned_salary_slip(name)
    if error:
        return error
    path = (
        "/api/method/frappe.utils.print_format.download_pdf"
        f"?doctype=Salary%20Slip&name={slip['name']}"
        f"&format={print_format or 'Standard'}&no_letterhead=0"
    )
    return success(
        {
            "name": slip["name"],
            # Resolve on the client against its signed-in public site. Using
            # frappe.utils.get_url here exposed private reverse-proxy hosts.
            "url": path,
        }
    )

def salary_ytd(year: int | str | None = None) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Salary Slip")
    if missing:
        return missing
    target_year = int(year or date.today().year)
    rows = frappe.get_list(
        "Salary Slip",
        filters=[
            ["employee", "=", employee["name"]],
            ["docstatus", "=", 1],
            ["start_date", ">=", f"{target_year}-01-01"],
            ["start_date", "<=", f"{target_year}-12-31"],
        ],
        fields=["name", "gross_pay", "total_deduction", "net_pay"],
        order_by="start_date asc",
        limit_page_length=60,
    )
    gross = sum(float(row.get("gross_pay") or 0) for row in rows)
    deductions = sum(float(row.get("total_deduction") or 0) for row in rows)
    net = sum(float(row.get("net_pay") or 0) for row in rows)
    return success(
        {
            "year": target_year,
            "gross_pay": gross,
            "total_deduction": deductions,
            "net_pay": net,
            "slip_count": len(rows),
        }
    )

def tax_declarations(limit: int = 50, offset: int = 0) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Employee Tax Exemption Declaration")
    if missing:
        return missing
    page_limit, page_offset = _page(limit, offset)
    rows = frappe.get_list(
        "Employee Tax Exemption Declaration",
        filters=[["employee", "=", employee["name"]]],
        fields=[
            "name",
            "payroll_period",
            "currency",
            "total_exemption_amount",
            "docstatus",
            "creation",
        ],
        order_by="creation desc",
        limit_start=page_offset,
        limit_page_length=page_limit,
    )
    return success(
        [
            {
                "name": row.get("name"),
                "payroll_period": row.get("payroll_period") or "",
                "currency": row.get("currency") or "",
                "amount": float(row.get("total_exemption_amount") or 0),
                "docstatus": int(row.get("docstatus") or 0),
                "creation": str(row.get("creation") or ""),
            }
            for row in rows
        ]
    )

def submit_tax_declaration(
    payroll_period: str, amount: float, exemption_sub_category: str | None = None
) -> dict:
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Employee Tax Exemption Declaration")
    if missing:
        return missing
    if not payroll_period or float(amount or 0) <= 0:
        return failure(
            "payroll_period and positive amount are required.", code="VALIDATION_REQUIRED"
        )
    try:
        payload = {
            "doctype": "Employee Tax Exemption Declaration",
            "employee": employee["name"],
            "company": employee.get("company"),
            "payroll_period": payroll_period,
            "total_exemption_amount": amount,
        }
        if exemption_sub_category:
            payload["declarations"] = [
                {
                    "exemption_sub_category": exemption_sub_category,
                    "amount": amount,
                }
            ]
        doc = frappe.get_doc(payload)
        doc.insert(ignore_permissions=False)
        frappe.db.commit()
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure("You do not have permission for this action.", code="PERMISSION_DENIED")
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(str(exc), code="VALIDATION_ERPNEXT")
    return success({"name": doc.name})

def salary_tax_projection(year: int | str | None = None) -> dict:
    """Project this payroll period's gross and tax from the slips issued so far.

    Deliberately arithmetic rather than a tax calculation: HRMS owns the real
    engine (slabs, cess, regime rules) and re-implementing it here would drift
    from whatever payroll actually pays. This extrapolates the periods already
    paid across the whole payroll period and reports the declared exemption
    beside it, which is what an employee wants mid-year — hence "projection".
    """
    employee, error = _employee_or_failure()
    if error:
        return error
    missing = _require_doctypes("Salary Slip")
    if missing:
        return missing
    target_year = int(year or date.today().year)

    period = _payroll_period(employee, target_year)
    start = _date_or_none(period.get("start_date")) or date(target_year, 1, 1)
    end = _date_or_none(period.get("end_date")) or date(target_year, 12, 31)

    slips = frappe.get_list(
        "Salary Slip",
        filters=[
            ["employee", "=", employee["name"]],
            ["docstatus", "=", 1],
            ["start_date", ">=", start.isoformat()],
            ["start_date", "<=", end.isoformat()],
        ],
        fields=["name", "start_date", "gross_pay", "total_deduction", "net_pay", "currency"],
        order_by="start_date asc",
        limit_page_length=60,
    )
    gross_ytd = sum(float(row.get("gross_pay") or 0) for row in slips)
    tax_ytd = _income_tax_deducted(slips)

    # Salary slips are monthly on every site we run, so "months paid" is just
    # the slip count; a period is 12 months unless payroll says otherwise.
    months_in_period = max(1, round(((end - start).days + 1) / 30.4375))
    paid = len(slips)
    projected_gross = gross_ytd / paid * months_in_period if paid else 0.0
    projected_tax = tax_ytd / paid * months_in_period if paid else 0.0

    return success(
        {
            "year": target_year,
            "payroll_period": period.get("name") or "",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "currency": (slips[0].get("currency") if slips else "") or "",
            "slips_paid": paid,
            "months_in_period": months_in_period,
            "gross_ytd": gross_ytd,
            "tax_deducted_ytd": tax_ytd,
            "projected_annual_gross": projected_gross,
            "projected_annual_tax": projected_tax,
            "declared_exemption": _declared_exemption(employee, period.get("name")),
            "income_tax_slab": _income_tax_slab(employee),
        }
    )

def _payroll_period(employee: dict, target_year: int) -> dict:
    """The Payroll Period covering [target_year], when the site defines one."""
    if not frappe.db.exists("DocType", "Payroll Period"):
        return {}
    rows = frappe.get_list(
        "Payroll Period",
        filters=[
            ["company", "=", employee.get("company")],
            ["start_date", "<=", f"{target_year}-12-31"],
            ["end_date", ">=", f"{target_year}-01-01"],
        ],
        fields=["name", "start_date", "end_date"],
        order_by="start_date desc",
        limit_page_length=1,
    )
    return rows[0] if rows else {}

def _income_tax_deducted(slips: list[dict]) -> float:
    """Sum only the tax rows of each slip's deductions, not every deduction.

    Loan repayments and salary advances are deductions too; counting them as
    tax would overstate the projection badly.
    """
    if not slips or not frappe.db.exists("DocType", "Salary Detail"):
        return 0.0
    rows = frappe.get_all(
        "Salary Detail",
        filters={
            "parent": ["in", [slip["name"] for slip in slips]],
            "parentfield": "deductions",
            "is_income_tax_component": 1,
        },
        fields=["amount"],
        ignore_permissions=True,
    )
    return sum(float(row.get("amount") or 0) for row in rows)

def _declared_exemption(employee: dict, payroll_period: str | None) -> float:
    if not payroll_period or not frappe.db.exists(
        "DocType", "Employee Tax Exemption Declaration"
    ):
        return 0.0
    rows = frappe.get_list(
        "Employee Tax Exemption Declaration",
        filters=[
            ["employee", "=", employee["name"]],
            ["payroll_period", "=", payroll_period],
            ["docstatus", "=", 1],
        ],
        fields=["total_exemption_amount"],
        limit_page_length=20,
    )
    return sum(float(row.get("total_exemption_amount") or 0) for row in rows)

def _income_tax_slab(employee: dict) -> str:
    """The slab from the employee's current salary structure assignment."""
    if not frappe.db.exists("DocType", "Salary Structure Assignment"):
        return ""
    rows = frappe.get_list(
        "Salary Structure Assignment",
        filters=[["employee", "=", employee["name"]], ["docstatus", "=", 1]],
        fields=["income_tax_slab"],
        order_by="from_date desc",
        limit_page_length=1,
    )
    return (rows[0].get("income_tax_slab") if rows else "") or ""
