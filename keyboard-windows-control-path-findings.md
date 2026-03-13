# Windows Keyboard Control Findings

Date: 2026-03-13

## Summary

The remaining keyboard-lighting issue is not just a packet-shape problem.

The current evidence points to a Windows-specific control stack layered on top of the Blade USB/HID path:

- direct `MI_02` writes are enough for fan and boost control
- Synapse keyboard traffic still uses interface `2` and 90-byte report-sized transfers
- static/off keyboard behavior is not yet being replicated by the direct HID path alone
- Windows also exposes a separate `RZCONTROL` control-device path, and that path is openable from user mode

## Confirmed device/control facts

- working low-level fan/boost HID path:
  - `VID_1532&PID_0270&MI_02`
- separate vendor control device exists:
  - `RZCONTROL\VID_1532&PID_0270&MI_00\...`
- confirmed openable from user mode:
  - `\\?\RZCONTROL#VID_1532&PID_0270&MI_00#...#{e3be005d-d130-4910-88ff-09ae02f680e9}`
- driver stack involved:
  - `RzCommon.sys`
  - `RzDev_0270.sys`

## Driver/package findings

- `RzDev_0270.sys` contains:
  - `RZCONTROL\VID_%04X&PID_%04X&MI_%02X`
- installed INF packages show:
  - `rzcommonu.inf`
  - `rzdevu_0270_dkm.inf`
  - `rzdevu_0270_kbd.inf`
  - `rzdevu_0270_mou.inf`

## Synapse-side user-mode findings

Synapse installs or stages several Windows-side native components beyond the visible app.

Relevant components discovered:

- `BladeNative_v1.0.10.1.dll`
- `lighting_driver_v1.9.11.0.dll`
- `RzLightingEngineApi_v4.0.54.0.dll`
- `rz_lamp_array_v1.0.46.0.dll`
- `razerwdl.exe`

## Dynamic-lighting package findings

There is a packaged dynamic-lighting component:

- AppX package:
  - `RazerDynamicLighting_1.0.3.0_x64__qemfkr3nbbywc`
- manifest declares:
  - executable: `razerwdl.exe`
  - extension: `com.microsoft.windows.lighting`
  - `AllowExternalContent=true`

The real executable is staged here:

- `C:\Users\Administrator\AppData\Local\Razer\RazerAppEngine\User Data\Apps\Common\LampArray\razerwdl.exe`

The dynamic-lighting/lamp-array stack appears to be:

- `rz_lamp_array_v1.0.46.0.dll`
  - contains `rpc::LampRpcClient::*`
  - contains references to `RazerWDL`
- `razerwdl.exe`
  - likely the Windows Dynamic Lighting / lamp-array host
- `lighting_driver_v1.9.11.0.dll`
  - imports `CreateFileW` and `DeviceIoControl`
  - likely the lower-level Windows lighting bridge
- `RzLightingEngineApi_v4.0.54.0.dll`
  - also imports `CreateFileW` and `DeviceIoControl`

## Library string findings

### `simple_service.dll`

Contains Windows device-enumeration imports:

- `SetupDiEnumDeviceInterfaces`
- `SetupDiGetDeviceInterfaceDetailW`
- `SetupDiGetClassDevsW`
- `CreateFileW`

This is consistent with user-mode enumeration of custom device interfaces such as `RZCONTROL`.

### `BladeNative_v1.0.10.1.dll`

Contains:

- `SetupDiEnumDeviceInterfaces`
- `SetupDiGetDeviceInterfaceDetailW`
- `CreateFileW`

This looks like Blade-specific device/platform enumeration, but not yet the final low-level lamp-array control layer.

### `lighting_driver_v1.9.11.0.dll`

Contains:

- `CreateFileW`
- `DeviceIoControl`
- type strings including:
  - `keyboard`
  - `rzDeviceLampArray`
  - `rzDeviceIoT`

This is currently the strongest candidate for the real Windows lighting bridge.

### `RzLightingEngineApi_v4.0.54.0.dll`

Contains:

- `CreateFileW`
- `DeviceIoControl`

This is another likely user-mode bridge into the Windows lighting/control stack.

### `rz_lamp_array_v1.0.46.0.dll`

Contains:

