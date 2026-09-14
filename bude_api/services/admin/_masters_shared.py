"""Generic master-data CRUD, driven by a single registry.

    GET/POST /api/method/bude_api.api.masters.list_masters      (auth)
    GET/POST /api/method/bude_api.api.masters.list_records      (auth)
    GET/POST /api/method/bude_api.api.masters.get_record        (auth)
    GET/POST /api/method/bude_api.api.masters.list_link_options (auth)
    POST     /api/method/bude_api.api.masters.create_record     (auth)
    POST     /api/method/bude_api.api.masters.update_record     (auth)
    POST     /api/method/bude_api.api.masters.set_disabled      (auth)

Every master is a standard ERPNext DocType — no custom DocTypes. Adding a new
master = one entry in MASTERS below; no new endpoints or screens needed.

Mutations run with ignore_permissions=False, so Frappe's role permissions are
the authoritative gate (the mobile UI only hides the screen for convenience).
There is no hard-delete endpoint by design: removal is "disable" (flip a flag),
so ERPNext references and history are never broken.
"""

try:
    import frappe
except ImportError:
    frappe = None

from ...utils.response import failure, success

def _f(name, label, type, required=False, options=None, link=None):
    """One field = one schema row sent to the client to render a form input."""
    return {
        "name": name,
        "label": label,
        "type": type,  # text | number | date | check | select | link
        "required": required,
        "options": options,  # for select
        "link": link,  # target doctype for link
    }

MASTERS = {
    # ── Inventory core ──────────────────────────────────────────────────────
    "item": {
        "doctype": "Item",
        "label": "Items",
        "list_fields": ["item_code", "item_name", "item_group", "disabled"],
        "search_fields": ["item_code", "item_name"],
        "disable_field": "disabled",
        "fields": [
            _f("item_code", "Item Code", "text", required=True),
            _f("item_name", "Item Name", "text", required=True),
            _f("item_group", "Item Group", "link", required=True, link="Item Group"),
            _f("stock_uom", "Default Unit", "link", required=True, link="UOM"),
            _f("description", "Description", "text"),
            _f("is_stock_item", "Maintain Stock", "check"),
            _f("disabled", "Disabled", "check"),
        ],
    },
    "item_group": {
        "doctype": "Item Group",
        "label": "Item Groups",
        "list_fields": ["item_group_name", "parent_item_group", "is_group"],
        "search_fields": ["item_group_name"],
        "fields": [
            _f("item_group_name", "Item Group Name", "text", required=True),
            _f("parent_item_group", "Parent Group", "link", link="Item Group"),
            _f("is_group", "Is Group", "check"),
        ],
    },
    "warehouse": {
        "doctype": "Warehouse",
        "label": "Warehouses",
        "list_fields": ["warehouse_name", "company", "disabled"],
        "search_fields": ["warehouse_name"],
        "disable_field": "disabled",
        "fields": [
            _f("warehouse_name", "Warehouse Name", "text", required=True),
            _f("company", "Company", "link", required=True, link="Company"),
            _f("parent_warehouse", "Parent Warehouse", "link", link="Warehouse"),
            _f("disabled", "Disabled", "check"),
        ],
    },
    "uom": {
        "doctype": "UOM",
        "label": "Units of Measure",
        "list_fields": ["uom_name", "enabled"],
        "search_fields": ["uom_name"],
        "disable_field": "enabled",
        "disable_value": 0,
        "enable_value": 1,
        "fields": [
            _f("uom_name", "Unit Name", "text", required=True),
            _f("must_be_whole_number", "Whole Numbers Only", "check"),
            _f("enabled", "Enabled", "check"),
        ],
    },
    "brand": {
        "doctype": "Brand",
        "label": "Brands",
        "list_fields": ["brand", "description"],
        "search_fields": ["brand"],
        "fields": [
            _f("brand", "Brand", "text", required=True),
            _f("description", "Description", "text"),
        ],
    },
    # ── Parties ─────────────────────────────────────────────────────────────
    "supplier": {
        "doctype": "Supplier",
        "label": "Suppliers",
        "list_fields": ["supplier_name", "supplier_group", "disabled"],
        "search_fields": ["supplier_name"],
        "disable_field": "disabled",
        "fields": [
            _f("supplier_name", "Supplier Name", "text", required=True),
            _f("supplier_group", "Supplier Group", "link", required=True, link="Supplier Group"),
            _f("supplier_type", "Type", "select", options=["Company", "Individual"]),
            _f("disabled", "Disabled", "check"),
        ],
    },
    "supplier_group": {
        "doctype": "Supplier Group",
        "label": "Supplier Groups",
        "list_fields": ["supplier_group_name", "parent_supplier_group", "is_group"],
        "search_fields": ["supplier_group_name"],
        "fields": [
            _f("supplier_group_name", "Supplier Group Name", "text", required=True),
            _f("parent_supplier_group", "Parent Group", "link", link="Supplier Group"),
            _f("is_group", "Is Group", "check"),
        ],
    },
    "customer": {
        "doctype": "Customer",
        "label": "Customers",
        "list_fields": ["customer_name", "customer_group", "disabled"],
        "search_fields": ["customer_name"],
        "disable_field": "disabled",
        "fields": [
            _f("customer_name", "Customer Name", "text", required=True),
            _f("customer_group", "Customer Group", "link", required=True, link="Customer Group"),
            _f("customer_type", "Type", "select", options=["Company", "Individual"]),
            _f("disabled", "Disabled", "check"),
        ],
    },
    "customer_group": {
        "doctype": "Customer Group",
        "label": "Customer Groups",
        "list_fields": ["customer_group_name", "parent_customer_group", "is_group"],
        "search_fields": ["customer_group_name"],
        "fields": [
            _f("customer_group_name", "Customer Group Name", "text", required=True),
            _f("parent_customer_group", "Parent Group", "link", link="Customer Group"),
            _f("is_group", "Is Group", "check"),
        ],
    },
    "company": {
        "doctype": "Company",
        "label": "Companies",
        "list_fields": ["company_name", "abbr", "default_currency"],
        "search_fields": ["company_name"],
        "fields": [
            _f("company_name", "Company Name", "text", required=True),
            _f("abbr", "Abbreviation", "text", required=True),
            _f("default_currency", "Default Currency", "link", required=True, link="Currency"),
            _f("country", "Country", "link", required=True, link="Country"),
        ],
    },
    # ── Assets ──────────────────────────────────────────────────────────────
    "asset_category": {
        "doctype": "Asset Category",
        "label": "Asset Categories",
        "list_fields": ["asset_category_name"],
        "search_fields": ["asset_category_name"],
        "fields": [
            _f("asset_category_name", "Asset Category Name", "text", required=True),
        ],
    },
    "location": {
        "doctype": "Location",
        "label": "Locations",
        "list_fields": ["location_name", "parent_location", "is_group"],
        "search_fields": ["location_name"],
        "fields": [
            _f("location_name", "Location Name", "text", required=True),
            _f("parent_location", "Parent Location", "link", link="Location"),
            _f("is_group", "Is Group", "check"),
        ],
    },
    # ── People ──────────────────────────────────────────────────────────────
    "employee": {
        "doctype": "Employee",
        "label": "Employees",
        "list_fields": ["employee_name", "company", "status"],
        "search_fields": ["employee_name"],
        "disable_field": "status",
        "disable_value": "Inactive",
        "enable_value": "Active",
        "fields": [
            _f("first_name", "First Name", "text", required=True),
            _f("last_name", "Last Name", "text"),
            _f("gender", "Gender", "link", required=True, link="Gender"),
            _f("date_of_birth", "Date of Birth", "date", required=True),
            _f("date_of_joining", "Date of Joining", "date", required=True),
            _f("company", "Company", "link", required=True, link="Company"),
            _f("designation", "Designation", "link", link="Designation"),
            _f("cell_number", "Mobile", "text"),
            _f("status", "Status", "select",
               options=["Active", "Inactive", "Suspended", "Left"]),
        ],
    },
}

