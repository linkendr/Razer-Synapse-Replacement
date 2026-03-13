param(
  [Parameter(Mandatory = $true, Position = 0)]
  [ValidateSet('start', 'stop', 'status', 'mark')]
  [string]$Action,

  [string]$OutputRoot = 'C:\Razer Synapse Replacement\captures\usbpcap',

  [string]$SessionName = 'RazerUsbPcap',

  [int[]]$DeviceIndices = @(1, 2),

  [string]$Label,

  [switch]$QuiesceProjectProcesses
)

$ErrorActionPreference = 'Stop'
$usbPcapExe = 'C:\Program Files\USBPcap\USBPcapCMD.exe'
$tsharkExe = 'C:\Program Files\Wireshark\tshark.exe'

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

function Ensure-Directory([string]$Path) {
  if (-not (Test-Path $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function Get-SessionPaths {
  $stateDir = Join-Path $OutputRoot '.state'
  $sessionFile = Join-Path $stateDir "$SessionName.json"
  return @{
    StateDir = $stateDir
    SessionFile = $sessionFile
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

function Stop-ProjectTraffic {
  $stoppedTasks = @()
  foreach ($taskName in $projectTaskNames) {
    try {
      $info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction Stop
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

function Restore-ProjectTraffic([object]$State) {
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

function Invoke-UsbPcapInit {
  if (-not (Test-Path $usbPcapExe)) {
    throw "USBPcap executable not found at $usbPcapExe"
  }
  & $usbPcapExe -I *> $null
}

function Get-UsbPcapCmdProcesses {
  @(Get-CimInstance Win32_Process -Filter "name = 'USBPcapCMD.exe'" -ErrorAction SilentlyContinue)
}

function Add-Marker([string]$CaptureDir, [string]$MarkerLabel) {
  $markerPath = Join-Path $CaptureDir 'markers.jsonl'
  $marker = @{
    timestamp = (Get-Date).ToString('o')
    label = $MarkerLabel
  } | ConvertTo-Json -Compress
  Add-Content -Path $markerPath -Value $marker
}

function Get-RazerDeviceAddresses([string]$PcapPath) {
  if (-not (Test-Path $tsharkExe)) {
    return @()
  }

  $lines = @(& $tsharkExe -r $PcapPath -Y 'usb.idVendor == 0x1532' -T fields -e usb.device_address 2>$null)
  @($lines | Where-Object { $_ } | Sort-Object -Unique)
}

function Export-RazerSummaries([string]$CaptureDir) {
  if (-not (Test-Path $tsharkExe)) {
    return
  }

  foreach ($pcap in @(Get-ChildItem -Path $CaptureDir -Filter '*.pcap' -File -ErrorAction SilentlyContinue)) {
    $addresses = @(Get-RazerDeviceAddresses -PcapPath $pcap.FullName)
    if ($addresses.Count -eq 0) {
      continue
    }

    $addresses | Set-Content -Path (Join-Path $CaptureDir ("{0}.razer-addresses.txt" -f $pcap.BaseName)) -Encoding ASCII

    $filters = @($addresses | ForEach-Object { "usb.device_address == $_" })
    $displayFilter = "({0}) && usb.setup.wLength == 90 && usb.data_fragment" -f ($filters -join ' || ')

    & $tsharkExe -r $pcap.FullName -Y $displayFilter -T fields `
      -e frame.number -e frame.time_relative -e usb.setup.bRequest -e usb.setup.wValue -e usb.setup.wIndex -e usb.setup.wLength -e usb.data_fragment `
      2>$null | Set-Content -Path (Join-Path $CaptureDir ("{0}.razer-wlen90.txt" -f $pcap.BaseName)) -Encoding ASCII
  }
}

function Start-OneDeviceCapture([string]$CaptureDir, [int]$Index) {
  $device = "\\.\USBPcap$Index"
  $pcapPath = Join-Path $CaptureDir ("usbpcap-{0}.pcap" -f $Index)
  $hostPath = Join-Path $CaptureDir ("usbpcap-{0}.host.ps1" -f $Index)
  $beforeIds = @(Get-UsbPcapCmdProcesses | ForEach-Object { $_.ProcessId })
  $hostCommand = "& '$usbPcapExe' -d '$device' -o '$pcapPath' -A --inject-descriptors"

  foreach ($path in @($pcapPath, $hostPath)) {
    if (Test-Path $path) {
      Remove-Item $path -Force
    }
  }

  $hostCommand | Set-Content -Path $hostPath -Encoding UTF8

  $helperProcess = Start-Process `
    -FilePath 'powershell.exe' `
    -ArgumentList @('-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $hostCommand) `
    -PassThru `
    -WindowStyle Minimized

  Start-Sleep -Seconds 4

  $captureProcess = Get-UsbPcapCmdProcesses |
    Where-Object {
      $_.CommandLine -and $_.CommandLine -like "*$pcapPath*" -and $beforeIds -notcontains $_.ProcessId
    } |
    Select-Object -First 1

  if (-not $captureProcess) {
    return [pscustomobject]@{
      device = $device
      opened = $false
      pid = $null
      exit_code = $null
      pcap_path = $pcapPath
      host_pid = $helperProcess.Id
      host_path = $hostPath
    }
  }

  return [pscustomobject]@{
    device = $device
    opened = $true
    pid = $captureProcess.ProcessId
    exit_code = $null
    pcap_path = $pcapPath
    host_pid = $helperProcess.Id
    host_path = $hostPath
  }
}

function Start-Capture {
  if (-not (Test-IsAdmin)) {
    throw 'USBPcap capture requires an elevated PowerShell session'
  }

  if (Load-Session) {
    throw "capture session '$SessionName' is already active"
  }

  Ensure-Directory $OutputRoot
  Invoke-UsbPcapInit

  $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $captureDir = Join-Path $OutputRoot "$timestamp-$SessionName"
  Ensure-Directory $captureDir

  $quiesceState = $null
  if ($QuiesceProjectProcesses) {
    $quiesceState = Stop-ProjectTraffic
    $quiesceState | ConvertTo-Json -Depth 8 | Set-Content -Path (Join-Path $captureDir 'quiesce-state.json') -Encoding UTF8
    Start-Sleep -Seconds 2
  }

  $results = @()
  foreach ($index in $DeviceIndices) {
    $results += Start-OneDeviceCapture -CaptureDir $captureDir -Index $index
  }

  $active = @($results | Where-Object { $_.opened })
  if ($active.Count -eq 0) {
    $allMissingDevices = @($results | Where-Object { $_.opened -eq $false -and $_.exit_code -eq 0 })
    $errorHint = 'USBPcap did not open any capture devices. If USBPcap was just installed, reboot Windows once so the filter driver can attach and expose \\.\USBPcapN capture devices.'
    throw $errorHint
  }

  $session = @{
    session_name = $SessionName
    capture_dir = $captureDir
    started_at = (Get-Date).ToString('o')
    active_devices = $active
    probe_results = $results
    quiesce_state = $quiesceState
  }
  Save-Session $session

  @"
USBPcap capture started: $(Get-Date -Format o)

Capture directory:
$captureDir

Active devices:
$((@($active | ForEach-Object { $_.device }) -join [Environment]::NewLine))

Next steps:
1. Change the target lighting state in Synapse.
2. Optionally mark the action:
   .\capture_razer_usbpcap.ps1 mark -Label "brightness off"
3. Stop the capture:
   .\capture_razer_usbpcap.ps1 stop

Outputs on stop:
- capture-files.json
- *.razer-addresses.txt
- *.razer-wlen90.txt
"@ | Set-Content -Path (Join-Path $captureDir 'README.txt') -Encoding UTF8

  Add-Marker -CaptureDir $captureDir -MarkerLabel 'capture-started'

  Write-Output "Started USBPcap capture: $captureDir"
  Write-Output ("Active devices: {0}" -f (@($active | ForEach-Object { $_.device }) -join ', '))
}

function Stop-Capture {
  if (-not (Test-IsAdmin)) {
    throw 'USBPcap capture stop requires an elevated PowerShell session'
  }

  $session = Load-Session
  if (-not $session) {
    throw "no active capture session named '$SessionName'"
  }

  foreach ($item in @($session.active_devices)) {
    try {
      Stop-Process -Id $item.pid -Force -ErrorAction Stop
    } catch {
      Write-Warning ("Failed to stop USBPcap process {0} for {1}: {2}" -f $item.pid, $item.device, $_)
    }
    if ($item.host_pid) {
      try {
        Stop-Process -Id $item.host_pid -Force -ErrorAction Stop
      } catch {
        Write-Warning ("Failed to stop helper PowerShell process {0} for {1}: {2}" -f $item.host_pid, $item.device, $_)
      }
    }
  }

  Start-Sleep -Seconds 2
  Add-Marker -CaptureDir $session.capture_dir -MarkerLabel 'capture-stopped'

  Export-RazerSummaries -CaptureDir $session.capture_dir

  $files = Get-ChildItem $session.capture_dir | Select-Object Name, Length, LastWriteTime
  $files | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $session.capture_dir 'capture-files.json') -Encoding UTF8

  Restore-ProjectTraffic -State $session.quiesce_state

  Write-Output "Stopped USBPcap capture: $($session.capture_dir)"
  Remove-Session
}

function Add-CaptureMarker {
  $session = Load-Session
  if (-not $session) {
    throw "no active capture session named '$SessionName'"
  }

  $markerLabel = if ([string]::IsNullOrWhiteSpace($Label)) { 'manual-mark' } else { $Label }
  Add-Marker -CaptureDir $session.capture_dir -MarkerLabel $markerLabel
  Write-Output ("Added marker '{0}' to {1}" -f $markerLabel, $session.capture_dir)
}

function Show-Status {
  $session = Load-Session
  if (-not $session) {
    Write-Output 'No active USBPcap capture session.'
    return
  }
  $session | ConvertTo-Json -Depth 8
}

switch ($Action) {
  'start' { Start-Capture }
  'stop' { Stop-Capture }
  'mark' { Add-CaptureMarker }
  'status' { Show-Status }
}
