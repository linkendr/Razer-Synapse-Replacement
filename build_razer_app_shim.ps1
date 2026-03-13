$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourcePath = Join-Path $projectRoot "RazerAppShim.cs"
$outputPath = Join-Path $projectRoot "Razer.exe"
$cscPath = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

if (-not (Test-Path $cscPath)) {
    $cscPath = "C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
}

if (-not (Test-Path $cscPath)) {
    throw "csc.exe not found"
}

& $cscPath /nologo /target:exe /out:$outputPath $sourcePath

if (-not (Test-Path $outputPath)) {
    throw "failed to build $outputPath"
}

Write-Host "Built $outputPath"
