$ErrorActionPreference = 'Continue'

$runPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$runValue = '"C:\Program Files\Razer\RazerAppEngine\RazerAppEngine.exe" --url-params=apps=synapse --launch-force-hidden=synapse --autoStart=1'

Set-Service -Name 'Razer Game Manager Service 3' -StartupType Automatic
Start-Service -Name 'Razer Game Manager Service 3'
New-ItemProperty -Path $runPath -Name 'RazerAppEngine' -PropertyType String -Value $runValue -Force | Out-Null

Write-Output 'Synapse runtime re-enabled.'
