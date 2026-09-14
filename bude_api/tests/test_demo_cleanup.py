from bude_api.demo.cleanup import DemoCleaner


def test_cleanup_refuses_untagged_records_even_for_transaction_doctypes():
    cleaner = DemoCleaner("BUDE-DEMO-20260102030405-preview", dry_run=True)

    assert cleaner._delete_doc("Item", "REAL-ITEM") is False
    assert cleaner._delete_doc("Stock Entry", "MAT-STE-0001") is False
    assert cleaner.report["warnings"]


def test_cleanup_allows_tagged_records_in_dry_run():
    cleaner = DemoCleaner("BUDE-DEMO-20260102030405-preview", dry_run=True)

    assert cleaner._delete_doc(
        "Item",
        "BUDE-DEMO-20260102030405-preview-ITEM-00001",
    ) is True
