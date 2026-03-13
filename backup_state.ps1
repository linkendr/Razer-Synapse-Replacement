$ErrorActionPreference = 'Continue'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backup = Join-Path $root 'backup'
$null = New-Item -ItemType Directory -Force -Path $backup
$null = New-Item -ItemType Directory -Force -Path (Join-Path $backup 'drivers')
$null = New-Item -ItemType Directory -Force -Path (Join-Path $backup 'registry')
$null = New-Item -ItemType Directory -Force -Path (Join-Path $backup 'system')
$null = New-Item -ItemType Directory -Force -Path (Join-Path $backup 'pnputil')

Get-CimInstance Win32_ComputerSystem | Format-List * | Out-File (Join-Path $backup 'system\computer_system.txt') -Encoding utf8
Get-CimInstance Win32_BIOS | Format-List * | Out-File (Join-Path $backup 'system\bios.txt') -Encoding utf8
Get-CimInstance Win32_BaseBoard | Format-List * | Out-File (Join-Path $backup 'system\baseboard.txt') -Encoding utf8
Get-CimInstance Win32_PnPEntity |
  Where-Object { $_.PNPDeviceID -like '*VID_1532*' -or $_.Name -like '*Razer*' } |
  Sort-Object Name |
  Format-List * |
  Out-File (Join-Path $backup 'system\razer_pnp_entities.txt') -Encoding utf8

Get-CimInstance Win32_PnPSignedDriver |
  Where-Object { $_.DeviceID -like '*VID_1532*' -or $_.DeviceName -like '*Razer*' -or $_.DriverProviderName -like '*Razer*' } |
  Sort-Object DeviceName |
  Format-List * |
  Out-File (Join-Path $backup 'system\razer_signed_drivers.txt') -Encoding utf8

Get-Process |
  Where-Object { $_.ProcessName -like '*Razer*' -or $_.ProcessName -like '*Synapse*' } |
  Sort-Object ProcessName |
  Format-List * |
  Out-File (Join-Path $backup 'system\razer_processes.txt') -Encoding utf8

Get-Service |
  Where-Object { $_.Name -like '*Razer*' -or $_.DisplayName -like '*Razer*' } |
  Sort-Object Name |
  Format-List * |
  Out-File (Join-Path $backup 'system\razer_services.txt') -Encoding utf8

Get-CimInstance Win32_StartupCommand |
  Where-Object { $_.Command -like '*Razer*' -or $_.Name -like '*Razer*' } |
  Sort-Object Name |
  Format-List * |
  Out-File (Join-Path $backup 'system\razer_startup.txt') -Encoding utf8

Get-ScheduledTask |
  Where-Object { $_.TaskName -like '*Razer*' -or $_.TaskPath -like '*Razer*' } |
  Sort-Object TaskPath, TaskName |
  Format-List * |
  Out-File (Join-Path $backup 'system\razer_scheduled_tasks.txt') -Encoding utf8

Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
  Where-Object { $_.DisplayName -like '*Razer*' -or $_.Publisher -like '*Razer*' } |
  Sort-Object DisplayName |
  Format-List * |
  Out-File (Join-Path $backup 'system\razer_installed_apps.txt') -Encoding utf8

pnputil /enum-drivers | Out-File (Join-Path $backup 'pnputil\enum_drivers.txt') -Encoding utf8
pnputil /enum-devices /connected | Out-File (Join-Path $backup 'pnputil\enum_devices_connected.txt') -Encoding utf8

$driverInfs = Get-CimInstance Win32_PnPSignedDriver |
  Where-Object { $_.DeviceID -like '*VID_1532*' -or $_.DeviceName -like '*Razer*' -or $_.DriverProviderName -like '*Razer*' } |
  Select-Object -ExpandProperty InfName -Unique |
  Where-Object { $_ }

$driverInfs | Sort-Object | Out-File (Join-Path $backup 'drivers\related_inf_names.txt') -Encoding utf8

foreach ($inf in $driverInfs) {
  pnputil /export-driver $inf (Join-Path $backup 'drivers') | Out-File -Append (Join-Path $backup 'drivers\export_log.txt') -Encoding utf8
}

$regTargets = @(
  @{ Path = 'HKLM\SOFTWARE\Razer'; File = 'HKLM_SOFTWARE_Razer.reg' },
  @{ Path = 'HKCU\SOFTWARE\Razer'; File = 'HKCU_SOFTWARE_Razer.reg' },
  @{ Path = 'HKLM\SYSTEM\CurrentControlSet\Services\Razer Game Manager Service'; File = 'HKLM_SYSTEM_CCS_Services_Razer_Game_Manager_Service.reg' },
  @{ Path = 'HKLM\SYSTEM\CurrentControlSet\Services\RzActionSvc'; File = 'HKLM_SYSTEM_CCS_Services_RzActionSvc.reg' },
  @{ Path = 'HKLM\SYSTEM\CurrentControlSet\Services\rzdev_0062'; File = 'HKLM_SYSTEM_CCS_Services_rzdev_0062.reg' },
  @{ Path = 'HKLM\SYSTEM\CurrentControlSet\Services\rzdev_0063'; File = 'HKLM_SYSTEM_CCS_Services_rzdev_0063.reg' },
  @{ Path = 'HKLM\SYSTEM\CurrentControlSet\Services\Razer Central Service'; File = 'HKLM_SYSTEM_CCS_Services_Razer_Central_Service.reg' }
)

foreach ($target in $regTargets) {
  $outFile = Join-Path $backup ('registry\' + $target.File)
  reg export $target.Path $outFile /y > $null 2>&1
}

Get-ChildItem -Recurse $backup |
  Select-Object FullName, Length, LastWriteTime |
  Sort-Object FullName |
  Format-Table -AutoSize |
  Out-File (Join-Path $backup 'backup_manifest.txt') -Encoding utf8

Write-Output "Backup complete: $backup"
