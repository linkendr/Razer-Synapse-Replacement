Razer HID capture started: 2026-03-13T11:16:20.0630781+01:00

Next steps:
1. Open Razer Synapse.
2. Change the keyboard to the target effect, for example:
   - static white
   - off
   - breathing/reactive if needed for comparison
3. Wait a few seconds after each change.
4. Run:
   .\capture_razer_hid_trace.ps1 stop

Outputs:
- razer-hid.etl
- razer-hid.txt
- pre-state.json
- post-state.json
