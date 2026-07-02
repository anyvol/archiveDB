# Download and install the archive site certificate into Windows Trusted Root store.
#
# Universal usage (from any client PC):
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\scripts\trust-cert-windows.ps1 -ServerBaseUrl https://192.168.2.136:8443/archive
#   .\scripts\trust-cert-windows.ps1 -ServerHost 192.168.2.136 -HttpsPort 8443
#
# Local file (on the server):
#   .\scripts\trust-cert-windows.ps1 -CertPath C:\archiveDB\nginx\certs\fullchain.pem
#
# Double-click is not supported for .ps1 — run trust-windows.cmd or use:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\trust-cert-windows.ps1 -ServerBaseUrl https://SERVER:8443/archive

param(
    [string]$ServerBaseUrl = "",
    [string]$ServerHost = "",
    [int]$HttpsPort = 8443,
    [string]$RootPath = "/archive",
    [string]$CertPath = "",
    [switch]$Elevated
)

$ErrorActionPreference = "Stop"

function Test-Administrator {
    $current = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($current)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    Write-Host "Requesting administrator privileges..."
    $argList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $PSCommandPath,
        "-Elevated"
    )
    if ($ServerBaseUrl) { $argList += "-ServerBaseUrl"; $argList += $ServerBaseUrl }
    if ($ServerHost) { $argList += "-ServerHost"; $argList += $ServerHost }
    if ($HttpsPort -ne 8443) { $argList += "-HttpsPort"; $argList += "$HttpsPort" }
    if ($RootPath -ne "/archive") { $argList += "-RootPath"; $argList += $RootPath }
    if ($CertPath) { $argList += "-CertPath"; $argList += $CertPath }
    $proc = Start-Process powershell.exe -ArgumentList $argList -Verb RunAs -PassThru -Wait
    exit $proc.ExitCode
}

function Install-TrustedRootCertificate {
    param([string]$Path)
    $certutil = Get-Command certutil.exe -ErrorAction SilentlyContinue
    if ($certutil) {
        & certutil.exe -addstore -f Root $Path | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "certutil failed with exit code $LASTEXITCODE"
        }
        return
    }
    Import-Certificate -FilePath $Path -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
}

function Assert-Administrator {
    if (-not (Test-Administrator)) {
        throw "Administrator privileges are required."
    }
}

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

function Normalize-BaseUrl {
    param([string]$Url)
    $normalized = $Url.Trim().TrimEnd('/')
    if (-not $normalized) {
        throw "ServerBaseUrl is empty."
    }
    return $normalized
}

function Build-CertUrl {
    param(
        [string]$HostName,
        [int]$Port,
        [string]$Root
    )
    $root = $Root.Trim()
    if (-not $root.StartsWith("/")) {
        $root = "/$root"
    }
    $root = $root.TrimEnd('/')
    if ($Port -in 443, 80) {
        return "https://${HostName}${root}/cert/fullchain.pem"
    }
    return "https://${HostName}:${Port}${root}/cert/fullchain.pem"
}

function Get-CertUrlCandidates {
    if ($ServerBaseUrl) {
        $baseUrl = Normalize-BaseUrl -Url $ServerBaseUrl
        $infoUrl = "$baseUrl/site-info.json"
        Write-Host "Fetching server info from $infoUrl ..."
        $tempInfo = Join-Path $env:TEMP "archive-site-info-$([Guid]::NewGuid().ToString('n')).json"
        try {
            Download-Certificate -Url $infoUrl -Destination $tempInfo
            $info = Get-Content $tempInfo -Raw | ConvertFrom-Json
            if ($info.cert_urls) {
                return @($info.cert_urls)
            }
            if ($info.cert_url) {
                return @($info.cert_url)
            }
        } catch {
            Write-Host "site-info.json unavailable, using ServerBaseUrl directly."
        } finally {
            Remove-Item $tempInfo -Force -ErrorAction SilentlyContinue
        }
        return @("$baseUrl/cert/fullchain.pem")
    }

    if ($ServerHost) {
        return @(Build-CertUrl -HostName $ServerHost -Port $HttpsPort -Root $RootPath)
    }

    throw @"
Specify how to reach the archive server:
  -ServerBaseUrl https://SERVER:8443/archive
  -ServerHost 192.168.2.136 -HttpsPort 8443
  -CertPath C:\path\to\fullchain.pem
"@
}

Assert-Administrator

if ($CertPath) {
    if (-not (Test-Path $CertPath)) {
        throw "Certificate not found: $CertPath"
    }
    $sourcePath = (Resolve-Path $CertPath).Path
} else {
    $certUrls = Get-CertUrlCandidates
    $sourcePath = Join-Path $env:TEMP "archive-site-$([Guid]::NewGuid().ToString('n')).pem"
    Download-Certificate-FromCandidates -Urls $certUrls -Destination $sourcePath
}

Write-Host "Installing trusted root certificate:"
Write-Host "  $sourcePath"
Install-TrustedRootCertificate -Path $sourcePath

if (-not $CertPath) {
    Remove-Item $sourcePath -Force
}

Write-Host ""
Write-Host "Done. Restart the browser."
if ($ServerBaseUrl) {
    Write-Host "Open: $(Normalize-BaseUrl -Url $ServerBaseUrl)/"
} elseif ($ServerHost) {
  $suffix = if ($HttpsPort -in 443, 80) { "" } else { ":$HttpsPort" }
  Write-Host "Open: https://${ServerHost}${suffix}$($RootPath.TrimEnd('/'))/"
}
