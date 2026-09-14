"""Grouped mobile endpoints: visits."""

import json
import math
from datetime import datetime

from ._mobile_shared import *  # noqa: F401,F403

def create_visit(
    customer: str,
    contact: str | None = None,
    notes: str | None = None,
    next_follow_up: str | None = None,
    latitude=None,
    longitude=None,
) -> dict:
    denied = require_sales_role(frappe)
    if denied:
        return denied
    customer = (customer or "").strip()
    if not customer:
        return failure("customer is required.", code="VALIDATION_REQUIRED")
    if not _exists("Customer", customer):
        return failure("Customer not found.", code="VALIDATION_UNKNOWN_CUSTOMER")
    event = _insert_doc(
        {
            "doctype": "Event",
            "subject": f"Customer visit - {customer}",
            "event_type": "Private",
            "description": _visit_description(notes, latitude, longitude),
            "starts_on": frappe.utils.now_datetime() if frappe else None,
            "event_participants": [{"reference_doctype": "Customer", "reference_docname": customer}],
        }
    )
    if event.get("ok") is not True:
        return event
    todo = None
    if next_follow_up:
        todo = _insert_doc(
            {
                "doctype": "ToDo",
                "description": notes or f"Follow up with {customer}",
                "reference_type": "Customer",
                "reference_name": customer,
                "allocated_to": _current_user(),
                "date": next_follow_up,
                "status": "Open",
            }
        )
    return success({"event": event["data"], "follow_up": todo.get("data") if todo else None, "contact": contact})


def visit_check_in(
    customer: str,
    latitude,
    longitude,
    accuracy=None,
    client_request_id: str | None = None,
) -> dict:
    denied = require_sales_role(frappe)
    if denied:
        return denied
    customer = str(customer or "").strip()
    coordinates = _coordinates(latitude, longitude)
    if not customer or coordinates is None:
        return failure("Customer and GPS coordinates are required.", code="VALIDATION_LOCATION")
    if not _exists("Customer", customer):
        return failure("Customer not found.", code="VALIDATION_UNKNOWN_CUSTOMER")

    def action():
        verification = _visit_verification(customer, coordinates, accuracy)
        now = frappe.utils.now_datetime() if frappe else datetime.now()
        event = _insert_doc(
            {
                "doctype": "Event",
                "subject": f"Field visit - {customer}",
                "event_type": "Private",
                "status": "Open",
                "starts_on": now,
                "description": _check_in_description(customer, coordinates, accuracy, verification),
                "event_participants": [
                    {"reference_doctype": "Customer", "reference_docname": customer}
                ],
            }
        )
        if event.get("ok") is not True:
            return event
        return {
            "event": event["data"]["name"],
            "customer": customer,
            "checked_in_at": str(now),
            **verification,
        }

    return _idempotent_visit("check_in", client_request_id, action)


def visit_check_out(
    event: str,
    latitude,
    longitude,
    accuracy=None,
    notes: str | None = None,
    client_request_id: str | None = None,
) -> dict:
    denied = require_sales_role(frappe)
    if denied:
        return denied
    event = str(event or "").strip()
    coordinates = _coordinates(latitude, longitude)
    if not event or coordinates is None:
        return failure("Visit and GPS coordinates are required.", code="VALIDATION_LOCATION")

    def action():
        try:
            doc = frappe.get_doc("Event", event)
        except Exception:
            return failure("Visit not found.", code="NOT_FOUND")
        if not str(getattr(doc, "subject", "")).startswith("Field visit - "):
            return failure("This Event is not a Bude field visit.", code="VALIDATION_VISIT")
        if getattr(doc, "owner", _current_user()) != _current_user() and not _is_sales_manager():
            return permission_denied("Only the visit owner can check out.")
        customer = str(getattr(doc, "subject", "")).removeprefix("Field visit - ").strip()
        verification = _visit_verification(customer, coordinates, accuracy)
        now = frappe.utils.now_datetime() if frappe else datetime.now()
        line = _location_line("Check-out", coordinates, accuracy, verification)
        current = str(getattr(doc, "description", "") or "").strip()
        doc.description = "\n".join(part for part in [current, line, str(notes or "").strip()] if part)
        doc.ends_on = now
        doc.status = "Completed"
        try:
            doc.save(ignore_permissions=False)
            frappe.db.commit()
        except frappe.ValidationError as exc:
            frappe.db.rollback()
            return failure(_erpnext_message(exc), code="VALIDATION_ERPNEXT")
        except frappe.PermissionError:
            frappe.db.rollback()
            return permission_denied()
        return {
            "event": event,
            "customer": customer,
            "checked_out_at": str(now),
            **verification,
        }

    return _idempotent_visit("check_out", client_request_id, action)


