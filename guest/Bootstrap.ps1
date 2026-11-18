$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force C:\Lab | Out-Null
Start-Transcript -Path C:\Lab\bootstrap.log -Append
try {
    $media = (Get-PSDrive -PSProvider FileSystem | Where-Object { Test-Path ($_.Root+'lab.pub') } | Select-Object -First 1).Name + ':'
    Copy-Item "$media\*.ps1" C:\Lab -Force
    Get-ChildItem C:\Lab -Filter '*.ps1' -File | ForEach-Object { $_.IsReadOnly=$false }
    if (!(Get-Service sshd -ErrorAction SilentlyContinue)) {
        $zip="$PSScriptRoot\OpenSSH-Win64.zip"
        if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne '@@OPENSSH_SHA256@@') { throw 'OpenSSH package hash mismatch.' }
        Expand-Archive $zip 'C:\Program Files' -Force
        $folder='C:\Program Files\OpenSSH-Win64'
        foreach ($file in @('sshd.exe','install-sshd.ps1')) {
            $sig=Get-AuthenticodeSignature "$folder\$file"
            if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Microsoft Corporation') { throw "Invalid Microsoft signature: $file $($sig.Status)" }
        }
        & "$folder\install-sshd.ps1"
        if (!(Get-Service sshd -ErrorAction SilentlyContinue)) { throw 'OpenSSH service installation failed.' }
        ('Microsoft-signed Win32-OpenSSH; sshd '+(Get-Item "$folder\sshd.exe").VersionInfo.FileVersion) | Set-Content C:\Lab\openssh-package.txt
    }
    New-Item -ItemType Directory -Force C:\ProgramData\ssh | Out-Null
    Copy-Item "$media\lab.pub" C:\ProgramData\ssh\administrators_authorized_keys -Force
    & icacls.exe C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r /grant '*S-1-5-32-544:F' /grant '*S-1-5-18:F' | Out-Null
    if ($LASTEXITCODE) { throw 'SSH key ACL setup failed' }
    Set-Service sshd -StartupType Automatic
    Start-Service sshd
    $config = 'C:\ProgramData\ssh\sshd_config'
    $content = Get-Content $config -Raw
    $content = "PasswordAuthentication no`r`n" + ($content -replace '(?m)^PasswordAuthentication no\r?\n','')
    Set-Content $config $content -Encoding ascii
    Get-NetFirewallRule -Name OpenSSH-Server-In-TCP -ErrorAction SilentlyContinue | Disable-NetFirewallRule
    Get-NetFirewallRule -Name LabSSH -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -Name LabSSH -DisplayName 'Lab SSH from host' -Direction Inbound -Protocol TCP -LocalPort 22 -RemoteAddress @@HOST_IP@@ -Action Allow | Out-Null
    Restart-Service sshd
    $winlogon = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
    Set-ItemProperty $winlogon AutoAdminLogon '0'
    Remove-ItemProperty $winlogon DefaultPassword -ErrorAction SilentlyContinue
    Set-LocalUser -Name labadmin -PasswordNeverExpires $true
    Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber | ConvertTo-Json | Set-Content C:\Lab\computer-info.json
    'ready' | Set-Content C:\Lab\bootstrap-ready.txt
} catch {
    $_ | Out-String | Set-Content C:\Lab\bootstrap-error.txt
    throw
} finally { Stop-Transcript }
