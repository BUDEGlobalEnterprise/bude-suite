from unittest.mock import patch

from bude_api.api.health import ping


def test_ping_returns_ok():
    result = ping()
    assert result["status"] == "ok"
    assert result["service"] == "bude_api"
    assert "version" in result
    assert "timestamp" in result
    # frappe isn't importable in unit tests → version resolution returns None,
    # but the key must always be present for the mobile validator.
    assert "erpnext_version" in result


@patch("bude_api.api.health.get_versions")
def test_ping_includes_erpnext_version_when_available(mock_get_versions):
    mock_get_versions.return_value = {"erpnext": {"version": "16.6.1"}}
    result = ping()
    assert result["erpnext_version"] == "16.6.1"


@patch("bude_api.api.health.get_versions")
def test_ping_tolerates_version_helper_raising(mock_get_versions):
    mock_get_versions.side_effect = RuntimeError("boom")
    result = ping()
    assert result["status"] == "ok"
    assert result["erpnext_version"] is None
