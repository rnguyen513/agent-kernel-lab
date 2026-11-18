param([string]$OutputDirectory = "$env:USERPROFILE\Desktop\LabEvidence")
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $OutputDirectory | Out-Null
Get-ComputerInfo | Out-File "$OutputDirectory\computer.txt"
Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard |
    ConvertTo-Json | Set-Content "$OutputDirectory\deviceguard.json"
& bcdedit /enum | Out-File "$OutputDirectory\boot.txt"
& driverquery /v /fo csv | Out-File "$OutputDirectory\drivers.csv"
Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\CrashControl' |
    ConvertTo-Json | Set-Content "$OutputDirectory\crash-config.json"
Write-Host "Saved evidence to $OutputDirectory. Also retain driver/PDB hashes and source commit."
