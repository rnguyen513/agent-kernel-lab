# Run after saving a working cold baseline. Applies only to the Echo sample.
#Requires -RunAsAdministrator
param([ValidateSet('Enable','Status','Disable')][string]$Action='Status')
$ErrorActionPreference='Stop'
if ($env:COMPUTERNAME -ine '@@TARGET@@') { throw 'Target VM only.' }
switch ($Action) {
 'Enable' {
  & verifier.exe /standard /driver echo.sys
  # Verifier returns 2 for success that requires a reboot.
  if ($LASTEXITCODE -notin @(0,2)) { throw 'Verifier configuration failed.' }
  & verifier.exe /bootmode oneboot
  if ($LASTEXITCODE -notin @(0,2)) {
   & verifier.exe /reset
   throw 'Could not limit Verifier to one boot; pending settings were reset.'
  }
  'Reboot target, run echoapp.exe, then collect verifier /query output.'
 }
 'Status' { & verifier.exe /querysettings; & verifier.exe /query }
 'Disable' {
  & verifier.exe /reset
  if ($LASTEXITCODE -notin @(0,2)) { throw 'Verifier reset failed.' }
  'Reboot target to finish disabling Verifier.'
 }
}
