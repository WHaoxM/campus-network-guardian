param(
    [ValidateSet('Preview','Status','Install','Uninstall')][string]$Mode = 'Preview',
    [ValidateSet('S4U','Password','Interactive')][string]$Logon = 'S4U',
    [string]$Config = (Join-Path $PSScriptRoot 'config\campus.toml')
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$Config = (Resolve-Path -LiteralPath $Config).Path
$configText = Get-Content -LiteralPath $Config -Raw -Encoding UTF8
function Read-Setting([string]$Key) {
    $m = [regex]::Match($configText, ('(?m)^' + [regex]::Escape($Key) + '\s*=\s*(?:"([^"\r\n]+)"|(\d+))\s*$'))
    if (!$m.Success) { throw "Missing setting: $Key" }
    if ($m.Groups[1].Success) { return $m.Groups[1].Value }
    return $m.Groups[2].Value
}
$name = Read-Setting task_name
if ($name -notmatch '^[A-Za-z0-9_-]+$') { throw 'Invalid task name.' }
$minutes = [int](Read-Setting task_watchdog_minutes)
if ($minutes -lt 1 -or $minutes -gt 60) { throw 'Invalid watchdog interval.' }
$pathFile = Join-Path (Split-Path -Parent $Config) (Read-Setting python_path_file)
$python = (Resolve-Path -LiteralPath (Get-Content -LiteralPath $pathFile -Raw -Encoding UTF8).Trim()).Path
$script = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'campus_maintenance.py')).Path
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$user = $identity.Name
$argsLine = '-X utf8 "{0}" watch --config "{1}"' -f $script, $Config
$action = New-ScheduledTaskAction -Execute $python -Argument $argsLine -WorkingDirectory $PSScriptRoot
$watchdog = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $minutes)
$start = if ($Logon -eq 'Interactive') { New-ScheduledTaskTrigger -AtLogOn -User $user } else { New-ScheduledTaskTrigger -AtStartup }
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType $Logon -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$description = 'CampusNetwork/ManagedCampusWatcher/v1; login and recovery only; never log out.'
$task = New-ScheduledTask -Action $action -Trigger @($start,$watchdog) -Principal $principal -Settings $settings -Description $description
if ($Mode -eq 'Preview') {
    Export-ScheduledTask -InputObject $task
    exit 0
}
$existing = Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue
if ($Mode -eq 'Status') {
    if ($existing) {
        $existing | Select-Object TaskName,State,Principal,Actions,Triggers | ConvertTo-Json -Depth 6
        Get-ScheduledTaskInfo -TaskName $name -TaskPath '\' | ConvertTo-Json
    } else { Write-Output 'Not installed.' }
    exit 0
}
if (-not [Security.Principal.WindowsPrincipal]::new($identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Install/Uninstall requires Administrator PowerShell. No task was changed.'
}
if ($Mode -eq 'Install') {
    & $python -X utf8 $script status --config $Config | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'The local portal profile is not configured or invalid. No task was changed.' }
}
if ($existing -and ($existing.Description -ne $description -or $existing.Actions[0].Execute -ne $python -or $existing.Actions[0].Arguments -ne $argsLine)) {
    throw 'Ownership mismatch; no task was changed.'
}
if ($Mode -eq 'Uninstall') {
    if ($existing) {
        Disable-ScheduledTask -TaskName $name -TaskPath '\' | Out-Null
        Stop-ScheduledTask -TaskName $name -TaskPath '\'
        Unregister-ScheduledTask -TaskName $name -TaskPath '\' -Confirm:$false
    }
    Write-Output 'Watcher removed. Active campus sessions are not logged out.'
    exit 0
}
if (-not $PSBoundParameters.ContainsKey('Logon')) {
    throw 'Install requires an explicit -Logon choice. Preview is non-mutating.'
}
& $python -X utf8 $script check --config $Config
if ($LASTEXITCODE -ne 0) { throw 'Configuration validation failed; no task was registered.' }
if ($Logon -eq 'Password') {
    $windowsCredential = Get-Credential -UserName $user -Message 'Windows Task Scheduler credential (not the campus account).'
    if (-not $windowsCredential -or $windowsCredential.UserName -ne $user) { throw 'Use the same Windows account as the project owner.' }
    try {
        Register-ScheduledTask -TaskName $name -TaskPath '\' -Force -Xml (Export-ScheduledTask -InputObject $task) `
            -User $user -Password ($windowsCredential.GetNetworkCredential().Password) | Out-Null
    } finally {
        $windowsCredential = $null
    }
} else {
    Register-ScheduledTask -TaskName $name -TaskPath '\' -InputObject $task -Force | Out-Null
}
Get-ScheduledTask -TaskName $name -TaskPath '\' | Select-Object TaskName,State,Principal | ConvertTo-Json -Depth 5
