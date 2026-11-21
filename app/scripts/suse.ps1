[CmdletBinding()]
param(
    [Parameter(Position=0)][string]$Action = 'open',
    [Parameter(Position=1)][string]$Directory,
    [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = Split-Path -Parent $PSScriptRoot
$entryRoot = Split-Path -Parent $root
$package = Test-Path -LiteralPath (Join-Path $entryRoot 'install-manifest.json') -PathType Leaf

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
        $marker = Join-Path $root 'config\browser_python.txt'
        $python = if (Test-Path -LiteralPath $marker -PathType Leaf) { [IO.File]::ReadAllText($marker).Trim() }
                  else { Join-Path $root 'runtime\python\python.exe' }
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

function Choose-Directory {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = [Windows.Forms.FolderBrowserDialog]::new()
    try {
        $dialog.Description = '选择一个空文件夹安装；旧用户请选择原来含 suse.cmd 的安装目录。'
        $dialog.ShowNewFolderButton = $true
        $dialog.SelectedPath = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs'
        if ($dialog.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) { return $dialog.SelectedPath }
        return $null
    } finally { $dialog.Dispose() }
}

try {
    if ($Action -in @('help','--help','-h','/?')) {
        Write-Output 'suse.cmd                         打开守护；在解压目录打开时会选择安装位置。'
        Write-Output 'suse.cmd install "目录"          安装到空目录。'
        Write-Output 'suse.cmd upgrade "原安装目录"    原地升级，保留账号与时段。'
        exit 0
    }
    if ($Action -eq 'open' -and $package) {
        if (!$Directory) { $Directory = Choose-Directory }
        if (!$Directory) { exit 0 }
        $Action = if (Test-Path -LiteralPath (Join-Path $Directory 'app\runtime\desktop\CampusGuardian.exe') -PathType Leaf) { 'upgrade' } else { 'install' }
    }
    if ($Action -in @('install','upgrade')) {
        if (!$package) { throw '请在完整解压的新版安装包里运行安装或升级。' }
        if (!$Directory) { throw '请指定安装目录，或双击安装包里的 suse.cmd 选择。' }
        if (!$NoLaunch) { Require-Browsers }
        & (Join-Path $PSScriptRoot 'deploy.ps1') -Mode $Action -Directory $Directory -NoLaunch:$NoLaunch
        exit 0
    }
    if ($Action -ne 'open') { throw '未知命令。运行 suse.cmd help 查看用法。' }
    if (Test-Path -LiteralPath (Join-Path $root 'runtime\install-transaction')) { throw '上次升级未完成，为保护旧版暂不启动。请先处理升级结果。' }
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
