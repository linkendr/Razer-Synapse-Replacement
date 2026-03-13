$taskName = 'RazerKeyboardWhite'

Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$processes = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -like '*keyboard_white_daemon.py*' }

foreach ($process in $processes) {
  Stop-Process -Id $process.ProcessId -Force
}

Write-Output ('Stopped keyboard white daemon instances: ' + $processes.Count)
