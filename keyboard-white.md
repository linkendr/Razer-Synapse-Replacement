# Keyboard White

## Purpose

Hold the Blade keyboard in stable `static white` through the Windows Razer lighting stack.

## Components

- `keyboard_white_daemon.py`
- `keyboard_windows_stack.py`
- `keyboard-white-config.json`
- `install_keyboard_white_startup.ps1`
- `remove_keyboard_white_startup.ps1`
- `install_keyboard_white_maintenance.ps1`
- `remove_keyboard_white_maintenance.ps1`
- `start_keyboard_white_now.ps1`
- `stop_keyboard_white_now.ps1`
- `refresh_keyboard_white_now.ps1`

## Current behavior

- the old direct-HID keyboard path is no longer the preferred path
- the working path is the Windows Razer lighting stack through:
  - `lighting_driver_v1.9.11.0.dll`
  - `RzChromaSDKProxy64.dll`
  - `RzLightingEngineApi_v4.0.54.0.dll`
- the current model is:
  - take ownership once
  - apply static white
  - keep the process alive
- the intended UX is not a visible periodic reinjection loop

## Default settings

- color: `255,255,255`
- brightness: `50%`
- implementation: `windows-stack`
- effect id: `6`
- reapply interval: `0`
- note:
  - `brightness_percent` is now applied through the Synapse-captured brightness packet family on the `windows-stack` path

## Startup task

- task name: `RazerKeyboardWhite`
- execution time limit: `PT0S`
- trigger: `AtLogOn`
- expected state after launch: `Running`

## Maintenance task

- task name: `RazerKeyboardWhiteRefresh`
- purpose:
  - restart the known-good keyboard daemon on a long cadence without touching the lighting sequence itself
- cadence:
  - every `6` hours

## Files on disk

- activity log: `keyboard-white.log`
- crash log: `keyboard-white-crash.log`
- full durable guide: `keyboard-control-playbook.md`

## Commands

Install startup:

```powershell
.\install_keyboard_white_startup.ps1
```

Remove startup:

```powershell
.\remove_keyboard_white_startup.ps1
```

Start now:

```powershell
.\start_keyboard_white_now.ps1
```

Refresh now:

```powershell
.\refresh_keyboard_white_now.ps1
```

Stop now:

```powershell
.\stop_keyboard_white_now.ps1
```

Install maintenance:

```powershell
.\install_keyboard_white_maintenance.ps1
```

Remove maintenance:

```powershell
.\remove_keyboard_white_maintenance.ps1
```

## Reverse-engineering state

Current keyboard understanding:

- interface index `2` is the relevant Blade keyboard interface
- Synapse capture and logs proved the Windows-stack path was the right model
- static white maps to engine `effect_id 6`
- the important handoff is now reconstructed locally
- the final missing issue was ownership lifetime, not basic static color payload
- brightness control is now also applied on the working Windows-stack path

For the full investigation history and the guide for future effects, see:

- `keyboard-control-playbook.md`
