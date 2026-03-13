# Razer Synapse Replacement

Custom controller workspace for a Razer Blade 14 2021.

## Core files

- `razer_fan_control.py`: Python controller CLI
- `auto_fan_daemon.py`: background auto fan controller
- `auto-fan-config.json`: temperature-to-RPM curve and daemon settings
- `cpu_boost_tray.py`: tray app for combined CPU boost and GPU mode control
- `cpu-boost-tray-config.json`: tray behavior and thresholds
- `keyboard_white_daemon.py`: keyboard-lighting helper
- `keyboard-white-config.json`: keyboard color, brightness, and reapply settings
- `install_*.ps1`: startup task installers
- `start_*.ps1` / `stop_*.ps1`: local launch helpers
- `research.md`: reverse-engineering and implementation notes
- `validation.md`: generalized validation notes
- `cpu-telemetry.md`: CPU telemetry dependency notes
- `auto-fan-daemon.md`: daemon behavior and operations
- `cpu-boost-tray.md`: tray behavior and operations
- `keyboard-white.md`: keyboard helper behavior and limitations
- `synapse-disable.md`: Synapse disable workflow notes
- `SECURITY-REVIEW.md`: repo-scope and publication notes

## Local-only artifacts

These are intentionally ignored by git:

- `.venv\`
- `vendor\`
- `backup\`
- `synapse-state\`
- `*.log`
- `*-crash.log`
- local verification/status notes such as `status.md`

## Setup

Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Some features also require local system dependencies:

- `PawnIO` for low-level CPU telemetry access
- `LibreHardwareMonitorLib.dll` available under `vendor\LibreHardwareMonitor-v0.9.6` if you choose to vendor it locally

## Usage

List candidate Razer HID interfaces:

```powershell
.\.venv\Scripts\python.exe .\razer_fan_control.py probe
```

Query current state:

```powershell
.\.venv\Scripts\python.exe .\razer_fan_control.py query
```

Query CPU and GPU temperatures:

```powershell
.\.venv\Scripts\python.exe .\razer_fan_control.py temps --json
```

Set both fans to manual mode at 3600 RPM using power mode `custom`:

```powershell
.\.venv\Scripts\python.exe .\razer_fan_control.py set-fans --rpm 3600 --power-mode custom
```

Return fan control to automatic mode:

```powershell
.\.venv\Scripts\python.exe .\razer_fan_control.py auto --power-mode balanced
```

Turn CPU boost on:

```powershell
.\.venv\Scripts\python.exe .\razer_fan_control.py set-cpu-boost --mode on
```

Set GPU to high mode:

```powershell
.\.venv\Scripts\python.exe .\razer_fan_control.py set-gpu-boost --mode high
```

Start the CPU boost tray now:

```powershell
.\start_cpu_boost_tray_now.ps1
```

Install the CPU boost tray at logon:

```powershell
.\install_cpu_boost_tray_startup.ps1
```

Set the keyboard solid white once:

```powershell
.\.venv\Scripts\python.exe .\razer_fan_control.py set-keyboard-solid --red 255 --green 255 --blue 255 --brightness-percent 100
```

Run one live fan-daemon cycle:

```powershell
.\.venv\Scripts\python.exe .\auto_fan_daemon.py --once --verbose
```

Install the fan daemon at startup:

```powershell
.\install_auto_fan_startup.ps1
```

Install the keyboard helper at logon:

```powershell
.\install_keyboard_white_startup.ps1
```

## Notes

- The working control interface on this model uses the `MI_02` HID interface.
- The CLI uses read and write feature reports directly and does not require Synapse APIs.
- CPU temperature is read through `LibreHardwareMonitorLib.dll` and a local `PawnIO` installation.
- The auto fan daemon uses the higher of CPU temperature, GPU hotspot, and GPU core temperature.
- The CPU boost tray drives both CPU boost and GPU high/balanced mode from the notification area.
- Tray hardware detection remains poll-based, but tray UI updates are driven by state changes instead of a periodic UI timer.
- Startup uses hidden scheduled tasks and `pythonw.exe`, so tray and fan startup should be background-only.
- Keyboard lighting replacement is still best-effort only on this Blade.
- The fan daemon may still show first-pass manual verification failures before recovering on retry/revalidation.
