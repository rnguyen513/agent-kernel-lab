$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ine '@@DEV@@') { throw 'Run only in the development VM.' }
# These fixed staging directories belong exclusively to this serialized profile.
foreach ($stale in @('C:\Lab\Samples\kmdf','C:\Lab\Build')) { if (Test-Path $stale) { Remove-Item $stale -Recurse -Force } }
New-Item -ItemType Directory -Force C:\Lab\Samples,C:\Lab\Build,C:\Lab\Symbols | Out-Null
Expand-Archive C:\Lab\kmdf-echo-source.zip C:\Lab\Samples -Force
$project='C:\Lab\Samples\kmdf\driver\AutoSync\echo.vcxproj'
& cmd.exe /d /c "C:\Lab\Build-Driver.cmd $project /t:Rebuild /p:Configuration=Debug /p:Platform=x64 /p:SignMode=Off /p:KMDF_VERSION_MINOR=33 /p:OutDir=C:\Lab\Build\driver\ /p:IntDir=C:\Lab\Build\obj\ /v:minimal" | Tee-Object C:\Lab\driver-build.log
if ($LASTEXITCODE) { throw "Driver build failed: $LASTEXITCODE" }
$project='C:\Lab\Samples\kmdf\exe\echoapp.vcxproj'
& cmd.exe /d /c "C:\Lab\Build-Driver.cmd $project /t:Rebuild /p:Configuration=Debug /p:Platform=x64 /p:OutDir=C:\Lab\Build\app\ /p:IntDir=C:\Lab\Build\app-obj\ /v:minimal" | Tee-Object C:\Lab\app-build.log
if ($LASTEXITCODE) { throw "Sample application build failed: $LASTEXITCODE" }
Get-ChildItem C:\Lab\Build -Recurse -Filter *.pdb | Copy-Item -Destination C:\Lab\Symbols -Force
Get-ChildItem C:\Lab\Build -Recurse -File | Where-Object Extension -in '.sys','.pdb','.inf','.exe' | Get-FileHash | Select-Object Path,Hash | ConvertTo-Json | Set-Content C:\Lab\sample-build-hashes.json
Get-Content C:\Lab\sample-build-hashes.json