def _read(fn):
    return fn if frappe is None else frappe.whitelist()(fn)

def _write(fn):
    return fn if frappe is None else frappe.whitelist(methods=["POST"])(fn)

def _resolve(master):
    spec = MASTERS.get(master)
    if spec is None:
        return None, failure(
            f"Unknown master '{master}'.", code="VALIDATION_UNKNOWN_MASTER"
        )
    return spec, None

def _editable_names(spec):
    return [f["name"] for f in spec["fields"]]

def _list_fields(spec):
    fields = list(spec["list_fields"])
    if "name" not in fields:
        fields = ["name"] + fields
    return fields

def _link_targets():
    targets = set()
    for spec in MASTERS.values():
        for fld in spec["fields"]:
            if fld["type"] == "link" and fld["link"]:
                targets.add(fld["link"])
    return targets

def _clean(spec, values):
    """Keep only known editable fields — silently drop anything else so a
    crafted payload can't write columns the master doesn't expose."""
    allowed = set(_editable_names(spec))
    return {k: v for k, v in (values or {}).items() if k in allowed}

def _check_required(spec, values):
    for fld in spec["fields"]:
        if not fld["required"]:
            continue
        val = values.get(fld["name"])
        if val is None or (isinstance(val, str) and not val.strip()):
            return failure(f"{fld['label']} is required.", code="VALIDATION_REQUIRED")
    return None

def _t(text):
    if frappe is None:
        return text
    try:
        return frappe._(text)
    except Exception:
        return text

def _erpnext_message(exc):
    msg = (str(exc) or "").strip() or "ERPNext rejected the document."
    try:  # Frappe messages can carry HTML; strip it for a clean mobile string.
        from frappe.utils import strip_html_tags

        msg = strip_html_tags(msg).strip() or msg
    except Exception:
        pass
    return msg

def _mutate(action):
    """Run a write, converting ERPNext's exceptions into clean envelopes and
    rolling back so a rejected write never leaves a stray record behind."""
    try:
        return action()
    except frappe.ValidationError as exc:
        frappe.db.rollback()
        return failure(_erpnext_message(exc), code="VALIDATION_ERPNEXT")
    except frappe.PermissionError:
        frappe.db.rollback()
        return failure(
            "You do not have permission for this action.", code="PERMISSION_DENIED"
        )

def _as_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)

def _coerce_limit(value, default, cap):
    try:
        return max(1, min(int(value), cap))
    except (TypeError, ValueError):
        return default

def _record_exists(doctype, name) -> bool:
    rows = frappe.get_list(
        doctype,
        filters=[["name", "=", name]],
        fields=["name"],
        limit=1,
    )
    return bool(rows)

def _save(spec, name, values):
    doc = frappe.get_doc(spec["doctype"], name)
    for key, val in values.items():
        doc.set(key, val)
    doc.save(ignore_permissions=False)
    return success({"name": doc.name})

__all__ = [name for name in globals() if not name.startswith("__")]
