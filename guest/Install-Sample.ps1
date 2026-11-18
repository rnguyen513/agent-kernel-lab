$ErrorActionPreference='Stop'
if ($env:COMPUTERNAME -ine '@@TARGET@@') { throw 'Target VM only.' }
if (Test-Path C:\Lab\SignedEcho) { Remove-Item C:\Lab\SignedEcho -Recurse -Force }
Expand-Archive C:\Lab\SignedEcho.zip C:\Lab\SignedEcho -Force
Set-Location C:\Lab\SignedEcho
& certutil.exe -addstore -f Root .\WKL-Test.cer
if ($LASTEXITCODE) { throw "Test certificate import into Root failed." }
& certutil.exe -addstore -f TrustedPublisher .\WKL-Test.cer
if ($LASTEXITCODE) { throw "Test certificate import into TrustedPublisher failed." }
$existing=@(Get-CimInstance Win32_PnPEntity | Where-Object { $_.HardwareID -contains 'root\ECHO' })
if ($existing.Count -gt 1) { throw 'Multiple Echo devices exist; inspect them before deployment.' }
if ($existing.Count) { & .\devcon.exe update .\echo.inf 'root\ECHO' }
else { & .\devcon.exe install .\echo.inf 'root\ECHO' }
if ($LASTEXITCODE -eq 1) { throw 'Driver deployment requires a target reboot; reboot and run Test-Sample.ps1 before claiming success.' }
if ($LASTEXITCODE -gt 1) { throw "Driver installation failed: $LASTEXITCODE" }
& .\devcon.exe status 'root\ECHO'
& .\echoapp.exe | Tee-Object C:\Lab\echo-functional-test.log
if ($LASTEXITCODE) { throw "Echo I/O test failed: $LASTEXITCODE" }
$device=@(Get-CimInstance Win32_PnPEntity | Where-Object { $_.HardwareID -contains 'root\ECHO' })
if ($device.Count -ne 1 -or $device[0].ConfigManagerErrorCode -ne 0) { throw 'Expected exactly one healthy Echo device.' }
$device | Select-Object Name,PNPDeviceID,Status,ConfigManagerErrorCode | ConvertTo-Json
