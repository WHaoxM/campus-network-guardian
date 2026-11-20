[CmdletBinding()]
param([string]$Dotnet)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$app = Join-Path $root 'app'
$runtime = Join-Path $root 'runtime'
$build = Join-Path $runtime 'desktop-build'
New-Item -ItemType Directory -Force -Path $build | Out-Null
if (-not $Dotnet) {
    $localSdk = Join-Path $build 'dotnet\dotnet.exe'
    if (Test-Path -LiteralPath $localSdk -PathType Leaf) { $Dotnet = $localSdk }
    else { $Dotnet = (Get-Command dotnet -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source }
}
if (-not $Dotnet -or -not (Test-Path -LiteralPath $Dotnet -PathType Leaf)) {
    throw 'Missing .NET 10 SDK. See docs/DEVELOPMENT.md.'
}
$env:DOTNET_CLI_HOME = $build
$env:NUGET_PACKAGES = Join-Path $build 'packages'
$env:NUGET_HTTP_CACHE_PATH = Join-Path $build 'nuget-http'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_NOLOGO = 'true'

& $Dotnet publish (Join-Path $app 'desktop\CampusGuardian.csproj') --configuration Release `
    --runtime win-x64 --self-contained true --artifacts-path (Join-Path $build 'artifacts') `
    --output (Join-Path $app 'runtime\desktop') --nologo
exit $LASTEXITCODE
