$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskName = 'RazerKeyboardWhite'
$script = Join-Path $root 'keyboard_white_daemon.py'
$config = Join-Path $root 'keyboard-white-config.json'
$processes = Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match '^pythonw?\.exe$' `
    -and $_.CommandLine -like "*$script*" `
    -and $_.CommandLine -like "*$config*"
}

if ($processes) {
  Write-Output ('Keyboard white daemon already running: ' + $processes.Count)
  return
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
  Start-ScheduledTask -TaskName $taskName
  Write-Output "Started scheduled task: $taskName"
} else {
  $python = Join-Path $root '.venv\Scripts\pythonw.exe'
  Start-Process -FilePath $python -ArgumentList @($script, '--config', $config) -WorkingDirectory $root -WindowStyle Hidden
  Write-Output 'Started keyboard white daemon directly.'
}
