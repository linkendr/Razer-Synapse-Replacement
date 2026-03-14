# Keyboard Control Playbook

Date: 2026-03-13

This file is the durable keyboard-lighting guide for the Razer Blade 14 2021 in this project.

If a future AI needs to understand, maintain, or extend keyboard lighting on this machine, it should start here instead of redoing the entire reverse-engineering process.

## Outcome

The keyboard is now controllable through the Windows Razer lighting stack.

The currently solved behavior is:

- stable `static white`
- `50%` brightness by default
- no old app-picker popup
- no visible 5-second reinjection loop
- the keyboard remains white as long as the background Windows-stack session stays alive

The final issue was not the static-white packet itself. The final issue was ownership lifetime.

## Final working model

The correct Windows path is:

1. initialize the Razer Windows lighting components
2. register the Blade keyboard on interface `2`
3. apply the captured Synapse ownership/bootstrap sequence
4. apply engine `effect_id 6` for `static`
5. keep the process alive to hold ownership

Brightness note:

- the solved Windows-stack path currently holds static color ownership correctly
- `brightness_percent` is now applied through the Synapse-captured `0x03 0x03 0x03 0x01 0x05 xx` brightness packet family

The important local files are:

- `keyboard_windows_stack.py`
- `keyboard_white_daemon.py`
- `keyboard-white-config.json`
- `install_keyboard_white_startup.ps1`
- `start_keyboard_white_now.ps1`
- `probe_blade_keyboard_windows_stack.py`
- `keyboard-hid-capture.md`
- `keyboard-synapse-capture-findings.md`
- `keyboard-windows-control-path-findings.md`

## What did not work

These were useful for discovery, but they are not the final path:

- direct keyboard HID writes as the primary solution
- brute-force reapplying white every few seconds as the final UX
- focusing on lamp-array / WDL as the main Blade keyboard path
- trying to solve the popup first as if it were the core keyboard problem

Symptoms of the older direct-HID path:

- Windows popup asking how to open `Razer`
- keyboard turning black or falling back to reactive/breathing
- partial behavior changes without true effect ownership

Conclusion:

- direct HID on `MI_02` is excellent for fan and boost control
- keyboard lighting on Windows required the Windows Razer lighting stack

## Core technical findings

### Device and transport findings

- the Blade uses `VID_1532`, `PID_0270`
- the working fan/boost HID interface is `MI_02`
- Synapse keyboard traffic also targets interface `2`
- Synapse keyboard traffic uses 90-byte HID feature-report style transfers

### Windows lighting components that mattered

- `lighting_driver_v1.9.11.0.dll`
- `RzChromaSDKProxy64.dll`
- `RzLightingEngineApi_v4.0.54.0.dll`

Other discovered components were useful context but not the final solved path:

- `BladeNative_v1.0.10.1.dll`
- `rz_lamp_array_v1.0.46.0.dll`
- `razerwdl.exe`
- `RZCONTROL` device path

### Important log sources

These were the most useful sources during reverse engineering. They are historical references now, not part of the normal post-Synapse runtime.

The most useful live sources were:

- `C:\Users\Administrator\AppData\Local\Razer\RazerAppEngine\User Data\Logs\lighting-engine.log`
- `C:\Users\Administrator\AppData\Local\Razer\RazerAppEngine\User Data\Logs\lighting_driver.log`
- `C:\Users\Administrator\AppData\Local\Razer\RazerAppEngine\User Data\Logs\products_624_mw {00000000-0000-0000-FFFF-FFFFFFFFFFFF}.log`

Those logs provided:

- effect-name to engine-effect mapping
- real `AddEffect` / `RemoveEffect` behavior
- device handle behavior
- support-effect inventory
- confirmation that the Blade was using `rzDevice25LedMatrix`

If those logs are no longer present because Synapse/Chroma has already been removed, use the preserved capture artifacts in this repo first. Only reinstall Synapse temporarily if you are extending the lighting path and the existing captures are insufficient.

## Static white effect mapping

The crucial mapping from Synapse logs is:

- UI `static` -> engine `effectId 6`

For static white, Synapse's higher JS layer shows:

- `{"color":"0xffffff"}`

But the low-level engine call that actually hits `RzLightingApi` becomes:

- `{"Color":16777215}`

That distinction matters. The string form is not the final low-level payload.

## Other discovered effect mappings

These came directly from Synapse log conversion lines and should be the starting point for future effect work:

- UI `static` -> engine `6`
- UI `reactive` -> engine `3`
- UI `spectrumCycling` -> engine `4`
- UI `ripple` -> engine `1`
- UI `starlight` -> engine `7`
- UI `tidal` -> engine `19`

This means the current solution is not limited to static white in principle. The same Windows-stack path should support more effects once the correct parameter transformations are mirrored.

### Full Synapse-supported quick-effect inventory seen on this Blade

From the product log, Synapse exposes these quick effects for the Blade keyboard UI:

- `STATIC` (`1`)
- `BREATHING` (`2`)
- `SPECTRUM_CYCLING` (`3`)
- `WAVE` (`4`)
- `REACTIVE` (`5`)
- `RIPPLE` (`6`)
- `STARLIGHT` (`7`)
- `FIRE` (`8`)
- `AMBIENT` (`11`)
- `AUDIO_METER` (`12`)
- `WHEEL` (`13`)
- `TIDAL` (`19`)

Not all of those have been mirrored locally yet, but this is the correct inventory for future expansion work.

## Reconstructed ownership and static-handoff sequence

The most useful captured static-white takeover sequence includes:

