$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskName = 'RazerKeyboardWhiteRefresh'
$script = Join-Path $root 'refresh_keyboard_white_now.cmd'

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$taskCommand = '"' + $script + '"'
schtasks.exe /Create /TN $taskName /TR $taskCommand /SC HOURLY /MO 6 /RL HIGHEST /F | Out-Null
Write-Output "Installed scheduled task: $taskName"
