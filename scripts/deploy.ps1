#Requires -Version 5.1
param(
    [switch]$SkipBackup,
    [switch]$SkipPull
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
Set-Location $ProjectDir

if (-not (Test-Path ".env")) {
    Write-Error ".env not found. Copy .env.example to .env and configure it."
}

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

if (-not $SkipBackup) {
    & (Join-Path $ScriptDir "backup.ps1")
}

if (-not $SkipPull) {
    if (Test-Path ".git") {
        Write-Host "Pulling latest changes..."
        git pull --ff-only
    }
}

Write-Host "Building and starting services..."
docker compose build api proxy
docker compose up -d

Write-Host "Applying migrations..."
docker compose exec -T api python run_migrations.py upgrade head

Write-Host "Running health check..."
& (Join-Path $ScriptDir "healthcheck.ps1")

$port = if ($env:HTTP_PORT) { $env:HTTP_PORT } else { "80" }
Write-Host "Deploy complete. Archive service: http://localhost:$port/archive/documents"
