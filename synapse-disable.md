# Synapse Disable Notes

Date: 2026-03-12

## Actions performed

- disabled and stopped the `Razer Game Manager Service 3` service
- removed the `RazerAppEngine` current-user startup entry
- stopped running `RazerAppEngine.exe` processes

## Result

The custom controller still worked after Synapse was disabled:

- query succeeded
- manual fan write succeeded
- automatic mode restore succeeded

This confirms the custom controller operates directly against the laptop control interface rather than depending on the Synapse runtime.

## Scripts

- disable again if needed:
  - `disable_synapse.ps1`
- re-enable the Synapse runtime:
  - `enable_synapse.ps1`
