"""Grouped helpdesk.field_service endpoints: field_checkins."""

from ._field_service_shared import *  # noqa: F401,F403

def job_check_in(ticket_name: str, latitude=None, longitude=None) -> dict:
    return _visit_toggle(ticket_name, "IN", latitude, longitude)

def job_check_out(ticket_name: str, latitude=None, longitude=None) -> dict:
    return _visit_toggle(ticket_name, "OUT", latitude, longitude)
