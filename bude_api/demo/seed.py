"""Seed synthetic production-like demo data inside a Frappe bench.

Usage:
    bench --site <site> execute bude_api.demo.seed.run --kwargs \
      '{"profile":"preview","base_url":"http://127.0.0.1:8000"}'
"""

from __future__ import annotations

import json
import secrets
from datetime import date, timedelta
from pathlib import Path
from typing import Any

try:
    import frappe
except ImportError:  # pragma: no cover - importable outside a bench
    frappe = None

from ..custom.rfid_fields import ensure_custom_fields
from . import scenarios
from .config import DemoProfile, demo_runs_root, get_profile, make_run_id, require_write_guard


def run(
    profile: str = "preview",
    run_id: str | None = None,
    dry_run: bool = False,
    confirm_demo_data: bool = False,
    base_url: str | None = None,
) -> dict:
    """Seed a demo profile and return the generated manifest."""
    selected = get_profile(profile)
    tag = run_id or make_run_id(selected.name)
    if not dry_run:
        site = getattr(getattr(frappe, "local", None), "site", None) if frappe else None
        require_write_guard(
            run_id=tag,
            site=site,
            base_url=base_url,
            confirm_demo_data=confirm_demo_data,
        )
    seeder = DemoSeeder(selected, tag, dry_run=dry_run)
    manifest = seeder.seed_all()
    seeder.write_manifest(manifest)
    return manifest


