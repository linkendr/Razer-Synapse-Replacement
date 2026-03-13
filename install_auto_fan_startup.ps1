$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root '.venv\Scripts\pythonw.exe'
$script = Join-Path $root 'auto_fan_daemon.py'
$config = Join-Path $root 'auto-fan-config.json'
$taskName = 'RazerFanControlAutoFan'
$argument = '"' + $script + '" --config "' + $config + '"'

Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name $taskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute $python -Argument $argument -WorkingDirectory $root
$startupTrigger = New-ScheduledTaskTrigger -AtStartup
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -Hidden -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -Priority 4

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($startupTrigger, $logonTrigger) -Principal $principal -Settings $settings -Force | Out-Null
Write-Output "Installed scheduled task: $taskName"
