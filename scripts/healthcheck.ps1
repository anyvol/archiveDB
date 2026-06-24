#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
Set-Location $ProjectDir

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return }
    Get-Content $Path | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
        $name, $value = $_ -split '=', 2
        Set-Item -Path "env:$name" -Value $value.Trim()
    }
}

Import-DotEnv (Join-Path $ProjectDir ".env")

$port = if ($env:HTTP_PORT) { $env:HTTP_PORT } else { "80" }
$healthUrl = "http://localhost:$port/health"

for ($i = 1; $i -le 30; $i++) {
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) {
            Write-Host "Health check OK: $healthUrl"
            exit 0
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

Write-Error "Health check failed: $healthUrl"
