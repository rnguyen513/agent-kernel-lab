$ErrorActionPreference='Stop'
if ($env:COMPUTERNAME -ine '@@DEV@@') { throw 'Development VM only.' }
if (Get-Process kd,windbg,cdb -ErrorAction SilentlyContinue) { throw 'Exit the debugger before restarting COM1.' }
$port=Get-CimInstance Win32_SerialPort -Filter "DeviceID='COM1'"
if ($port.PNPDeviceID -ne 'ACPI\PNP0501\1') { throw 'Unexpected debug serial device; no change made.' }
& pnputil.exe /restart-device $port.PNPDeviceID
if ($LASTEXITCODE -ne 0) { throw "Port restart returned $LASTEXITCODE; inspect before retrying the debugger." }