def _coordinates(latitude, longitude):
    try:
        lat, lng = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


def _visit_verification(customer, coordinates, accuracy):
    try:
        accuracy_value = float(accuracy) if accuracy not in (None, "") else None
    except (TypeError, ValueError):
        accuracy_value = None
    try:
        max_accuracy = float(frappe.conf.get("bude_sales_visit_max_accuracy_m") or 100)
        radius = float(frappe.conf.get("bude_sales_visit_geofence_m") or 250)
    except Exception:
        max_accuracy, radius = 100.0, 250.0
    customer_coordinates = _customer_coordinates(customer)
    distance = (
        _haversine_meters(coordinates, customer_coordinates)
        if customer_coordinates is not None
        else None
    )
    accurate = accuracy_value is not None and accuracy_value <= max_accuracy
    within = distance is None or distance <= radius
    verified = accurate and within
    reason = (
        "verified"
        if verified
        else "low_accuracy"
        if not accurate
        else "outside_customer_geofence"
    )
    return {
        "verified": verified,
        "verification_reason": reason,
        "accuracy_meters": accuracy_value,
        "distance_from_customer_meters": round(distance, 1) if distance is not None else None,
        "geofence_radius_meters": radius,
    }


def _customer_coordinates(customer):
    try:
        # Dynamic Link is a child DocType and must be queried with get_all() to
        # retain its parent field on Frappe v16.
        links = frappe.get_all(
            "Dynamic Link",
            filters=[
                ["link_doctype", "=", "Customer"],
                ["link_name", "=", customer],
                ["parenttype", "=", "Address"],
            ],
            fields=["parent"],
            limit_page_length=5,
        )
        names = [row.get("parent") for row in links if row.get("parent")]
        if not names:
            return None
        rows = frappe.get_list(
            "Address",
            filters=[["name", "in", names]],
            fields=["latitude", "longitude"],
            limit_page_length=5,
        )
    except Exception:
        return None
    for row in rows:
        value = _coordinates(row.get("latitude"), row.get("longitude"))
        if value is not None:
            return value
    return None


def _haversine_meters(first, second):
    lat1, lng1 = map(math.radians, first)
    lat2, lng2 = map(math.radians, second)
    dlat, dlng = lat2 - lat1, lng2 - lng1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _check_in_description(customer, coordinates, accuracy, verification):
    return "\n".join(
        [
            "BUDE FIELD VISIT",
            f"Customer: {customer}",
            _location_line("Check-in", coordinates, accuracy, verification),
        ]
    )


def _location_line(label, coordinates, accuracy, verification):
    return (
        f"{label}: {coordinates[0]:.7f}, {coordinates[1]:.7f}; "
        f"accuracy={accuracy or ''}m; verified={str(verification['verified']).lower()}; "
        f"reason={verification['verification_reason']}"
    )


def _idempotent_visit(action_name, request_id, action):
    request_id = str(request_id or "").strip()
    if request_id:
        try:
            rows = frappe.get_list(
                "Integration Request",
                filters=[
                    ["integration_request_service", "=", f"bude_sales_visit:{action_name}"],
                    ["request_id", "=", request_id],
                ],
                fields=["output"],
                limit_page_length=1,
            )
        except Exception:
            rows = []
        if rows:
            try:
                return success(json.loads(rows[0].get("output") or "{}"))
            except (TypeError, ValueError):
                pass
    result = action()
    if isinstance(result, dict) and result.get("ok") is False:
        return result
    if request_id:
        try:
            log = frappe.get_doc(
                {
                    "doctype": "Integration Request",
                    "integration_request_service": f"bude_sales_visit:{action_name}",
                    "status": "Completed",
                    "request_id": request_id,
                    "request_description": action_name,
                    "output": json.dumps(result, default=str),
                }
            )
            log.insert(ignore_permissions=True)
        except Exception:
            pass
    return success(result)
