#!/bin/sh
# Print recommended host paths for WSL2 (Windows disk) vs native Linux.

if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "# Detected WSL — store data on Windows host:"
  echo "UPLOAD_HOST_PATH=/mnt/c/ArchiveDB/uploaded_files"
  echo "BACKUP_HOST_PATH=/mnt/c/ArchiveDB/backups"
else
  echo "# Native Linux host paths:"
  echo "UPLOAD_HOST_PATH=./uploaded_files"
  echo "BACKUP_HOST_PATH=./backups"
fi
