import frappe
from frappe import _
from frappe.model.document import Document

from bude_api.services.mobile_permissions.validators import (
    permission_code_for,
    validity_window_ok,
)


class MobileAppScreen(Document):
    def validate(self):
        if self.screen_key and "." in self.screen_key:
            frappe.throw(_("Screen Key must not contain a dot."))
        # permission_code == docname == <app_key>.<screen_key>; keep them in sync.
        self.permission_code = permission_code_for(self.app, self.screen_key)
        self._validate_role_permissions()
        self._validate_user_overrides()

    def _validate_role_permissions(self):
        seen = set()
        for row in self.role_permissions:
            if row.role in seen:
                frappe.throw(_("Role {0} is granted more than once.").format(row.role))
            seen.add(row.role)

    def _validate_user_overrides(self):
        seen = set()
        for row in self.user_overrides:
            if row.user in seen:
                frappe.throw(
                    _("User {0} has more than one override.").format(row.user)
                )
            seen.add(row.user)
            if not validity_window_ok(row.valid_from, row.valid_until):
                frappe.throw(
                    _("Valid Until must be later than Valid From for {0}.").format(
                        row.user
                    )
                )
