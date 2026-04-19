# Validation Notes

Date: 2026-03-12
Target platform: Razer Blade 14 2021 (`VID_1532&PID_0270`)

## Confirmed locally

- The working control interface is:
  - `VID_1532&PID_0270&MI_02`
- A read-only fan query succeeds on that interface.
- Query results successfully report:
  - fan RPM
  - manual and automatic fan mode
  - power mode
  - CPU boost
  - GPU boost

## Write-path validation

Tested command:

```powershell
.\.venv\Scripts\python.exe .\razer_fan_control.py set-fans --rpm 3200 --power-mode custom
```

Observed result:

- write succeeded
- follow-up query showed the requested manual mode and power mode state

Recovery command:

```powershell
.\.venv\Scripts\python.exe .\razer_fan_control.py auto
```

Observed result:

- write succeeded
- follow-up query returned to automatic fan mode

## Practical interpretation

This machine can already be controlled directly without Synapse APIs using the custom CLI in this folder.

## CPU boost tray validation

Date: 2026-04-19
Target platform: Razer Blade 14 2021 (`VID_1532&PID_0270`)

### Confirmed locally

- the tray performance path now controls both:
  - the Razer CPU/GPU performance modes
  - the Windows AC processor-state policy through `powercfg`
- current default Windows AC policy targets are:
  - boost on: `min=50`, `max=95`
  - boost off: `min=5`, `max=95`
- the tray is now intended to run as a two-state manual controller:
  - CPU boost always on
  - tray state controls GPU high vs balanced and the AC minimum
- startup is intended to force `Boost Off`

### Write-path validation

Validated through the tray app logic with a temporary config copy and direct hardware/power-policy readback.

Observed results:

- manual on drove:
  - `CPU Boost = 1`
  - `GPU Boost = 2`
  - Windows AC processor policy `50/95`
- manual off drove:
  - `CPU Boost = 1`
  - `GPU Boost = 1`
  - Windows AC processor policy `5/95`

### Live thermal behavior

Under sustained local GitHub Actions / WSL load on 2026-04-19, the machine was observed at roughly:

- CPU load near `100%`
- CPU clock around `2298-3124 MHz` with the capped AC max policies
- CPU temperature around the upper `70sC` to upper `80sC` after capping AC max below `100`
- tray state still balanced:
  - `CPU Boost = 1`
  - `GPU Boost = 1`
  - Windows AC processor policy `5/95`

Practical interpretation:

- this is expected with the current config
- boost-off mode is not a hard throttle because Windows AC max stays at `95`
- sustained thermal control now comes primarily from the Windows AC max cap instead of the older auto thermal gate

### Startup/runtime note

- on this Windows setup, launching the tray through the venv `pythonw.exe` creates a parent/child `pythonw.exe` pair
- that pair is expected and should not be treated as proof of two independent tray instances by itself
