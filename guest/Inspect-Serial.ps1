$ErrorActionPreference='Stop'
Get-Process kd,windbg,cdb -ErrorAction SilentlyContinue | Select-Object Name,Id
Get-CimInstance Win32_SerialPort | Select-Object DeviceID,PNPDeviceID,Status | ConvertTo-Json
Get-CimInstance Win32_PnPEntity -Filter "PNPClass='Mouse'" | Select-Object Name,PNPDeviceID,Service,Status | ConvertTo-Json
& bcdedit.exe /enum '{current}'
