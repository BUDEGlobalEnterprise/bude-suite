from bude_api.demo.verify import ApiResult, build_cases, normalize_body, summarize_results


def test_normalize_body_unwraps_frappe_message():
    assert normalize_body({"message": {"ok": True}}) == {"ok": True}
    assert normalize_body({"ok": True}) == {"ok": True}


def test_build_cases_includes_read_and_write_coverage():
    samples = {
        "item": "ITEM-1",
        "warehouse": "Stores - B",
        "target_warehouse": "Finished Goods - B",
        "barcode": "BC1",
        "epc": "EPC1",
        "purchase_order": "PO-1",
        "sales_order": "SO-1",
        "asset": "ASSET-1",
        "location": "HQ",
        "asset_category": "IT",
        "maintenance_log": "AML-1",
    }

    cases = build_cases(samples, write_checks=True)
    names = {case.name for case in cases}

    assert "items.search" in names
    assert "stock.transfer" in names
    assert "stock.receipt.po" in names
    assert "assets.complete_maintenance" in names


def test_build_cases_can_be_read_only():
    names = {case.name for case in build_cases({}, write_checks=False)}

    assert "items.search" in names
    assert "stock.transfer" not in names


def test_summarize_results_counts_failures_and_slowest():
    results = [
        ApiResult("a", "/a", 200, True, 5, None, {}),
        ApiResult("b", "/b", 500, False, 50, "bad", {}),
    ]

    summary = summarize_results(results)

    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["slowest"][0]["name"] == "b"
