$ErrorActionPreference = "Stop"

$baseKey = "HKCU:\Software\Classes\Razer"

if (Test-Path $baseKey) {
    Remove-Item -Path $baseKey -Recurse -Force
    Write-Host "Removed temporary Razer URI handler for current user."
} else {
    Write-Host "No temporary Razer URI handler was installed for current user."
}
