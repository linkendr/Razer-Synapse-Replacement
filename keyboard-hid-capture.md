# Keyboard HID Capture

## Purpose

Capture the native Windows USB/HID trace while Razer Synapse changes the Blade keyboard lighting effect.

The goal is to identify the exact packet or event sequence for:

- static white
- off
- any effect-reset command needed to clear breathing or reactive mode

## Script

- `capture_razer_hid_trace.ps1`
- `capture_razer_usbpcap.ps1`

## Requirements

- run from an elevated PowerShell session
- `pktmon.exe` must be available
- Razer Synapse installed for the comparison run
- `USBPcap` is recommended when you need the actual control-transfer payload bytes

## Start a capture

```powershell
.\capture_razer_hid_trace.ps1 start
```

Optional quieter capture:

```powershell
.\capture_razer_hid_trace.ps1 start -QuiesceProjectProcesses
```

That optional flag stops the local tray/fan/keyboard helpers for a cleaner capture, then restores scheduled tasks on stop.

## During the capture

1. Open Synapse.
2. Change keyboard lighting to the target state.
3. Wait a few seconds after each change.
4. Stop the capture.

## Stop the capture

```powershell
.\capture_razer_hid_trace.ps1 stop
```

## Outputs

A timestamped directory is created under:

- `captures\`

Each capture contains:

- `razer-hid.etl`
- `razer-hid.txt`
- `pre-state.json`
- `post-state.json`
- `README.txt`

## USBPcap payload capture

Use this when ETW confirms the right USB/HID traffic but you still need the actual control-transfer payloads.

Start:

```powershell
.\capture_razer_usbpcap.ps1 start
```

Quieter start that temporarily stops the local tray/fan/keyboard helpers:

```powershell
.\capture_razer_usbpcap.ps1 start -QuiesceProjectProcesses
```

While capture is active, add explicit markers when you click something in Synapse:

```powershell
.\capture_razer_usbpcap.ps1 mark -Label "brightness off"
.\capture_razer_usbpcap.ps1 mark -Label "brightness on"
```

Stop:

```powershell
.\capture_razer_usbpcap.ps1 stop
```

This workflow starts capture on the two real `USBPcapN` root-hub devices exposed on this machine and writes the helper host commands into the session folder for traceability.

If `USBPcap` was installed in the current Windows session and no `USBPcapN` devices open, reboot once before retrying. The filter driver may not expose its capture devices until after reboot.

On stop, the script also exports quick analysis artifacts when Wireshark `tshark.exe` is installed:

- `markers.jsonl`
- `capture-files.json`
- `*.razer-addresses.txt`
- `*.razer-wlen90.txt`

`*.razer-wlen90.txt` is the main fast-path file for keyboard analysis. It contains the 90-byte control payloads for the Razer device only, which makes Synapse mode and brightness commands much easier to isolate than searching the raw `.pcap` files manually.

## Recommended capture sequence

Use separate captures for:

1. Baseline with no lighting change
2. Synapse set to static white
3. Synapse set to off
4. Synapse set to breathing or reactive if comparison is needed

This makes it easier to diff the traces and isolate the effect-setting sequence.
