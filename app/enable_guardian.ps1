[CmdletBinding()]
param([ValidateSet('Status','Enable')][string]$Mode = 'Status', [string]$OwnerSid)

$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot 'install_campus_maintenance.ps1'
$desktop = Join-Path $PSScriptRoot 'install_desktop.ps1'
$config = Join-Path $PSScriptRoot 'config\campus.toml'
$settings = Get-Content -LiteralPath $config -Encoding UTF8 -Raw
function Read-Value([string]$Key) {
    $match = [regex]::Match($settings, ('(?m)^' + $Key + '\s*=\s*"([^"\r\n]+)"\s*$'))
    if (!$match.Success) { throw "Missing guardian setting: $Key" }
    return $match.Groups[1].Value
}
$name = Read-Value task_name
if ($name -notmatch '^[A-Za-z0-9_-]+$') { throw 'Invalid task name.' }
$python = (Get-Content -LiteralPath (Join-Path (Split-Path $config) (Read-Value python_path_file)) -Encoding UTF8 -Raw).Trim()
$script = Join-Path $PSScriptRoot 'campus_maintenance.py'
$argsLine = '-X utf8 "{0}" watch --config "{1}"' -f $script, $config
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if ($Mode -eq 'Enable' -and $OwnerSid -ne $identity.User.Value) { exit 32 }
$task = Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue
if ($task) {
    try {
        $sid = ([Security.Principal.NTAccount]$task.Principal.UserId).Translate([Security.Principal.SecurityIdentifier]).Value
    } catch { $sid = $task.Principal.UserId }
    if ($sid -ne $identity.User.Value -or
        $task.Description -ne 'CampusNetwork/ManagedCampusWatcher/v1; login and recovery only; never log out.' -or
        @($task.Actions).Count -ne 1 -or $task.Actions[0].Execute -ne $python -or $task.Actions[0].Arguments -ne $argsLine) {
        exit 31
    }
}
$desktopState = & $desktop -Mode Status
if ($Mode -eq 'Status') {
    if ($task -and $task.Principal.LogonType -eq 'S4U' -and $task.State -in @('Ready','Running') -and $desktopState.Installed) {
        exit 0
    }
    exit 20
}
if ($desktopState.Conflict) { exit 31 }
try {
    & $desktop -Mode Prepare | Out-Null
    if ($task -and $task.State -eq 'Running' -and $task.Principal.LogonType -ne 'S4U') { exit 31 }
    if (-not $task -or $task.Principal.LogonType -ne 'S4U' -or $task.State -eq 'Disabled') {
        & $installer -Mode Install -Logon S4U | Out-Null
        if ($LASTEXITCODE -ne 0) { exit 32 }
    }
    $task = Get-ScheduledTask -TaskName $name -TaskPath '\'
    if ($task.State -ne 'Running') { Start-ScheduledTask -InputObject $task }
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(55)
    $status = Join-Path (Join-Path (Split-Path $config) (Read-Value runtime_dir)) (Read-Value desktop_status_file)
    do {
        try {
            $snapshot = Get-Content -Raw -Encoding UTF8 -LiteralPath $status | ConvertFrom-Json
            $age = ([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($snapshot.heartbeat_at)).TotalSeconds
            if ($snapshot.schema -eq 1 -and $snapshot.fixture -eq $false -and $age -ge -2 -and $age -le 30 -and
                (Get-ScheduledTask -TaskName $name -TaskPath '\').State -eq 'Running' -and
                (Get-Process -Id $snapshot.pid -ErrorAction SilentlyContinue)) {
                & $desktop -Mode Install | Out-Null
                if ((& $desktop -Mode Status).Installed) { exit 0 }
            }
        } catch [System.Management.Automation.ItemNotFoundException] { }
          catch [System.FormatException] { }
        Start-Sleep -Milliseconds 500
    } until ([DateTimeOffset]::UtcNow -gt $deadline)
    exit 33
} catch {
    # Never include configuration or exception text in UI messages.
    exit 32
}
