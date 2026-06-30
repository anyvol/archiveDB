# Install the archive self-signed certificate into Windows Trusted Root store.
# After this, Chrome/Edge will show a normal padlock for https://SERVER-PDM:8443/
#
# Run as Administrator:
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\scripts\trust-cert-windows.ps1
#   .\scripts\trust-cert-windows.ps1 -CertPath C:\path\to\fullchain.pem

param(
    [string]$CertPath = ""
)

$ErrorActionPreference = "Stop"

if (-not $CertPath) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $CertPath = Join-Path $scriptDir "..\nginx\certs\fullchain.pem"
    $CertPath = (Resolve-Path $CertPath -ErrorAction SilentlyContinue).Path
}

if (-not $CertPath -or -not (Test-Path $CertPath)) {
    Write-Error "Certificate not found. Copy nginx/certs/fullchain.pem from the server or pass -CertPath."
}

Write-Host "Importing trusted root certificate:"
Write-Host "  $CertPath"

Import-Certificate -FilePath $CertPath -CertStoreLocation Cert:\LocalMachine\Root | Out-Null

Write-Host ""
Write-Host "Done. Restart the browser and open:"
Write-Host "  https://SERVER-PDM:8443/archive/"
Write-Host "  https://192.168.4.108:8443/archive/   (only if IP is in certificate SAN)"
Write-Host ""
Write-Host "To remove:"
Write-Host "  Get-ChildItem Cert:\LocalMachine\Root | Where-Object Subject -match 'SERVER-PDM' | Remove-Item"
