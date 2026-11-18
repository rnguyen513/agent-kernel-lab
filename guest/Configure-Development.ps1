$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ine '@@DEV@@') { throw 'Run only in @@DEV@@.' }
$ewdk = Get-PSDrive -PSProvider FileSystem | Where-Object { (Test-Path ($_.Name + ':\BuildEnv\SetupBuildEnv.cmd')) } | Select-Object -First 1
if (!$ewdk) { throw 'Attach the EWDK ISO first.' }
$root = $ewdk.Name + ':'
New-Item -ItemType Directory -Force C:\Lab,C:\Symbols,C:\Lab\Symbols,C:\Tools\Debuggers | Out-Null
Copy-Item "$root\Program Files\Windows Kits\10\Debuggers\x64" C:\Tools\Debuggers -Recurse -Force
$kd = 'C:\Tools\Debuggers\x64\kd.exe'
$signature = Get-AuthenticodeSignature $kd
if ($signature.Status -ne 'Valid') { throw "Debugger signature verification failed: $($signature.Status)" }
[Environment]::SetEnvironmentVariable('_NT_SYMBOL_PATH','srv*C:\Symbols*https://msdl.microsoft.com/download/symbols;C:\Lab\Symbols','Machine')
$build = "@echo off`r`ncall `"$root\BuildEnv\SetupBuildEnv.cmd`" amd64`r`nif errorlevel 1 exit /b %errorlevel%`r`nmsbuild %*`r`n"
Set-Content C:\Lab\Build-Driver.cmd $build -Encoding ascii
Set-Content C:\Lab\Start-KernelDebugger.cmd '@powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Lab\Start-KernelDebugger.ps1' -Encoding ascii
& cmd.exe /d /c "call `"$root\BuildEnv\SetupBuildEnv.cmd`" amd64 && msbuild -version" | Tee-Object C:\Lab\build-tools-version.txt
if ($LASTEXITCODE) { throw 'Build environment validation failed.' }
[ordered]@{EwdkDrive=$root;DebuggerVersion=(Get-Item $kd).VersionInfo.FileVersion;DebuggerSignature=$signature.Status.ToString();EwdkSetup=@(Get-Content "$root\BuildEnv\SetupBuildEnv.cmd" | Select-String 'set "BuildLab=' | ForEach-Object { $_.Line })} | ConvertTo-Json | Set-Content C:\Lab\development-tools.json
Get-Content C:\Lab\development-tools.json
