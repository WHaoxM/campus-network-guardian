[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Install','Upgrade')][string]$Mode,
    [Parameter(Mandatory)][string]$Directory,
    [string]$OwnerSid,
    [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$utf8 = [Text.UTF8Encoding]::new($false)
$source = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$target = [IO.Path]::GetFullPath($Directory).TrimEnd('\')
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = [Security.Principal.WindowsPrincipal]::new($identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$taskDescription = 'CampusNetwork/ManagedCampusWatcher/v1; login and recovery only; never log out.'

function Assert-LocalPath([string]$Path) {
    if ($Path -notmatch '^[A-Za-z]:\\[^\\]' -or $Path -match '[\x00-\x1f"<>|?*]') { throw '请选择本机磁盘上的普通文件夹。' }
    for ($p = $Path; $p; $p = Split-Path $p -Parent) {
        if ((Test-Path -LiteralPath $p) -and ((Get-Item -LiteralPath $p -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw '所选目录经过链接或重解析点，未修改安装。'
        }
    }
}

function Read-Json([string]$Path) { Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json }
function Write-Json([string]$Path, $Value) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 7 -Compress), $utf8)
}
function Get-Setting([string]$Text, [string]$Key) {
    $match = [regex]::Match($Text, '(?m)^' + [regex]::Escape($Key) + '\s*=\s*"([^"\r\n]+)"\s*$')
    if (!$match.Success) { throw "现有设置缺少 $Key，未修改安装。" }
    return $match.Groups[1].Value
}

function Get-OwnedTask([string]$Name, [string[]]$Interpreters) {
    $existing = Get-ScheduledTask -TaskName $Name -TaskPath '\' -ErrorAction SilentlyContinue
    if (!$existing) { return $null }
    try { $sid = ([Security.Principal.NTAccount]$existing.Principal.UserId).Translate([Security.Principal.SecurityIdentifier]).Value }
    catch { $sid = $existing.Principal.UserId }
    if ($sid -ne $identity.User.Value -or $existing.Description -ne $taskDescription -or
        $existing.Principal.LogonType -ne 'S4U' -or @($existing.Actions).Count -ne 1 -or
        $existing.Actions[0].Execute -notin $Interpreters -or $existing.Actions[0].Arguments -ne $taskArguments -or
        $existing.Actions[0].WorkingDirectory -ne $app) {
        throw '此计划任务不属于所选安装目录，或不是可继承的 S4U 任务；未修改现有安装。'
    }
    return $existing
}

function Wait-TaskStopped([string]$Name, $PreviousProcess) {
    $end = [DateTime]::UtcNow.AddSeconds(16)
    do {
        if ((Get-ScheduledTask -TaskName $Name -TaskPath '\').State -ne 'Running' -and
            (!$PreviousProcess -or $PreviousProcess.HasExited)) { return }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $end)
    throw '原守护进程未退出，未切换到新版。'
}

function Wait-NewWatcher([string]$Name, [DateTimeOffset]$After) {
    $end = [DateTimeOffset]::UtcNow.AddSeconds(58)
    do {
        try {
            $s = Read-Json $heartbeat
            $age = ([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($s.heartbeat_at)).TotalSeconds
            if ($s.schema -eq 1 -and $s.fixture -eq $false -and $s.phase -ne 'starting' -and
                [DateTimeOffset]::Parse($s.started_at) -ge $After.AddSeconds(-1) -and
                $age -ge -2 -and $age -le 30 -and
                (Get-ScheduledTask -TaskName $Name -TaskPath '\').State -eq 'Running' -and
                (Get-Process -Id $s.pid -ErrorAction SilentlyContinue).Path -eq $python) { return }
        } catch { }
        Start-Sleep -Milliseconds 500
    } while ([DateTimeOffset]::UtcNow -lt $end)
    throw '新版守护没有发来新的运行状态。'
}

if ($OwnerSid -and $OwnerSid -ne $identity.User.Value) { throw '请用原 Windows 账号安装，不支持切换到其他管理员账号。' }
Assert-LocalPath $target
if ($target -eq $source -or $target.StartsWith($source + '\',[StringComparison]::OrdinalIgnoreCase) -or
    $source.StartsWith($target + '\',[StringComparison]::OrdinalIgnoreCase)) { throw '请选解压目录以外的安装目录。' }
$manifest = Read-Json (Join-Path $source 'install-manifest.json')
if ($manifest.schema -ne 1 -or $manifest.product -ne 'SUSE.CampusNetworkGuardian' -or
    $manifest.version -notmatch '^\d+\.\d+\.\d+$') { throw '安装包清单无效。' }

$app = Join-Path $target 'app'
$runtime = Join-Path $app 'runtime'
$config = Join-Path $app 'config\campus.toml'
$exe = Join-Path $runtime 'desktop\CampusGuardian.exe'
$python = Join-Path $runtime 'python\python.exe'
$oldVenv = Join-Path $app '.venv\Scripts\python.exe'
$marker = Join-Path $app 'config\browser_python.txt'
$profile = Join-Path $app 'config\browser_login.toml'
$heartbeat = Join-Path $runtime 'campus\desktop\status.json'
$installed = Join-Path $target 'installed.json'
$task = $null

if ($Mode -eq 'Upgrade') {
    if (!(Test-Path -LiteralPath $exe -PathType Leaf) -or !(Test-Path -LiteralPath $config -PathType Leaf)) { throw '未找到可升级的原安装。' }
    Assert-LocalPath $exe
    $previousVersion = (Get-Item -LiteralPath $exe).VersionInfo.FileVersion
    if (!(Test-Path -LiteralPath $installed) -and $previousVersion -ne '0.2.5.0') {
        throw '只支持从 v0.2.5 或本安装器管理的版本原地升级。'
    }
    if ((Test-Path -LiteralPath $installed) -and (Read-Json $installed).owner -ne $identity.User.Value) { throw '安装属于其他 Windows 用户。' }
    if ([version]$manifest.version -lt [version]($previousVersion -replace '\.0$','')) { throw '不支持覆盖安装旧版本。' }
    Assert-LocalPath $config
    $settings = [IO.File]::ReadAllText($config,$utf8)
    $taskName = Get-Setting $settings 'task_name'
    if ($taskName -notmatch '^[A-Za-z0-9_-]+$' -or (Get-Setting $settings 'runtime_dir') -ne '../runtime/campus' -or
        (Get-Setting $settings 'desktop_status_file') -ne 'desktop/status.json' -or
        (Get-Setting $settings 'python_path_file') -ne 'browser_python.txt') {
        throw '所选安装使用自定义的运行目录，不能自动覆盖。'
    }
    $taskArguments = '-X utf8 "{0}" watch --config "{1}"' -f (Join-Path $app 'campus_maintenance.py'), $config
    $task = Get-OwnedTask $taskName @($oldVenv,$python)
    if ($task -and !$isAdmin) {
        $ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $argsLine = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "{0}" -Mode Upgrade -Directory "{1}" -OwnerSid {2} -NoLaunch' -f $PSCommandPath,$target,$identity.User.Value
        try { $child = Start-Process -FilePath $ps -ArgumentList $argsLine -Verb RunAs -PassThru -Wait -WindowStyle Hidden }
        catch { throw '升级现有开机守护需要同一个 Windows 用户确认权限；旧版未修改。' }
        if ($child.ExitCode) { throw '升级没有完成，或已回退。请查看原安装目录的升级结果。' }
        if (!$NoLaunch) { Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe -Parent) }
        Write-Output ("安装完成：{0}  {1}" -f $manifest.version,$target)
        return
    }
} elseif ((Test-Path -LiteralPath $target) -and (Get-ChildItem -LiteralPath $target -Force | Select-Object -First 1)) {
    throw '安装目录不是空目录。要保留原账号与设置，请选“升级原安装”。'
}

$trayKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$tray = (Get-ItemProperty -LiteralPath $trayKey -Name 'SUSE.CampusNetworkGuardian' -ErrorAction SilentlyContinue).'SUSE.CampusNetworkGuardian'
if ($tray -and $tray -ne ('"' + $exe + '" --tray') -and ($Mode -eq 'Upgrade' -or !$NoLaunch)) { throw '检测到另一目录的托盘启动项，未接管。' }

Assert-LocalPath $runtime
[IO.Directory]::CreateDirectory($runtime) | Out-Null
$lock = $null
$work = Join-Path $runtime 'install-transaction'
$success = $false
$rolledBack = $false
$ownsWork = $false
$records = [Collections.Generic.List[object]]::new()
$stopped = $false
$rebound = $false
$newWatcher = $false
$newDesktop = $null
$oldAction = if ($task) { $task.Actions[0] } else { $null }
$oldWatcher = $null
$shouldRestart = $task -and $task.State -ne 'Disabled'
$oldDesktop = $false
$legacyMarker = if (Test-Path -LiteralPath $marker -PathType Leaf) { [IO.File]::ReadAllText($marker).Trim() } else { '' }
try {
    $lock = [IO.File]::Open((Join-Path $runtime 'install.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    if (Test-Path -LiteralPath $work) { throw '上次升级仍有保留的回退材料，未重复覆盖。' }
    $stage = Join-Path $work 'incoming'
    $previous = Join-Path $work 'previous'
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    $ownsWork = $true
    [IO.Directory]::CreateDirectory($previous) | Out-Null
    $entries = $manifest.files.PSObject.Properties
    $groups = @('app/runtime/desktop','app/runtime/python','app/licenses','app/media')
    $individual = [Collections.Generic.List[string]]::new()
    foreach ($entry in $entries) {
        $name = $entry.Name
        if ($name -notmatch '^(?:suse\.cmd|README\.md|LICENSE|app/(?:runtime/(?:python|desktop)/[^:]+|licenses/[^:]+|media/[^:]+|config/(?:campus\.toml|browser_login\.example\.toml)|scripts/(?:suse|deploy)\.ps1|[a-z_]+\.(?:ps1|py|txt)))$' -or
            $name -match '(?:^|/)(?:\.|\.\.)(?:/|$)|[\\\x00-\x1f"<>|?*]' -or $entry.Value -notmatch '^[a-f0-9]{64}$') { throw '安装包含有不属于程序的路径。' }
        $inputFile = Join-Path $source $name
        Assert-LocalPath $inputFile
        $stagedFile = Join-Path $stage $name
        [IO.Directory]::CreateDirectory((Split-Path $stagedFile -Parent)) | Out-Null
        [IO.File]::Copy($inputFile,$stagedFile)
        if ((Get-FileHash -LiteralPath $stagedFile -Algorithm SHA256).Hash -ne $entry.Value) { throw "安装包内容不完整：$name" }
        if (!($groups | Where-Object { $name.StartsWith($_ + '/', [StringComparison]::Ordinal) })) { $individual.Add($name) }
    }
    if (!(Test-Path -LiteralPath (Join-Path $stage 'app/runtime/python/python.exe')) -or
        !(Test-Path -LiteralPath (Join-Path $stage 'app/runtime/desktop/CampusGuardian.exe'))) { throw '安装包不含运行环境或桌面程序。' }
    $pinMatch = [regex]::Match([IO.File]::ReadAllText((Join-Path $stage 'app/requirements.txt')), '(?m)^playwright==([0-9.]+)\s*$')
    if (!$pinMatch.Success) { throw '安装包缺少 Playwright 版本。' }
    & (Join-Path $stage 'app/runtime/python/python.exe') -I -B -c "import sys; from importlib.metadata import version; from playwright.sync_api import sync_playwright; sys.exit(version('playwright') != sys.argv[1])" $pinMatch.Groups[1].Value
    if ($LASTEXITCODE) { throw '离线 Python 环境不可用，未切换安装。' }

    $userFiles = @('app/config/campus.toml','app/config/browser_login.toml','app/config/browser_python.txt')
    foreach ($rel in @($groups) + @($individual) + @($userFiles[1],$userFiles[2],'installed.json')) {
        $dest = Join-Path $target $rel
        Assert-LocalPath $dest
        if ($rel -in $userFiles[0..1] -and (Test-Path -LiteralPath $dest)) { continue }
        $backup = Join-Path $previous $rel
        $item = Get-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
        if ($item -and $item.PSIsContainer) {
            $foreign = Get-ChildItem -LiteralPath $dest -Recurse -Force | Where-Object {
                ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
                $_.Name -in @('.git','.env','accounts.private.json','schedule.json','Local State','Cookies')
            } | Select-Object -First 1
            if ($foreign) { throw "所选程序目录包含其他数据：$rel" }
        }
        $records.Add([pscustomobject]@{ dest=$dest; backup=$backup; staged=(Join-Path $stage $rel); existed=($null -ne $item); saved=$false; applied=$false })
    }

    if ($task) {
        $task = Get-OwnedTask $taskName @($oldVenv,$python)
        if (!$task) { throw '升级期间原守护任务消失，未替换程序。' }
        if ($task.State -eq 'Running') {
            $previousStatus = Read-Json $heartbeat
            $oldWatcher = Get-Process -Id $previousStatus.pid -ErrorAction SilentlyContinue
            $previousAge = ([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($previousStatus.heartbeat_at)).TotalSeconds
            if ($previousStatus.fixture -ne $false -or $previousStatus.schema -ne 1 -or $previousAge -lt -2 -or
                $previousAge -gt 45 -or !$oldWatcher -or $oldWatcher.Path -ne $oldAction.Execute) {
                throw '无法确认原守护进程身份，未替换程序。'
            }
        }
        # Disable triggers while files are changing. An exactly owned task is
        # re-enabled only if it was enabled before the transaction.
        Disable-ScheduledTask -InputObject $task | Out-Null
        $stopped = $true
        if ($task.State -eq 'Running') { Stop-ScheduledTask -InputObject $task }
        Wait-TaskStopped $taskName $oldWatcher
    }
    if ($Mode -eq 'Upgrade') {
        foreach ($process in @(Get-Process -Name CampusGuardian -ErrorAction SilentlyContinue | Where-Object Path -eq $exe)) {
            $oldDesktop = $true
            Stop-Process -InputObject $process
            if (!$process.WaitForExit(8000)) { throw '旧桌面窗口尚未退出。' }
        }
    }
    foreach ($record in $records) {
        if ($record.existed) {
            [IO.Directory]::CreateDirectory((Split-Path $record.backup -Parent)) | Out-Null
            Move-Item -LiteralPath $record.dest -Destination $record.backup
            $record.saved = $true
        }
        if (Test-Path -LiteralPath $record.staged) {
            [IO.Directory]::CreateDirectory((Split-Path $record.dest -Parent)) | Out-Null
            Move-Item -LiteralPath $record.staged -Destination $record.dest
        }
        $record.applied = $true
    }
    & (Join-Path $app 'setup.ps1')
    if ($LASTEXITCODE) { throw '新的本地环境未能初始化。' }
    $reply = '{"action":"list"}' | & $python -I -B -X utf8 (Join-Path $app 'campus_accounts.py') $config live $heartbeat
    if ($LASTEXITCODE -or !$reply -or ($reply | ConvertFrom-Json).error) { throw '新版无法读取现有账号或时段，已停止切换。' }
    if ($task) {
        $action = New-ScheduledTaskAction -Execute $python -Argument $taskArguments -WorkingDirectory $app
        Set-ScheduledTask -TaskName $taskName -TaskPath '\' -Action $action | Out-Null
        $rebound = $true
        if ($shouldRestart) {
            Enable-ScheduledTask -TaskName $taskName -TaskPath '\' | Out-Null
            $begin = [DateTimeOffset]::UtcNow
            Start-ScheduledTask -TaskName $taskName -TaskPath '\'
            $newWatcher = $true
            Wait-NewWatcher $taskName $begin
        }
    }
    Write-Json $installed @{schema=1;version=$manifest.version;owner=$identity.User.Value}
    if (!$NoLaunch) {
        $newDesktop = Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe -Parent) -PassThru
        Start-Sleep -Milliseconds 850
        if ($newDesktop.HasExited) { throw '新版桌面程序未能启动。' }
    }
    $success = $true
    if ($Mode -eq 'Upgrade' -and $legacyMarker -eq $oldVenv -and
        (Test-Path -LiteralPath (Join-Path $app '.venv\pyvenv.cfg') -PathType Leaf)) {
        try {
            $legacyEnv = Join-Path $app '.venv'
            Assert-LocalPath $legacyEnv
            $foreign = Get-ChildItem -LiteralPath $legacyEnv -Recurse -Force | Where-Object {
                ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
                $_.Name -in @('.git','.env','accounts.private.json','schedule.json','Local State','Cookies')
            } | Select-Object -First 1
            if (!$foreign) { Move-Item -LiteralPath $legacyEnv -Destination (Join-Path $work 'retired-managed-venv') }
        } catch { Write-Warning '旧的项目虚拟环境无法确认安全回收，已保留。' }
    }
} catch {
    $reason = $_
    if ($newDesktop -and !$newDesktop.HasExited) { Stop-Process -InputObject $newDesktop }
    if ($task -and $stopped) {
        Disable-ScheduledTask -TaskName $taskName -TaskPath '\' | Out-Null
        if ($newWatcher) { Stop-ScheduledTask -TaskName $taskName -TaskPath '\' }
        Wait-TaskStopped $taskName
    }
    # Roll back replaceable material only; never the protected runtime data.
    for ($i = $records.Count - 1; $i -ge 0; $i--) {
        $r = $records[$i]
        if ($r.applied -and (Test-Path -LiteralPath $r.dest)) {
            $discard = Join-Path $work ('discard-' + $i)
            Move-Item -LiteralPath $r.dest -Destination $discard
        }
        if ($r.saved) { Move-Item -LiteralPath $r.backup -Destination $r.dest }
    }
    if ($task -and $stopped) {
        if ($rebound) { Set-ScheduledTask -TaskName $taskName -TaskPath '\' -Action $oldAction | Out-Null }
        if ($shouldRestart) {
            Enable-ScheduledTask -TaskName $taskName -TaskPath '\' | Out-Null
            Start-ScheduledTask -TaskName $taskName -TaskPath '\'
        }
    }
    if ($oldDesktop -and (Test-Path -LiteralPath $exe)) { Start-Process -FilePath $exe -ArgumentList '--tray' -WindowStyle Hidden }
    $rolledBack = $true
    throw $reason
} finally {
    if ($lock) { $lock.Dispose() }
    if ($ownsWork -and ($success -or $rolledBack) -and (Test-Path -LiteralPath $work) -and $work.StartsWith($runtime + '\',[StringComparison]::OrdinalIgnoreCase)) {
        # Only the owned staging/rollback directory participates in cleanup.
        Assert-LocalPath $work
        try { [IO.Directory]::Delete($work,$true) }
        catch { Write-Warning '已保留无法回收的升级临时目录，未触碰用户数据。' }
    }
}
Write-Output ("安装完成：{0}  {1}" -f $manifest.version,$target)
