# Hardware Abstraction Layer (HAL)

## Why this exists

Inventory operations need to scan barcodes and read RFID tags from a mix of hardware: device cameras, integrated handheld scanners (Chainway, Zebra, Urovo, Honeywell), and future Bluetooth/USB UHF readers. Without an abstraction layer, every business module would link directly against vendor SDKs, and adding a new device would mean code changes throughout the app.

This phase establishes interfaces and a manager so business code only ever calls a generic adapter. Vendor SDKs land behind these interfaces, one per `vendors/<vendor>/` folder.

## Architectural rules

1. **No vendor SDK imports outside `lib/core/hardware/`.** Business modules import only `BarcodeAdapter`, `RfidAdapter`, `DeviceAdapter` from `lib/core/hardware/adapters/`.
2. **No business logic inside adapters.** They translate vendor-specific events into HAL entities (`ScanEvent`, `RfidTag`) and that's it.
3. **One vendor per folder.** `vendors/chainway/`, `vendors/zebra/`, etc. Native code (Kotlin/Java) lives next to the adapter that bridges to it.
4. **Stubs ship by default; real SDKs are opt-in.** Every vendor folder ships a stub that throws `VendorSdkUnavailableException` with a clear hint. The build is always green even if no vendor SDK is bundled.

## Layout

```text
lib/core/hardware/
├── adapters/
│   ├── barcode_adapter.dart       # interface
│   ├── rfid_adapter.dart          # interface
│   ├── device_adapter.dart        # interface (battery/firmware/etc.)
│   └── hardware_exceptions.dart
├── entities/
│   ├── scan_event.dart
│   ├── rfid_tag.dart
│   └── device_info.dart
├── camera/
│   └── camera_barcode_adapter.dart  # default fallback
├── vendors/
│   ├── _stub_barcode_adapter.dart   # shared stub base
│   ├── _stub_rfid_adapter.dart      # shared stub base
│   ├── chainway/                    # Chainway C72, C66, etc.
│   ├── zebra/                       # TC-series + RFID8500/RFD40
│   ├── urovo/
│   ├── honeywell/                   # CT40, EDA series (barcode only)
│   ├── generic/                     # last-resort UHF stub
│   └── registered_plugins.dart      # central registration
├── device_probe.dart                # detects manufacturer / model
├── hardware_registry.dart           # plugin registry singleton
├── hardware_manager.dart            # orchestrator
└── providers.dart                   # Riverpod wiring
```

## How adapter selection works

1. At app boot, `main.dart` calls `registerBuiltInHardwarePlugins()` to populate `HardwareRegistry.instance` with all known vendor plugins.
2. `bootstrapHardwareManager()` constructs a `HardwareManager` with the `CameraBarcodeAdapter` as fallback, then calls `initialize()`.
3. `initialize()` runs `DeviceProbe.probe()` (default `DefaultDeviceProbe` returns `manufacturer: "unknown"`; production builds wire in `AndroidDeviceProbe` via a method channel reading `Build.MANUFACTURER` / `Build.MODEL` / capability sensing).
4. The manager iterates `registry.plugins` in registration order. First plugin whose `matches(deviceInfo)` returns true is selected. Its `barcodeFactory` and `rfidFactory` (each nullable) produce the adapter instances.
5. If no plugin matches or the matched plugin doesn't supply a barcode factory, the `fallbackBarcode` (camera) is used. There is no RFID fallback — `rfid` returns null on devices with no UHF reader.

```dart
// Business code never sees a vendor name:
final scanner = ref.read(barcodeAdapterProvider);
if (scanner == null) {
  // unreachable in practice — camera fallback always present
} else {
  await scanner.startScan();
  final scan = await scanner.events.first;
}
```

## Plugin contract (current phase)

A "plugin" today is a compile-time `HardwarePlugin` instance registered via `HardwareRegistry.instance.register(...)`. Each plugin declares:

- `vendor` — stable id
- `matches(DeviceInfo)` — predicate
- `barcodeFactory` — `BarcodeAdapter Function()?`
- `rfidFactory` — `RfidAdapter Function()?`

A true runtime marketplace (sideloaded APKs registering themselves) is out of scope for this phase — see "Future work" below.

## Integrating a real vendor SDK

Reference: replace the Chainway stubs.

1. Drop the vendor's Android library files into `android/app/libs/` (per their docs).
2. Write Kotlin platform-channel code under `android/app/src/main/kotlin/.../chainway/` that exposes start/stop/inventory/etc.
3. Create concrete classes in `lib/core/hardware/vendors/chainway/` that implement `BarcodeAdapter` / `RfidAdapter` directly (not via `StubBarcodeAdapter`) and call the method channels.
4. Update `registered_plugins.dart` so `chainway.barcodeFactory` and `rfidFactory` point at the real implementations.
5. No changes to any business module.

## Testing strategy

- `HardwareRegistry.replaceAll([...])` lets tests inject fake plugins.
- `_FixedProbe(DeviceInfo(...))` controls what device the manager thinks it's running on.
- Stub adapter contracts (throw with a hint) are covered by direct tests; vendor-specific behavior is only meaningfully testable on real hardware.

See `test/core/hardware/hardware_manager_test.dart` for ~9 cases covering fallback, vendor selection, registration order, re-init disposal, and stub behavior.

## Future work

- **Runtime plugin marketplace**: Flutter doesn't support dynamic loading of native plugins out of the box. A real marketplace would require either (a) a custom APK distribution system where each vendor plugin is a separate Android app that exposes its adapters via Service binding + AIDL, or (b) a fully reflective Dart loader (still needs the native code shipped in the main APK). Out of scope for this phase.
- **Real Chainway/Zebra/Urovo/Honeywell integration**: each requires SDK access, native Kotlin code, and physical device testing. Tracked in [`integration-roadmap.md`](../hardware-roadmap/integration-roadmap.md).
- **`DeviceAdapter` Android impl**: battery / firmware / connection-status reporting via method channel. Currently the interface ships without a default impl. The `AndroidDeviceProbe` channel (`bude.hardware/probe`) is a model for how this would look — see [`lib/core/hardware/probes/ANDROID_NATIVE_INSTALL.md`](../../mobile-app/flutter_app/lib/core/hardware/probes/ANDROID_NATIVE_INSTALL.md).
- **Multi-adapter selection**: today the manager picks one barcode + one rfid adapter. Some setups (camera as backup when handheld is offline) would benefit from a "primary + fallback" model.
