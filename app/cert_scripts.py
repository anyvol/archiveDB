"""Generate client trust scripts with embedded certificate download URL."""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from fastapi import Request

from app.config import PUBLIC_HTTPS_PORT, ROOT_PATH

SSL_CERT_CN = os.getenv("SSL_CERT_CN", "").strip()
SSL_CERT_IP = os.getenv("SSL_CERT_IP", "").strip()

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _https_port() -> str:
    if PUBLIC_HTTPS_PORT and PUBLIC_HTTPS_PORT not in ("443", "80"):
        return PUBLIC_HTTPS_PORT
    return "443"


def _request_hostname(request: Request) -> str:
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        host = forwarded_host.split(",")[0].strip()
    else:
        host = request.headers.get("host", request.url.netloc)
    return host.split(":")[0]


def resolve_public_hostname(request: Request) -> str:
    """Hostname clients should use to reach this server over HTTPS/LAN."""
    hostname = _request_hostname(request)
    if hostname.lower() in _LOCAL_HOSTS:
        if SSL_CERT_IP:
            return SSL_CERT_IP
        if SSL_CERT_CN and SSL_CERT_CN.lower() not in _LOCAL_HOSTS:
            return SSL_CERT_CN
    return hostname


def build_cert_download_url(hostname: str, *, https_port: str | None = None, root_path: str | None = None) -> str:
    port = https_port or _https_port()
    root = (root_path if root_path is not None else ROOT_PATH).rstrip("/")
    host = hostname
    if port not in ("443", "80"):
        host = f"{hostname}:{port}"
    return f"https://{host}{root}/cert/fullchain.pem"


def build_base_url(hostname: str, *, https_port: str | None = None, root_path: str | None = None) -> str:
    port = https_port or _https_port()
    root = (root_path if root_path is not None else ROOT_PATH).rstrip("/")
    host = hostname
    if port not in ("443", "80"):
        host = f"{hostname}:{port}"
    return f"https://{host}{root}"


def cert_url_candidates(request: Request) -> list[str]:
    """Ordered HTTPS certificate URLs to try (primary host first, then alternates)."""
    port = _https_port()
    root = ROOT_PATH.rstrip("/") if ROOT_PATH else ""
    primary = resolve_public_hostname(request)
    hosts: list[str] = [primary]

    for candidate in (SSL_CERT_IP, SSL_CERT_CN, _request_hostname(request)):
        if candidate and candidate not in hosts:
            hosts.append(candidate)

    return [build_cert_download_url(host, https_port=port, root_path=root) for host in hosts]


def server_site_info(request: Request) -> dict[str, Any]:
    port = _https_port()
    root = ROOT_PATH.rstrip("/") if ROOT_PATH else ""
    public_host = resolve_public_hostname(request)
    cert_urls = cert_url_candidates(request)
    return {
        "public_host": public_host,
        "https_port": int(port) if port.isdigit() else port,
        "root_path": root or "/",
        "cert_cn": SSL_CERT_CN or None,
        "cert_ip": SSL_CERT_IP or None,
        "base_url": build_base_url(public_host, https_port=port, root_path=root),
        "cert_url": cert_urls[0],
        "cert_urls": cert_urls,
    }


def _request_host(request: Request, *, https: bool = False) -> str:
    hostname = resolve_public_hostname(request) if https else _request_hostname(request)
    if https and PUBLIC_HTTPS_PORT and PUBLIC_HTTPS_PORT not in ("443", "80"):
        return f"{hostname}:{PUBLIC_HTTPS_PORT}"
    if PUBLIC_HTTPS_PORT and PUBLIC_HTTPS_PORT not in ("443", "80") and ":" not in hostname and not https:
        return f"{hostname}:{PUBLIC_HTTPS_PORT}"
    return hostname


def external_base_url(request: Request, *, https: bool = False) -> str:
    if https:
        return build_base_url(resolve_public_hostname(request))
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = _request_host(request)
    root = ROOT_PATH.rstrip("/") if ROOT_PATH else ""
    return f"{scheme}://{host}{root}"


def cert_download_url(request: Request) -> str:
    return cert_url_candidates(request)[0]


def site_info_json(request: Request) -> str:
    return json.dumps(server_site_info(request), indent=2, ensure_ascii=False) + "\n"


def _powershell_cert_urls_literal(cert_urls: list[str]) -> str:
    quoted = ",\n    ".join(f'"{url}"' for url in cert_urls)
    return f"@(\n    {quoted}\n)"


