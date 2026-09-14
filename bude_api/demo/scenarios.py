"""Deterministic names and payload builders for demo data/API tests."""

from __future__ import annotations

import hashlib

COMPANY_NAMES = [
    "Bude Demo Distribution",
    "Bude Demo Retail",
    "Bude Demo Service",
]

WAREHOUSE_AREAS = [
    "Main Receiving Dock",
    "Bulk Reserve Aisle A",
    "Bulk Reserve Aisle B",
    "Fast Pick Zone",
    "Quality Hold Cage",
    "Returns Processing",
    "Finished Goods Dispatch",
    "Field Service Spares",
]

ITEM_GROUPS = [
    "RFID Hardware",
    "Barcode and Labeling",
    "Warehouse Consumables",
    "Safety and Compliance",
    "Field Service Spares",
    "IT Accessories",
]

ITEM_CATALOG = [
    ("RFID Hardware", "CHAINWAY-C72-UHF", "Chainway C72 UHF handheld reader", "Nos", 3),
    ("RFID Hardware", "ZEBRA-RFD40-SLED", "Zebra RFD40 RFID sled", "Nos", 4),
    ("RFID Hardware", "IMPINJ-M730-TAG", "Impinj M730 wet inlay roll", "Roll", 12),
    ("Barcode and Labeling", "ZEBRA-ZT411-300DPI", "Zebra ZT411 300 dpi thermal printer", "Nos", 2),
    (
        "Barcode and Labeling",
        "LABEL-100X50-PP",
        "100 x 50 mm polypropylene RFID labels",
        "Roll",
        20,
    ),
    ("Barcode and Labeling", "RIBBON-WAX-110X300", "110 mm x 300 m wax ribbon", "Roll", 25),
    (
        "Warehouse Consumables",
        "PALLET-EURO-1200X800",
        "Reusable euro pallet 1200 x 800 mm",
        "Nos",
        50,
    ),
    (
        "Warehouse Consumables",
        "TOTE-6428-BLUE",
        "Blue stackable tote 600 x 400 x 280 mm",
        "Nos",
        80,
    ),
    ("Warehouse Consumables", "STRETCH-FILM-23MIC", "Machine stretch film 23 micron", "Roll", 40),
    ("Safety and Compliance", "VEST-HIVIS-L", "High visibility warehouse vest large", "Nos", 30),
    ("Safety and Compliance", "GLOVE-CUT5-M", "Cut level 5 handling gloves medium", "Pair", 60),
    ("Safety and Compliance", "FLOOR-MARK-YELLOW", "Yellow floor marking tape 75 mm", "Roll", 18),
    ("Field Service Spares", "BATTERY-C72-8000", "Spare battery for Chainway C72", "Nos", 10),
    ("Field Service Spares", "USB-C-RUGGED-2M", "Rugged USB-C cable 2 m", "Nos", 35),
    ("Field Service Spares", "ANTENNA-UHF-8DBI", "UHF panel antenna 8 dBi", "Nos", 8),
    ("IT Accessories", "TABLET-MOUNT-FORKLIFT", "Forklift tablet mount with RAM arm", "Nos", 6),
    ("IT Accessories", "AP-WIFI6-WAREHOUSE", "Warehouse Wi-Fi 6 access point", "Nos", 5),
    ("IT Accessories", "POE-INJECTOR-GIGE", "Gigabit PoE injector", "Nos", 12),
]

SUPPLIERS = [
    "Apex RFID Systems",
    "Kovai Industrial Supplies",
    "South India Packaging Co",
    "Metro Barcode Solutions",
    "NexGen Warehouse Safety",
    "Prime Mobility Devices",
]

CUSTOMERS = [
    "Coimbatore Distribution Hub",
    "Kovai Auto Components",
    "Nilgiri Retail Stores",
    "Tiruppur Textile Logistics",
    "Salem Pharma Warehouse",
    "Erode Engineering Works",
    "Madurai FMCG Depot",
    "Chennai Field Services",
]

ASSET_CATEGORIES = [
    "RFID Readers",
    "Material Handling Equipment",
    "Thermal Printers",
    "Network Infrastructure",
    "Mobile Workstations",
]

ASSET_NAMES = [
    "Chainway C72 Handheld",
    "Zebra RFD40 Sled",
    "Toyota Reach Truck",
    "Zebra ZT411 Printer",
    "Warehouse Wi-Fi Access Point",
    "Mobile Packing Workstation",
]

LOCATIONS = [
    "Kovai DC - Receiving",
    "Kovai DC - Dispatch",
    "Kovai DC - QA Hold",
    "Kovai DC - Service Bay",
    "Tiruppur Field Office",
    "Chennai Service Point",
]


