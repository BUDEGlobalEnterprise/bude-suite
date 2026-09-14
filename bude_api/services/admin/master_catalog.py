"""Grouped admin.masters endpoints: master_catalog."""

from ._masters_shared import *  # noqa: F401,F403

def list_masters():
    """Catalog of editable masters + their field schema (drives the UI)."""
    out = []
    for key, spec in MASTERS.items():
        out.append(
            {
                "key": key,
                "label": _t(spec["label"]),
                "doctype": spec["doctype"],
                "can_disable": bool(spec.get("disable_field")),
                "fields": [{**fld, "label": _t(fld["label"])} for fld in spec["fields"]],
            }
        )
    return success(out)
