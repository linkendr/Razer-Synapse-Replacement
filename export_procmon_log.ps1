param(
    [Parameter(Mandatory = $true)]
    [string]$InputPml,

    [Parameter(Mandatory = $true)]
    [string]$OutputCsv
)

$ErrorActionPreference = "Stop"

$procmon = "C:\Users\Administrator\tools\Procmon\Procmon64.exe"

$InputPml = [System.IO.Path]::GetFullPath($InputPml)
$OutputCsv = [System.IO.Path]::GetFullPath($OutputCsv)

if (-not (Test-Path $procmon)) {
    throw "Procmon64.exe not found at $procmon"
}

if (-not (Test-Path $InputPml)) {
    throw "Input PML does not exist: $InputPml"
}

$outDir = Split-Path -Parent $OutputCsv
if ($outDir) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}

if (Test-Path $OutputCsv) {
    Remove-Item $OutputCsv -Force
}

Get-Process Procmon64 -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 750

$proc = Start-Process -FilePath $procmon `
    -ArgumentList @(
        "/AcceptEula",
        "/Quiet",
        "/Minimized",
        "/OpenLog",
        $InputPml,
        "/SaveAs",
        $OutputCsv
    ) `
    -PassThru

if (-not $proc.WaitForExit(120000)) {
    try { $proc.Kill() } catch {}
    throw "Procmon export timed out for $InputPml"
}

Start-Sleep -Seconds 1

if (-not (Test-Path $OutputCsv)) {
    throw "Procmon export did not create CSV: $OutputCsv"
}

Write-Host "Exported Procmon log:"
Write-Host "  Input : $InputPml"
Write-Host "  Output: $OutputCsv"
