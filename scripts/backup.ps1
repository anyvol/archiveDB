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

$BackupDir = if ($env:BACKUP_DIR) { $env:BACKUP_DIR } else { "./data/backups" }
$RetentionDays = if ($env:BACKUP_RETENTION_DAYS) { [int]$env:BACKUP_RETENTION_DAYS } else { 14 }
$UploadPath = if ($env:UPLOAD_HOST_PATH) { $env:UPLOAD_HOST_PATH } else { "./data/uploads" }
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$PostgresUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "archiveuser" }
$PostgresDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "archivedb" }

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

Write-Host "Backing up database..."
$sqlFile = Join-Path $BackupDir "db_$Timestamp.sql"
docker compose exec -T db pg_dump -U $PostgresUser $PostgresDb | Set-Content -Path $sqlFile -Encoding utf8

if (Test-Path $UploadPath) {
    Write-Host "Backing up uploaded files from $UploadPath..."
    $tarFile = Join-Path $BackupDir "files_$Timestamp.tar.gz"
    $parent = Split-Path -Parent (Resolve-Path $UploadPath)
    $name = Split-Path -Leaf (Resolve-Path $UploadPath)
    tar -czf $tarFile -C $parent $name
} else {
    Write-Host "Upload path not found ($UploadPath), skipping file backup."
}

Write-Host "Removing backups older than $RetentionDays days..."
$cutoff = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem $BackupDir -Filter "db_*.sql" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt $cutoff } | Remove-Item -Force
Get-ChildItem $BackupDir -Filter "files_*.tar.gz" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt $cutoff } | Remove-Item -Force

Write-Host "Backup complete: $BackupDir"
