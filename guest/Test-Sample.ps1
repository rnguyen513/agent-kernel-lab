$ErrorActionPreference='Stop'
if ($env:COMPUTERNAME -ine '@@TARGET@@') { throw 'Target VM only.' }
$device=@(Get-CimInstance Win32_PnPEntity | Where-Object { $_.HardwareID -contains 'root\ECHO' })
if ($device.Count -ne 1 -or $device[0].ConfigManagerErrorCode -ne 0) { throw 'Expected exactly one healthy Echo device.' }
$driver=Get-CimInstance Win32_SystemDriver -Filter "Name='ECHO'"
if ($driver.State -ne 'Running') { throw 'Echo driver is not running.' }
& C:\Lab\SignedEcho\echoapp.exe | Tee-Object C:\Lab\echo-functional-test.log
if ($LASTEXITCODE) { throw "Echo I/O test failed: $LASTEXITCODE" }
[ordered]@{Device=($device | Select-Object Name,PNPDeviceID,Status,ConfigManagerErrorCode);Driver=($driver | Select-Object Name,State,PathName)} | ConvertTo-Json -Depth 4
