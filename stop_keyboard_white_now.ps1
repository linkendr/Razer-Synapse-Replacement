$taskName = 'RazerKeyboardWhite'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $root 'keyboard_white_daemon.py'
$config = Join-Path $root 'keyboard-white-config.json'

Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$processes = Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match '^pythonw?\.exe$' `
    -and $_.CommandLine -like "*$script*" `
    -and $_.CommandLine -like "*$config*"
}

foreach ($process in $processes) {
  Stop-Process -Id $process.ProcessId -Force
}

Write-Output ('Stopped keyboard white daemon instances: ' + $processes.Count)
