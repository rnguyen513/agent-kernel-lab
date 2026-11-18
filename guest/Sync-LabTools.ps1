$ErrorActionPreference='Stop'
if ($env:COMPUTERNAME -notin @('@@DEV@@','@@TARGET@@')) { throw 'Lab guests only.' }
Get-ChildItem C:\Lab -Filter '*.ps1' -File | ForEach-Object { $_.IsReadOnly=$false }
Expand-Archive C:\Lab\guest-tools.zip C:\Lab -Force
Get-ChildItem C:\Lab -Filter '*.ps1' -File | ForEach-Object { $_.IsReadOnly=$false }
if ($env:COMPUTERNAME -ieq '@@DEV@@') {
 Set-Content C:\Lab\Start-KernelDebugger.cmd '@powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Lab\Start-KernelDebugger.ps1' -Encoding ascii
}
Get-ChildItem C:\Lab -Filter '*.ps1' -File | Get-FileHash | Select-Object Path,Hash | ConvertTo-Json | Set-Content C:\Lab\guest-tool-hashes.json
'Guest helper scripts synchronized.'