def _powershell_download_snippet() -> str:
    return """
function Download-Certificate {
    param([string]$Url, [string]$Destination)
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        & curl.exe -fsSk $Url -o $Destination
        return
    }
    if ($PSVersionTable.PSVersion.Major -ge 6) {
        Invoke-WebRequest -Uri $Url -OutFile $Destination -SkipCertificateCheck
        return
    }
    $tls12 = [Net.SecurityProtocolType]::Tls12
    if ([Enum]::IsDefined([Net.SecurityProtocolType], 'Tls13')) {
        $tls13 = [Net.SecurityProtocolType]::Tls13
        [Net.ServicePointManager]::SecurityProtocol = $tls12 -bor $tls13
    } else {
        [Net.ServicePointManager]::SecurityProtocol = $tls12
    }
    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
    try {
        (New-Object System.Net.WebClient).DownloadFile($Url, $Destination)
    } finally {
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = $null
    }
}

function Download-Certificate-FromCandidates {
    param([string[]]$Urls, [string]$Destination)
    $errors = @()
    foreach ($url in $Urls) {
        try {
            Write-Host "Trying $url ..."
            Download-Certificate -Url $url -Destination $Destination
            Write-Host "Downloaded from $url"
            return
        } catch {
            $errors += "$url -> $($_.Exception.Message)"
        }
    }
    throw "Could not download certificate. Tried:`n$($errors -join "`n")"
}
""".strip()


def _trust_windows_powershell_body(site_info: dict[str, Any]) -> str:
    cert_urls = site_info["cert_urls"]
    base_url = site_info["base_url"]
    return f"""$ErrorActionPreference = "Stop"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {{ throw "Run this file as Administrator." }}
$CertUrls = {_powershell_cert_urls_literal(cert_urls)}
$TempCert = Join-Path $env:TEMP "archive-site-$([Guid]::NewGuid().ToString('n')).pem"
{_powershell_download_snippet()}
Download-Certificate-FromCandidates -Urls $CertUrls -Destination $TempCert
Write-Host "Installing certificate into Trusted Root..."
Import-Certificate -FilePath $TempCert -CertStoreLocation Cert:\\LocalMachine\\Root | Out-Null
Remove-Item $TempCert -Force
Write-Host "Done. Restart the browser and open:"
Write-Host "  {base_url}/"
"""


def trust_windows_cmd(site_info: dict[str, Any]) -> str:
    encoded = base64.b64encode(_trust_windows_powershell_body(site_info).encode("utf-16-le")).decode("ascii")
    return f"""@echo off
REM Archive site certificate trust (auto-generated for this server)
REM Right-click and "Run as administrator", or run from elevated cmd.

echo Installing archive site certificate...
powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}
if errorlevel 1 (
    echo.
    echo Failed. Run this file as Administrator.
    pause
    exit /b 1
)
echo.
pause
"""


def _shell_cert_urls_array(cert_urls: list[str]) -> str:
    return " ".join(f'"{url}"' for url in cert_urls)


def trust_linux_script(site_info: dict[str, Any]) -> str:
    cert_urls = site_info["cert_urls"]
    base_url = site_info["base_url"]
    return f"""#!/usr/bin/env bash
# Archive site certificate trust (auto-generated for this server)
# Run: sudo ./trust-linux.sh

set -euo pipefail

CERT_URLS=({_shell_cert_urls_array(cert_urls)})
TEMP="$(mktemp)"
trap 'rm -f "$TEMP"' EXIT

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run as root: sudo $0" >&2
    exit 1
fi

downloaded=0
for cert_url in "${{CERT_URLS[@]}}"; do
    echo "Trying $cert_url ..."
    if curl -fsSk "$cert_url" -o "$TEMP"; then
        echo "Downloaded from $cert_url"
        downloaded=1
        break
    fi
done

if [[ "$downloaded" -ne 1 ]]; then
    echo "Could not download certificate from server." >&2
    exit 1
fi

if command -v update-ca-certificates >/dev/null 2>&1; then
    cp "$TEMP" /usr/local/share/ca-certificates/archive-site.crt
    update-ca-certificates
elif command -v update-ca-trust >/dev/null 2>&1; then
    cp "$TEMP" /etc/pki/ca-trust/source/anchors/archive-site.pem
    update-ca-trust extract
else
    echo "Unsupported distribution. Import the certificate manually." >&2
    exit 1
fi

echo "Done. Restart the browser and open:"
echo "  {base_url}/"
"""


def trust_macos_script(site_info: dict[str, Any]) -> str:
    cert_urls = site_info["cert_urls"]
    base_url = site_info["base_url"]
    return f"""#!/usr/bin/env bash
# Archive site certificate trust (auto-generated for this server)
# Run: sudo ./trust-macos.sh

set -euo pipefail

CERT_URLS=({_shell_cert_urls_array(cert_urls)})
TEMP="$(mktemp)"
trap 'rm -f "$TEMP"' EXIT

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run as root: sudo $0" >&2
    exit 1
fi

downloaded=0
for cert_url in "${{CERT_URLS[@]}}"; do
    echo "Trying $cert_url ..."
    if curl -fsSk "$cert_url" -o "$TEMP"; then
        echo "Downloaded from $cert_url"
        downloaded=1
        break
    fi
done

if [[ "$downloaded" -ne 1 ]]; then
    echo "Could not download certificate from server." >&2
    exit 1
fi

security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain "$TEMP"

echo "Done. Restart the browser and open:"
echo "  {base_url}/"
"""
