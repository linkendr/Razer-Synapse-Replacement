# Auto Fan Daemon

## Purpose

Run a lightweight background process during Windows startup that:

- reads CPU temperature
- reads GPU temperature and hotspot
- uses the highest of those temperatures as the control temperature
- runs a startup fan blast phase before normal curve control
- selects a fan RPM from a configurable curve
- applies manual fan RPM when needed
- falls back to automatic fan mode at low temperature

## Components

- `auto_fan_daemon.py`
- `auto-fan-config.json`
- `install_auto_fan_startup.ps1`
- `remove_auto_fan_startup.ps1`
- `start_auto_fan_now.ps1`
- `stop_auto_fan_now.ps1`

## Behavior

- control temperature is the maximum of:
  - CPU package temperature
  - NVIDIA GPU hotspot temperature
  - NVIDIA GPU core temperature
- startup can force both fans to max RPM for a configured duration before curve control begins
- fan increases are applied immediately
- fan decreases are delayed by `cooldown_samples` polls to reduce hunting
- fan decreases also require temperatures to clear a step-down deadband before the daemon will drop to the next lower step
- manual fan mode is kept in `balanced` power mode by default
- low temperature falls back to automatic fan mode

## Startup model

Startup uses a hidden scheduled task:

- task name: `RazerFanControlAutoFan`
- action: `pythonw.exe auto_fan_daemon.py --config auto-fan-config.json`
- triggers:
  - system startup
  - any-user logon fallback
- principal: `SYSTEM`
- priority: `4`
- execution time limit: `PT0S`

## Exit behavior

- the daemon restores automatic fan mode on clean exit
- the daemon keeps balanced power mode by default
- a follow-up query can still show the last RPM briefly while the EC ramps down

## Default startup phase

- startup blast duration: `30` seconds
- startup blast target: `5300 RPM`

## Default curve

- below `70 C`: automatic mode
- `70 C`: `3100 RPM`
- `75 C`: `3300 RPM`
- `80 C`: `3700 RPM`
- `84 C`: `4200 RPM`
- `87 C`: `4700 RPM`
- `90 C`: `5300 RPM`

## Default hysteresis

- poll interval: `5` seconds
- step-down cooldown: `4` polls
- temperature deadband on step-down: `3 C`

## Files on disk

- config file: `auto-fan-config.json`
- activity log: `auto-fan-daemon.log`
- crash log: `auto-fan-daemon-crash.log`

## Commands

Install startup:

```powershell
.\install_auto_fan_startup.ps1
```

Remove startup:

```powershell
.\remove_auto_fan_startup.ps1
```

Start now:

```powershell
.\start_auto_fan_now.ps1
```

Stop now:

```powershell
.\stop_auto_fan_now.ps1
```

Inspect task state:

```powershell
Get-ScheduledTask -TaskName RazerFanControlAutoFan
```
