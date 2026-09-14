"""HTTP API smoke runner for seeded Bude API demo data."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from . import scenarios
from .config import demo_runs_root


@dataclass(frozen=True)
class ApiCase:
    name: str
    method: str
    endpoint: str
    payload: dict[str, Any] | None = None
    expect_ok: bool = True


@dataclass
class ApiResult:
    name: str
    endpoint: str
    status: int
    ok: bool
    elapsed_ms: int
    error: str | None
    body: Any

    def as_dict(self) -> dict:
        return asdict(self)


class ApiClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        api_secret: str | None = None,
        host_header: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.host_header = host_header
        self.cookies: dict[str, str] = {}

    def login(self, username: str, password: str) -> dict:
        body = self.request(
            "POST",
            "/api/method/bude_api.api.auth.login",
            {"usr": username, "pwd": password},
            unwrap=False,
        )
        return body

    def request(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        *,
        unwrap: bool = True,
    ) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if self.host_header:
            headers["Host"] = self.host_header
        if self.api_key and self.api_secret:
            headers["Authorization"] = f"token {self.api_key}:{self.api_secret}"
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if method.upper() == "GET" and payload:
            endpoint = f"{endpoint}?{parse.urlencode(payload, doseq=True)}"
        elif payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{endpoint}",
            data=data,
            headers=headers,
            method=method.upper(),
        )
        with request.urlopen(req, timeout=30) as response:
            set_cookie = response.headers.get("Set-Cookie")
            if set_cookie:
                first = set_cookie.split(";", 1)[0]
                if "=" in first:
                    key, value = first.split("=", 1)
                    self.cookies[key] = value
            raw = response.read().decode("utf-8")
        body = json.loads(raw) if raw else {}
        return normalize_body(body) if unwrap else body


def normalize_body(body: Any) -> Any:
    if isinstance(body, dict) and "message" in body:
        return body["message"]
    return body


def build_cases(samples: dict, *, write_checks: bool = True) -> list[ApiCase]:
    item = samples.get("item") or ""
    company = samples.get("company") or ""
    warehouse = samples.get("warehouse") or ""
    target = samples.get("target_warehouse") or warehouse
    barcode = samples.get("barcode") or item
    epc = samples.get("epc") or barcode
    asset = samples.get("asset") or ""
    location = samples.get("location") or ""
    target_location = samples.get("target_location") or _alternate_location(location)
    category = samples.get("asset_category") or ""
    po = samples.get("purchase_order") or ""
    maintenance_log = samples.get("maintenance_log") or ""

    cases = [
        ApiCase("health.ping", "GET", "/api/method/bude_api.api.health.ping"),
        ApiCase("branding.get", "GET", "/api/method/bude_api.api.branding.get"),
        ApiCase("companies.list", "GET", "/api/method/bude_api.api.companies.list_companies"),
        ApiCase("warehouses.list", "GET", "/api/method/bude_api.api.warehouses.list"),
        ApiCase(
            "warehouses.stock",
            "GET",
            "/api/method/bude_api.api.warehouses.get_stock",
            {"warehouse": warehouse},
        ),
        ApiCase("items.groups", "GET", "/api/method/bude_api.api.items.list_groups"),
        ApiCase(
            "items.search",
            "GET",
            "/api/method/bude_api.api.items.search",
            {"query": item[:20], "limit": 10},
        ),
        ApiCase(
            "items.barcode",
            "GET",
            "/api/method/bude_api.api.items.get_by_barcode",
            {"barcode": barcode},
        ),
        ApiCase(
            "items.ledger",
            "GET",
            "/api/method/bude_api.api.items.get_ledger",
            {"item_code": item, "warehouse": warehouse},
        ),
        ApiCase(
            "items.stock",
            "GET",
            "/api/method/bude_api.api.items.get_stock",
            {"item_code": item, "warehouse": warehouse},
        ),
        ApiCase(
            "purchase_orders.open", "GET", "/api/method/bude_api.api.purchase_orders.list_open"
        ),
        ApiCase(
            "scan.resolve_epc", "GET", "/api/method/bude_api.api.scan.resolve_epc", {"epc": epc}
        ),
        ApiCase(
            "analytics.stock_aging",
            "GET",
            "/api/method/bude_api.api.analytics.get_stock_aging",
            {"warehouse": warehouse},
        ),
        ApiCase(
            "analytics.reconciliation_history",
            "GET",
            "/api/method/bude_api.api.analytics.get_reconciliation_history",
            {"warehouse": warehouse},
        ),
        ApiCase("alerts.list", "GET", "/api/method/bude_api.api.alerts.list_alerts"),
        ApiCase(
            "assets.list",
            "GET",
            "/api/method/bude_api.api.assets.list_assets",
            {"search": asset[:20], "limit": 10},
        ),
        ApiCase(
            "assets.detail", "GET", "/api/method/bude_api.api.assets.get_asset", {"name": asset}
        ),
        ApiCase(
            "assets.movements",
            "GET",
            "/api/method/bude_api.api.assets.get_asset_movements",
            {"asset": asset},
        ),
        ApiCase("assets.locations", "GET", "/api/method/bude_api.api.assets.list_locations"),
        ApiCase(
            "assets.categories", "GET", "/api/method/bude_api.api.assets.list_asset_categories"
        ),
        ApiCase(
            "assets.maintenance_logs",
            "GET",
            "/api/method/bude_api.api.assets.list_maintenance_logs",
            {"asset": asset},
        ),
        ApiCase("reports.asset_summary", "GET", "/api/method/bude_api.api.reports.asset_summary"),
        ApiCase(
            "reports.asset_register",
            "GET",
            "/api/method/bude_api.api.reports.asset_register",
            {"location": location, "category": category},
        ),
        ApiCase(
            "reports.maintenance_history",
            "GET",
            "/api/method/bude_api.api.reports.maintenance_history",
            {"asset": asset},
        ),
        ApiCase(
            "reports.asset_utilization", "GET", "/api/method/bude_api.api.reports.asset_utilization"
        ),
    ]
    if write_checks:
        cases.extend(
            [
                ApiCase(
                    "navigation.save",
                    "POST",
                    "/api/method/bude_api.api.navigation.save",
                    {"config_json": json.dumps(scenarios.navigation_payload())},
                ),
                ApiCase(
                    "stock.transfer",
                    "POST",
                    "/api/method/bude_api.api.stock.create_transfer",
                    scenarios.transfer_payload(item, warehouse, target, company),
                ),
                ApiCase(
                    "stock.receipt.free",
                    "POST",
                    "/api/method/bude_api.api.stock.create_receipt",
                    scenarios.receipt_payload(item, warehouse, company=company),
                ),
                ApiCase(
                    "stock.receipt.po",
                    "POST",
                    "/api/method/bude_api.api.stock.create_receipt",
                    scenarios.receipt_payload(item, warehouse, po, company),
                ),
                ApiCase(
                    "stock.reconciliation",
                    "POST",
                    "/api/method/bude_api.api.stock.create_reconciliation",
                    scenarios.reconciliation_payload(item, warehouse, company),
                ),
                ApiCase(
                    "assets.set_epc",
                    "POST",
                    "/api/method/bude_api.api.assets.set_epc",
                    {"doctype": "Item", "name": item, "epc": f"{epc}-VERIFY"},
                ),
                ApiCase(
                    "assets.movement",
                    "POST",
                    "/api/method/bude_api.api.assets.create_asset_movement",
                    {"assets": [asset], "purpose": "Transfer", "target_location": target_location},
                ),
                ApiCase(
                    "assets.repair",
                    "POST",
                    "/api/method/bude_api.api.assets.create_asset_repair",
                    {"asset": asset, "description": "API smoke demo repair"},
                ),
                ApiCase(
                    "assets.complete_maintenance",
                    "POST",
                    "/api/method/bude_api.api.assets.complete_maintenance_log",
                    {"log": maintenance_log},
                ),
            ]
        )
    return cases


def _alternate_location(location: str) -> str:
    if " 001" in location:
        return location.replace(" 001", " 002", 1)
    return location


def run(
    base_url: str,
    username: str | None = None,
    password: str | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
    host_header: str | None = None,
    manifest_path: str | None = None,
    output_dir: str | None = None,
    write_checks: bool = True,
) -> dict:
    manifest = _read_manifest(manifest_path)
    samples = manifest.get("samples", {})
    client = ApiClient(
        base_url,
        api_key=api_key,
        api_secret=api_secret,
        host_header=host_header,
    )
    if username and password and not (api_key and api_secret):
        login_body = normalize_body(client.login(username, password))
        if isinstance(login_body, dict) and login_body.get("ok"):
            data = login_body.get("data") or {}
            client.api_key = data.get("api_key")
            client.api_secret = data.get("api_secret")

    results = [
        execute_case(client, case) for case in build_cases(samples, write_checks=write_checks)
    ]
    summary = summarize_results(results)
    report = {"summary": summary, "results": [r.as_dict() for r in results]}
    _write_reports(report, manifest, output_dir)
    return report


def execute_case(client: ApiClient, case: ApiCase) -> ApiResult:
    start = time.perf_counter()
    status = 200
    body: Any = None
    error_text = None
    try:
        body = client.request(case.method, case.endpoint, case.payload)
        ok = bool(body.get("ok", True)) if isinstance(body, dict) else True
        passed = ok is case.expect_ok
    except error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
        error_text = raw[:500]
        body = raw
        passed = False
    except Exception as exc:
        error_text = str(exc)
        passed = False
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return ApiResult(case.name, case.endpoint, status, passed, elapsed_ms, error_text, body)


def summarize_results(results: list[ApiResult]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r.ok)
    failed = total - passed
    slowest = sorted(results, key=lambda r: r.elapsed_ms, reverse=True)[:5]
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "slowest": [{"name": r.name, "elapsed_ms": r.elapsed_ms} for r in slowest],
    }


def _read_manifest(path: str | None) -> dict:
    if not path:
        return {"samples": {}}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_reports(report: dict, manifest: dict, output_dir: str | None) -> None:
    run_id = manifest.get("run_id") or "manual-api-smoke"
    root = Path(output_dir) if output_dir else demo_runs_root() / run_id
    root.mkdir(parents=True, exist_ok=True)
    (root / "api-results.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    lines = [
        "# Bude API Smoke Results",
        "",
        f"- Total: {report['summary']['total']}",
        f"- Passed: {report['summary']['passed']}",
        f"- Failed: {report['summary']['failed']}",
        "",
        "| Case | Status | Latency | Result |",
        "| --- | ---: | ---: | --- |",
    ]
    for result in report["results"]:
        state = "PASS" if result["ok"] else "FAIL"
        lines.append(
            f"| {result['name']} | {result['status']} | {result['elapsed_ms']} ms | {state} |"
        )
    (root / "api-results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Bude API smoke checks.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--api-key")
    parser.add_argument("--api-secret")
    parser.add_argument("--host-header")
    parser.add_argument("--manifest-path")
    parser.add_argument("--output-dir")
    parser.add_argument("--read-only", action="store_true")
    args = parser.parse_args(argv)
    report = run(
        base_url=args.base_url,
        username=args.username,
        password=args.password,
        api_key=args.api_key,
        api_secret=args.api_secret,
        host_header=args.host_header,
        manifest_path=args.manifest_path,
        output_dir=args.output_dir,
        write_checks=not args.read_only,
    )
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
