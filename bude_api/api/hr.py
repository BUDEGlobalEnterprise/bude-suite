"""Public API wrappers for `hr.py`.

Business logic lives in `bude_api.services.hr.mobile`.
Endpoint names stay here for Frappe/mobile compatibility.
"""
import builtins
import inspect
try:
    import frappe
except ImportError:
    frappe = None
_PUBLIC_NAMES = {'profile', 'employee_documents', 'attendance_status', 'attendance_history', 'attendance_summary', 'check_in', 'upload_checkin_selfie', 'shift_status', 'shift_roster', 'shift_requests', 'apply_shift_request', 'manager_pending_shift_requests', 'decide_shift_request', 'attendance_calendar', 'attendance_requests', 'apply_attendance_request', 'leave_balances', 'holidays', 'apply_leave', 'leave_requests', 'leave_request_detail', 'upload_leave_attachment', 'leave_attachments', 'cancel_leave', 'comp_off_requests', 'apply_comp_off', 'expense_claims', 'submit_expense_claim', 'expense_types', 'expense_claim_detail', 'upload_expense_attachment', 'expense_attachments', 'employee_advances', 'apply_employee_advance', 'travel_requests', 'apply_travel_request', 'todo_requests', 'submit_todo_request', 'grievances', 'submit_grievance', 'salary_slips', 'salary_slip_detail', 'salary_slip_pdf_url', 'salary_ytd', 'tax_declarations', 'submit_tax_declaration', 'appraisals', 'training_events', 'notifications', 'notification_detail', 'mark_notification_read', 'register_push_token', 'clear_push_token', 'manager_pending_leaves', 'manager_pending_expenses', 'manager_summary', 'manager_direct_reports', 'manager_team_attendance_exceptions', 'manager_report_profile', 'manager_team_calendar', 'manager_today', 'attendance_anomalies', 'timesheets', 'submit_timesheet', 'onboarding_checklists', 'complete_onboarding_activity', 'decide_leave', 'decide_expense', 'export_history', 'salary_tax_projection'}
from ..services.hr import mobile as _service
def _whitelist(methods=None, allow_guest: bool = False):
    if frappe is None:
        def decorator(fn):
            return fn
        return decorator
    return frappe.whitelist(allow_guest=allow_guest, methods=methods or ["GET", "POST"])
def _export_service_helpers():
    for name, value in vars(_service).items():
        if name == "frappe" or name.startswith("__"):
            continue
        globals().setdefault(name, value)

_export_service_helpers()
def _sync_service_globals():
    if hasattr(_service, "frappe"):
        _service.frappe = frappe
    if hasattr(_service, "sync_frappe"):
        _service.sync_frappe(frappe)
    reserved = {"builtins", "inspect", "frappe", "_service", "_whitelist", "_export_service_helpers", "_sync_service_globals", "_call", "_PUBLIC_NAMES"} | _PUBLIC_NAMES
    for name, value in builtins.list(globals().items()):
        if name in reserved or name.startswith("__"):
            continue
        if hasattr(_service, name):
            setattr(_service, name, value)
    for value in builtins.list(vars(_service).values()):
        if inspect.ismodule(value) and getattr(value, "__name__", "").startswith("bude_api.services") and hasattr(value, "frappe"):
            value.frappe = frappe
        if callable(value) and hasattr(value, "__globals__") and value.__globals__.get("__name__") == getattr(_service, "__name__", None) and "frappe" in value.__globals__:
            value.__globals__["frappe"] = frappe
    if hasattr(_service, "sync_frappe"):
        _service.sync_frappe(frappe)

def _call(name, *args, **kwargs):
    _sync_service_globals()
    return getattr(_service, name)(*args, **kwargs)
@_whitelist(["GET", "POST"])
def profile():
    return _call("profile")

@_whitelist(["GET", "POST"])
def employee_documents(limit: int=50):
    return _call("employee_documents", limit)

@_whitelist(["GET", "POST"])
def attendance_status():
    return _call("attendance_status")

@_whitelist(["GET", "POST"])
def attendance_history(limit: int=30):
    return _call("attendance_history", limit)

@_whitelist(["GET", "POST"])
def attendance_summary(days: int=30):
    return _call("attendance_summary", days)

@_whitelist(["POST"])
def check_in(type: str='IN', latitude: float | None=None, longitude: float | None=None, accuracy: float | None=None):
    return _call("check_in", type, latitude, longitude, accuracy)

@_whitelist(["POST"])
def upload_checkin_selfie(checkin_name: str, file_name: str, content_base64: str):
    return _call("upload_checkin_selfie", checkin_name, file_name, content_base64)

@_whitelist(["GET", "POST"])
def shift_status():
    return _call("shift_status")

@_whitelist(["GET", "POST"])
def shift_roster(month: str | None=None, limit: int=50, offset: int=0):
    return _call("shift_roster", month, limit, offset)

