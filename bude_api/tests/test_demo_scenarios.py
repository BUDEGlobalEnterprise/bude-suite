from bude_api.demo import scenarios


def test_demo_names_are_deterministic_and_tagged():
    run_id = "BUDE-DEMO-20260102030405-preview"

    assert scenarios.item_code(run_id, 7).startswith(run_id)
    assert "PALLET" in scenarios.item_code(run_id, 7)
    assert scenarios.item_name(1) == "Chainway C72 UHF handheld reader"
    assert scenarios.warehouse_name(run_id, 2).startswith(run_id)
    assert scenarios.asset_name(run_id, 3).startswith(run_id)
    assert scenarios.customer_name(run_id, 1).startswith(run_id)


def test_stock_operation_payload_builders():
    transfer = scenarios.transfer_payload("ITEM-1", "A", "B")
    receipt = scenarios.receipt_payload("ITEM-1", "A", "PO-1")
    reconciliation = scenarios.reconciliation_payload("ITEM-1", "A")

    assert transfer["items"] == [{"item_code": "ITEM-1", "qty": 1}]
    assert transfer["source_warehouse"] == "A"
    assert transfer["target_warehouse"] == "B"
    assert receipt["against_po"] == "PO-1"
    assert reconciliation["counts"] == [{"item_code": "ITEM-1", "qty": 1}]


def test_navigation_payload_has_role_buckets():
    payload = scenarios.navigation_payload()

    assert "admin" in payload["roles"]
    assert "settings" in payload["roles"]["admin"]
    assert payload["order"][0] == "dashboard"
