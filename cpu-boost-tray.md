# CPU Boost Tray

This tray app adds a notification-area icon for combined CPU boost and GPU mode control without Synapse.

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
- auto icon is a green circle with a lightning bolt and an `AUTO` badge overlay
- left click cycles `AUTO -> Manual On -> Manual Off -> AUTO`
- `Manual On` means `CPU Boost On + GPU High`
- `Manual Off` means `CPU Boost Off + GPU Balanced`
- menu status lines show:
  - `CPU: BOOST` or `CPU: Normal`
  - `GPU: High` or `GPU: Normal`
- supports `Manual Boost ON`, `Manual Boost OFF`, `Auto Mode`, and `Exit`
- default startup mode is `auto`
- auto mode checks telemetry every `5` seconds by default
- auto mode requires AC power by default
- auto mode forces the balanced profile when Battery Saver is active
- auto mode also reads Windows GPU counters for the NVIDIA adapter:
  - GPU 3D engine utilization
  - dedicated VRAM usage

## Runtime model

- telemetry sampling runs on a background worker thread
- hardware-utilization detection remains poll-based
- tray UI updates are driven by state changes instead of a periodic UI timer
- hardware mode sync reuses the last known working HID interface instead of rediscovering it every time
- hardware mode sync is throttled to every `60` seconds by default
- telemetry logging is throttled to every `30` seconds by default
- NVIDIA GPU counters are read through native `.NET PerformanceCounter` APIs instead of spawning `powershell.exe`
- repeated refresh failures are log-throttled

## Startup

- uses a hidden scheduled task named `RazerCpuBoostTray`
- launches `pythonw.exe`, so it should not leave a console window open
- the installed task is registered with `ExecutionTimeLimit = PT0S`

## Files on disk

- config file: `cpu-boost-tray-config.json`
- activity log: `cpu-boost-tray.log`
- crash log: `cpu-boost-tray-crash.log`

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
- the tray app persists the selected mode back into the config file
- the tray app does not modify fan control behavior
