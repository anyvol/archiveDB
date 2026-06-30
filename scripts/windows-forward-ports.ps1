# Windows: forward ports to WSL when Docker runs inside WSL2.
# Required for LAN access (e.g. https://192.168.x.x:8443/) — WSL does not
# publish Docker ports on the Windows LAN interface by default.
#
# Run in PowerShell **as Administrator**:
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\scripts\windows-forward-ports.ps1

$ErrorActionPreference = "Stop"

$ports = @(80, 8443)

try {
    $wslIp = (wsl.exe hostname -I).Trim().Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries)[0]
} catch {
    Write-Error "Cannot get WSL IP. Is WSL running?"
}

if (-not $wslIp) {
    Write-Error "WSL IP is empty."
}

Write-Host "WSL IP: $wslIp"

# Listen on localhost and every Windows IPv4 address (LAN access).
$listenAddresses = @("127.0.0.1")
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -notmatch '^127\.' -and
        $_.PrefixOrigin -ne 'WellKnown' -and
        $_.IPAddress -notmatch '^169\.254\.'
    } |
    ForEach-Object { $listenAddresses += $_.IPAddress }

$listenAddresses = $listenAddresses | Select-Object -Unique
Write-Host "Forward targets: $($listenAddresses -join ', ')"

foreach ($addr in $listenAddresses) {
    foreach ($port in $ports) {
        netsh interface portproxy delete v4tov4 listenport=$port listenaddress=$addr 2>$null | Out-Null
        netsh interface portproxy add v4tov4 listenport=$port listenaddress=$addr connectport=$port connectaddress=$wslIp
        Write-Host "  ${addr}:${port} -> ${wslIp}:${port}"
    }
}

foreach ($port in $ports) {
    Remove-NetFirewallRule -DisplayName "archive-app TCP $port" -ErrorAction SilentlyContinue | Out-Null
    New-NetFirewallRule -DisplayName "archive-app TCP $port" -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Any | Out-Null
    Write-Host "Firewall: allow inbound TCP $port"
}

Write-Host ""
Write-Host "Current portproxy rules:"
netsh interface portproxy show all

Write-Host ""
Write-Host "Test from this PC:"
Write-Host "  http://localhost/archive/"
Write-Host "  https://localhost:8443/archive/"
Write-Host ""
Write-Host "Test from another PC on LAN (use this server's IP):"
Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notmatch '^127\.' -and $_.PrefixOrigin -ne 'WellKnown' } |
    ForEach-Object {
        Write-Host "  https://$($_.IPAddress):8443/archive/"
    }
Write-Host ""
Write-Host "Permanent alternative: enable mirrored networking in %UserProfile%\.wslconfig :"
Write-Host "  [wsl2]"
Write-Host "  networkingMode=mirrored"
Write-Host "Then: wsl --shutdown"
Write-Host ""
Write-Host "To remove forwarding:"
Write-Host "  netsh interface portproxy reset"
