[CmdletBinding()]
param([string]$Python)

$ErrorActionPreference = 'Stop'
if (-not $Python) {
    $Python = (Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
}
if (-not $Python) { throw 'Python 3.11+ is required. See docs/INSTALL.md.' }
& $Python -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'Use Python 3.11 or newer.' }

$venv = Join-Path $PSScriptRoot '.venv'
$exe = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    & $Python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create the project environment.' }
}
& $exe -m pip --disable-pip-version-check install --no-cache-dir -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install the pinned dependencies.' }

$config = Join-Path $PSScriptRoot 'config'
[IO.File]::WriteAllText((Join-Path $config 'browser_python.txt'), $exe + "`r`n", [Text.UTF8Encoding]::new($false))
$profile = Join-Path $config 'browser_login.toml'
if (-not (Test-Path -LiteralPath $profile)) {
    Copy-Item -LiteralPath (Join-Path $config 'browser_login.example.toml') -Destination $profile
}
Write-Output 'Setup ready. Double-click runtime\desktop\CampusGuardian.exe (or open it with .\open_guardian.cmd).'
