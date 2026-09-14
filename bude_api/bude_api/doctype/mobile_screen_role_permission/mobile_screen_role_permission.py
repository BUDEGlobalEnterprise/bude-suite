from frappe.model.document import Document


class MobileScreenRolePermission(Document):
    """Child table row of Mobile App Screen. Uniqueness and validation are
    handled by the parent (MobileAppScreen.validate) since a child row always
    saves through its parent."""
