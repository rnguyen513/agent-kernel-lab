$ErrorActionPreference='Stop'
if ($env:COMPUTERNAME -notin @('@@DEV_UPPER@@','@@TARGET_UPPER@@')) { throw 'Lab guests only.' }
$rule=Get-NetFirewallRule -Name LabSSH
$addresses=$rule | Get-NetFirewallAddressFilter
$config=Get-Content C:\ProgramData\ssh\sshd_config
$winlogon=Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
[ordered]@{
 ComputerName=$env:COMPUTERNAME
 SSHService=(Get-CimInstance Win32_Service -Filter "Name='sshd'" | Select-Object State,StartMode,PathName)
 PasswordAuthenticationDisabled=([bool]($config -match '^PasswordAuthentication no$'))
 SSHFirewall=($rule | Select-Object Enabled,Direction,Action)
 SSHRemoteAddresses=@($addresses.RemoteAddress)
 AutomaticLogon=$winlogon.AutoAdminLogon
 StoredLogonPasswordPresent=([bool]$winlogon.DefaultPassword)
} | ConvertTo-Json -Depth 4
