$ErrorActionPreference='Stop'
if ($env:COMPUTERNAME -ine '@@DEV@@') { throw 'Development VM only.' }
$ewdk=Get-PSDrive -PSProvider FileSystem | Where-Object { (Test-Path ($_.Name+':\BuildEnv\SetupBuildEnv.cmd')) } | Select-Object -First 1
$kit=$ewdk.Name+':\Program Files\Windows Kits\10'
$sign=(Get-ChildItem "$kit\bin\*\x64\signtool.exe" | Sort-Object FullName -Descending | Select-Object -First 1).FullName
$inf2cat=(Get-ChildItem "$kit\bin\*\x86\Inf2Cat.exe" | Sort-Object FullName -Descending | Select-Object -First 1).FullName
$devcon=(Get-ChildItem "$kit\Tools\*\x64\devcon.exe" | Sort-Object FullName -Descending | Select-Object -First 1).FullName
if (!$sign -or !$inf2cat -or !$devcon) { throw 'Required WDK signing/deployment tool missing.' }
$cert=Get-ChildItem Cert:\LocalMachine\My | Where-Object Subject -eq 'CN=WKL Development Test Only' | Where-Object HasPrivateKey | Select-Object -First 1
if (!$cert) { $cert=New-SelfSignedCertificate -Type CodeSigningCert -Subject 'CN=WKL Development Test Only' -CertStoreLocation Cert:\LocalMachine\My -KeyAlgorithm RSA -KeyLength 3072 -HashAlgorithm SHA256 -KeyExportPolicy NonExportable -NotAfter (Get-Date).AddYears(2) }
if (Test-Path C:\Lab\SignedEcho) { Remove-Item C:\Lab\SignedEcho -Recurse -Force }
$package='C:\Lab\SignedEcho'
New-Item -ItemType Directory -Force $package | Out-Null
$inf=Get-ChildItem C:\Lab\Build\driver -Recurse -Filter echo.inf | Select-Object -First 1
$sys=Get-ChildItem C:\Lab\Build\driver -Recurse -Filter echo.sys | Select-Object -First 1
if (!$inf -or !$sys) { throw 'Build Echo first.' }
Copy-Item $inf.FullName,$sys.FullName $package -Force
Export-Certificate -Cert $cert -FilePath "$package\WKL-Test.cer" | Out-Null
& certutil.exe -addstore -f Root "$package\WKL-Test.cer"
if ($LASTEXITCODE) { throw "Test certificate import into Root failed." }
& certutil.exe -addstore -f TrustedPublisher "$package\WKL-Test.cer"
if ($LASTEXITCODE) { throw "Test certificate import into TrustedPublisher failed." }
& $sign sign /v /fd SHA256 /sm /s My /sha1 $cert.Thumbprint "$package\echo.sys"
if ($LASTEXITCODE) { throw 'SYS signing failed.' }
& $inf2cat "/driver:$package" /os:10_X64 /uselocaltime
if ($LASTEXITCODE) { throw 'Catalog generation failed.' }
Get-ChildItem $package -Filter *.cat | ForEach-Object {
    & $sign sign /v /fd SHA256 /sm /s My /sha1 $cert.Thumbprint $_.FullName
    if ($LASTEXITCODE) { throw 'Catalog signing failed.' }
    & $sign verify /pa /v $_.FullName
    if ($LASTEXITCODE) { throw 'Catalog verification failed.' }
}
Copy-Item $devcon "$package\devcon.exe" -Force
Copy-Item (Get-ChildItem C:\Lab\Build\app -Recurse -Filter echoapp.exe | Select-Object -First 1).FullName $package -Force
Compress-Archive "$package\*" C:\Lab\SignedEcho.zip -Force
Get-ChildItem $package -File | Get-FileHash | Select-Object Path,Hash | ConvertTo-Json | Set-Content C:\Lab\signed-package-hashes.json
Get-Content C:\Lab\signed-package-hashes.json
