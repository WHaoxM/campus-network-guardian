[CmdletBinding()]
param([ValidateSet('Status','Prepare','Install','Uninstall')][string]$Mode = 'Status', [string]$StatusFile)

$ErrorActionPreference = 'Stop'
$exe = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'runtime\desktop\CampusGuardian.exe'))
$entry = '"' + $exe + '" --tray'
$location = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$name = 'SUSE.CampusNetworkGuardian'
$controlDir = Join-Path $PSScriptRoot 'runtime\campus\desktop'
if ($StatusFile -and [IO.Path]::GetFullPath($StatusFile) -ne (Join-Path $controlDir 'status.json')) {
    throw 'Unexpected control path; no directory or startup change.'
}
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$ids = @($sid.Value, 'S-1-5-18', 'S-1-5-32-544')

function Test-ControlDirectory {
    if (-not (Test-Path -LiteralPath $controlDir -PathType Container)) { return $false }
    if ((Get-Item -LiteralPath $controlDir).Attributes -band [IO.FileAttributes]::ReparsePoint) { return $false }
    $acl = Get-Acl -LiteralPath $controlDir
    $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
    return $acl.AreAccessRulesProtected -and ($rules.Count -gt 0) -and
        (@($rules | Where-Object { $_.IdentityReference.Value -notin $ids }).Count -eq 0)
}

function Read-StartupEntry {
    $key = Get-ItemProperty -LiteralPath $location -ErrorAction SilentlyContinue
    if ($key) {
        $property = $key.PSObject.Properties[$name]
        if ($property) { return $property.Value }
    }
    return $null
}

$prior = Read-StartupEntry
if ($Mode -in @('Install','Uninstall') -and $null -ne $prior -and $prior -ne $entry) {
    throw 'Startup entry belongs to a different location; no change made.'
}
switch ($Mode) {
    'Prepare' {
        if (-not (Test-Path -LiteralPath $controlDir -PathType Container)) {
            $acl = [Security.AccessControl.DirectorySecurity]::new()
            $acl.SetAccessRuleProtection($true, $false)
            foreach ($id in $ids) {
                $identity = [Security.Principal.SecurityIdentifier]::new($id)
                $rule = [Security.AccessControl.FileSystemAccessRule]::new(
                    $identity, 'FullControl', 'ContainerInherit, ObjectInherit', 'None', 'Allow')
                $acl.AddAccessRule($rule)
            }
            [IO.Directory]::CreateDirectory($controlDir, $acl) | Out-Null
        }
        if (-not (Test-ControlDirectory)) { throw 'Desktop control directory is not private; no startup change.' }
    }
    'Install' {
        if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Desktop release not found.' }
        if (-not (Test-ControlDirectory)) { throw 'Desktop control directory is not private; run Prepare first.' }
        $statePath = Join-Path $controlDir 'status.json'
        if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) { throw 'Live desktop status not yet published.' }
        $view = Get-Content -Raw -Encoding UTF8 -LiteralPath $statePath | ConvertFrom-Json
        if ($view.schema -ne 1 -or $view.fixture -ne $false -or
            ([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($view.heartbeat_at)).TotalSeconds -gt 45) {
            throw 'No fresh production guardian snapshot; startup was not installed.'
        }
        if (-not (Test-Path -LiteralPath $location)) { New-Item -Path $location -Force | Out-Null }
        New-ItemProperty -Path $location -Name $name -PropertyType String -Value $entry -Force | Out-Null
    }
    'Uninstall' {
        if ($null -ne $prior) { Remove-ItemProperty -Path $location -Name $name }
    }
}
[pscustomobject]@{
    Mode = $Mode
    Installed = (Read-StartupEntry) -eq $entry
    Conflict = $null -ne $prior -and $prior -ne $entry
    PrivateControl = Test-ControlDirectory
}
