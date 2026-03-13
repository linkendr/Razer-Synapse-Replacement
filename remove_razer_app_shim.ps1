$ErrorActionPreference = "Stop"

$key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\Razer.exe"

if (Test-Path $key) {
    Remove-Item -Path $key -Recurse -Force
    Write-Host "Removed temporary Razer.exe app-path shim for current user."
} else {
    Write-Host "No temporary Razer.exe app-path shim was installed for current user."
}
