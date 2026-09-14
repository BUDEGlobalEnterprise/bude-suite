app_name = "bude_api"
app_title = "Bude Global Enterprises"
app_publisher = "Bude Global Enterprises"
app_description = "Unified operations platform for Bude Global Enterprises."
app_license = "MIT"
app_version = "0.1.0"

# Apply the Bude design system to every standard Frappe Desk workspace, list,
# report and form without replacing Frappe's native components or behaviour.
app_include_css = "/assets/bude_api/css/bude_theme.css"
web_include_css = "/assets/bude_api/css/bude_web_theme.css"

required_apps = ["erpnext"]

# Idempotently ensure the bude_epc Custom Fields exist, plus the Mobile
# Permission Manager role and the four Mobile Application records.
after_install = [
    "bude_api.custom.rfid_fields.ensure_custom_fields",
    "bude_api.custom.mobile_permissions_setup.ensure_mobile_permission_setup",
]
after_migrate = [
    "bude_api.custom.rfid_fields.ensure_custom_fields",
    "bude_api.custom.mobile_permissions_setup.ensure_mobile_permission_setup",
]

# CRM reminders use only standard Notification Log records. The frequent job
# creates due reminders and then fans out all unsent logs to registered devices.
scheduler_events = {
    "cron": {
        "*/15 * * * *": ["bude_api.services.sales_crm.reminders.run_crm_reminders"],
        "7,22,37,52 * * * *": ["bude_api.services.helpdesk.automation.run_helpdesk_automation"],
    },
}

_bump_version = "bude_api.services.mobile_permissions.versioning.bump_app_version"

# Demotes the public demo login (see services/common/demo_readonly.py) to
# read-only, independent of any role's own permissions -- real staff holding
# the same roles are unaffected. Enforced at the request level (an allowlist
# of exact bude_api.api.* paths, GET-only on the generic REST API): a
# has_permission hook was tried first and does not work for this, see that
# module's docstring for why.
before_request = "bude_api.services.common.demo_readonly.before_request"

doc_events = {
    "Lead": {"on_update": "bude_api.services.sales_crm.reminders.on_crm_record_update"},
    "Opportunity": {"on_update": "bude_api.services.sales_crm.reminders.on_crm_record_update"},
    "CRM Lead": {"on_update": "bude_api.services.sales_crm.reminders.on_crm_record_update"},
    "CRM Deal": {"on_update": "bude_api.services.sales_crm.reminders.on_crm_record_update"},
    # Any permission change bumps the owning app's permission_version so clients
    # know their cached permissions are stale. Role/user-override grants are
    # child tables of Mobile App Screen, so editing the grid and saving the
    # screen already fires this — no separate hook needed for them.
    "Mobile App Screen": {"on_update": _bump_version, "on_trash": _bump_version},
}
