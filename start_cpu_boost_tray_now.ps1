$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskName = 'RazerCpuBoostTray'

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
  Start-ScheduledTask -TaskName $taskName
  Write-Output "Started scheduled task: $taskName"
} else {
  $python = Join-Path $root '.venv\Scripts\pythonw.exe'
  $script = Join-Path $root 'cpu_boost_tray.py'
  $config = Join-Path $root 'cpu-boost-tray-config.json'
  $argument = '"' + $script + '" --config "' + $config + '"'
  Start-Process -FilePath $python -ArgumentList $argument -WorkingDirectory $root -WindowStyle Hidden
  Write-Output 'Started CPU boost tray directly.'
}
