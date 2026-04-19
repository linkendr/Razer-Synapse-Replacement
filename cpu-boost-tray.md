# CPU Boost Tray

This tray app adds a notification-area icon for two manual performance states without Synapse.

## Files

- `cpu_boost_tray.py`
- `cpu-boost-tray-config.json`
- `start_cpu_boost_tray_now.ps1`
- `stop_cpu_boost_tray_now.ps1`
- `install_cpu_boost_tray_startup.ps1`
- `remove_cpu_boost_tray_startup.ps1`

## Behavior

- sits in the Windows notification area
- manual-on icon is a green circle with a filled lightning bolt
- manual-off icon is a red circle with a hollow lightning bolt
- left click toggles `Boost Off <-> Boost On`
- `Boost On` means:
  - `CPU Boost On`
  - `GPU High`
  - Windows AC processor policy min/max = `50/95`
- `Boost Off` means:
  - `CPU Boost On`
  - `GPU Balanced`
  - Windows AC processor policy min/max = `5/95`
- menu status lines show:
  - `CPU: BOOST`
  - `GPU: High` or `GPU: Normal`
- supports `Boost ON`, `Boost OFF`, and `Exit`
- startup always forces `Boost Off`
- the background worker now serves mostly as periodic hardware-state sync and error recovery

## Runtime model

- telemetry sampling runs on a background worker thread
- tray UI updates are driven by state changes instead of a periodic UI timer
- hardware mode sync reuses the last known working HID interface instead of rediscovering it every time
- hardware mode sync is throttled to every `300` seconds by default, with immediate sync on startup and after our own writes
- periodic telemetry logging is disabled by default; normal steady-state logging is mostly transitions, sync, and errors
- repeated refresh failures are log-throttled

## Expected behavior

- `Boost Off` is not a hard CPU throttle
- with the current defaults, `Boost Off` restores Windows AC processor policy to `5/95`
- that means the CPU may still climb to high utilization and high clocks under real load because the AC max remains `95`
- `Boost On` keeps CPU boost enabled, raises the GPU to high mode, and raises the Windows AC floor to `50%`
- the tray no longer has an auto mode or thermal trigger logic in the active UI path
- temperature control now comes primarily from the fixed Windows AC max cap and the chosen AC minimum for each tray state

## Startup

- uses a hidden scheduled task named `RazerCpuBoostTray`
- launches `pythonw.exe`, so it should not leave a console window open
- the installed task is registered with `ExecutionTimeLimit = PT0S`
- on this machine, Task Scheduler starts the tray through the venv `pythonw.exe`, which in turn spawns the base Python `pythonw.exe`
- that parent/child `pythonw.exe` pair is expected here and does not by itself mean there are two independent tray instances

## Files on disk

- config file: `cpu-boost-tray-config.json`
- activity log: `cpu-boost-tray.log`
- crash log: `cpu-boost-tray-crash.log`
- processor-policy config keys:
  - `manage_windows_processor_policy`
  - `startup_boost_enabled`
  - `boost_ac_min_percent`
  - `boost_ac_max_percent`
  - `balanced_ac_min_percent`
  - `balanced_ac_max_percent`

## Commands

Start now:

```powershell
.\start_cpu_boost_tray_now.ps1
```

Stop now:

```powershell
.\stop_cpu_boost_tray_now.ps1
```

Install at logon:

```powershell
.\install_cpu_boost_tray_startup.ps1
```

Remove startup:

```powershell
.\remove_cpu_boost_tray_startup.ps1
```

## Notes

- CPU boost `off` maps to mode `0`
- CPU boost `on` maps to mode `1`
- GPU `low` maps to mode `0`
- GPU `balanced` / `medium` maps to mode `1`
- GPU `high` maps to mode `2`
- default Windows AC processor policy targets are:
  - boost on: `min=50`, `max=95`
  - boost off: `min=5`, `max=95`
- startup forces `Boost Off` by default through `startup_boost_enabled = false`
- the tray app persists its config and now always normalizes to manual two-state behavior on startup
- the tray app now also manages Windows AC processor state on transitions by calling `powercfg`
- legacy auto/thermal tuning keys may still remain in `cpu-boost-tray-config.json` for backward compatibility, but the live tray UI no longer uses them
- the tray app does not modify fan control behavior

## 2026-04-19 validation notes

- manual on was validated to drive:
  - Razer modes `cpu=1 gpu=2`
  - Windows AC processor policy `50/95`
- manual off was validated to drive:
  - Razer modes `cpu=1 gpu=1`
  - Windows AC processor policy `5/95`
- later live observation under local GitHub Actions / WSL load showed:
  - `CPU Boost = 1` is the intended steady-state for both tray positions after this redesign
  - `GPU Boost = 1`
  - Windows AC processor policy `5/95`
  - CPU load can still remain high under runner load
  - temperature should stay materially below the prior `100C+` behavior because AC max is capped at `95`