- `rpc::LampRpcClient::StartWatcher`
- `rpc::LampRpcClient::StopWatcher`
- `rpc::LampRpcClient::JsonApi`
- `rpc::LampRpcClient::SetCallback`
- `rpc::LampRpcClient::ExecuteRpcServer`
- strings referencing `RazerWDL`

This strongly suggests that part of Synapse keyboard/dynamic-lighting behavior is mediated through a local RPC service boundary, not just raw HID packets.

## Popup findings

The popup seen during direct keyboard writes was investigated.

What was tried:

- temporary `Razer:` URI handler
- temporary `Razer.exe` app-path shim
- Procmon capture around the popup

Current conclusion:

- the popup is not explained by a normal `Razer:` URI launch alone
- Explorer/AppResolver activity was seen around `Razer.exe`
- the temporary shim experiments did not intercept a clean executable launch
- those temporary handler/shim experiments have been removed to avoid contaminating later tests

## Procmon note

The earlier popup capture artifacts still exist:

- `captures\procmon\20260313-131217-popup.pml`
- `captures\procmon\20260313-131217-popup.csv`

Automated Procmon export scripting is still noisy and should not be treated as solved.

## Current conclusion

The most promising remaining path is:

1. keep the captured Synapse USB packets as protocol reference
2. stop assuming direct HID alone is the whole Windows keyboard path
3. investigate or call into the Windows-side lighting stack:
   - `lighting_driver_v1.9.11.0.dll`
   - `RzLightingEngineApi_v4.0.54.0.dll`
   - `rz_lamp_array_v1.0.46.0.dll`
   - `razerwdl.exe`
   - `RZCONTROL` device interface

The project is now past the stage of blind packet guessing. The remaining work is Windows control-path reconstruction.

## New engine/proxy findings

Two Windows DLL paths are now confirmed callable from Python:

- `RzLightingEngineApi_v4.0.54.0.dll`
- `RzChromaSDKProxy64.dll`

Working local probes now exist:

- `probe_rzlighting_engine.py`
- `probe_chroma_sdk_proxy.py`

Confirmed results:

- `RzLightingEngineApi` can successfully:
  - create engine
  - create device
  - add device
  - set position
  - add effect
  - enable engine
- `RzChromaSDKProxy64.dll` can successfully:
  - initialize
  - enumerate the active device count
  - add the Blade device
  - set the device state

Important user-visible result:

- the engine/proxy path does **not** trigger the old app-picker popup
- but it still does **not** take ownership of the Blade keyboard output
- the keyboard remains off at idle and falls back to reactive/breathing behavior on keypress

This makes the remaining issue much narrower:

- the popup belonged to the old direct-write path
- the remaining keyboard problem is now a missing Windows-side bring-up/ownership step

## Lamp-array finding narrowed further

The lamp-array / Windows Dynamic Lighting path is no longer considered the main target for the Blade keyboard.

Current log evidence shows the lamp-array activity belongs to the external Logitech keyboard:

- device name in logs: `G915 TKL`
- path family: `HID_DEVICE_SYSTEM_VHF`

That means:

- `rz_lamp_array_v1.0.46.0.dll`
- `razerwdl.exe`

are useful context for the Windows lighting stack, but they do not appear to be the actual ownership path for the Blade 14 keyboard effect we need to control.

## Strongest remaining suspect

The most promising remaining missing step is now the Blade-specific bring-up sequence visible in Synapse logs:

- `mode.set` / `setDeviceMode` to mode `3`
- `hid.configureDevicesDefaultData` before and after device ready
- `rzDeviceHelper.setChromaEffectCommon ... effectId:8`

Observed log pattern:

- Synapse reuses the same engine/device once the Blade is initialized
- on later static-white changes it removes the prior effect and adds the new one
- before those quick effects, the Blade path shows a mode/bootstrap sequence on:
  - `claimInterface: 2`
  - `protocol: 25`
  - `reportLength: 91`

Current best hypothesis:

- `RzLightingEngineApi` + `RzChromaSDKProxy64` are necessary but not sufficient
- the missing step is likely a Blade-specific lighting-driver bootstrap such as:
  - `device.register`
  - `mode.set(3)`
  - default HID bootstrap packets

## New Synapse-sequence reconstruction findings

The keyboard reverse-engineering work moved beyond generic engine/proxy bring-up.

