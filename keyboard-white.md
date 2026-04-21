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
  - keep the process alive with a very low-churn maintenance cadence
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
- this task is intentionally interactive-session based
- do not convert it to `AtStartup` / `SYSTEM` like the fan daemon unless you are re-validating the entire Windows lighting path
- expected steady state:
  - the keyboard remains static white while the background process stays alive
  - Task Scheduler may still show `Ready` after the effect is applied, so the better checks are `keyboard-white.log` and the running `keyboard_white_daemon.py` process

## Maintenance task

- task name: `RazerKeyboardWhiteRefresh`
- purpose:
  - ensure the known-good keyboard daemon is present on a long cadence without forcibly interrupting lighting
- operational note:
  - this task is optional
  - removing it is supported if the goal is to rely only on the normal interactive-session startup task
  - remove it with `.\remove_keyboard_white_maintenance.ps1`
- cadence:
  - `12:00 AM`
  - `6:00 AM`
  - `12:00 PM`
  - `6:00 PM`
- current machine note as of `2026-04-19`:
  - on `DESKTOP-IHLSOUK`, this optional maintenance task is currently not installed
  - the live baseline is the `AtLogOn` resident daemon only
  - a temporary blind `300s` daemon reapply experiment was tried and reverted the same day
  - if drift is reported again, do not assume a short daemon cadence is desired; verify the actual keyboard behavior first

## Supported modes

- supported:
  - `RazerKeyboardWhite` at `AtLogOn`
  - optional `RazerKeyboardWhiteRefresh` maintenance task
  - resident `keyboard_white_daemon.py` process holding ownership after startup
- not currently documented as a supported steady-state mode:
  - apply once at startup/logon and then exit with no resident daemon
  - converting the keyboard helper to `AtStartup` / `SYSTEM` without revalidation
- important semantics:
  - keep the daemon resident at logon
  - hold the Windows lighting session open in the background
  - `reapply_interval_seconds = 0` means "do not do blind periodic reapply"
  - the optional maintenance task is the long-cadence ensure-running fallback

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

Force restart now:

```powershell
.\refresh_keyboard_white_now.ps1 -ForceRestart
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