def short_tag(run_id: str) -> str:
    return "".join(ch for ch in run_id if ch.isalnum())[-10:]


def company_name(run_id: str, index: int) -> str:
    base = COMPANY_NAMES[(index - 1) % len(COMPANY_NAMES)]
    return f"{run_id} {base} {index:02d}"


def company_abbr(run_id: str, index: int) -> str:
    digest = hashlib.sha1(run_id.encode("utf-8")).hexdigest()[:5]
    return f"B{index:02d}{digest}".upper()[:10]


def warehouse_name(run_id: str, index: int) -> str:
    area = WAREHOUSE_AREAS[(index - 1) % len(WAREHOUSE_AREAS)]
    return f"{run_id} {area} {index:02d}"


def item_group_name(run_id: str, index: int) -> str:
    group = ITEM_GROUPS[(index - 1) % len(ITEM_GROUPS)]
    return f"{run_id} {group}"


def item_code(run_id: str, index: int) -> str:
    _, sku, _, _, _ = item_template(index)
    return f"{run_id}-{sku}-{index:05d}"


def item_template(index: int) -> tuple[str, str, str, str, int]:
    return ITEM_CATALOG[(index - 1) % len(ITEM_CATALOG)]


def item_name(index: int) -> str:
    _, _, name, _, _ = item_template(index)
    batch = ((index - 1) // len(ITEM_CATALOG)) + 1
    return name if batch == 1 else f"{name} Batch {batch:02d}"


def item_description(run_id: str, index: int) -> str:
    group, sku, name, uom, safety_stock = item_template(index)
    return (
        f"{name}. Demo SKU {sku} for {group.lower()} workflows; "
        f"stocked in {uom} with reorder point {safety_stock}. Run: {run_id}."
    )


def item_uom(index: int) -> str:
    _, _, _, uom, _ = item_template(index)
    return uom


def item_safety_stock(index: int) -> int:
    _, _, _, _, safety_stock = item_template(index)
    return safety_stock


def barcode(run_id: str, index: int) -> str:
    return f"{short_tag(run_id)}BC{index:08d}"


def epc(run_id: str, kind: str, index: int) -> str:
    return f"{short_tag(run_id)}{kind.upper()[:3]}{index:08d}"


def supplier_name(run_id: str, index: int) -> str:
    supplier = SUPPLIERS[(index - 1) % len(SUPPLIERS)]
    return f"{run_id} {supplier} {index:02d}"


def customer_name(run_id: str, index: int) -> str:
    customer = CUSTOMERS[(index - 1) % len(CUSTOMERS)]
    return f"{run_id} {customer} {index:02d}"


def asset_category_name(run_id: str, index: int) -> str:
    category = ASSET_CATEGORIES[(index - 1) % len(ASSET_CATEGORIES)]
    return f"{run_id} {category}"


def location_name(run_id: str, index: int) -> str:
    location = LOCATIONS[(index - 1) % len(LOCATIONS)]
    return f"{run_id} {location}"


def asset_name(run_id: str, index: int) -> str:
    asset = ASSET_NAMES[(index - 1) % len(ASSET_NAMES)]
    return f"{run_id} {asset} {index:05d}"


def transfer_payload(
    item: str,
    source_warehouse: str,
    target_warehouse: str,
    company: str | None = None,
) -> dict:
    payload = {
        "items": [{"item_code": item, "qty": 1}],
        "source_warehouse": source_warehouse,
        "target_warehouse": target_warehouse,
    }
    if company:
        payload["company"] = company
    return payload


def receipt_payload(
    item: str,
    target_warehouse: str,
    against_po: str | None = None,
    company: str | None = None,
) -> dict:
    payload = {
        "items": [{"item_code": item, "qty": 1}],
        "target_warehouse": target_warehouse,
    }
    if against_po:
        payload["against_po"] = against_po
    if company:
        payload["company"] = company
    return payload


def reconciliation_payload(item: str, warehouse: str, company: str | None = None) -> dict:
    payload = {"counts": [{"item_code": item, "qty": 1}], "warehouse": warehouse}
    if company:
        payload["company"] = company
    return payload


def navigation_payload() -> dict:
    return {
        "roles": {
            "admin": ["dashboard", "search", "transfer", "receipt", "count", "settings"],
            "manager": ["dashboard", "analytics", "reports", "alerts"],
            "operator": ["dashboard", "search", "transfer", "receipt", "count", "sync"],
        },
        "order": [
            "dashboard",
            "search",
            "transfer",
            "receipt",
            "count",
            "analytics",
            "reports",
            "alerts",
            "sync",
            "settings",
        ],
    }
