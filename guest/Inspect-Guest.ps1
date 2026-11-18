$ErrorActionPreference = 'Stop'
$os = Get-CimInstance Win32_OperatingSystem
$version = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
$boot = & bcdedit /enum '{current}'
$activation = Get-CimInstance SoftwareLicensingProduct | Where-Object { $_.ApplicationID -eq '55c92734-d682-4d71-983e-d6ec3f16059f' -and $_.PartialProductKey } | Select-Object Name,LicenseStatus
$result = [ordered]@{
 ComputerName=$env:COMPUTERNAME; Caption=$os.Caption; Version=$os.Version; Build=$os.BuildNumber; UBR=$version.UBR
 LastBoot=$os.LastBootUpTime.ToString('o'); SystemDrive=$os.SystemDrive; WindowsDirectory=$os.WindowsDirectory
 SetupState=(Get-ItemProperty 'HKLM:\SYSTEM\Setup').SystemSetupInProgress
 BootstrapReady=(Test-Path C:\Lab\bootstrap-ready.txt)
 SSH=(Get-Service sshd).Status.ToString(); SecureBoot=(Confirm-SecureBootUEFI)
 TPM=(Get-Tpm | Select-Object TpmPresent,TpmReady)
 BitLocker=(Get-BitLockerVolume -MountPoint C: | Select-Object VolumeStatus,ProtectionStatus,EncryptionPercentage,@{n="ProtectorTypes";e={@($_.KeyProtector.KeyProtectorType)}})
 CPU=(Get-CimInstance Win32_ComputerSystem | Select-Object NumberOfProcessors,NumberOfLogicalProcessors)
 SerialPorts=@(Get-CimInstance Win32_SerialPort | Select-Object DeviceID,Name)
 Activation=@($activation)
 BootConfiguration=@($boot)
 DeviceGuard=(Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard | Select-Object VirtualizationBasedSecurityStatus,SecurityServicesRunning)
 Disk=(Get-Volume -DriveLetter C | Select-Object Size,SizeRemaining,FileSystem)
}
$result | ConvertTo-Json -Depth 5
