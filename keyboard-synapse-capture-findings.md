# Keyboard Synapse Capture Findings

Date: 2026-03-13

## Purpose

Document the current reverse-engineering state for the Blade 14 2021 keyboard lighting path while Razer Synapse is temporarily reinstalled.

The goal is to identify the exact packets Synapse uses for:

- keyboard brightness off/on
- static white
- off
- any effect-reset sequence needed to clear the persistent breathing/reactive state

## Why this was needed

The earlier public reverse-engineered lighting commands were enough to:

- write keyboard row colors
- change some brightness values

But they were not enough to fully clear the firmware effect state on this machine. The keyboard could still remain in breathing or reactive mode even when white color and brightness writes succeeded.

That meant the next reliable path was packet capture from Synapse itself.

## Capture tooling now in the project

- `capture_razer_hid_trace.ps1`
- `capture_razer_usbpcap.ps1`
- `keyboard-hid-capture.md`

## ETW capture result

The native ETW / `pktmon` workflow was validated first.

Confirmed:

- Synapse talks to the Blade over the expected USB/HID path
- the trace includes 90-byte control-transfer activity
- ETW was enough to prove we were looking at the right device class

Limitation:

- ETW did not expose the full payload bytes we needed for exact packet reproduction

Conclusion:

- ETW is useful for confirmation
- `USBPcap` is required for payload-level reconstruction

## USBPcap workflow result

`USBPcap` is now installed and the capture workflow is functional.

Important implementation detail:

- `USBPcapCMD.exe` had to be launched through a persistent PowerShell console host
- detached `Start-Process` modes were not reliable for this tool on this machine

The active capture workflow now supports:

- `start`
- `stop`
- `status`
- `mark`
- optional `-QuiesceProjectProcesses`

On stop, it also exports:

- `capture-files.json`
- `markers.jsonl`
- `*.razer-addresses.txt`
- `*.razer-wlen90.txt`

These exports make it much easier to isolate Synapse actions without manually digging through the full `.pcap`.

## First successful payload capture

Successful USB payload capture session:

- `captures\usbpcap\20260313-114129-RazerUsbPcap`

Files:

- `usbpcap-1.pcap`
- `usbpcap-2.pcap`

Result:

- the Razer Blade keyboard/control traffic is in `usbpcap-1.pcap`
- the Razer device appears as:
  - bus `1`
  - device address `3`
  - `VID_1532`
  - `PID_0270`

## Key protocol findings from the capture

The important control packets are 90-byte HID feature reports sent as:

- `URB_FUNCTION_CLASS_INTERFACE`
- `SET_REPORT`
- `bmRequestType = 0x21`
- `bRequest = 0x09`
- `wValue = 0x0300`
- `wIndex = 2`
- `wLength = 90`

This matches the general transport pattern expected from the reverse-engineered Blade projects.

## Brightness off/on finding

During the clean Synapse brightness toggle capture, the distinctive brightness packets were:

- `off`: frame `585`
- `on`: frame `589`

Packet payloads:

- off:
  - `000b00000003030301050000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000700`
- on:
  - `000c0000000303030105ff0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000f800`

Observed difference:

- the key changing byte is the brightness value:
  - `00` for off
  - `ff` for on

Practical implication:

- Synapse is not using the same keyboard-brightness packet path that our current replacement code assumed
- the correct Synapse-controlled brightness path on this Blade appears to be the `0x03 0x03 0x03 0x01 0x05 xx` style packet family captured above

## Additional capture observations

The same capture also contains:

- repeated 6-row white matrix writes using the expected 90-byte row packet family
- shorter effect/mode packets that appear separate from the row-color writes

This supports the earlier conclusion that:

- color data
- brightness
- effect mode

are separate controls on this machine

## Current interpretation

What we know now:

- the correct device is captured
- the payload capture workflow is working
- Synapse brightness off/on has been isolated at the payload level
- our current replacement code does not yet match this exact brightness packet family

Later Windows-side reverse engineering clarified an important point:

- the missing keyboard behavior is not just a raw packet-shape problem anymore
- the Blade keyboard effect path on Windows also involves native Razer control layers:
  - `RzLightingEngineApi_v4.0.54.0.dll`
  - `RzChromaSDKProxy64.dll`
  - `lighting_driver_v1.9.11.0.dll`

What is now confirmed:

- the engine DLL accepts the expected static-white quick-effect sequence without error
- the Chroma proxy DLL accepts device bootstrap calls without error
- that path avoids the old popup entirely

What is still missing:

- the engine/proxy replay still does not take ownership of the Blade keyboard output
- the keyboard still falls back to the built-in reactive/breathing behavior
- the strongest remaining suspect is the Blade-specific mode/bootstrap step logged by Synapse before quick effects take over

That means the USB captures remain important as reference, but the remaining work is now focused on reproducing Synapse's Windows control-path setup, not just replaying row packets.

What is still outstanding:

- capture and isolate the exact static-mode / effect-reset command sequence
- verify the packet sequence for:
  - static white
  - off
  - clearing breathing/reactive mode
- implement those exact packets in `razer_fan_control.py`
- remove Synapse again after validation

## Recommended next capture pattern

Use one action per capture when possible:

1. start capture
2. `mark` the intended action
3. click the Synapse control once
4. stop capture

Suggested labels:

- `brightness off`
- `brightness on`
- `static white`
- `static off`
- `reactive blue`
- `breathing white`

That keeps each `.pcap` and each exported `*.razer-wlen90.txt` narrow and easy to diff.
