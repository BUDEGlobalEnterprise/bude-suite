"""Grouped admin.masters endpoints: master_records."""

from ._masters_shared import *  # noqa: F401,F403

def list_records(master, search=None, limit=50, offset=0):
    spec, err = _resolve(master)
    if err:
        return err
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    or_filters = None
    if search:
        or_filters = [[fld, "like", f"%{search}%"] for fld in spec["search_fields"]]

    rows = frappe.get_list(
        spec["doctype"],
        fields=_list_fields(spec),
        or_filters=or_filters,
        limit_start=max(0, int(offset or 0)),
        limit_page_length=_coerce_limit(limit, 50, 200),
        order_by="modified desc",
    )
    return success(rows)

def get_record(master, name):
    spec, err = _resolve(master)
    if err:
        return err
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")
    if not _record_exists(spec["doctype"], name):
        return failure(f"{master} '{name}' not found.", code="NOT_FOUND")

    doc = frappe.get_doc(spec["doctype"], name)
    data = {"name": doc.name}
    for fld in _editable_names(spec):
        data[fld] = doc.get(fld)
    return success(data)

def list_link_options(doctype, search=None, limit=20):
    """Dropdown source for link fields. Restricted to doctypes actually
    referenced by the registry, so this can't read arbitrary doctypes."""
    if doctype not in _link_targets():
        return failure(
            f"DocType '{doctype}' is not an allowed link target.",
            code="VALIDATION_BAD_DOCTYPE",
        )
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    or_filters = [["name", "like", f"%{search}%"]] if search else None
    rows = frappe.get_list(
        doctype,
        fields=["name"],
        or_filters=or_filters,
        limit_page_length=_coerce_limit(limit, 20, 50),
        order_by="modified desc",
    )
    return success([row["name"] for row in rows])
