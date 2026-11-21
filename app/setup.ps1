[CmdletBinding()]
param([string]$Python)

$ErrorActionPreference = 'Stop'
$config = Join-Path $PSScriptRoot 'config'
$requirements = Join-Path $PSScriptRoot 'requirements.txt'
$runtime = Join-Path $PSScriptRoot 'runtime'
$venv = Join-Path $PSScriptRoot '.venv'
$embedded = Join-Path $runtime 'python\python.exe'
$bundled = Test-Path -LiteralPath $embedded -PathType Leaf
$exe = if ($bundled) { $embedded } else { Join-Path $venv 'Scripts\python.exe' }
$utf8 = [Text.UTF8Encoding]::new($false)

function Test-BasePython([string]$Executable, [string[]]$Prefix = @()) {
    $check = "import sys, sysconfig; sys.exit(0 if sys.version_info >= (3, 11) and sysconfig.get_platform() == 'win-amd64' else 1)"
    try {
        & $Executable @Prefix -I -c $check 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Find-Python {
    if ($Python) {
        if (Test-BasePython $Python) { return @{ Exe = $Python; Prefix = @() } }
        throw '指定的 Python 不可用。需要 64 位 Python 3.11 或更新版本。'
    }
    foreach ($name in @('python.exe','py.exe')) {
        foreach ($command in @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
            # Do not activate a Store installation alias.
            if ($command.Source -match '\\Microsoft\\WindowsApps\\') { continue }
            $prefix = if ($name -eq 'py.exe') { @('-3') } else { @() }
            if (Test-BasePython $command.Source $prefix) { return @{ Exe = $command.Source; Prefix = @($prefix) } }
        }
    }
    throw '找不到 64 位 Python 3.11 或更新版本。请安装 Python（建议 3.13，并勾选 Add Python to PATH），再运行 suse.cmd：https://www.python.org/downloads/windows/'
}

function Test-Dependencies {
    if (!(Test-Path -LiteralPath $exe -PathType Leaf)) { return $false }
    $check = "import sys; from importlib.metadata import version; from playwright.sync_api import sync_playwright; sys.exit(0 if version('playwright') == sys.argv[1] else 1)"
    try { & $exe -I -c $check $pinned 2>$null | Out-Null; return $LASTEXITCODE -eq 0 }
    catch { return $false }
}

$pin = [regex]::Match([IO.File]::ReadAllText($requirements), '(?m)^playwright==([0-9.]+)\s*$')
if (!$pin.Success) { throw '便携包缺少固定的 Playwright 版本。' }
$pinned = $pin.Groups[1].Value
[IO.Directory]::CreateDirectory($runtime) | Out-Null
try {
    $lock = [IO.File]::Open((Join-Path $runtime 'setup.lock'), [IO.FileMode]::OpenOrCreate,
        [IO.FileAccess]::Write, [IO.FileShare]::None)
} catch [IO.IOException] { throw '另一个窗口正在准备环境，或目录不可写。请稍后重试。' }
try {
    if (!(Test-Dependencies)) {
        if ($bundled -or (Test-Path -LiteralPath (Join-Path (Split-Path $PSScriptRoot -Parent) 'installed.json'))) {
            throw '本地运行环境不完整。请用同版本安装包运行升级修复，不会联网安装依赖。'
        }
        if (!(Test-Path -LiteralPath $exe -PathType Leaf)) {
            $interpreter = Find-Python
            $prefix = $interpreter.Prefix
            Write-Output '正在准备项目内的 Python 环境…'
            & $interpreter.Exe @prefix -m venv $venv
            if ($LASTEXITCODE -ne 0) { throw '无法创建项目环境。请检查目录是否可写，再运行 suse.cmd。' }
        }
        if (!(Test-BasePython $exe)) { throw '项目内的 Python 环境已失效。请检查原 Python 安装，未删除现有文件。' }
        Write-Output '正在安装 Playwright（首次需要联网）…'
        & $exe -I -m pip --disable-pip-version-check install --no-cache-dir -r $requirements
        if ($LASTEXITCODE -ne 0 -or !(Test-Dependencies)) { throw '依赖未安装完成。联网后再运行 suse.cmd 即可重试。' }
    }
    $profile = Join-Path $config 'browser_login.toml'
    if (!(Test-Path -LiteralPath $profile)) {
        [IO.File]::Copy((Join-Path $config 'browser_login.example.toml'), $profile)
    }
    $marker = Join-Path $config 'browser_python.txt'
    if (!(Test-Path -LiteralPath $marker -PathType Leaf) -or [IO.File]::ReadAllText($marker).Trim() -ne $exe) {
        [IO.File]::WriteAllText($marker, $exe + [Environment]::NewLine, $utf8)
    }
    $global:LASTEXITCODE = 0
} finally {
    $lock.Dispose()
}
