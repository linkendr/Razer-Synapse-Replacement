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
- `refresh_keyboard_white_now.ps1`: restart helper for the keyboard hold
- `keyboard-control-playbook.md`: durable keyboard reverse-engineering and extension guide
- `capture_razer_hid_trace.ps1`: ETW-based USB/HID capture helper
- `capture_razer_usbpcap.ps1`: payload-level USBPcap capture helper
- `install_*.ps1`: startup task installers
- `start_*.ps1` / `stop_*.ps1`: local launch helpers
- `research.md`: reverse-engineering and implementation notes
- `validation.md`: generalized validation notes
- `cpu-telemetry.md`: CPU telemetry dependency notes
- `auto-fan-daemon.md`: daemon behavior and operations
- `cpu-boost-tray.md`: tray behavior and operations
- `keyboard-white.md`: keyboard helper behavior and limitations
- `keyboard-control-playbook.md`: full keyboard control findings, solved path, and future effect-work guide
- `keyboard-hid-capture.md`: capture workflow for Synapse USB/HID analysis
- `keyboard-synapse-capture-findings.md`: current packet-level findings from Synapse captures
- `keyboard-windows-control-path-findings.md`: Windows-side control-path findings for keyboard lighting (`RZCONTROL`, `razerwdl`, lamp-array, lighting driver)
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

Important lighting note:

- the working keyboard-lighting path requires a local copy of the vendored Razer runtime under `vendor\razer-runtime`
- that runtime is intentionally not published in git, so a fresh clone needs those DLLs restored locally before keyboard lighting will work

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

Install keyboard maintenance refresh:

```powershell
.\install_keyboard_white_maintenance.ps1
```

Remove keyboard maintenance refresh:

```powershell
.\remove_keyboard_white_maintenance.ps1
```

Start a payload capture for Synapse keyboard actions:

```powershell
.\capture_razer_usbpcap.ps1 start -QuiesceProjectProcesses
```

Mark a specific Synapse action during capture:

```powershell
.\capture_razer_usbpcap.ps1 mark -Label "brightness off"
```

Stop the payload capture and export Razer-only summaries:

```powershell
.\capture_razer_usbpcap.ps1 stop
```

## Notes

- On this machine, this repo is currently mounted at `C:\Users\Administrator\AI-DESKTOP-INSTRUCTIONS\tools\windows\razer-synapse-replacement`.
- The working control interface on this model uses the `MI_02` HID interface.
- Fan, boost, and the base CLI control path use direct feature-report traffic and do not depend on Synapse APIs.
- CPU temperature is read through `LibreHardwareMonitorLib.dll` and a local `PawnIO` installation.
- The auto fan daemon uses the higher of CPU temperature, GPU hotspot, and GPU core temperature.
- The CPU boost tray drives both CPU boost and GPU high/balanced mode from the notification area.
- Tray hardware detection remains poll-based, but tray UI updates are driven by state changes instead of a periodic UI timer.
- The CPU boost tray now uses adaptive worker intervals:
  - `5s` in active auto mode
  - `10s` in clearly idle balanced auto mode
  - `20s` in manual modes
- The CPU boost tray also backs off to the slower cadence when battery policy is forcing balanced mode.
- The CPU boost tray now skips CPU/GPU telemetry entirely in manual mode and while auto mode is power-gated by battery policy.
- The CPU boost tray now uses a hybrid CPU trigger:
  - package average for heavy all-core work
  - top-2 logical-core average for lightly threaded CPU-bound work
  - hottest-core fast path for bursty CPU pressure
- The current default CPU hot-core thresholds are tuned toward faster gaming reaction:
  - `top-2 >= 80% for 6s`
  - `top-1 >= 85% for 5s`
- The CPU boost tray now has a CPU thermal override:
  - force balanced at `>= 95C` sustained
  - do not re-enter boost until the CPU cools to `<= 91C`
- The CPU boost tray only does per-core CPU polling in active auto mode.
- The CPU boost tray now uses a longer `300s` fallback hardware-state sync and disables periodic telemetry logging by default.
- Startup uses hidden scheduled tasks and `pythonw.exe`, so tray and fan startup should be background-only.
- If this repo path changes, rerun the `install_*_startup.ps1` and `install_keyboard_white_maintenance.ps1` scripts because the scheduled tasks store absolute paths.
- Keyboard static-white lighting is now working through the Windows stack and the vendored runtime under `vendor\razer-runtime`.
- Keyboard brightness is now also applied on that Windows-stack path.
- Keyboard maintenance now uses a non-disruptive ensure-running task instead of a forced periodic teardown.
- The keyboard maintenance task is optional; the supported baseline is still the interactive-session `AtLogOn` task plus the resident keyboard daemon.
- A true one-shot keyboard mode that applies once and exits is not the documented supported steady state for the current Windows-stack path.
- The USBPcap workflow is now working and has already isolated real Synapse brightness packets for this Blade.
- newer Windows-side findings now point to additional control-path work beyond raw HID:
  - openable `RZCONTROL` device interface
  - `RazerDynamicLighting`
  - `razerwdl.exe`
  - `lighting_driver_v1.9.11.0.dll`
  - `RzLightingEngineApi_v4.0.54.0.dll`
  - `rz_lamp_array_v1.0.46.0.dll`
- keyboard reverse engineering is now on a working Windows-stack path that can hold static white while resident with only low-churn maintenance reapplication
- `Razer Chroma` has been removed; the keyboard runtime is now vendored locally under `vendor\razer-runtime`
- the main remaining keyboard work is extending the same path to more effects
- The fan daemon may still show first-pass manual verification failures before recovering on retry/revalidation.
