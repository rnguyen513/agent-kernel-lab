#Requires -RunAsAdministrator
[CmdletBinding()]
param([switch]$EnableTestSigning)
$ErrorActionPreference = 'Stop'
$system = Get-CimInstance Win32_ComputerSystem
if ($env:COMPUTERNAME -ine '@@TARGET@@' -or "$($system.Manufacturer) $($system.Model)" -notmatch 'QEMU|KVM') {
    throw 'Run only inside the lab target VM.'
}
if (Confirm-SecureBootUEFI) { throw 'Disable Secure Boot in target firmware after saving the clean baseline.' }
$volume = Get-BitLockerVolume -MountPoint C:
if ($volume.ProtectionStatus -eq 'On') { throw 'Save your BitLocker recovery key and suspend protection before changing boot configuration.' }
& bcdedit /debug on
if ($LASTEXITCODE) { throw 'Failed to enable debugging.' }
& bcdedit /dbgsettings serial debugport:1 baudrate:115200
if ($LASTEXITCODE) { throw 'Failed to configure COM1.' }
if ($EnableTestSigning) {
    & bcdedit /set testsigning on
    if ($LASTEXITCODE) { throw 'Failed to enable test signing.' }
}
$crash = 'HKLM:\SYSTEM\CurrentControlSet\Control\CrashControl'
Set-ItemProperty $crash CrashDumpEnabled 2
Set-ItemProperty $crash AutoReboot 0
Set-ItemProperty $crash DumpFile '%SystemRoot%\MEMORY.DMP'
$computer = Get-CimInstance Win32_ComputerSystem
Set-CimInstance $computer -Property @{AutomaticManagedPagefile=$true} | Out-Null
Write-Host 'Kernel debugging and kernel dumps configured. Reboot the target.'
