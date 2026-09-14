"""Grouped admin.masters endpoints: master_writes."""

from ._masters_shared import *  # noqa: F401,F403

def create_record(master, values):
    spec, err = _resolve(master)
    if err:
        return err
    values = _clean(spec, values)
    req_err = _check_required(spec, values)
    if req_err:
        return req_err
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    def _do():
        doc = frappe.get_doc({"doctype": spec["doctype"], **values})
        doc.insert(ignore_permissions=False)
        return success({"name": doc.name})

    return _mutate(_do)

def update_record(master, name, values):
    spec, err = _resolve(master)
    if err:
        return err
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    if not _record_exists(spec["doctype"], name):
        return failure(f"{master} '{name}' not found.", code="NOT_FOUND")

    values = _clean(spec, values)
    return _mutate(lambda: _save(spec, name, values))

def set_disabled(master, name, disabled=True):
    spec, err = _resolve(master)
    if err:
        return err
    field = spec.get("disable_field")
    if not field:
        return failure(
            f"'{master}' does not support disabling.", code="DISABLE_NOT_SUPPORTED"
        )
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    if not _record_exists(spec["doctype"], name):
        return failure(f"{master} '{name}' not found.", code="NOT_FOUND")

    value = (
        spec.get("disable_value", 1)
        if _as_bool(disabled)
        else spec.get("enable_value", 0)
    )
    return _mutate(lambda: _save(spec, name, {field: value}))