The current local probes now reproduce:

- `lighting_driver` startup and `protocol.use_base_class`
- `device.register`
- `mode.set(3)`
- Blade default bootstrap packets before and after proxy registration
- the Synapse-captured `0x0d` ownership cluster
- a same-process callback bridge for `hid.sendFeatureReportInBatch`
- `RzLightingEngineApi` effect creation and enable

New helper modules/scripts now in the project:

- `probe_blade_keyboard_windows_stack.py`
- `keyboard_windows_stack.py`
- updated `keyboard_white_daemon.py`

## Strongest packet-level finding

The most useful captured static-white handoff sequence is no longer just the shared
`0x030b` row writes plus `0x030a` apply.

The best candidate static-white takeover sequence now includes:

- a leading `0x03030301` pair
- the `0x0d87 / 0x0d01 / 0x0d02 / 0x0d82 / 0x0d81` cluster
- then the white row writes and apply

In the best static-white transition capture, that ordering is:

1. `0x03030301` pair
2. `0x030d0100` pair
3. `0x040d0200`
4. `0x040d8200`
5. `0x030d8100` pair
6. fresh `0x030b` white rows
7. `0x030a` apply

This sequence is now reproduced locally in `STATIC_WHITE_HANDOFF_SEQUENCE`.

## Current user-visible behavior

The project can now seize the Blade keyboard temporarily through the Windows stack.

Observed results from the latest testing:

- old direct HID keyboard writes are no longer the main path
- the Windows stack path does not require active Synapse userland processes
- at least one run produced:
  - static white for about `1` second
  - then fallback to white breathing
- a later run produced:
  - static white for about `30` seconds
  - then fallback to default breathing
- another controlled run with `effect_id 7` and a short keepalive produced:
  - repeated white static intervals
  - interleaved flashes/fallbacks
  - less failure than earlier effect variants

That means:

- the Windows stack path is fundamentally correct
- the captured handoff is meaningful
- the remaining gap is now the steady-state effect/ownership latch, not raw transport

## Conflict finding

The current fallback does not appear to be caused by active Synapse userland reclaiming the keyboard.

Direct checks confirmed:

- no running `Razer*`, `*Chroma*`, `*AppEngine*`, or `*GameManager*` processes during recent tests
- Razer services were stopped during recent tests, including:
  - `Razer Game Manager Service 3`
  - `Razer Chroma SDK Service`
  - `Razer Chroma SDK Server`

Current conclusion:

- the remaining fallback is more likely firmware / EC default behavior
- or an incomplete steady-state lighting sequence on our side
- it is not mainly a visible Synapse runtime conflict

## Current best hypothesis

The current leading theory is:

- the static-white handoff/takeover is substantially correct
- the remaining issue is the engine steady-state layer:
  - wrong `effect_id`
  - wrong enable/clear behavior
  - or incomplete post-takeover ordering

Because of that, the next useful work is controlled steady-state testing:

- one clean takeover
- then one steady-state variant at a time
- no disruptive full re-handoffs on every refresh

## Practical project state

Keyboard lighting is no longer in the blind packet-guessing stage.

The project now has:

- a usable Windows-stack takeover path
- a reproducible captured static-white handoff sequence
- evidence that the keyboard can be forced into static white temporarily

The remaining work is to convert that temporary takeover into a stable non-breathing steady state.

## Final static-white resolution

That remaining gap is now resolved for static white.

The decisive finding was:

- static white already worked
- but only while the Windows-stack process stayed alive

So the final issue was not the static effect itself. The final issue was ownership lifetime.

The fix was:

- keep the Windows lighting session resident
- avoid visible periodic full re-handoffs
- use engine `effect_id 6`
- keep the background ownership-holder process alive

The current keyboard path now:

- uses the Windows lighting stack
- applies the reconstructed handoff once
- applies static white
- keeps the process alive in the background

This is the first keyboard path in the project that crossed the earlier `35-40` second failure point cleanly.

## Cold-start direction

A future AI should not restart this investigation from direct HID popup debugging.

It should start from:

- `keyboard-control-playbook.md`
- `keyboard_windows_stack.py`

The direct-HID path was part of discovery, but the final control model for the Blade keyboard on Windows is the Windows-stack resident-session model.
