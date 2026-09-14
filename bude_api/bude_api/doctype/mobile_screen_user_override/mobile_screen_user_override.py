from frappe.model.document import Document


class MobileScreenUserOverride(Document):
    """Child table row of Mobile App Screen. Uniqueness and the valid_from/
    valid_until window are validated by the parent (MobileAppScreen.validate)
    since a child row always saves through its parent."""
