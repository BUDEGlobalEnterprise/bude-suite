"""Shared constants for the mobile screen-permission system.

Permission codes are ``<app_key>.<screen_key>`` and equal the ``Mobile App
Screen`` docname, so screen identity is stable and globally unique.
"""

# The six action flags every screen/role/override row carries. Order matters
# only for stable serialisation; membership is what callers check against.
ACTIONS = ("view", "create", "edit", "delete", "approve", "export")

# Roles/users that bypass or broadly satisfy screen checks. Kept here so the
# rule is explicit and greppable rather than sprinkled through the resolver.
ADMINISTRATOR = "Administrator"
GUEST = "Guest"
SYSTEM_MANAGER_ROLE = "System Manager"

# Dedicated role allowed to manage permission DocTypes and call admin previews.
MOBILE_PERMISSION_MANAGER_ROLE = "Mobile Permission Manager"

# How long a Flutter client may trust a cached permission response before it
# should refetch. Version bumps invalidate sooner; this is the ceiling.
DEFAULT_CACHE_TTL_SECONDS = 900

ACCESS_MODE_ALLOW = "Allow"
ACCESS_MODE_DENY = "Deny"
