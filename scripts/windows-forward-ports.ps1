# Windows network setup for archiveDB.
# - Docker Desktop on Windows: opens firewall only (ports are published directly).
# - Docker inside WSL2: forwards Windows ports to the WSL VM + opens firewall.
#
# Run in PowerShell **as Administrator**:
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\scripts\windows-forward-ports.ps1
#
# Optional custom ports (must match .env / docker-compose.override.yaml):
#   .\scripts\windows-forward-ports.ps1 -HttpPort 8080 -HttpsPort 8443

param(
    [int]$HttpPort = 80,
    [int]$HttpsPort = 8443
)

$ErrorActionPreference = "Stop"

$ports = @($HttpPort, $HttpsPort)
if ($HttpsPort -ne 443) {
    $ports += 443
}
$ports = $ports | Select-Object -Unique

function Get-WslIpAddress {
    $commands = @(
        { wsl.exe -e sh -c "ip -4 route get 1.1.1.1 2>/dev/null | awk '{print `$7; exit}'" },
        { wsl.exe hostname -i },
        { wsl.exe hostname -I }
    )

    foreach ($command in $commands) {
        try {
            $raw = (& $command 2>$null | Out-String).Trim()
            if (-not $raw) { continue }
            $candidate = $raw.Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries)[0]
            if ($candidate -match '^\d{1,3}(\.\d{1,3}){3}$') {
                return $candidate
            }
        } catch {
            continue
        }
    }

    return $null
}

function Test-DockerRunsInWsl {
    try {
        $context = (docker context show 2>$null).Trim()
        if ($context -match 'wsl') {
            return $true
        }
    } catch {
        # Docker CLI not available — fall back to WSL IP probing below.
    }

    return [bool](Get-WslIpAddress)
}

function Enable-ArchiveFirewallRules {
    param([int[]]$TcpPorts)

    foreach ($port in $TcpPorts) {
        Remove-NetFirewallRule -DisplayName "archive-app TCP $port" -ErrorAction SilentlyContinue | Out-Null
        New-NetFirewallRule `
            -DisplayName "archive-app TCP $port" `
            -Direction Inbound `
            -Protocol TCP `
            -LocalPort $port `
            -Action Allow `
            -Profile Any | Out-Null
        Write-Host "Firewall: allow inbound TCP $port"
    }
}

function Get-ListenAddresses {
    $listenAddresses = @("127.0.0.1")
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notmatch '^127\.' -and
            $_.PrefixOrigin -ne 'WellKnown' -and
            $_.IPAddress -notmatch '^169\.254\.'
        } |
        ForEach-Object { $listenAddresses += $_.IPAddress }

    return $listenAddresses | Select-Object -Unique
}

$dockerInWsl = Test-DockerRunsInWsl

if ($dockerInWsl) {
    $wslIp = Get-WslIpAddress
    if (-not $wslIp) {
        Write-Error "Docker appears to run in WSL, but WSL IP could not be detected. Is WSL running?"
    }

    Write-Host "Mode: Docker in WSL2 (port forwarding required)"
    Write-Host "WSL IP: $wslIp"

    $listenAddresses = Get-ListenAddresses
    Write-Host "Forward targets: $($listenAddresses -join ', ')"

    foreach ($addr in $listenAddresses) {
        foreach ($port in $ports) {
            netsh interface portproxy delete v4tov4 listenport=$port listenaddress=$addr 2>$null | Out-Null
            netsh interface portproxy add v4tov4 listenport=$port listenaddress=$addr connectport=$port connectaddress=$wslIp
            Write-Host "  ${addr}:${port} -> ${wslIp}:${port}"
        }
    }

    Write-Host ""
    Write-Host "Current portproxy rules:"
    netsh interface portproxy show all
} else {
    Write-Host "Mode: Docker Desktop / native Windows (portproxy skipped)"
}

Enable-ArchiveFirewallRules -TcpPorts $ports

Write-Host ""
Write-Host "Test from this PC:"
if ($HttpPort -eq 80) {
    Write-Host "  http://localhost/archive/"
} else {
    Write-Host "  http://localhost:${HttpPort}/archive/"
}
if ($HttpsPort -eq 443) {
    Write-Host "  https://localhost/archive/"
} else {
    Write-Host "  https://localhost:${HttpsPort}/archive/"
}

Write-Host ""
Write-Host "Test from another PC on LAN (use this server's IP):"
Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notmatch '^127\.' -and $_.PrefixOrigin -ne 'WellKnown' } |
    ForEach-Object {
        Write-Host "  https://$($_.IPAddress):${HttpsPort}/archive/  (primary HTTPS + push)"
        if ($HttpsPort -ne 443) {
            Write-Host "  https://$($_.IPAddress)/archive/  (fallback if browser drops :${HttpsPort})"
        }
        Write-Host "  http://$($_.IPAddress)/archive/  (HTTP, no push)"
    }

if ($dockerInWsl) {
    Write-Host ""
    Write-Host "Permanent alternative: enable mirrored networking in %UserProfile%\.wslconfig :"
    Write-Host "  [wsl2]"
    Write-Host "  networkingMode=mirrored"
    Write-Host "Then: wsl --shutdown"
    Write-Host ""
    Write-Host "To remove forwarding:"
    Write-Host "  netsh interface portproxy reset"
}
