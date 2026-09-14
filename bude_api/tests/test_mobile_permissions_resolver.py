"""Unit tests for the pure permission resolver (no Frappe needed)."""

from bude_api.services.mobile_permissions.resolver import (
    apply_overrides,
    merge_role_rows,
    resolve,
)

ALL = {"inventory.dashboard", "inventory.items", "inventory.stock_transfer"}


def _row(screen, **flags):
    base = {"screen": screen, "access_mode": flags.pop("access_mode", None)}
    base.update(flags)
    return base


def test_single_role_grants_view():
    out = resolve([_row("inventory.dashboard", view=True)], [], ALL)
    assert out["inventory.dashboard"]["view"] is True
    assert "inventory.items" not in out  # default deny


def test_multiple_roles_union():
    rows = [
        _row("inventory.dashboard", view=True),
        _row("inventory.items", view=True, create=True),
    ]
    out = resolve(rows, [], ALL)
    assert set(out) == {"inventory.dashboard", "inventory.items"}
    assert out["inventory.items"]["create"] is True


def test_role_or_merge_combines_actions():
    merged = merge_role_rows(
        [
            _row("inventory.items", view=True),
            _row("inventory.items", create=True),
        ]
    )
    assert merged["inventory.items"]["view"] is True
    assert merged["inventory.items"]["create"] is True


def test_no_matching_role_is_denied():
    assert resolve([], [], ALL) == {}


def test_user_allow_override_adds_screen():
    out = resolve([], [_row("inventory.items", access_mode="Allow", view=True)], ALL)
    assert out["inventory.items"]["view"] is True


def test_user_deny_overrides_role_grant():
    out = resolve(
        [_row("inventory.dashboard", view=True)],
        [_row("inventory.dashboard", access_mode="Deny", view=True)],
        ALL,
    )
    assert "inventory.dashboard" not in out


def test_deny_single_action_keeps_screen_but_removes_action():
    out = resolve(
        [_row("inventory.items", view=True, create=True)],
        [_row("inventory.items", access_mode="Deny", create=True)],
        ALL,
    )
    assert out["inventory.items"]["view"] is True
    assert out["inventory.items"]["create"] is False


def test_screen_not_in_active_set_is_dropped():
    # Role grants a screen that is no longer active -> excluded.
    out = resolve([_row("inventory.retired", view=True)], [], ALL)
    assert out == {}


def test_system_manager_gets_all_active_screens():
    out = resolve([], [], ALL, is_system_manager=True)
    assert set(out) == ALL
    assert all(out[s]["export"] for s in ALL)


def test_user_deny_beats_system_manager():
    out = resolve(
        [],
        [_row("inventory.items", access_mode="Deny", view=True)],
        ALL,
        is_system_manager=True,
    )
    assert "inventory.items" not in out
    assert "inventory.dashboard" in out  # others untouched


def test_apply_overrides_does_not_mutate_input():
    base = {"inventory.items": {a: True for a in ("view", "create", "edit",
                                                 "delete", "approve", "export")}}
    apply_overrides(base, [_row("inventory.items", access_mode="Deny", view=True)])
    assert base["inventory.items"]["view"] is True  # original untouched