@_whitelist(["GET", "POST"])
def shift_requests(limit: int=50, offset: int=0):
    return _call("shift_requests", limit, offset)

@_whitelist(["POST"])
def apply_shift_request(shift_type: str, from_date: str, to_date: str, reason: str | None=None):
    return _call("apply_shift_request", shift_type, from_date, to_date, reason)

@_whitelist(["GET", "POST"])
def manager_pending_shift_requests(limit: int=50, offset: int=0):
    return _call("manager_pending_shift_requests", limit, offset)

@_whitelist(["POST"])
def decide_shift_request(name: str, approved: bool, comment: str | None=None):
    return _call("decide_shift_request", name, approved, comment)

@_whitelist(["GET", "POST"])
def attendance_calendar(month: str | None=None):
    return _call("attendance_calendar", month)

@_whitelist(["GET", "POST"])
def attendance_requests(limit: int=50):
    return _call("attendance_requests", limit)

@_whitelist(["POST"])
def apply_attendance_request(from_date: str, to_date: str, reason: str, explanation: str | None=None, half_day: bool=False, half_day_date: str | None=None):
    return _call("apply_attendance_request", from_date, to_date, reason, explanation, half_day, half_day_date)

@_whitelist(["GET", "POST"])
def leave_balances():
    return _call("leave_balances")

@_whitelist(["GET", "POST"])
def holidays(from_date: str | None=None, to_date: str | None=None, limit: int=100):
    return _call("holidays", from_date, to_date, limit)

@_whitelist(["POST"])
def apply_leave(leave_type: str, from_date: str, to_date: str, reason: str | None=None, half_day: bool=False, half_day_date: str | None=None):
    return _call("apply_leave", leave_type, from_date, to_date, reason, half_day, half_day_date)

@_whitelist(["GET", "POST"])
def leave_requests(limit: int=50):
    return _call("leave_requests", limit)

@_whitelist(["GET", "POST"])
def leave_request_detail(name: str):
    return _call("leave_request_detail", name)

@_whitelist(["POST"])
def upload_leave_attachment(leave_name: str, file_name: str, content_base64: str):
    return _call("upload_leave_attachment", leave_name, file_name, content_base64)

@_whitelist(["GET", "POST"])
def leave_attachments(leave_name: str, limit: int=20):
    return _call("leave_attachments", leave_name, limit)

@_whitelist(["POST"])
def cancel_leave(name: str):
    return _call("cancel_leave", name)

@_whitelist(["GET", "POST"])
def comp_off_requests(limit: int=50):
    return _call("comp_off_requests", limit)

@_whitelist(["POST"])
def apply_comp_off(leave_type: str, work_from_date: str, work_end_date: str, reason: str | None=None, half_day: bool=False, half_day_date: str | None=None):
    return _call("apply_comp_off", leave_type, work_from_date, work_end_date, reason, half_day, half_day_date)

@_whitelist(["GET", "POST"])
def expense_claims(limit: int=50):
    return _call("expense_claims", limit)

@_whitelist(["POST"])
def submit_expense_claim(expense_type: str, amount: float, description: str | None=None, posting_date: str | None=None):
    return _call("submit_expense_claim", expense_type, amount, description, posting_date)

@_whitelist(["GET", "POST"])
def expense_types():
    return _call("expense_types")

@_whitelist(["GET", "POST"])
def expense_claim_detail(name: str):
    return _call("expense_claim_detail", name)

@_whitelist(["POST"])
def upload_expense_attachment(claim_name: str, file_name: str, content_base64: str):
    return _call("upload_expense_attachment", claim_name, file_name, content_base64)

@_whitelist(["GET", "POST"])
def expense_attachments(claim_name: str, limit: int=20):
    return _call("expense_attachments", claim_name, limit)

@_whitelist(["GET", "POST"])
def employee_advances(limit: int=50):
    return _call("employee_advances", limit)

@_whitelist(["POST"])
def apply_employee_advance(amount: float, purpose: str, posting_date: str | None=None):
    return _call("apply_employee_advance", amount, purpose, posting_date)

@_whitelist(["GET", "POST"])
def travel_requests(limit: int=50):
    return _call("travel_requests", limit)

@_whitelist(["POST"])
def apply_travel_request(travel_type: str, purpose: str, description: str | None=None, travel_funding: str | None=None):
    return _call("apply_travel_request", travel_type, purpose, description, travel_funding)

@_whitelist(["GET", "POST"])
def todo_requests(limit: int=50, offset: int=0):
    return _call("todo_requests", limit, offset)

@_whitelist(["POST"])
def submit_todo_request(subject: str, description: str | None=None, priority: str='Medium'):
    return _call("submit_todo_request", subject, description, priority)

@_whitelist(["GET", "POST"])
def grievances(limit: int=50):
    return _call("grievances", limit)

