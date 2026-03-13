$taskName = 'RazerFanControlAutoFan'

Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$processes = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -like '*auto_fan_daemon.py*' }

foreach ($process in $processes) {
  Stop-Process -Id $process.ProcessId -Force
}

Write-Output ('Stopped auto fan daemon instances: ' + $processes.Count)
