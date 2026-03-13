$taskName = 'RazerKeyboardWhite'

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Output "Removed startup registration: $taskName"
