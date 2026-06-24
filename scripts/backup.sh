#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

BACKUP_DIR="${BACKUP_DIR:-./data/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
UPLOAD_PATH="${UPLOAD_HOST_PATH:-./data/uploads}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
POSTGRES_USER="${POSTGRES_USER:-archiveuser}"
POSTGRES_DB="${POSTGRES_DB:-archivedb}"

mkdir -p "${BACKUP_DIR}"

echo "Backing up database..."
docker compose exec -T db pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" > "${BACKUP_DIR}/db_${TIMESTAMP}.sql"

if [[ -d "${UPLOAD_PATH}" ]]; then
  echo "Backing up uploaded files from ${UPLOAD_PATH}..."
  tar -czf "${BACKUP_DIR}/files_${TIMESTAMP}.tar.gz" -C "$(dirname "${UPLOAD_PATH}")" "$(basename "${UPLOAD_PATH}")"
else
  echo "Upload path not found (${UPLOAD_PATH}), skipping file backup."
fi

echo "Removing backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name 'db_*.sql' -mtime +"${RETENTION_DAYS}" -delete 2>/dev/null || true
find "${BACKUP_DIR}" -name 'files_*.tar.gz' -mtime +"${RETENTION_DAYS}" -delete 2>/dev/null || true

echo "Backup complete: ${BACKUP_DIR}"
