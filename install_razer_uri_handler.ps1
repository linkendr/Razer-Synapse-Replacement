$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$handlerPath = Join-Path $projectRoot "razer_uri_handler.ps1"
$handlerPath = [System.IO.Path]::GetFullPath($handlerPath)

$baseKey = "HKCU:\Software\Classes\Razer"
$commandKey = Join-Path $baseKey "shell\open\command"
$command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$handlerPath`" `"%1`""

New-Item -Path $baseKey -Force | Out-Null
Set-ItemProperty -Path $baseKey -Name "(default)" -Value "URL:Razer Protocol" -Force
New-ItemProperty -Path $baseKey -Name "URL Protocol" -Value "" -PropertyType String -Force | Out-Null
New-Item -Path (Join-Path $baseKey "shell") -Force | Out-Null
New-Item -Path (Join-Path $baseKey "shell\open") -Force | Out-Null
New-Item -Path $commandKey -Force | Out-Null
Set-ItemProperty -Path $commandKey -Name "(default)" -Value $command -Force

Write-Host "Installed temporary Razer URI handler for current user."
Write-Host "Command: $command"
