$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root '.venv\Scripts\pythonw.exe'
$script = Join-Path $root 'keyboard_white_daemon.py'
$config = Join-Path $root 'keyboard-white-config.json'
$taskName = 'RazerKeyboardWhite'
$userId = "$env:USERDOMAIN\$env:USERNAME"
$argument = '"' + $script + '" --config "' + $config + '" --once'

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute $python -Argument $argument -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -Hidden -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Output "Installed scheduled task: $taskName"
