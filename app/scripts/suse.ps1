[CmdletBinding()]
param([Parameter(Position=0)][string]$Action = 'open')

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = Split-Path -Parent $PSScriptRoot

function Require-Browsers {
    $roots = @([Environment]::GetFolderPath('ProgramFilesX86'), [Environment]::GetFolderPath('ProgramFiles'),
               [Environment]::GetFolderPath('LocalApplicationData'))
    $edge = @($roots | Where-Object {
        $_ -and (Test-Path -LiteralPath (Join-Path $_ 'Microsoft\Edge\Application\msedge.exe') -PathType Leaf)
    })
    if (!$edge.Count) { throw '找不到 Microsoft Edge。请安装 Edge 后重新运行 suse.cmd。' }

    # Evergreen WebView2 product registration, per machine or per user.
    $id = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    $keys = @("HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$id",
              "HKCU:\Software\Microsoft\EdgeUpdate\Clients\$id")
    foreach ($key in $keys) {
        $v = (Get-ItemProperty -LiteralPath $key -Name pv -ErrorAction SilentlyContinue).pv
        $parsed = [version]'0.0'
        if ($v -and [version]::TryParse($v, [ref]$parsed) -and $parsed -gt [version]'0.0.0.0') { return }
    }
    throw '找不到 Microsoft Edge WebView2 Runtime。请安装后重新运行 suse.cmd。'
}

function Check-InstallLocation {
    $config = Join-Path $root 'config\campus.toml'
    $settings = [IO.File]::ReadAllText($config)
    $match = [regex]::Match($settings, '(?m)^task_name\s*=\s*"([A-Za-z0-9_-]+)"\s*$')
    if (!$match.Success) { throw '守护配置不完整，请重新解压便携包。' }
    $existing = Get-ScheduledTask -TaskName $match.Groups[1].Value -TaskPath '\' -ErrorAction SilentlyContinue
    $desktop = & (Join-Path $root 'install_desktop.ps1') -Mode Status
    if ($desktop.Conflict) { throw '发现另一目录的托盘启动项，未改动现有安装。旧版不能直接覆盖升级。' }
    if ($existing) {
        $python = Join-Path $root '.venv\Scripts\python.exe'
        $watcher = Join-Path $root 'campus_maintenance.py'
        $argsLine = '-X utf8 "{0}" watch --config "{1}"' -f $watcher, $config
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        try {
            $owner = ([Security.Principal.NTAccount]$existing.Principal.UserId).Translate([Security.Principal.SecurityIdentifier]).Value
        } catch { $owner = $existing.Principal.UserId }
        if ($owner -ne $identity.User.Value -or
            $existing.Description -ne 'CampusNetwork/ManagedCampusWatcher/v1; login and recovery only; never log out.' -or
            @($existing.Actions).Count -ne 1 -or $existing.Actions[0].Execute -ne $python -or
            $existing.Actions[0].Arguments -ne $argsLine) {
            throw '发现另一目录的守护任务，未改动现有安装。旧版不能直接覆盖升级。'
        }
    }
}

try {
    if ($Action -in @('help','--help','-h','/?')) {
        Write-Output 'suse.cmd       准备环境并打开 SUSE 校园网守护；再次运行直接打开。'
        exit 0
    }
    if ($Action -ne 'open') { throw '未知命令。运行 suse.cmd help 查看用法。' }
    $exe = Join-Path $root 'runtime\desktop\CampusGuardian.exe'
    if (!(Test-Path -LiteralPath $exe -PathType Leaf)) { throw '找不到桌面程序，请完整解压 Windows 便携包。' }
    Check-InstallLocation
    Require-Browsers
    & (Join-Path $root 'setup.ps1')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe)
    Write-Output '已启动 SUSE 守护器。'
    exit 0
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
