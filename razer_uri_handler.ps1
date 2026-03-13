$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$logPath = Join-Path $projectRoot "razer-uri-handler.log"

$entry = [pscustomobject]@{
    timestamp = (Get-Date).ToString("o")
    args = $args
    raw = ($args -join " ")
}

$entry | ConvertTo-Json -Compress | Add-Content -Path $logPath -Encoding UTF8

exit 0
