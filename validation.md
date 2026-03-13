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
