$ErrorActionPreference = 'Continue'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$stateDir = Join-Path $root 'synapse-state'
$null = New-Item -ItemType Directory -Force -Path $stateDir

Get-Service 'Razer Game Manager Service 3' -ErrorAction SilentlyContinue |
  Select-Object Status, StartType, Name, DisplayName |
  Format-List |
  Out-File (Join-Path $stateDir 'pre_disable_service.txt') -Encoding utf8

reg query 'HKCU\Software\Microsoft\Windows\CurrentVersion\Run' /v RazerAppEngine > (Join-Path $stateDir 'pre_disable_run_value.txt') 2>&1

Get-Process RazerAppEngine -ErrorAction SilentlyContinue |
  Select-Object ProcessName, Id, Path |
  Format-Table -AutoSize |
  Out-File (Join-Path $stateDir 'pre_disable_processes.txt') -Encoding utf8

Set-Service -Name 'Razer Game Manager Service 3' -StartupType Disabled
Stop-Service -Name 'Razer Game Manager Service 3' -Force -ErrorAction SilentlyContinue
Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'RazerAppEngine' -ErrorAction SilentlyContinue
Get-Process RazerAppEngine -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

Get-Service 'Razer Game Manager Service 3' -ErrorAction SilentlyContinue |
  Select-Object Status, StartType, Name, DisplayName |
  Format-List |
  Out-File (Join-Path $stateDir 'post_disable_service.txt') -Encoding utf8

reg query 'HKCU\Software\Microsoft\Windows\CurrentVersion\Run' /v RazerAppEngine > (Join-Path $stateDir 'post_disable_run_value.txt') 2>&1

Get-Process RazerAppEngine -ErrorAction SilentlyContinue |
  Select-Object ProcessName, Id, Path |
  Format-Table -AutoSize |
  Out-File (Join-Path $stateDir 'post_disable_processes.txt') -Encoding utf8

Write-Output 'Synapse runtime disabled.'
