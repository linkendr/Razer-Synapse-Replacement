$taskName = 'RazerFanControlAutoFan'

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name $taskName -ErrorAction SilentlyContinue
Write-Output "Removed startup registration: $taskName"
