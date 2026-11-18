param([Parameter(Mandatory=$true)][string]$Directory)
$ErrorActionPreference='Stop'
$failed=$false
$files=@(Get-ChildItem $Directory -Filter *.ps1 -Recurse)
if (!$files.Count) { throw 'No rendered PowerShell scripts found.' }
foreach ($file in $files) {
    $tokens=$null; $errors=$null
    [System.Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors) | Out-Null
    if ($errors.Count) {
        $failed=$true
        $errors | ForEach-Object { Write-Output ($file.Name+': '+$_.Message) }
    }
}
if ($failed) { throw 'PowerShell parse errors.' }
Write-Output ("Parsed {0} PowerShell files successfully." -f $files.Count)
