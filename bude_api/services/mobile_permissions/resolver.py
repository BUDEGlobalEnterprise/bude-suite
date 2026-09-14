"""Pure, deterministic permission resolution.

No Frappe imports here on purpose: this is the security-critical core, so it is
kept side-effect free and unit-tested in isolation. The service layer fetches
rows from the database and feeds them in.

Effective precedence (highest wins):

    1. Explicit user-level DENY
    2. Explicit user-level ALLOW
    3. Permission granted through any assigned role (OR-merged)
    4. Default DENY

A user with multiple roles gets the union of their role grants, unless a
user-level DENY override removes it. There is at most one override row per
(screen, user) — the unique constraint guarantees it — so ALLOW and DENY never
collide on the same screen; access_mode just picks the direction.
"""

from .constants import ACCESS_MODE_DENY, ACTIONS


def _empty_flags() -> dict:
    return {action: False for action in ACTIONS}


def merge_role_rows(role_rows: list[dict]) -> dict:
    """OR-merge every role permission row into per-screen effective flags.

    Each row is ``{"screen": <permission_code>, "view": bool, ...}``. Rows for
    the same screen (i.e. the user holds several roles that all grant it) are
    combined so a grant from *any* role wins.
    """
    merged: dict[str, dict] = {}
    for row in role_rows:
        screen = row["screen"]
        flags = merged.setdefault(screen, _empty_flags())
        for action in ACTIONS:
            if row.get(action):
                flags[action] = True
    return merged


def apply_overrides(base: dict, override_rows: list[dict]) -> dict:
    """Apply user overrides on top of role-merged flags.

    DENY forces every action flagged on the override off; if ``view`` ends up
    off the screen is dropped entirely. ALLOW forces flagged actions on and can
    introduce a screen the user's roles never granted. Callers must pre-filter
    override_rows to active, in-window rows only.
    """
    result = {screen: dict(flags) for screen, flags in base.items()}
    for row in override_rows:
        screen = row["screen"]
        flags = result.setdefault(screen, _empty_flags())
        grant = row.get("access_mode") != ACCESS_MODE_DENY
        for action in ACTIONS:
            if row.get(action):
                flags[action] = grant
    return {screen: flags for screen, flags in result.items() if flags["view"]}


def resolve(
    role_rows: list[dict],
    override_rows: list[dict],
    all_screen_codes: set[str],
    is_system_manager: bool = False,
) -> dict:
    """Compute effective per-screen flags for one user.

    ``all_screen_codes`` is every *active* screen for the app. System Manager is
    modelled as a broad role grant (all actions on all active screens) so a
    user-level DENY override can still remove access from a System Manager —
    keeping the documented precedence intact rather than short-circuiting it.
    """
    rows = list(role_rows)
    if is_system_manager:
        rows.extend(
            {"screen": code, **{action: True for action in ACTIONS}}
            for code in all_screen_codes
        )
    merged = merge_role_rows(rows)
    # Only ever expose screens that are currently active.
    merged = {s: f for s, f in merged.items() if s in all_screen_codes}
    return apply_overrides(merged, override_rows)
