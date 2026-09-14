# Integration Roadmap

## Phases

| Phase | Scope | Status |
|---|---|---|
| 1 | Repository skeleton, Flutter base, Frappe API skeleton, CI/CD foundation | In progress |
| 2 | Auth + Item lookup + barcode scan (camera) end-to-end against ERPNext | Planned |
| 3 | Stock entries, warehouse transfers, offline sync | Planned |
| 4 | RFID hardware adapters (Chainway first) | In progress |
| 5 | Additional ERP connectors (Zoho, SAP) behind the same client interface | Planned |

## Hardware abstraction

The mobile app talks to the Hardware Abstraction Layer (HAL) — see [`architecture/hal-design.md`](../architecture/hal-design.md) for the full design.

Business code consumes three vendor-agnostic interfaces from `lib/core/hardware/adapters/`:

```dart
abstract class BarcodeAdapter { /* startScan, stopScan, scanSingle, events */ }
abstract class RfidAdapter    { /* connect, startInventory, readTag, writeTagEpc, ... */ }
abstract class DeviceAdapter  { /* getDeviceInfo, getDeviceStatus, ... */ }
```

`HardwareManager` selects the right implementation at app start based on a `DeviceProbe`. Vendor plugins register themselves via `HardwareRegistry.instance.register(...)`.

| Adapter | Status | Devices |
|---|---|---|
| `CameraBarcodeAdapter` | Shipped | Any device with a camera (always available as fallback) |
| `ChainwayBarcodeAdapter` + `ChainwayRfidAdapter` | Android SDK bridge built; physical validation pending | Chainway C72, C66, R6 |
| `ZebraBarcodeAdapter` + `ZebraRfidAdapter` | Stub | Zebra TC-series + RFD40 / RFID8500 sleds |
| `UrovoBarcodeAdapter` + `UrovoRfidAdapter` | Stub | Urovo RFID handhelds |
| `HoneywellBarcodeAdapter` | Stub (barcode only) | Honeywell CT40, EDA series |
| `GenericUhfRfidAdapter` | Stub | Catch-all for BLE / USB / LLRP readers |

Replacing a stub with a real impl is a self-contained per-vendor task — see "Integrating a real vendor SDK" in `hal-design.md`. The rest of the app is unaware of which hardware is in use.

## Chainway integration status

Implemented:

- Public Chainway SDK archives cached in `vendor_sdk_cache/chainway/`.
- `DeviceAPI_ver20251103_release.aar` copied into `mobile-app/flutter_app/android/app/libs/`.
- Android Gradle app dependency configured for local `.aar` / `.jar` files.
- `ChainwayHardwarePlugin` registers method/event channels for barcode and UHF RFID.
- `ChainwayBarcodeAdapter` now calls the native `Barcode2D` SDK.
- `ChainwayRfidAdapter` now calls `RFIDWithUHFUART` for connect/disconnect, inventory, single tag read, EPC write, lock, kill, and power level.
- `HardwareProbePlugin` now detects Chainway capability by SDK class lookup as well as manufacturer string.

Pending before marking complete:

- Test on a physical C72/C66/R6 device with real tags.
- Confirm whether each target model uses `RFIDWithUHFUART` or needs an alternate Chainway class such as `RFIDWithUHFA4`.
- Validate trigger-key behavior and whether barcode continuous scan should use `Barcode2D.scan()` loop or a decode callback on each target.
- Confirm lock-code policy with product owner before using lock operations in production workflows.
- Add a device-backed integration test script/checklist once hardware is available.

## ERP abstraction

`backend/bude_api/services/erpnext_client.py` is the first implementation of an `ErpClient` interface. When SAP B1, Zoho, NetSuite, or Dynamics 365 connectors are added, they will live alongside `erpnext_client.py` and conform to the same interface. The mobile client stays unchanged.

## Out of scope (Phase 1)

- Custom DocTypes — never.
- Real RFID SDK integration.
- SAP / Zoho connectors.
- Push notifications.
- Multi-language UI.
