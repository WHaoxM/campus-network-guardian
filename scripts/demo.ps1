[CmdletBinding()]
param([string]$Dotnet, [switch]$SkipBuild)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$app = Join-Path $root 'app'
$python = Join-Path $app '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Run .\app\setup.ps1 first.' }
if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot 'build_desktop.ps1') -Dotnet $Dotnet
    if ($LASTEXITCODE -ne 0) { throw 'Desktop build did not succeed.' }
}
$exe = Join-Path $app 'runtime\desktop\CampusGuardian.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Build the application or omit -SkipBuild.' }
$output = Join-Path $root 'runtime\demo'
Write-Output 'Demo uses a loopback portal and an isolated browser profile.'
$null = & $python -X utf8 (Join-Path $root 'tests\e2e_desktop.py') --exe $exe --output $output --preview
if ($LASTEXITCODE -ne 0) { throw 'The isolated desktop journey failed.' }
$report = Get-Content -LiteralPath (Join-Path $output 'desktop-e2e.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($report.outcome -ne 'passed') { throw 'Unexpected rehearsal result.' }
Write-Output ("PASS  Desktop journey: {0} checks" -f @($report.checks).Count)
Write-Output ("      Loopback login submissions: {0}" -f $report.fixture_login_submissions)
Write-Output ("      Portal logout requests:     {0}" -f $report.logout_requests)
Write-Output '      Report: runtime\demo\desktop-e2e.json'