class DemoSeeder:
    def __init__(self, profile: DemoProfile, run_id: str, dry_run: bool = False) -> None:
        self.profile = profile
        self.run_id = run_id
        self.dry_run = dry_run
        self.manifest: dict[str, Any] = {
            "run_id": run_id,
            "profile": profile.as_dict(),
            "dry_run": dry_run,
            "records": {},
            "samples": {},
            "warnings": [],
        }

    def seed_all(self) -> dict:
        if frappe is None and not self.dry_run:
            raise RuntimeError("Frappe is not available. Run inside a Frappe bench.")

        if not self.dry_run:
            ensure_custom_fields()

        companies = self._seed_companies()
        self._commit()
        warehouses = self._seed_warehouses(companies)
        self._commit()
        users = self._seed_users(warehouses)
        self._commit()
        groups = self._seed_item_groups()
        self._commit()
        self._seed_uoms()
        self._commit()
        items = self._seed_items(groups)
        self._commit()
        suppliers = self._seed_suppliers()
        self._commit()
        customers = self._seed_customers()
        self._commit()
        purchase_orders = self._seed_purchase_orders(companies, suppliers, items, warehouses)
        self._commit()
        sales_orders = self._seed_sales_orders(companies, customers, items, warehouses)
        self._commit()
        stock_docs = self._seed_stock_operations(companies, items, warehouses)
        self._commit()
        locations = self._seed_locations()
        self._commit()
        categories = self._seed_asset_categories(companies)
        self._commit()
        assets = self._seed_assets(companies, items, locations, categories)
        self._commit()
        asset_movements = self._seed_asset_movements(assets, locations)
        self._commit()
        repairs = self._seed_repairs(assets)
        self._commit()
        maintenance = self._seed_maintenance_logs(assets)

        self.manifest["samples"] = {
            "company": _first(companies),
            "warehouse": _first(warehouses),
            "target_warehouse": warehouses[1] if len(warehouses) > 1 else _first(warehouses),
            "item": _first(items),
            "barcode": scenarios.barcode(self.run_id, 1) if self.profile.barcodes else None,
            "epc": scenarios.epc(self.run_id, "itm", 1) if self.profile.epc_records else None,
            "purchase_order": _first(purchase_orders),
            "sales_order": _first(sales_orders),
            "customer": _first(customers),
            "asset": _first(assets),
            "location": _first(locations),
            "target_location": locations[1] if len(locations) > 1 else _first(locations),
            "asset_category": _first(categories),
            "asset_movement": _first(asset_movements),
            "repair": _first(repairs),
            "maintenance_log": _first(maintenance),
            "stock_document": _first(stock_docs),
            "api_user": _first(users),
            "api_key": self.manifest.get("api_credentials", {}).get("api_key"),
            "api_secret": self.manifest.get("api_credentials", {}).get("api_secret"),
        }
        if frappe and not self.dry_run:
            frappe.db.commit()
        return self.manifest

    def write_manifest(self, manifest: dict) -> Path:
        root = demo_runs_root() / self.run_id
        root.mkdir(parents=True, exist_ok=True)
        path = root / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _seed_companies(self) -> list[str]:
        names = []
        for index in range(1, self.profile.companies + 1):
            name = scenarios.company_name(self.run_id, index)
            names.append(
                self._ensure_doc(
                    "Company",
                    name,
                    {
                        "company_name": name,
                        "abbr": scenarios.company_abbr(self.run_id, index),
                        "default_currency": self._default_currency(),
                        "country": "United States",
                    },
                )
            )
        return self._record("Company", names)

    def _seed_warehouses(self, companies: list[str]) -> list[str]:
        names = []
        for index in range(1, self.profile.warehouses + 1):
            company = companies[(index - 1) % max(1, len(companies))]
            name = scenarios.warehouse_name(self.run_id, index)
            names.append(
                self._ensure_doc(
                    "Warehouse",
                    name,
                    {
                        "warehouse_name": name,
                        "company": company,
                        "disabled": 0,
                    },
                )
            )
        return self._record("Warehouse", names)

    def _seed_users(self, warehouses: list[str]) -> list[str]:
        email = f"{self.run_id.lower()}@example.test"
        api_key = f"bude_demo_{secrets.token_hex(8)}"
        api_secret = secrets.token_urlsafe(18)
        roles = self._available_roles(
            [
                "System Manager",
                "Stock Manager",
                "Stock User",
                "Item Manager",
                "Purchase Manager",
                "Purchase User",
                "Sales Manager",
                "Sales User",
                "Accounts Manager",
                "Accounts User",
                "Quality Manager",
                "Manufacturing Manager",
                "Manufacturing User",
                "Maintenance User",
                "Report Manager",
                "Prepared Report User",
                "Assets Manager",
            ]
        )
        if self.dry_run:
            self.manifest["api_credentials"] = {"api_key": api_key, "api_secret": api_secret}
            return self._record("User", [email])

        if frappe.db.exists("User", email):
            doc = frappe.get_doc("User", email)
        else:
            doc = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": "Bude Demo",
                    "last_name": self.run_id,
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "user_type": "System User",
                }
            )
            doc.insert(ignore_permissions=True)
        doc.api_key = api_key
        doc.api_secret = api_secret
        if warehouses and frappe.get_meta("User").has_field("default_warehouse"):
            doc.default_warehouse = warehouses[0]
        doc.roles = []
        for role in roles:
            doc.append("roles", {"role": role})
        doc.save(ignore_permissions=True)
        self.manifest["api_credentials"] = {"api_key": api_key, "api_secret": api_secret}
        return self._record("User", [email])

    def _available_roles(self, desired: list[str]) -> list[str]:
        if self.dry_run:
            return desired
        existing = set(
            frappe.get_all(
                "Role",
                filters=[["name", "in", desired]],
                pluck="name",
                limit_page_length=len(desired),
            )
        )
        return [role for role in desired if role in existing]

    def _seed_item_groups(self) -> list[str]:
        parent = self._default_item_group_parent()
        names = []
        for index in range(1, self.profile.item_groups + 1):
            name = scenarios.item_group_name(self.run_id, index)
            data = {"item_group_name": name, "is_group": 0}
            if parent:
                data["parent_item_group"] = parent
            names.append(self._ensure_doc("Item Group", name, data))
        return self._record("Item Group", names)

    def _seed_uoms(self) -> list[str]:
        names = sorted({scenarios.item_uom(index) for index in range(1, self.profile.items + 1)})
        if self.dry_run:
            return self._record("UOM", names)
        for name in names:
            if frappe.db.exists("UOM", name):
                continue
            doc = frappe.get_doc(
                {
                    "doctype": "UOM",
                    "uom_name": name,
                    "enabled": 1,
                }
            )
            doc.insert(ignore_permissions=True)
        return self._record("UOM", names)

    def _seed_items(self, groups: list[str]) -> list[str]:
        names = []
        for index in range(1, self.profile.items + 1):
            code = scenarios.item_code(self.run_id, index)
            group_name, _, _, _, _ = scenarios.item_template(index)
            preferred_group = f"{self.run_id} {group_name}"
            row = {
                "item_code": code,
                "item_name": scenarios.item_name(index),
                "description": scenarios.item_description(self.run_id, index),
                "item_group": preferred_group
                if preferred_group in groups
                else (groups[(index - 1) % max(1, len(groups))] if groups else None),
                "stock_uom": scenarios.item_uom(index),
                "is_stock_item": 1,
                "disabled": 0,
                "safety_stock": scenarios.item_safety_stock(index),
            }
            if index <= self.profile.epc_records:
                row["bude_epc"] = scenarios.epc(self.run_id, "itm", index)
            if index <= self.profile.barcodes:
                row["barcodes"] = [{"barcode": scenarios.barcode(self.run_id, index)}]
            names.append(self._ensure_doc("Item", code, row, commit_every=500, index=index))
        return self._record("Item", names)

    def _seed_suppliers(self) -> list[str]:
        names = []
        for index in range(1, self.profile.suppliers + 1):
            name = scenarios.supplier_name(self.run_id, index)
            names.append(
                self._ensure_doc(
                    "Supplier",
                    name,
                    {"supplier_name": name, "supplier_type": "Company"},
                )
            )
        return self._record("Supplier", names)

    def _seed_customers(self) -> list[str]:
        names = []
        for index in range(1, self.profile.customers + 1):
            name = scenarios.customer_name(self.run_id, index)
            names.append(
                self._ensure_doc(
                    "Customer",
                    name,
                    {
                        "customer_name": name,
                        "customer_type": "Company",
                    },
                )
            )
        return self._record("Customer", names)

    def _seed_purchase_orders(
        self,
        companies: list[str],
        suppliers: list[str],
        items: list[str],
        warehouses: list[str],
    ) -> list[str]:
        names = []
        today = date.today()
        for index in range(1, self.profile.purchase_orders + 1):
            company = companies[(index - 1) % max(1, len(companies))]
            supplier = suppliers[(index - 1) % max(1, len(suppliers))]
            warehouse = warehouses[(index - 1) % max(1, len(warehouses))]
            lines = []
            for offset in range(3):
                item = items[(index + offset - 1) % max(1, len(items))]
                lines.append(
                    {
                        "item_code": item,
                        "qty": 5 + ((index + offset) % 20),
                        "rate": 10 + ((index + offset) % 50),
                        "schedule_date": str(today + timedelta(days=7 + offset)),
                        "warehouse": warehouse,
                    }
                )
            name = f"{self.run_id}-PO-{index:05d}"
            names.append(
                self._insert_transaction(
                    "Purchase Order",
                    name,
                    {
                        "supplier": supplier,
                        "company": company,
                        "transaction_date": str(today),
                        "schedule_date": str(today + timedelta(days=7)),
                        "items": lines,
                    },
                    submit=True,
                    commit_every=100,
                    index=index,
                )
            )
        return self._record("Purchase Order", names)

    def _seed_sales_orders(
        self,
        companies: list[str],
        customers: list[str],
        items: list[str],
        warehouses: list[str],
    ) -> list[str]:
        names = []
        if not customers or not items:
            return self._record("Sales Order", names)
        today = date.today()
        for index in range(1, self.profile.sales_orders + 1):
            company = companies[(index - 1) % max(1, len(companies))]
            customer = customers[(index - 1) % len(customers)]
            warehouse = warehouses[(index - 1) % max(1, len(warehouses))] if warehouses else None
            lines = []
            for offset in range(2):
                item = items[(index + offset - 1) % len(items)]
                lines.append(
                    {
                        "item_code": item,
                        "qty": 2 + ((index + offset) % 8),
                        "rate": 25 + ((index + offset) % 75),
                        "delivery_date": str(today + timedelta(days=2 + offset)),
                        "warehouse": warehouse,
                    }
                )
            name = f"{self.run_id}-SO-{index:05d}"
            maybe_name = self._try_transaction(
                "Sales Order",
                name,
                {
                    "customer": customer,
                    "company": company,
                    "transaction_date": str(today),
                    "delivery_date": str(today + timedelta(days=3)),
                    "items": lines,
                },
                submit=True,
                commit_every=100,
                index=index,
            )
            if maybe_name:
                names.append(maybe_name)
        return self._record("Sales Order", names)

    def _seed_stock_operations(
        self, companies: list[str], items: list[str], warehouses: list[str]
    ) -> list[str]:
        names = []
        names_by_type = {"Stock Entry": [], "Stock Reconciliation": []}
        if not items or not warehouses:
            return names
        for index in range(1, self.profile.stock_operations + 1):
            company = companies[(index - 1) % max(1, len(companies))]
            item = items[(index - 1) % len(items)]
            source = warehouses[(index - 1) % len(warehouses)]
            target = warehouses[index % len(warehouses)]
            if index <= len(items):
                purpose = "Material Receipt"
                doctype = "Stock Entry"
                data = {
                    "company": company,
                    "stock_entry_type": purpose,
                    "purpose": purpose,
                    "posting_date": str(date.today()),
                    "remarks": self.run_id,
                    "items": [
                        {
                            "item_code": item,
                            "qty": 20 + index % 30,
                            "t_warehouse": source,
                            "basic_rate": 10 + index % 50,
                        }
                    ],
                }
            elif index % 5 == 0:
                doctype = "Stock Reconciliation"
                data = {
                    "company": company,
                    "purpose": "Stock Reconciliation",
                    "posting_date": str(date.today()),
                    "remarks": self.run_id,
                    "items": [
                        {
                            "item_code": item,
                            "warehouse": source,
                            "qty": 20 + index % 30,
                            "valuation_rate": 10 + index % 50,
                        }
                    ],
                }
            else:
                purpose = "Material Transfer" if index % 3 == 0 else "Material Receipt"
                row = {"item_code": item, "qty": 2 + index % 15}
                if purpose == "Material Transfer":
                    row["s_warehouse"] = source
                    row["t_warehouse"] = target
                else:
                    row["t_warehouse"] = source
                    row["basic_rate"] = 10 + index % 50
                doctype = "Stock Entry"
                data = {
                    "company": company,
                    "stock_entry_type": purpose,
                    "purpose": purpose,
                    "posting_date": str(date.today()),
                    "remarks": self.run_id,
                    "items": [row],
                }
            doc_name = self._insert_transaction(
                doctype,
                f"{self.run_id}-STOCK-{index:06d}",
                data,
                submit=True,
                commit_every=100,
                index=index,
            )
            names.append(doc_name)
            if doctype in names_by_type:
                names_by_type[doctype].append(doc_name)
        for doctype, doc_names in names_by_type.items():
            self._record(doctype, doc_names)
        return self._record("Stock Operation", names)

    def _seed_locations(self) -> list[str]:
        names = []
        for index in range(1, self.profile.asset_locations + 1):
            name = scenarios.location_name(self.run_id, index)
            names.append(
                self._ensure_doc(
                    "Location",
                    name,
                    {
                        "location_name": name,
                        "is_group": 0,
                    },
                )
            )
        return self._record("Location", names)

    def _seed_asset_categories(self, companies: list[str]) -> list[str]:
        names = []
        for index in range(1, self.profile.asset_categories + 1):
            name = scenarios.asset_category_name(self.run_id, index)
            names.append(
                self._try_doc(
                    "Asset Category",
                    name,
                    {
                        "asset_category_name": name,
                        "accounts": self._asset_category_accounts(companies),
                    },
                )
            )
        return self._record("Asset Category", [name for name in names if name])

    def _seed_assets(
        self,
        companies: list[str],
        items: list[str],
        locations: list[str],
        categories: list[str],
    ) -> list[str]:
        names = []
        if not categories:
            self.manifest["warnings"].append("Skipping assets: no Asset Category could be created.")
            return names
        today = date.today()
        for index in range(1, self.profile.assets + 1):
            name = scenarios.asset_name(self.run_id, index)
            category = categories[(index - 1) % len(categories)]
            asset_item = self._ensure_asset_item(index, category)
            data = {
                "asset_name": name,
                "company": companies[(index - 1) % max(1, len(companies))],
                "item_code": asset_item,
                "asset_category": category,
                "location": locations[(index - 1) % max(1, len(locations))] if locations else None,
                "purchase_date": str(today - timedelta(days=index % 365)),
                "available_for_use_date": str(today - timedelta(days=index % 300)),
                "gross_purchase_amount": 500 + (index % 5000),
                "net_purchase_amount": 500 + (index % 5000),
                "value_after_depreciation": 300 + (index % 3000),
                "maintenance_required": 1 if index % 3 == 0 else 0,
            }
            if index <= self.profile.epc_records:
                data["bude_epc"] = scenarios.epc(self.run_id, "ast", index)
            maybe_name = self._try_asset(name, data, commit_every=100, index=index)
            if maybe_name:
                names.append(maybe_name)
        return self._record("Asset", names)

    def _ensure_asset_item(self, index: int, category: str) -> str:
        code = f"{self.run_id}-ASSET-ITEM-{index:05d}"
        return self._ensure_doc(
            "Item",
            code,
            {
                "item_code": code,
                "item_name": f"{scenarios.asset_name(self.run_id, index)} capital item",
                "item_group": self._default_item_group_parent(),
                "stock_uom": "Nos",
                "is_stock_item": 0,
                "is_fixed_asset": 1,
                "asset_category": category,
                "disabled": 0,
            },
            commit_every=100,
            index=index,
        )

    def _seed_asset_movements(self, assets: list[str], locations: list[str]) -> list[str]:
        names = []
        if not assets or not locations:
            return names
        for index in range(1, self.profile.asset_movements + 1):
            asset = assets[(index - 1) % len(assets)]
            current_location = self._asset_location(asset)
            target = locations[index % len(locations)]
            if current_location and target == current_location:
                alternatives = [location for location in locations if location != current_location]
                target = alternatives[0] if alternatives else target
            company = self._asset_company(asset)
            names.append(
                self._try_transaction(
                    "Asset Movement",
                    f"{self.run_id}-ASM-{index:06d}",
                    {
                        "company": company,
                        "purpose": "Transfer",
                        "transaction_date": str(date.today()),
                        "assets": [{"asset": asset, "target_location": target}],
                    },
                    submit=True,
                    commit_every=100,
                    index=index,
                )
            )
        return self._record("Asset Movement", [name for name in names if name])

    def _asset_company(self, asset: str) -> str | None:
        if self.dry_run:
            return None
        return frappe.db.get_value("Asset", asset, "company")

    def _asset_location(self, asset: str) -> str | None:
        if self.dry_run:
            return None
        return frappe.db.get_value("Asset", asset, "location")

    def _seed_repairs(self, assets: list[str]) -> list[str]:
        names = []
        if not assets:
            return names
        for index in range(1, self.profile.repairs + 1):
            asset = assets[(index - 1) % len(assets)]
            names.append(
                self._try_doc(
                    "Asset Repair",
                    f"{self.run_id}-ASR-{index:06d}",
                    {
                        "asset": asset,
                        "failure_date": str(date.today() - timedelta(days=index % 60)),
                        "repair_status": "Pending",
                        "description": f"Demo repair generated by {self.run_id}.",
                        "repair_cost": 25 + index % 250,
                    },
                    commit_every=100,
                    index=index,
                )
            )
        return self._record("Asset Repair", [name for name in names if name])

    def _seed_maintenance_logs(self, assets: list[str]) -> list[str]:
        names = []
        if not assets:
            return names
        for index in range(1, self.profile.maintenance_logs + 1):
            asset = assets[(index - 1) % len(assets)]
            names.append(
                self._try_doc(
                    "Asset Maintenance Log",
                    f"{self.run_id}-AML-{index:06d}",
                    {
                        "asset_name": asset,
                        "maintenance_status": "Planned" if index % 4 else "Overdue",
                        "due_date": str(date.today() + timedelta(days=(index % 45) - 15)),
                    },
                    commit_every=100,
                    index=index,
                )
            )
        return self._record("Asset Maintenance Log", [name for name in names if name])

    def _ensure_doc(
        self,
        doctype: str,
        name: str,
        data: dict,
        *,
        commit_every: int | None = None,
        index: int = 0,
    ) -> str:
        if self.dry_run:
            return name
        if frappe.db.exists(doctype, name):
            return name
        existing = self._existing_doc_name(doctype, data)
        if existing:
            return existing
        doc_data = {
            "doctype": doctype,
            "name": name,
            **{k: v for k, v in data.items() if v is not None},
        }
        doc = frappe.get_doc(doc_data)
        doc.insert(ignore_permissions=True)
        self._maybe_commit(commit_every, index)
        return doc.name

    def _existing_doc_name(self, doctype: str, data: dict) -> str | None:
        unique_filters = {
            "Warehouse": ["warehouse_name", "company"],
            "Item Group": ["item_group_name"],
            "Supplier": ["supplier_name"],
            "Customer": ["customer_name"],
            "Location": ["location_name"],
            "Asset Category": ["asset_category_name"],
            "UOM": ["uom_name"],
        }
        fields = unique_filters.get(doctype)
        if not fields:
            return None
        filters = {field: data.get(field) for field in fields if data.get(field)}
        if len(filters) != len(fields):
            return None
        rows = frappe.get_all(doctype, filters=filters, pluck="name", limit=1)
        return rows[0] if rows else None

    def _insert_transaction(
        self,
        doctype: str,
        name: str,
        data: dict,
        *,
        submit: bool,
        commit_every: int | None = None,
        index: int = 0,
    ) -> str:
        if self.dry_run:
            return name
        if frappe.db.exists(doctype, name):
            return name
        doc = frappe.get_doc(
            {"doctype": doctype, "name": name, **{k: v for k, v in data.items() if v is not None}}
        )
        doc.insert(ignore_permissions=True)
        if submit:
            doc.submit()
        self._maybe_commit(commit_every, index)
        return doc.name

    def _try_doc(self, doctype: str, name: str, data: dict, **kwargs) -> str | None:
        try:
            return self._ensure_doc(doctype, name, data, **kwargs)
        except Exception as exc:  # pragma: no cover - depends on ERPNext setup
            self.manifest["warnings"].append(f"Skipped {doctype} {name}: {exc}")
            if frappe:
                frappe.db.rollback()
            return None

    def _try_asset(self, asset_name: str, data: dict, **kwargs) -> str | None:
        try:
            if self.dry_run:
                return asset_name
            existing = frappe.get_all(
                "Asset",
                filters={"asset_name": asset_name},
                pluck="name",
                limit=1,
            )
            if existing:
                doc = frappe.get_doc("Asset", existing[0])
                if doc.docstatus == 0:
                    doc.submit()
                return doc.name
            doc = frappe.get_doc(
                {
                    "doctype": "Asset",
                    **{k: v for k, v in data.items() if v is not None},
                }
            )
            doc.insert(ignore_permissions=True)
            doc.submit()
            self._maybe_commit(kwargs.get("commit_every"), kwargs.get("index", 0))
            return doc.name
        except Exception as exc:  # pragma: no cover - depends on ERPNext setup
            self.manifest["warnings"].append(f"Skipped Asset {asset_name}: {exc}")
            if frappe:
                frappe.db.rollback()
            return None

    def _try_transaction(self, doctype: str, name: str, data: dict, **kwargs) -> str | None:
        try:
            return self._insert_transaction(doctype, name, data, **kwargs)
        except Exception as exc:  # pragma: no cover - depends on ERPNext setup
            self.manifest["warnings"].append(f"Skipped {doctype} {name}: {exc}")
            if frappe:
                frappe.db.rollback()
            return None

    def _record(self, doctype: str, names: list[str]) -> list[str]:
        self.manifest["records"][doctype] = {"count": len(names), "names": names}
        return names

    def _maybe_commit(self, every: int | None, index: int) -> None:
        if not self.dry_run and every and index and index % every == 0:
            frappe.db.commit()

    def _commit(self) -> None:
        if frappe and not self.dry_run:
            frappe.db.commit()

    def _default_item_group_parent(self) -> str | None:
        if self.dry_run:
            return None
        rows = frappe.get_list(
            "Item Group",
            filters={"is_group": 1},
            fields=["name"],
            order_by="lft asc",
            limit=1,
        )
        return rows[0]["name"] if rows else None

    def _default_currency(self) -> str:
        if self.dry_run:
            return "INR"
        return (
            frappe.db.get_default("currency")
            or frappe.db.get_single_value("Global Defaults", "default_currency")
            or "INR"
        )

    def _asset_category_accounts(self, companies: list[str]) -> list[dict]:
        rows = []
        if self.dry_run:
            return rows
        for company in companies:
            rows.append(
                {
                    "company_name": company,
                    "fixed_asset_account": self._account(company, "Fixed Asset"),
                    "accumulated_depreciation_account": self._account(
                        company, "Accumulated Depreciation"
                    ),
                    "depreciation_expense_account": self._account(company, "Depreciation"),
                }
            )
        return rows

    def _account(self, company: str, account_type: str) -> str | None:
        rows = frappe.get_list(
            "Account",
            filters=[
                ["company", "=", company],
                ["account_type", "=", account_type],
                ["is_group", "=", 0],
            ],
            fields=["name"],
            limit=1,
        )
        return rows[0]["name"] if rows else None


def _first(values: list[str]) -> str | None:
    return values[0] if values else None