@_whitelist(["POST"])
def submit_grievance(subject: str, description: str, grievance_type: str | None=None, grievance_against_party: str | None=None, grievance_against: str | None=None):
    return _call("submit_grievance", subject, description, grievance_type, grievance_against_party, grievance_against)

@_whitelist(["GET", "POST"])
def salary_slips(limit: int=24):
    return _call("salary_slips", limit)

@_whitelist(["GET", "POST"])
def salary_slip_detail(name: str):
    return _call("salary_slip_detail", name)

@_whitelist(["GET", "POST"])
def salary_slip_pdf_url(name: str, print_format: str='Standard'):
    return _call("salary_slip_pdf_url", name, print_format)

@_whitelist(["GET", "POST"])
def salary_ytd(year: int | str | None=None):
    return _call("salary_ytd", year)

@_whitelist(["GET", "POST"])
def tax_declarations(limit: int=50, offset: int=0):
    return _call("tax_declarations", limit, offset)

@_whitelist(["POST"])
def submit_tax_declaration(payroll_period: str, amount: float, exemption_sub_category: str | None=None):
    return _call("submit_tax_declaration", payroll_period, amount, exemption_sub_category)

@_whitelist(["GET", "POST"])
def appraisals(limit: int=20):
    return _call("appraisals", limit)

@_whitelist(["GET", "POST"])
def training_events(limit: int=50):
    return _call("training_events", limit)

@_whitelist(["GET", "POST"])
def notifications(limit: int=50):
    return _call("notifications", limit)

@_whitelist(["GET", "POST"])
def notification_detail(name: str):
    return _call("notification_detail", name)

@_whitelist(["POST"])
def mark_notification_read(name: str):
    return _call("mark_notification_read", name)

@_whitelist(["POST"])
def register_push_token(token: str, platform: str='', device_id: str=''):
    return _call("register_push_token", token, platform, device_id)

@_whitelist(["POST"])
def clear_push_token(token: str='', device_id: str=''):
    return _call("clear_push_token", token, device_id)

@_whitelist(["GET", "POST"])
def manager_pending_leaves(limit: int=50):
    return _call("manager_pending_leaves", limit)

@_whitelist(["GET", "POST"])
def manager_pending_expenses(limit: int=50):
    return _call("manager_pending_expenses", limit)

@_whitelist(["GET", "POST"])
def manager_summary():
    return _call("manager_summary")

@_whitelist(["GET", "POST"])
def manager_direct_reports(limit: int=100):
    return _call("manager_direct_reports", limit)

@_whitelist(["GET", "POST"])
def manager_team_attendance_exceptions(days: int=7, limit: int=100):
    return _call("manager_team_attendance_exceptions", days, limit)

@_whitelist(["GET", "POST"])
def manager_report_profile(employee: str):
    return _call("manager_report_profile", employee)

@_whitelist(["GET", "POST"])
def manager_team_calendar(month: str | None=None, limit: int=500):
    return _call("manager_team_calendar", month, limit)

@_whitelist(["GET", "POST"])
def manager_today():
    return _call("manager_today")

@_whitelist(["GET", "POST"])
def attendance_anomalies(from_date: str | None=None, to_date: str | None=None, type: str | None=None, late_minutes: int=15, limit: int=50, offset: int=0):
    return _call("attendance_anomalies", from_date, to_date, type, late_minutes, limit, offset)

@_whitelist(["GET", "POST"])
def timesheets(limit: int=50, offset: int=0):
    return _call("timesheets", limit, offset)

@_whitelist(["POST"])
def submit_timesheet(activity_type: str, from_time: str, to_time: str, hours: float, project: str | None=None, task: str | None=None, note: str | None=None):
    return _call("submit_timesheet", activity_type, from_time, to_time, hours, project, task, note)

@_whitelist(["GET", "POST"])
def onboarding_checklists(limit: int=50, offset: int=0):
    return _call("onboarding_checklists", limit, offset)

@_whitelist(["POST"])
def complete_onboarding_activity(parent_doctype: str, parent_name: str, activity_name: str):
    return _call("complete_onboarding_activity", parent_doctype, parent_name, activity_name)

@_whitelist(["POST"])
def decide_leave(name: str, approved: bool, comment: str | None=None):
    return _call("decide_leave", name, approved, comment)

@_whitelist(["POST"])
def decide_expense(name: str, approved: bool, comment: str | None=None):
    return _call("decide_expense", name, approved, comment)

@_whitelist(["GET", "POST"])
def export_history(kind: str, from_date: str | None=None, to_date: str | None=None, format: str='csv'):
    return _call("export_history", kind, from_date, to_date, format)

@_whitelist(["GET", "POST"])
def salary_tax_projection(year: int | str | None=None):
    return _call("salary_tax_projection", year)
