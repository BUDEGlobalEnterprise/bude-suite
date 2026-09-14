from unittest.mock import patch

from bude_api.api import branding as branding_api


@patch("bude_api.api.branding.frappe")
@patch("bude_api.api.branding.get_versions")
def test_get_returns_full_payload_when_company_and_address_present(
    mock_get_versions,
    mock_frappe,
):
    mock_frappe.db.get_default.return_value = "Acme Inc"

    def get_list(doctype, **kwargs):
        if doctype == "Company":
            return [
                {
                    "name": "Acme Inc",
                    "company_logo": "/files/acme.png",
                    "country": "USA",
                    "default_currency": "USD",
                }
            ]
        if doctype == "Dynamic Link":
            return [{"parent": "Acme HQ-Billing"}]
        if doctype == "Address":
            return [
                {
                    "address_line1": "1 Main St",
                    "address_line2": None,
                    "city": "Springfield",
                    "state": "IL",
                    "country": "USA",
                    "pincode": "12345",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    mock_frappe.get_all.side_effect = get_list
    mock_frappe.get_installed_apps.return_value = ["frappe", "erpnext"]
    mock_get_versions.return_value = {"erpnext": {"version": "15.0.0"}}

    result = branding_api.get()

    assert result["ok"] is True
    data = result["data"]
    assert data["company_name"] == "Acme Inc"
    assert data["company_logo"] == "/files/acme.png"
    assert data["erpnext_version"] == "15.0.0"
    assert data["bude_api_version"]
    assert "1 Main St" in data["company_address"]
    assert "Springfield" in data["company_address"]
    assert data["feature_flags"]["transfer"] is True
    assert data["feature_flags"]["receipt"] is True


@patch("bude_api.api.branding.frappe")
@patch("bude_api.api.branding.get_versions")
def test_get_falls_back_to_first_company_when_no_default(
    mock_get_versions,
    mock_frappe,
):
    mock_frappe.db.get_default.return_value = None

    def get_list(doctype, **kwargs):
        if doctype == "Company":
            # First call resolves the name, second call loads the company.
            fields = kwargs.get("fields") or []
            if fields == ["name"]:
                return [{"name": "First Co"}]
            return [
                {
                    "name": "First Co",
                    "company_logo": None,
                    "country": None,
                    "default_currency": "USD",
                }
            ]
        return []

    mock_frappe.get_list.side_effect = get_list
    mock_frappe.get_all.side_effect = get_list
    mock_frappe.get_installed_apps.return_value = ["frappe", "erpnext"]
    mock_get_versions.return_value = {"erpnext": {"version": "15.0.0"}}

    result = branding_api.get()

    assert result["ok"] is True
    assert result["data"]["company_name"] == "First Co"
    assert result["data"]["company_logo"] == branding_api.DEFAULT_COMPANY_LOGO
    assert result["data"]["company_address"] is None  # no Dynamic Link rows


@patch("bude_api.api.branding.frappe")
@patch("bude_api.api.branding.get_versions")
def test_get_handles_no_company_at_all(mock_get_versions, mock_frappe):
    mock_frappe.db.get_default.return_value = None
    mock_frappe.get_list.return_value = []
    mock_frappe.get_all.return_value = []
    mock_frappe.get_installed_apps.return_value = ["frappe", "erpnext"]
    mock_get_versions.return_value = {"erpnext": {"version": "15.0.0"}}

    result = branding_api.get()

    assert result["ok"] is True
    assert result["data"]["company_name"] is None
    assert result["data"]["company_logo"] == branding_api.DEFAULT_COMPANY_LOGO
    assert result["data"]["company_address"] is None
    assert result["data"]["erpnext_version"] == "15.0.0"


@patch("bude_api.api.branding.frappe")
@patch("bude_api.api.branding.get_versions")
def test_get_tolerates_versions_helper_raising(mock_get_versions, mock_frappe):
    mock_frappe.db.get_default.return_value = None
    mock_frappe.get_list.return_value = []
    mock_frappe.get_all.return_value = []
    mock_frappe.get_installed_apps.return_value = ["frappe", "erpnext"]
    mock_get_versions.side_effect = RuntimeError("boom")

    result = branding_api.get()

    assert result["ok"] is True
    assert result["data"]["erpnext_version"] is None


@patch("bude_api.api.branding.frappe")
@patch("bude_api.api.branding.get_versions")
def test_feature_flags_disabled_when_erpnext_not_installed(
    mock_get_versions,
    mock_frappe,
):
    mock_frappe.db.get_default.return_value = None
    mock_frappe.get_list.return_value = []
    mock_frappe.get_installed_apps.return_value = ["frappe"]  # no erpnext
    mock_get_versions.return_value = {}

    result = branding_api.get()

    assert result["ok"] is True
    flags = result["data"]["feature_flags"]
    assert flags["transfer"] is False
    assert flags["receipt"] is False
    assert flags["reconciliation"] is False
