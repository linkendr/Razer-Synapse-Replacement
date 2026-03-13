# Razer URI Handler

## Purpose

Temporarily handle the plain `Razer:` URI scheme on this machine so keyboard-lighting experiments do not trigger the Windows app chooser popup.

The handler is diagnostic only:

- it logs the invoked URI
- it exits successfully
- it does not launch Synapse or any other Razer app

## Files

- `razer_uri_handler.ps1`
- `install_razer_uri_handler.ps1`
- `remove_razer_uri_handler.ps1`
- `RazerAppShim.cs`
- `build_razer_app_shim.ps1`
- `install_razer_app_shim.ps1`
- `remove_razer_app_shim.ps1`

## Scope

- installs under `HKCU:\Software\Classes\Razer`
- affects the current user only
- intended as a temporary debugging aid

## Log

- `razer-uri-handler.log`

Each line is a JSON object containing:

- timestamp
- args
- raw

## Install

```powershell
.\install_razer_uri_handler.ps1
```

## Remove

```powershell
.\remove_razer_uri_handler.ps1
```

## Current reason for use

Direct keyboard-lighting writes on this Blade 14 2021 can trigger a Windows chooser popup for the plain `Razer` URI scheme.

At the time this handler was added:

- `HKCR\Razer` was missing
- `HKCR\RazerAppEngine.chroma-app` existed
- the popup still appeared even with Synapse UI and main Razer services stopped

That makes the missing `Razer:` protocol registration a strong suspect and this handler a low-risk way to capture what the Razer stack is trying to open.

## App-Path shim

If the popup is not a true URI launch and the system is instead trying to resolve a bare `Razer` executable target, install the temporary app-path shim:

```powershell
.\install_razer_app_shim.ps1
```

This builds `Razer.exe`, registers it under:

- `HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\Razer.exe`

and logs launches to:

- `razer-app-shim.log`

Remove it with:

```powershell
.\remove_razer_app_shim.ps1
```