- a leading `0x03030301` pair
- the `0x0d87 / 0x0d01 / 0x0d02 / 0x0d82 / 0x0d81` cluster
- white row writes
- apply

This sequence is represented locally as:

- `STATIC_WHITE_HANDOFF_SEQUENCE`

This handoff mattered for taking control before the engine effect applied.

## The breakthrough

The key tests converged to one answer:

- static white was already correct
- but only while our Windows-stack process remained alive

Observed progression:

- early tests: white for a moment, then breathing
- later tests: white for about `30` seconds, then fallback
- decisive test: white for the full lifetime of a held process, then black/fallback only after process exit

That proved the remaining bug was:

- ownership/session lifetime

It was not:

- the wrong static color
- the wrong interface
- active Synapse userland fighting us

## Final implementation details

### `keyboard_windows_stack.py`

This is the main solved control path.

It now does all of the following:

- initialize proxy, engine, and lighting driver
- `protocol.use_base_class`
- register the Blade keyboard on interface `2`
- `mode.set(3)`
- send default bootstrap packets
- send the captured static-white handoff sequence once
- create and add the engine device
- remove the previous effect handle before adding the next one
- apply engine `effect_id 6`
- keep the session alive

Important implementation details:

- static white uses low-level `{"Color": 16777215}`
- the session tracks `current_effect_handle`
- previous effects are removed with engine `Action 34`

### `keyboard_white_daemon.py`

The daemon is now a resident ownership holder.

Important runtime behavior:

- `implementation = "windows-stack"`
- `effect_id = 6`
- `reapply_interval_seconds = 0`

In the final semantics, `reapply_interval_seconds = 0` means:

- apply once
- avoid frequent visible reinjection loops
- keep the process alive and only wake on a very low cadence for maintenance

This is different from the old meaning of "apply once and exit."

### Startup task behavior

The scheduled task is:

- `RazerKeyboardWhite`

Operational note:

- this task is intentionally `AtLogOn` / interactive-session based
- do not convert it to `AtStartup` / `SYSTEM` without revalidating the whole lighting path
- Task Scheduler may still show `Ready` after the effect is applied, so the real checks are:
  - `keyboard-white.log`
  - the running `keyboard_white_daemon.py` process
  - the actual keyboard state

## How to use the current solved path

Start now:

```powershell
.\start_keyboard_white_now.ps1
```

Stop now:

```powershell
.\stop_keyboard_white_now.ps1
```

Install startup:

```powershell
.\install_keyboard_white_startup.ps1
```

Remove startup:

```powershell
.\remove_keyboard_white_startup.ps1
```

Check task state:

```powershell
Get-ScheduledTask -TaskName RazerKeyboardWhite
```

Check keyboard log:

```powershell
Get-Content .\keyboard-white.log -Tail 50
```

## How to extend this to more effects later

This is the most important future-looking part of the guide.

The correct extension workflow is:

1. keep using the Windows-stack session model
2. do not return to raw direct-HID-first experiments
3. set the target effect in Synapse once
4. inspect `lighting-engine.log`
5. find:
   - `convertUItoLighting()`
   - `AddEffect`
   - `RemoveEffect`
   - any transformed effect params
6. mirror those params in `keyboard_windows_stack.py`
7. keep the same ownership/bootstrap/session pattern

### What to look for in logs

For a new effect, capture these lines:

- UI effect name and `uiEffectId`
- converted engine `effectId`
- high-layer params
- transformed low-level `AddEffect` params

Examples already seen:

- `static` becomes low-level `Color`
- `reactive` becomes a more structured payload with duration and transformed stops
- `tidal` becomes a complex wave payload

### Extension principle

Do not assume all effects are just `{"Color": value}`.

For simple static:

- one integer `Color` field is enough

For reactive, tidal, ripple, breathing, and other dynamic effects:

- Synapse transforms the higher-level UI parameters into richer engine payloads
- those transformed payloads need to be mirrored at the engine layer

## After removing Synapse

The current working keyboard path no longer depends on an installed Synapse/Chroma runtime.

The required Windows lighting DLLs are now loaded from the local vendored runtime:

- `vendor\razer-runtime\common\lighting_driver_v1.9.11.0.dll`
- `vendor\razer-runtime\common\RzLightingEngineApi_v4.0.54.0.dll`
- `vendor\razer-runtime\sdk-bin\RzChromaSDKProxy64.dll`

Important operational note:

- `vendor\` is git-ignored in this project
- a fresh clone will not have those DLLs automatically
- keyboard lighting will not work until `vendor\razer-runtime` is restored locally

## Cold-start AI checklist

If a future AI starts fresh, it should do this:

1. read this file
2. inspect `keyboard_windows_stack.py`
3. inspect `keyboard-white-config.json`
4. inspect `keyboard_white_daemon.py`
5. check whether `RazerKeyboardWhite` is running
6. use the preserved captures and playbook notes for effect work first
7. only if those are insufficient, temporarily reinstall Synapse to regenerate `lighting-engine.log` / related logs for the new effect

It should not restart from:

- direct HID popup debugging
- lamp-array / Logitech paths
- packet brute-forcing from scratch

## Most important short version

If a future AI only remembers five facts, it should remember these:

1. Keyboard control on this Blade is solved through the Windows Razer lighting stack, not direct HID alone.
2. Static white is engine `effect_id 6`.
3. The captured ownership/bootstrap handoff matters before the engine effect.
4. The final bug was ownership lifetime, not color payload.
5. Keep the session alive if you want the keyboard to remain white.
