param(
  [switch]$ForceRestart
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$stopScript = Join-Path $root 'stop_keyboard_white_now.ps1'
$startScript = Join-Path $root 'start_keyboard_white_now.ps1'
$scriptPath = Join-Path $root 'keyboard_white_daemon.py'
$configPath = Join-Path $root 'keyboard-white-config.json'

$processes = Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match '^pythonw?\.exe$' `
    -and $_.CommandLine -like "*$scriptPath*" `
    -and $_.CommandLine -like "*$configPath*"
}

if ($ForceRestart) {
  & $stopScript | Out-Null
  Start-Sleep -Seconds 2
  & $startScript
  exit 0
}

if ($processes) {
  Write-Output ('Keyboard white daemon already running: ' + $processes.Count)
  exit 0
}

& $startScript
