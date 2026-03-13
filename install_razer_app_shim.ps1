$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$exePath = Join-Path $projectRoot "Razer.exe"

if (-not (Test-Path $exePath)) {
    & (Join-Path $projectRoot "build_razer_app_shim.ps1")
}

$key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\Razer.exe"
New-Item -Path $key -Force | Out-Null
Set-ItemProperty -Path $key -Name "(default)" -Value $exePath -Force
Set-ItemProperty -Path $key -Name "Path" -Value $projectRoot -Force

Write-Host "Installed temporary Razer.exe app-path shim for current user."
Write-Host "Executable: $exePath"
