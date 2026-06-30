# Windows: forward localhost ports to WSL when Docker runs inside WSL2.
# Run in PowerShell **as Administrator**.
#
# Usage:
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

foreach ($port in $ports) {
    netsh interface portproxy delete v4tov4 listenport=$port listenaddress=127.0.0.1 2>$null
    netsh interface portproxy add v4tov4 listenport=$port listenaddress=127.0.0.1 connectport=$port connectaddress=$wslIp
    Write-Host "Forwarded 127.0.0.1:${port} -> ${wslIp}:${port}"
}

netsh advfirewall firewall add rule name="archive-app HTTP" dir=in action=allow protocol=TCP localport=80 2>$null
netsh advfirewall firewall add rule name="archive-app HTTPS" dir=in action=allow protocol=TCP localport=8443 2>$null

Write-Host ""
Write-Host "Done. Try from Windows:"
Write-Host "  http://localhost/archive/           (push works)"
Write-Host "  https://localhost:8443/archive/     (after accepting self-signed cert)"
Write-Host ""
Write-Host "To remove forwarding:"
Write-Host "  netsh interface portproxy delete v4tov4 listenport=80 listenaddress=127.0.0.1"
Write-Host "  netsh interface portproxy delete v4tov4 listenport=8443 listenaddress=127.0.0.1"
