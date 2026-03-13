# Keyboard White

## Purpose

Attempt a simple one-shot keyboard lighting apply without Synapse.

## Components

- `keyboard_white_daemon.py`
- `keyboard-white-config.json`
- `install_keyboard_white_startup.ps1`
- `remove_keyboard_white_startup.ps1`
- `start_keyboard_white_now.ps1`
- `stop_keyboard_white_now.ps1`

## Behavior

- sends a solid RGB color write to all 6 keyboard rows
- sends a keyboard brightness write
- can reapply the requested color periodically if you explicitly enable that in config
- the default startup config applies once and exits instead of staying resident
- startup runs through a hidden scheduled task

## Important limitation

- keyboard lighting replacement is not considered fully solved on this Blade 14 2021
- color and brightness writes can work, but the firmware effect state can still override them
- startup should be treated as a best-effort one-shot apply, not a guaranteed static lighting replacement
- lid logo control is also not confirmed in this project

## Default settings

- color: `255,255,255`
- brightness: `50%`
- reapply interval: `0` seconds, which means apply once and exit

## Startup task

- task name: `RazerKeyboardWhite`
- launch path: `pythonw.exe keyboard_white_daemon.py --config keyboard-white-config.json --once`
- execution time limit: `PT0S`

## Files on disk

- activity log: `keyboard-white.log`
- crash log: `keyboard-white-crash.log`

## Commands

Install startup:

```powershell
.\install_keyboard_white_startup.ps1
```

Remove startup:

```powershell
.\remove_keyboard_white_startup.ps1
```

Start now:

```powershell
.\start_keyboard_white_now.ps1
```

Stop now:

```powershell
.\stop_keyboard_white_now.ps1
```
