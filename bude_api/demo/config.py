"""Config and safety helpers for demo data generation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar
from urllib.parse import urlparse

RUN_ID_PREFIX = "BUDE-DEMO"


@dataclass(frozen=True)
class DemoProfile:
    name: str
    companies: int
    warehouses: int
    item_groups: int
    items: int
    barcodes: int
    epc_records: int
    suppliers: int
    customers: int
    purchase_orders: int
    sales_orders: int
    stock_operations: int
    assets: int
    asset_locations: int
    asset_categories: int
    asset_movements: int
    repairs: int
    maintenance_logs: int
    enabled: bool = True

    def as_dict(self) -> dict:
        return asdict(self)


PROFILES: dict[str, DemoProfile] = {
    "preview": DemoProfile(
        name="preview",
        companies=1,
        warehouses=4,
        item_groups=4,
        items=40,
        barcodes=30,
        epc_records=20,
        suppliers=5,
        customers=8,
        purchase_orders=8,
        sales_orders=10,
        stock_operations=20,
        assets=12,
        asset_locations=6,
        asset_categories=4,
        asset_movements=12,
        repairs=4,
        maintenance_logs=12,
    ),
    "large-safe": DemoProfile(
        name="large-safe",
        companies=2,
        warehouses=30,
        item_groups=40,
        items=12_000,
        barcodes=8_000,
        epc_records=4_000,
        suppliers=250,
        customers=500,
        purchase_orders=800,
        sales_orders=1_200,
        stock_operations=20_000,
        assets=3_000,
        asset_locations=60,
        asset_categories=30,
        asset_movements=6_000,
        repairs=1_000,
        maintenance_logs=4_000,
    ),
    "massive-stress": DemoProfile(
        name="massive-stress",
        companies=3,
        warehouses=120,
        item_groups=120,
        items=100_000,
        barcodes=80_000,
        epc_records=40_000,
        suppliers=1_000,
        customers=5_000,
        purchase_orders=8_000,
        sales_orders=15_000,
        stock_operations=200_000,
        assets=30_000,
        asset_locations=250,
        asset_categories=80,
        asset_movements=60_000,
        repairs=10_000,
        maintenance_logs=40_000,
        enabled=False,
    ),
}


def get_profile(name: str) -> DemoProfile:
    key = (name or "").strip().lower()
    if key not in PROFILES:
        known = ", ".join(sorted(PROFILES))
        raise ValueError(f"Unknown demo profile '{name}'. Known profiles: {known}.")
    profile = PROFILES[key]
    if not profile.enabled:
        raise ValueError(f"Profile '{profile.name}' is disabled. Enable it in code before use.")
    return profile


def make_run_id(profile: str, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M%S")
    normalized = (profile or "preview").strip().lower().replace("_", "-")
    return f"{RUN_ID_PREFIX}-{timestamp}-{normalized}"


def validate_run_id(run_id: str) -> str:
    value = (run_id or "").strip()
    if not value.startswith(f"{RUN_ID_PREFIX}-"):
        raise ValueError(f"run_id must start with '{RUN_ID_PREFIX}-'.")
    if len(value) < len(RUN_ID_PREFIX) + 10:
        raise ValueError("run_id is too short to be a generated demo tag.")
    return value


def is_safe_local_target(site: str | None = None, base_url: str | None = None) -> bool:
    candidates = [c for c in [site, base_url] if c]
    if not candidates:
        return False
    for candidate in candidates:
        text = str(candidate).strip().lower()
        parsed = urlparse(text if "://" in text else f"http://{text}")
        host = parsed.hostname or text
        if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
            return True
        if host.endswith(".local") or host.endswith(".test"):
            return True
        if "dev" in host or "staging" in host:
            return True
    return False


def require_write_guard(
    *,
    run_id: str,
    site: str | None = None,
    base_url: str | None = None,
    confirm_demo_data: bool = False,
) -> None:
    validate_run_id(run_id)
    if confirm_demo_data or is_safe_local_target(site=site, base_url=base_url):
        return
    raise RuntimeError(
        "Refusing to write demo data: target is not clearly local/dev. "
        "Pass confirm_demo_data=True only for an intentional demo-data write."
    )


def demo_runs_root() -> Path:
    return Path(__file__).resolve().parents[2] / "demo_runs"


T = TypeVar("T")


def chunked(values: Iterable[T], size: int) -> Iterable[list[T]]:
    batch: list[T] = []
    for value in values:
        batch.append(value)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
