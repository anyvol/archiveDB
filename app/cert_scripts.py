"""Generate client trust scripts with embedded certificate download URL."""

from __future__ import annotations

from fastapi import Request

from app.config import PUBLIC_HTTPS_PORT, ROOT_PATH


def _sanitize_host(host: str) -> str:
    host = host.strip()
    if not host:
        return host
    if "/" in host:
        host = host.split("/", 1)[0]
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    return host


def _request_host(request: Request) -> str:
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        host = _sanitize_host(forwarded_host.split(",")[0])
    else:
        host = _sanitize_host(request.headers.get("host", request.url.netloc))

    if PUBLIC_HTTPS_PORT and PUBLIC_HTTPS_PORT not in ("443", "80") and ":" not in host:
        host = f"{host}:{PUBLIC_HTTPS_PORT}"
    return host


def external_base_url(request: Request) -> str:
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = _request_host(request)
    root = ROOT_PATH.rstrip("/") if ROOT_PATH else ""
    return f"{scheme}://{host}{root}"


def cert_download_url(request: Request) -> str:
    return f"{external_base_url(request)}/cert/fullchain.pem"


def trust_windows_ps1(cert_url: str) -> str:
    return f"""# Archive site certificate trust (auto-generated)
# Right-click -> Run with PowerShell (as Administrator)
# Or from elevated PowerShell: .\\trust-windows.ps1

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdmin) {{
    Write-Error "Run this script as Administrator."
}}

$CertUrl = "{cert_url}"
$TempCert = Join-Path $env:TEMP "archive-site-$([Guid]::NewGuid().ToString('n')).pem"

Write-Host "Installing archive site certificate..."
Write-Host "Downloading certificate from $CertUrl ..."

if ($PSVersionTable.PSVersion.Major -ge 6) {{
    Invoke-WebRequest -Uri $CertUrl -OutFile $TempCert -SkipCertificateCheck
}} else {{
    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = {{ $true }}
    try {{
        Invoke-WebRequest -Uri $CertUrl -OutFile $TempCert
    }} finally {{
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = $null
    }}
}}

Write-Host "Installing certificate into Trusted Root..."
Import-Certificate -FilePath $TempCert -CertStoreLocation Cert:\\LocalMachine\\Root | Out-Null
Remove-Item $TempCert -Force

Write-Host "Done. Restart the browser."
Read-Host "Press Enter to close"
"""


def trust_windows_cmd(cert_url: str) -> str:
    return f"""@echo off
REM Archive site certificate trust (auto-generated)
REM Right-click and "Run as administrator".

echo Installing archive site certificate...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {{ throw 'Run this file as Administrator.' }};" ^
  "$CertUrl='{cert_url}';" ^
  "$TempCert=Join-Path $env:TEMP ('archive-site-' + [Guid]::NewGuid().ToString('n') + '.pem');" ^
  "Write-Host ('Downloading certificate from ' + $CertUrl + ' ...');" ^
  "if ($PSVersionTable.PSVersion.Major -ge 6) {{ Invoke-WebRequest -Uri $CertUrl -OutFile $TempCert -SkipCertificateCheck }} else {{ [System.Net.ServicePointManager]::ServerCertificateValidationCallback = {{ $true }}; try {{ Invoke-WebRequest -Uri $CertUrl -OutFile $TempCert }} finally {{ [System.Net.ServicePointManager]::ServerCertificateValidationCallback = $null }} }};" ^
  "Write-Host 'Installing certificate into Trusted Root...';" ^
  "Import-Certificate -FilePath $TempCert -CertStoreLocation Cert:\\LocalMachine\\Root ^| Out-Null;" ^
  "Remove-Item $TempCert -Force;" ^
  "Write-Host 'Done. Restart the browser.'"

if errorlevel 1 (
    echo.
    echo Failed. Run this file as Administrator.
    pause
    exit /b 1
)
echo.
pause
"""


def trust_linux_script(cert_url: str) -> str:
    return f"""#!/usr/bin/env bash
# Archive site certificate trust (auto-generated)
# Run: sudo ./trust-linux.sh

set -euo pipefail

CERT_URL="{cert_url}"
TEMP="$(mktemp)"
trap 'rm -f "$TEMP"' EXIT

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run as root: sudo $0" >&2
    exit 1
fi

echo "Downloading certificate from ${{CERT_URL}} ..."
curl -fsSk "${{CERT_URL}}" -o "$TEMP"

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

echo "Done. Restart the browser."
"""


def trust_macos_script(cert_url: str) -> str:
    return f"""#!/usr/bin/env bash
# Archive site certificate trust (auto-generated)
# Run: sudo ./trust-macos.sh

set -euo pipefail

CERT_URL="{cert_url}"
TEMP="$(mktemp)"
trap 'rm -f "$TEMP"' EXIT

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run as root: sudo $0" >&2
    exit 1
fi

echo "Downloading certificate from ${{CERT_URL}} ..."
curl -fsSk "${{CERT_URL}}" -o "$TEMP"

security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain "$TEMP"

echo "Done. Restart the browser."
"""
