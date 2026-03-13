$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$stopScript = Join-Path $root 'stop_keyboard_white_now.ps1'
$startScript = Join-Path $root 'start_keyboard_white_now.ps1'

& $stopScript | Out-Null
Start-Sleep -Seconds 2
& $startScript
