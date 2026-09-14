"""Whitelisted provider-neutral CRM endpoints used by Bude Sales."""

try:
    import frappe
except ImportError:
    frappe = None

from ..services.sales_crm import SalesCrmService
from ..services.sales_crm.deployment import deployment_status, entitlement_status, track_event
from ..services.sales_crm.quote_response import (
    create_payment_request,
    create_response_link,
    response_context,
    response_status,
    submit_response,
)
from ..services.sales_crm.manager import (
    apply_automation,
    automation_templates,
    manager_outcomes,
)


def _whitelist(methods=None, allow_guest=False):
    if frappe is None:
        def decorator(fn):
            return fn
        return decorator
    return frappe.whitelist(methods=methods or ["GET", "POST"], allow_guest=allow_guest)


def _service():
    return SalesCrmService(frappe)


@_whitelist(["GET"])
def bootstrap():
    return _service().bootstrap()


@_whitelist(["GET"])
def setup_doctor():
    return deployment_status(frappe)


@_whitelist(["GET"])
def entitlement():
    return entitlement_status(frappe)


@_whitelist(["POST"])
def telemetry(event, properties=None, client_request_id=None):
    return track_event(frappe, event, properties, client_request_id)


@_whitelist(["POST"])
def quotation_response_link(quotation, valid_days=14):
    return create_response_link(frappe, quotation, valid_days)


@_whitelist(["GET"])
def quotation_response_status(quotation):
    return response_status(frappe, quotation)


@_whitelist(["GET"], allow_guest=True)
def quotation_response_context(quotation, expires, signature):
    return response_context(frappe, quotation, expires, signature)


@_whitelist(["POST"], allow_guest=True)
def quotation_response(quotation, action, expires, signature, notes=None):
    return submit_response(frappe, quotation, action, expires, signature, notes)


@_whitelist(["POST"])
def payment_request(reference_doctype, reference_name):
    return create_payment_request(frappe, reference_doctype, reference_name)


@_whitelist(["GET"])
def manager_dashboard(days=30):
    return manager_outcomes(frappe, days)


@_whitelist(["GET"])
def playbooks():
    return automation_templates(frappe)


@_whitelist(["POST"])
def apply_playbook(template, kind, name, client_request_id=None):
    return apply_automation(frappe, template, kind, name, client_request_id)


@_whitelist(["GET"])
def list_leads(search=None, status=None, source=None, territory=None, assigned_to_me=True, stale_days=None, limit=None, offset=0):
    return _service().list_leads(search, status, source, territory, assigned_to_me in (True, 1, "1", "true", "True"), stale_days, limit, offset)


@_whitelist(["GET"])
def get_lead(lead):
    return _service().get_lead(lead)


@_whitelist(["GET"])
def check_duplicates(email=None, phone=None, name=None, organization=None):
    return _service().check_duplicates(email, phone, name, organization)


@_whitelist(["POST"])
def merge_leads(source, target, payload=None, client_request_id=None):
    return _service().merge_leads(source, target, payload, client_request_id)


@_whitelist(["GET"])
def conversion_options(lead):
    return _service().conversion_options(lead)


@_whitelist(["POST"])
def create_lead(payload, client_request_id=None):
    return _service().create_lead(payload, client_request_id)


@_whitelist(["POST"])
def update_lead(lead, payload, base_modified=None, client_request_id=None):
    return _service().update_lead(lead, payload, base_modified, client_request_id)


@_whitelist(["POST"])
def convert_lead(lead, payload, client_request_id=None):
    return _service().convert_lead(lead, payload, client_request_id)


@_whitelist(["GET"])
def list_deals(search=None, stage=None, assigned_to_me=True, expected_from=None, expected_to=None, stale_days=None, limit=None, offset=0):
    return _service().list_deals(search, stage, assigned_to_me in (True, 1, "1", "true", "True"), expected_from, expected_to, stale_days, limit, offset)


@_whitelist(["GET"])
def get_deal(deal):
    return _service().get_deal(deal)


@_whitelist(["POST"])
def create_deal(payload, client_request_id=None):
    return _service().create_deal(payload, client_request_id)


@_whitelist(["POST"])
def update_deal(deal, payload, base_modified=None, client_request_id=None):
    return _service().update_deal(deal, payload, base_modified, client_request_id)


@_whitelist(["POST"])
def close_deal(deal, outcome, reason=None, notes=None, client_request_id=None, customer=None, create_customer=False):
    return _service().close_deal(
        deal,
        outcome,
        reason,
        notes,
        client_request_id,
        customer,
        create_customer in (True, 1, "1", "true", "True"),
    )


@_whitelist(["POST"])
def create_quotation(deal, payload, client_request_id=None):
    return _service().create_quotation(deal, payload, client_request_id)


@_whitelist(["POST"])
def create_sales_order(quotation, client_request_id=None):
    return _service().create_sales_order(quotation, client_request_id)


@_whitelist(["GET"])
def list_tasks(status=None, assigned_to_me=True, overdue_only=False, reference_kind=None, reference_name=None, limit=None, offset=0):
    return _service().list_tasks(status, assigned_to_me in (True, 1, "1", "true", "True"), overdue_only in (True, 1, "1", "true", "True"), reference_kind, reference_name, limit, offset)


@_whitelist(["POST"])
def create_task(payload, client_request_id=None):
    return _service().create_task(payload, client_request_id)


@_whitelist(["POST"])
def update_task(task, payload, base_modified=None, client_request_id=None):
    return _service().update_task(task, payload, base_modified, client_request_id)


@_whitelist(["GET"])
def timeline(kind, name, limit=50):
    return _service().timeline(kind, name, limit)


@_whitelist(["POST"])
def add_note(kind, name, content, title=None, client_request_id=None):
    return _service().add_note(kind, name, content, title, client_request_id)


@_whitelist(["POST"])
def upload_attachment(kind, name, file_name, content_base64, client_request_id=None):
    return _service().upload_attachment(kind, name, file_name, content_base64, client_request_id)


@_whitelist(["POST"])
def delete_attachment(kind, name, attachment):
    return _service().delete_attachment(kind, name, attachment)


@_whitelist(["POST"])
def log_activity(payload, client_request_id=None):
    return _service().log_activity(payload, client_request_id)


@_whitelist(["POST"])
def send_email(kind, name, recipients, subject, content, client_request_id=None):
    return _service().send_email(kind, name, recipients, subject, content, client_request_id)


@_whitelist(["GET"])
def analytics(scope="mine"):
    return _service().analytics(scope)


@_whitelist(["POST"])
def bulk_update(kind, names, payload):
    return _service().bulk_update(kind, names, payload)


@_whitelist(["POST"], allow_guest=True)
def capture_intake(channel, payload, timestamp, signature, external_id=None):
    return _service().capture_intake(channel, payload, timestamp, signature, external_id)
