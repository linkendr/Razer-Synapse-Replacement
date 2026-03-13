$taskName = 'RazerCpuBoostTray'

Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$processes = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -like '*cpu_boost_tray.py*' }

foreach ($process in $processes) {
  Stop-Process -Id $process.ProcessId -Force
}

Write-Output ('Stopped CPU boost tray instances: ' + $processes.Count)
