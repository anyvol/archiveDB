# Windows: create ArchiveDB folders on host and print .env lines for WSL
$base = "C:\ArchiveDB"
New-Item -ItemType Directory -Force -Path "$base\uploaded_files", "$base\backups" | Out-Null
Write-Host "UPLOAD_HOST_PATH=/mnt/c/ArchiveDB/uploaded_files"
Write-Host "BACKUP_HOST_PATH=/mnt/c/ArchiveDB/backups"
