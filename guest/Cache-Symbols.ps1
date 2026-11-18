$ErrorActionPreference='Stop'
if ($env:COMPUTERNAME -ine '@@DEV@@') { throw 'Development VM only.' }
$symchk='C:\Tools\Debuggers\x64\symchk.exe'
foreach ($file in @('C:\Windows\System32\ntoskrnl.exe','C:\Windows\System32\hal.dll','C:\Windows\System32\drivers\Wdf01000.sys')) {
 & $symchk $file /s 'srv*C:\Symbols*https://msdl.microsoft.com/download/symbols' /v
 if ($LASTEXITCODE) { throw "Symbol verification failed: $file" }
}
