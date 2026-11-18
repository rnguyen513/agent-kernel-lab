#Requires -RunAsAdministrator
[CmdletBinding()]
param([string]$Log='C:\Lab\kernel-debugger.log',[switch]$OnlineSymbols)
$ErrorActionPreference='Stop'
if ($env:COMPUTERNAME -ine '@@DEV@@') { throw 'Development VM only.' }
if (Get-Process kd,windbg,cdb -ErrorAction SilentlyContinue) { throw 'A debugger is already running; reconnect to that session or exit it first.' }
function Test-DebugPort {
 $port=New-Object System.IO.Ports.SerialPort -ArgumentList 'COM1',115200
 try { $port.Open() } finally { $port.Dispose() }
}
try { Test-DebugPort } catch {
 Write-Output 'COM1 is unavailable; checking and restarting only the lab debug serial device.'
 & C:\Lab\Restart-DebugPort.ps1
 Test-DebugPort
}
$symbols='srv*C:\Symbols;C:\Lab\Symbols'
if ($OnlineSymbols) { $symbols='srv*C:\Symbols*https://msdl.microsoft.com/download/symbols;C:\Lab\Symbols' }
$env:_NT_SYMBOL_PATH=$symbols
$env:_NT_ALT_SYMBOL_PATH=''
& C:\Tools\Debuggers\x64\kd.exe -b -k com:port=COM1,baud=115200 -y $symbols -logo $Log
