from frappe.model.document import Document


class MobileApplication(Document):
    def before_insert(self):
        if self.permission_version is None:
            self.permission_version = 1
