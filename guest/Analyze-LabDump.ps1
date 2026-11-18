$ErrorActionPreference='Stop'
if ($env:COMPUTERNAME -ine '@@DEV@@') { throw 'Development VM only.' }
$dump=Get-Item C:\Lab\MEMORY.DMP
$dump | Select-Object Length,LastWriteTime | ConvertTo-Json
$env:_NT_SYMBOL_PATH='srv*C:\Symbols;C:\Lab\Symbols'
$env:_NT_ALT_SYMBOL_PATH=''
& C:\Tools\Debuggers\x64\kd.exe -z $dump.FullName -y 'srv*C:\Symbols;C:\Lab\Symbols' -c '!analyze -v;q'
if ($LASTEXITCODE) { throw "Dump analysis failed: $LASTEXITCODE" }
