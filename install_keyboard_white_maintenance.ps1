$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskName = 'RazerKeyboardWhiteRefresh'
$powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$script = Join-Path $root 'refresh_keyboard_white_now.ps1'
$argument = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $script + '"'
$userId = "$env:USERDOMAIN\$env:USERNAME"

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute $powershell -Argument $argument -WorkingDirectory $root
$triggers = @(
  (New-ScheduledTaskTrigger -Daily -At '12:00 AM'),
  (New-ScheduledTaskTrigger -Daily -At '6:00 AM'),
  (New-ScheduledTaskTrigger -Daily -At '12:00 PM'),
  (New-ScheduledTaskTrigger -Daily -At '6:00 PM')
)
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -Hidden -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers -Principal $principal -Settings $settings -Force | Out-Null
Write-Output "Installed scheduled task: $taskName"
