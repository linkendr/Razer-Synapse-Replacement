param(
  [Parameter(Mandatory = $true, Position = 0)]
  [ValidateSet('start', 'stop', 'status')]
  [string]$Action,

  [string]$OutputRoot = 'C:\Razer Synapse Replacement\captures',

  [string]$SessionName = 'RazerHidTrace',

  [switch]$QuiesceProjectProcesses
)

$ErrorActionPreference = 'Stop'

$providers = @(
  'Microsoft-Windows-Input-HIDCLASS',
  'Microsoft-Windows-USB-UCX',
  'Microsoft-Windows-USB-USBHUB',
  'Microsoft-Windows-USB-USBHUB3',
  'Microsoft-Windows-USB-USBPORT',
  'Microsoft-Windows-USB-USBXHCI'
)

$projectProcesses = @(
  'pythonw',
  'python'
)

$projectTaskNames = @(
  'RazerCpuBoostTray',
  'RazerFanControlAutoFan',
  'RazerKeyboardWhite'
)

function Test-IsAdmin {
  $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-SessionPaths {
  $stateDir = Join-Path $OutputRoot '.state'
  $sessionFile = Join-Path $stateDir "$SessionName.json"
  return @{
    StateDir = $stateDir
    SessionFile = $sessionFile
  }
}

function Ensure-Directory([string]$Path) {
  if (-not (Test-Path $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function Get-RazerSnapshot {
  $pnp = @(Get-PnpDevice | Where-Object { $_.InstanceId -like '*VID_1532*' -or $_.FriendlyName -like '*Razer*' -or $_.Class -like '*HID*' })
  $signedDrivers = @(Get-CimInstance Win32_PnPSignedDriver | Where-Object { $_.DeviceID -like '*VID_1532*' -or $_.DeviceName -like '*Razer*' -or $_.DriverProviderName -like '*Razer*' })
  $hidDevices = @(Get-CimInstance Win32_PnPEntity | Where-Object { $_.DeviceID -like '*VID_1532*' -or $_.Name -like '*Razer*' })
  $services = @(Get-Service | Where-Object { $_.Name -like '*Razer*' -or $_.DisplayName -like '*Razer*' })
  $processes = @(
    Get-Process | ForEach-Object {
      try {
        $path = $_.Path
      } catch {
        $path = $null
      }
      if ($_.ProcessName -like '*Razer*' -or $path -like 'C:\Razer Synapse Replacement\*') {
        [pscustomobject]@{
          ProcessName = $_.ProcessName
          Id = $_.Id
          Path = $path
        }
      }
    }
  )
  return @{
    captured_at = (Get-Date).ToString('o')
    pnp_devices = $pnp
    signed_drivers = $signedDrivers
    hid_entities = $hidDevices
    services = $services
    processes = $processes
  }
}

function Stop-ProjectTraffic {
  $stoppedTasks = @()
  foreach ($taskName in $projectTaskNames) {
    try {
      $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
      $info = Get-ScheduledTaskInfo -TaskName $taskName
      if ($info.State -eq 'Running') {
        Stop-ScheduledTask -TaskName $taskName | Out-Null
        $stoppedTasks += $taskName
      }
    } catch {
      continue
    }
  }

  $killed = @()
  foreach ($proc in Get-Process -ErrorAction SilentlyContinue) {
    if ($projectProcesses -contains $proc.ProcessName) {
      try {
        $path = $proc.Path
      } catch {
        $path = $null
      }
      if ($path -like 'C:\Razer Synapse Replacement\*') {
        Stop-Process -Id $proc.Id -Force
        $killed += @{
          process_name = $proc.ProcessName
          pid = $proc.Id
          path = $path
        }
      }
    }
  }

  return @{
    stopped_tasks = $stoppedTasks
    killed_processes = $killed
  }
}

function Restore-ProjectTraffic([hashtable]$State) {
  if (-not $State) {
    return
  }

  foreach ($taskName in @($State.stopped_tasks)) {
    try {
      Start-ScheduledTask -TaskName $taskName | Out-Null
    } catch {
      Write-Warning ("Failed to restart scheduled task {0}: {1}" -f $taskName, $_)
    }
  }
}

function Save-Session([hashtable]$Data) {
  $paths = Get-SessionPaths
  Ensure-Directory $paths.StateDir
  $Data | ConvertTo-Json -Depth 8 | Set-Content -Path $paths.SessionFile -Encoding UTF8
}

function Load-Session {
  $paths = Get-SessionPaths
  if (-not (Test-Path $paths.SessionFile)) {
    return $null
  }
  return Get-Content -Raw $paths.SessionFile | ConvertFrom-Json
}

function Remove-Session {
  $paths = Get-SessionPaths
  if (Test-Path $paths.SessionFile) {
    Remove-Item $paths.SessionFile -Force
  }
}

function Invoke-PktMon {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$Arguments,

    [switch]$IgnoreExitCode
  )

  $oldPreference = $global:PSNativeCommandUseErrorActionPreference
  $global:PSNativeCommandUseErrorActionPreference = $false
  try {
    & pktmon @Arguments
    $exitCode = $LASTEXITCODE
  } finally {
    $global:PSNativeCommandUseErrorActionPreference = $oldPreference
  }

  if ((-not $IgnoreExitCode) -and $exitCode -ne 0) {
    throw "pktmon exited with code $exitCode for arguments: $($Arguments -join ' ')"
  }
}

function Stop-PktMonQuiet {
  cmd.exe /c "pktmon stop >nul 2>&1" | Out-Null
}

function Resolve-EtlFiles([string]$ConfiguredPath) {
  if (Test-Path $ConfiguredPath) {
    return @($ConfiguredPath)
  }

  $directory = Split-Path -Parent $ConfiguredPath
  $stem = [System.IO.Path]::GetFileNameWithoutExtension($ConfiguredPath)
  $pattern = "$stem*.etl"
  return @(Get-ChildItem -Path $directory -Filter $pattern -File -ErrorAction SilentlyContinue | Sort-Object Name | ForEach-Object { $_.FullName })
}

function Start-Capture {
  if (-not (Test-IsAdmin)) {
    throw 'capture start requires an elevated PowerShell session'
  }

  $existing = Load-Session
  if ($existing) {
    throw "capture session '$SessionName' is already active at $($existing.capture_dir)"
  }

  Ensure-Directory $OutputRoot
  $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $captureDir = Join-Path $OutputRoot "$timestamp-$SessionName"
  Ensure-Directory $captureDir

  $preState = Get-RazerSnapshot
  $preState | ConvertTo-Json -Depth 8 | Set-Content -Path (Join-Path $captureDir 'pre-state.json') -Encoding UTF8

  $quiesceState = $null
  if ($QuiesceProjectProcesses) {
    $quiesceState = Stop-ProjectTraffic
    $quiesceState | ConvertTo-Json -Depth 8 | Set-Content -Path (Join-Path $captureDir 'quiesce-state.json') -Encoding UTF8
    Start-Sleep -Seconds 2
  }

  $etlPath = Join-Path $captureDir 'razer-hid.etl'
  $readmePath = Join-Path $captureDir 'README.txt'
  @"
Razer HID capture started: $(Get-Date -Format o)

Next steps:
1. Open Razer Synapse.
2. Change the keyboard to the target effect, for example:
   - static white
   - off
   - breathing/reactive if needed for comparison
3. Wait a few seconds after each change.
4. Run:
   .\capture_razer_hid_trace.ps1 stop

Outputs:
- razer-hid.etl
- razer-hid.txt
- pre-state.json
- post-state.json
"@ | Set-Content -Path $readmePath -Encoding UTF8

  $args = @('start', '--trace')
  foreach ($provider in $providers) {
    $args += @('--provider', $provider)
  }
  $args += @('--file-name', $etlPath, '--file-size', '256', '--log-mode', 'memory')

  Stop-PktMonQuiet
  Invoke-PktMon -Arguments $args *> $null

  $session = @{
    session_name = $SessionName
    capture_dir = $captureDir
    etl_path = $etlPath
    started_at = (Get-Date).ToString('o')
    providers = $providers
    quiesce_project_processes = [bool]$QuiesceProjectProcesses
    quiesce_state = $quiesceState
  }
  Save-Session $session

  Write-Output "Started capture: $captureDir"
}

function Stop-Capture {
  if (-not (Test-IsAdmin)) {
    throw 'capture stop requires an elevated PowerShell session'
  }

  $session = Load-Session
  if (-not $session) {
    throw "no active capture session named '$SessionName'"
  }

  $defaultPktMonPath = Join-Path $session.capture_dir 'PktMon.etl'
  if (Test-Path $defaultPktMonPath) {
    Remove-Item $defaultPktMonPath -Force
  }

  Push-Location $session.capture_dir
  try {
    Stop-PktMonQuiet
  } finally {
    Pop-Location
  }

  if ((-not (Test-Path $session.etl_path)) -and (Test-Path $defaultPktMonPath)) {
    Move-Item -Path $defaultPktMonPath -Destination $session.etl_path -Force
  }

  $postState = Get-RazerSnapshot
  $postState | ConvertTo-Json -Depth 8 | Set-Content -Path (Join-Path $session.capture_dir 'post-state.json') -Encoding UTF8

  $txtPath = Join-Path $session.capture_dir 'razer-hid.txt'
  $etlFiles = @(Resolve-EtlFiles $session.etl_path)
  if ($etlFiles.Count -eq 0) {
    throw "pktmon completed, but no ETL file was found under $($session.capture_dir)"
  }

  $primaryEtl = $etlFiles[0]
  Invoke-PktMon -Arguments @('etl2txt', $primaryEtl, '--out', $txtPath) *> $null

  if ($session.quiesce_project_processes) {
    Restore-ProjectTraffic $session.quiesce_state
  }

  Write-Output "Stopped capture: $($session.capture_dir)"
  Write-Output "ETL file: $primaryEtl"
  Write-Output "Trace text: $txtPath"
  Remove-Session
}

function Show-Status {
  $session = Load-Session
  if (-not $session) {
    Write-Output 'No active capture session.'
    return
  }
  $session | ConvertTo-Json -Depth 8
}

switch ($Action) {
  'start' { Start-Capture }
  'stop' { Stop-Capture }
  'status' { Show-Status }
}
