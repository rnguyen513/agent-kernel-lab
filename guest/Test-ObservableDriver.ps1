$ErrorActionPreference='Stop'
if ($env:COMPUTERNAME -ine '@@TARGET@@') { throw 'Target VM only.' }
$driver=Get-CimInstance Win32_SystemDriver -Filter "Name='ECHO'"
if ($driver.State -ne 'Running') { throw 'Echo driver is not running.' }
$loadedPath=$driver.PathName.Trim('"')
$packageHash=(Get-FileHash C:\Lab\SignedEcho\echo.sys -Algorithm SHA256).Hash
$installedHash=(Get-FileHash $loadedPath -Algorithm SHA256).Hash
if ($packageHash -ne $installedHash) { throw 'Installed driver file differs from the deployed package.' }
[ordered]@{ComputerName=$env:COMPUTERNAME;InstalledDriver=$loadedPath;PackageSHA256=$packageHash;InstalledSHA256=$installedHash;ApplicationSHA256=(Get-FileHash C:\Lab\SignedEcho\echoapp.exe).Hash} | ConvertTo-Json
& C:\Lab\SignedEcho\echoapp.exe -Probe | Tee-Object C:\Lab\observable-probe.log
if ($LASTEXITCODE) { throw "Custom IOCTL probe failed: $LASTEXITCODE" }
