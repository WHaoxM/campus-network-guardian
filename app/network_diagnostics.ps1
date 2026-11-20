param([guid]$WifiGuid, [string]$ProbeHosts)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$hostsToCheck = $ProbeHosts -split ','
if ($hostsToCheck.Count -lt 1 -or $hostsToCheck.Count -gt 2 -or
    @($hostsToCheck | Where-Object { $_ -notmatch '^[a-z0-9][a-z0-9.-]{0,252}$' }).Count) { exit 2 }

$adapters = @(Get-NetAdapter -IncludeHidden)
$wlan = @($adapters | Where-Object { $_.InterfaceGuid -and [guid]$_.InterfaceGuid -eq $WifiGuid })
if ($wlan.Count -ne 1 -or $wlan[0].Status -ne 'Up') { exit 2 }
$servers = @((Get-DnsClientServerAddress -InterfaceIndex $wlan[0].ifIndex -AddressFamily IPv4).ServerAddresses)
$wifiResolver = $servers | Where-Object { $_ -and $_ -ne '0.0.0.0' } | Select-Object -First 1
$vpnHint = @($adapters | Where-Object {
    $_.Status -eq 'Up' -and $_.ifIndex -ne $wlan[0].ifIndex -and
    ($_.InterfaceDescription + ' ' + $_.Name) -match '(?i)\b(vpn|wireguard|wintun|tailscale|tap-windows|tun)\b'
}).Count -gt 0

function Test-UsableAddress([string]$Address) {
    $ip = $null
    if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$ip)) { return $false }
    $bytes = $ip.GetAddressBytes()
    if ($bytes.Count -ne 4) { return $false }
    $a, $b = $bytes[0], $bytes[1]
    # Public probe names should not resolve exclusively to local or synthetic ranges.
    return -not ($a -in @(0, 10, 127) -or $a -ge 224 -or
        ($a -eq 169 -and $b -eq 254) -or ($a -eq 172 -and $b -ge 16 -and $b -le 31) -or
        ($a -eq 192 -and $b -eq 168) -or ($a -eq 100 -and $b -ge 64 -and $b -le 127) -or
        ($a -eq 198 -and $b -in @(18, 19)))
}

function Test-Resolve([string]$Query, [string]$Resolver) {
    $options = @{ Name = $Query; Type = 'A'; DnsOnly = $true; NoHostsFile = $true; QuickTimeout = $true }
    if ($Resolver) { $options.Server = $Resolver }
    try {
        return @((Resolve-DnsName @options) | Where-Object { Test-UsableAddress $_.IPAddress }).Count -gt 0
    } catch { return $false }
}
# Compare the same name against both resolvers. Different successful CDN IPs
# by themselves do not mean DNS interference. Never emit addresses or names.
foreach ($hostname in $hostsToCheck) {
    if (Test-Resolve $hostname '') {
        @{ system = $true; wifi = $null; vpn = $vpnHint } | ConvertTo-Json -Compress
        exit 0
    }
    if ($wifiResolver -and (Test-Resolve $hostname $wifiResolver)) {
        @{ system = $false; wifi = $true; vpn = $vpnHint } | ConvertTo-Json -Compress
        exit 0
    }
}
@{ system = $false; wifi = $null; vpn = $vpnHint } | ConvertTo-Json -Compress
