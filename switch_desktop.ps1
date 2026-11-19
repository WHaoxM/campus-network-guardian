[CmdletBinding()]
param([ValidateSet('Activate','Rollback')][string]$Mode = 'Activate')

$ErrorActionPreference = 'Stop'
$config = Join-Path $PSScriptRoot 'config\campus.toml'
$settings = [IO.File]::ReadAllText($config)
$taskName = 'CampusNetwork-Maintenance'
$setting = 'desktop_status_file = "desktop/status.json"'
$task = Get-ScheduledTask -TaskName $taskName -TaskPath '\'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
try {
    $taskSid = ([Security.Principal.NTAccount]$task.Principal.UserId).Translate([Security.Principal.SecurityIdentifier]).Value
} catch { $taskSid = $task.Principal.UserId }
if ($taskSid -ne $identity.User.Value -or
    $task.Description -ne 'CampusNetwork/ManagedCampusWatcher/v1; login and recovery only; never log out.' -or
    @($task.Actions).Count -ne 1 -or
    -not $task.Actions[0].Arguments.Contains('"' + (Join-Path $PSScriptRoot 'campus_maintenance.py') + '" watch --config "' + $config + '"')) {
    throw 'Unexpected guardian task ownership or command; no change made.'
}
if ($settings -match '(?m)^desktop_status_file\s*=' -and -not $settings.Contains($setting)) {
    throw 'A different desktop status path is configured; no change made.'
}

function Write-Config([string]$Text) {
    $pending = $config + '.desktop-switch.tmp'
    [IO.File]::WriteAllText($pending, $Text, [Text.UTF8Encoding]::new($false))
    [IO.File]::Replace($pending, $config, [System.Management.Automation.Language.NullString]::Value)
}

$statusPath = Join-Path $PSScriptRoot 'runtime\campus\desktop\status.json'
if ($Mode -eq 'Rollback' -and (Test-Path -LiteralPath (Join-Path (Split-Path $statusPath) 'accounts.private.json'))) {
    throw 'The managed account pool needs desktop status enabled. To stop only the tray, use install_desktop.ps1 -Mode Uninstall.'
}
$installer = Join-Path $PSScriptRoot 'install_desktop.ps1'
$existingStartup = & $installer -Mode Status
if ($Mode -eq 'Activate') {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'runtime\desktop\CampusGuardian.exe') -PathType Leaf)) {
        throw 'Build the desktop package before switching.'
    }
    & $installer -Mode Prepare | Out-Null
    $observed = & (Join-Path $PSScriptRoot 'campus_maintenance.cmd') observe | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $observed.suse_probe_ok -ne $true) {
        throw 'SUSE is not verified online; no watcher or startup change made.'
    }
}

$configChanged = $false
$taskStopped = $false
try {
    if ($task.State -eq 'Running') {
        # The already-registered owner task is the only process we may stop.
        Stop-ScheduledTask -TaskName $taskName -TaskPath '\'
        $taskStopped = $true
        $limit = (Get-Date).AddSeconds(12)
        do {
            Start-Sleep -Milliseconds 250
            $currentTask = Get-ScheduledTask -TaskName $taskName -TaskPath '\'
        } until ($currentTask.State -ne 'Running' -or (Get-Date) -gt $limit)
        if ($currentTask.State -eq 'Running') { throw 'Existing managed task did not stop.' }
    } elseif ($task.State -ne 'Ready') {
        throw 'Guardian task is not ready or running.'
    }
    $next = $settings
    if ($Mode -eq 'Activate' -and -not $settings.Contains($setting)) {
        $next = [regex]::Replace($settings, '(?m)^runtime_dir = "../runtime/campus"(?=\r?$)', {param($m) $m.Value + "`n" + $setting})
        if ($next -eq $settings) { throw 'Guardian runtime config differs from the expected layout.' }
    } elseif ($Mode -eq 'Rollback') {
        $next = $settings -replace '(?m)^desktop_status_file = "desktop/status\.json"\r?\n', ''
    }
    if ($next -ne $settings) { Write-Config $next; $configChanged = $true }
    $started = [DateTimeOffset]::UtcNow
    Start-ScheduledTask -TaskName $taskName -TaskPath '\'
    $taskStopped = $false
    if ($Mode -eq 'Rollback') {
        & $installer -Mode Uninstall
        return
    }
    $deadline = (Get-Date).AddSeconds(35)
    do {
        Start-Sleep -Milliseconds 500
        if (-not (Test-Path -LiteralPath $statusPath -PathType Leaf)) { continue }
        $snapshot = Get-Content -Raw -Encoding UTF8 -LiteralPath $statusPath | ConvertFrom-Json
        if ($snapshot.fixture -eq $false -and $snapshot.schema -eq 1 -and $snapshot.phase -eq 'monitoring' -and
            [DateTimeOffset]::Parse($snapshot.started_at) -ge $started -and $snapshot.internet -eq 'online') {
            & $installer -Mode Install
            return
        }
    } until ((Get-Date) -gt $deadline)
    throw 'New watcher did not confirm live SUSE state; startup was not installed.'
} catch {
    if ($configChanged) {
        Write-Config $settings
        $nowTask = Get-ScheduledTask -TaskName $taskName -TaskPath '\'
        if ($nowTask.State -eq 'Running') {
            Stop-ScheduledTask -TaskName $taskName -TaskPath '\'
            $taskStopped = $true
            Start-Sleep -Milliseconds 900
        }
    }
    if ($taskStopped) { Start-ScheduledTask -TaskName $taskName -TaskPath '\' }
    if (-not $existingStartup.Installed -and (& $installer -Mode Status).Installed) { & $installer -Mode Uninstall | Out-Null }
    throw
}
