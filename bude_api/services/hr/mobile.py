"""Grouped service facade for `hr.mobile` endpoints."""

from . import profile as _profile
from .profile import profile, employee_documents
from . import attendance as _attendance
from .attendance import attendance_status, attendance_history, attendance_summary, check_in, upload_checkin_selfie, attendance_calendar, attendance_requests, apply_attendance_request, attendance_anomalies
from . import shifts as _shifts
from .shifts import shift_status, shift_roster, shift_requests, apply_shift_request, manager_pending_shift_requests, decide_shift_request
from . import leave as _leave
from .leave import leave_balances, holidays, apply_leave, leave_requests, leave_request_detail, upload_leave_attachment, leave_attachments, cancel_leave, comp_off_requests, apply_comp_off, manager_pending_leaves, decide_leave
from . import expenses as _expenses
from .expenses import expense_claims, submit_expense_claim, expense_types, expense_claim_detail, upload_expense_attachment, expense_attachments, employee_advances, apply_employee_advance, manager_pending_expenses, decide_expense
from . import requests as _requests
from .requests import travel_requests, apply_travel_request, todo_requests, submit_todo_request, grievances, submit_grievance
from . import payroll as _payroll
from .payroll import salary_slips, salary_slip_detail, salary_slip_pdf_url, salary_ytd, tax_declarations, submit_tax_declaration, salary_tax_projection
from . import learning as _learning
from .learning import appraisals, training_events, onboarding_checklists, complete_onboarding_activity
from . import notifications as _notifications
from .notifications import notifications, notification_detail, mark_notification_read, register_push_token, clear_push_token
from . import manager as _manager
from .manager import manager_summary, manager_direct_reports, manager_team_attendance_exceptions, manager_report_profile, manager_team_calendar, manager_today, timesheets, submit_timesheet
from . import exports as _exports
from .exports import export_history
from . import _mobile_shared as _shared

for _name, _value in vars(_shared).items():
    if not _name.startswith("__"):
        globals().setdefault(_name, _value)

_GROUP_MODULES = [_profile, _attendance, _shifts, _leave, _expenses, _requests, _payroll, _learning, _notifications, _manager, _exports]

def sync_frappe(frappe_module):
    _shared.frappe = frappe_module
    _facade_globals = globals()
    _skip = {"_shared", "_GROUP_MODULES", "sync_frappe", "_facade_globals", "_skip", "_name", "_value", "module", "value"}
    for _name, _value in list(_facade_globals.items()):
        if _name.startswith("__") or _name in _skip:
            continue
        if hasattr(_shared, _name):
            setattr(_shared, _name, _value)
    for module in _GROUP_MODULES:
        if hasattr(module, "frappe"):
            module.frappe = frappe_module
        for _name, _value in list(_facade_globals.items()):
            if _name.startswith("__") or _name in _skip:
                continue
            if hasattr(module, _name):
                setattr(module, _name, _value)
        for value in vars(module).values():
            if callable(value) and hasattr(value, "__globals__") and "frappe" in value.__globals__:
                value.__globals__["frappe"] = frappe_module
