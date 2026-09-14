from datetime import datetime, timezone

import pytest

from bude_api.demo.config import (
    chunked,
    get_profile,
    is_safe_local_target,
    make_run_id,
    require_write_guard,
    validate_run_id,
)


def test_profiles_validate_preview_and_large_safe():
    assert get_profile("preview").items == 40
    assert get_profile("preview").sales_orders == 10
    assert get_profile("large-safe").items == 12_000


def test_massive_stress_is_disabled_by_default():
    with pytest.raises(ValueError):
        get_profile("massive-stress")


def test_make_and_validate_run_id():
    run_id = make_run_id("preview", datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
    assert run_id == "BUDE-DEMO-20260102030405-preview"
    assert validate_run_id(run_id) == run_id


def test_validate_run_id_rejects_untagged_values():
    with pytest.raises(ValueError):
        validate_run_id("production")


def test_write_guard_allows_local_targets():
    require_write_guard(
        run_id="BUDE-DEMO-20260102030405-preview",
        base_url="http://127.0.0.1:8000",
    )


def test_write_guard_rejects_non_local_without_confirmation():
    with pytest.raises(RuntimeError):
        require_write_guard(
            run_id="BUDE-DEMO-20260102030405-preview",
            base_url="https://erp.example.com",
        )


def test_local_target_detection():
    assert is_safe_local_target(base_url="http://localhost:8000")
    assert is_safe_local_target(site="bude-dev.local")
    assert not is_safe_local_target(base_url="https://erp.example.com")


def test_chunked_batches_values():
    assert list(chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]
