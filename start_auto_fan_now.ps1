$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskName = 'RazerFanControlAutoFan'

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
  Start-ScheduledTask -TaskName $taskName
  Write-Output "Started scheduled task: $taskName"
} else {
  $python = Join-Path $root '.venv\Scripts\pythonw.exe'
  $script = Join-Path $root 'auto_fan_daemon.py'
  $config = Join-Path $root 'auto-fan-config.json'
  Start-Process -FilePath $python -ArgumentList @($script, '--config', $config) -WorkingDirectory $root -WindowStyle Hidden
  Write-Output 'Started auto fan daemon directly.'
}
