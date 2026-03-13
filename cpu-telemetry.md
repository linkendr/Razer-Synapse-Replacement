# CPU Telemetry Notes

Date: 2026-03-12
Target platform: Razer Blade 14 2021

## Goal

Obtain CPU temperature locally so the custom fan controller can make automatic decisions without Synapse.

## What failed

The stock Windows thermal APIs did not provide a usable CPU package temperature:

- `MSAcpi_ThermalZoneTemperature` was not supported
- `Win32_TemperatureProbe` did not provide useful data
- standard thermal performance counters did not provide the needed reading

## Why hardware monitors work

Tools such as `HWMonitor` and `LibreHardwareMonitor` do not rely on the weak Windows thermal-zone APIs for Ryzen laptop CPU temperature.

They use a privileged low-level hardware access driver to read AMD internal registers directly.

For `LibreHardwareMonitor`, the relevant pieces are:

- `LibreHardwareMonitorLib/Hardware/Cpu/Amd17Cpu.cs`
- `LibreHardwareMonitorLib/PawnIo/AmdFamily17.cs`
- `LibreHardwareMonitorLib/PawnIo/PawnIo.cs`

The AMD Family 17h / Zen 3 temperature logic reads:

- SMN register `0x00059800` (`F17H_M01H_THM_TCON_CUR_TMP`)

## The missing dependency

The reason CPU temperature originally showed `0.0` was that the required low-level hardware access driver, `PawnIO`, was not installed.

Without `PawnIO`, `LibreHardwareMonitor` could enumerate the CPU and GPU, but the Ryzen register reads effectively returned zeros for the CPU temperature path.

## Fix applied

Install:

```powershell
winget install --id namazso.PawnIO --accept-package-agreements --accept-source-agreements --disable-interactivity
```

After installation, `LibreHardwareMonitor` began returning valid CPU temperature and power telemetry.

## Local implementation path

The project now reads CPU temperature through:

- `LibreHardwareMonitorLib.dll`
- Python via `pythonnet`
- the installed `PawnIO` driver

Vendored files can be stored under:

- `vendor\LibreHardwareMonitor-v0.9.6`

## Practical result

The project has the inputs needed to build an automatic fan daemon:

- CPU temperature
- GPU temperature
- direct fan control
- direct auto/manual fan mode control
- power mode control

## Source references

- <https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/blob/master/LibreHardwareMonitorLib/Hardware/Cpu/Amd17Cpu.cs>
- <https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/blob/master/LibreHardwareMonitorLib/PawnIo/AmdFamily17.cs>
- <https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/blob/master/LibreHardwareMonitorLib/PawnIo/PawnIo.cs>
- <https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/blob/master/LibreHardwareMonitorLib/Hardware/RyzenSMU.cs>
- <https://github.com/LibreHardwareMonitor/LibreHardwareMonitor>
- <https://github.com/namazso/PawnIO.Setup>
