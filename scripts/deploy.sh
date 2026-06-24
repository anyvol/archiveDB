#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

SKIP_BACKUP=false
SKIP_PULL=false

for arg in "$@"; do
  case "${arg}" in
    --skip-backup) SKIP_BACKUP=true ;;
    --skip-pull) SKIP_PULL=true ;;
  esac
done

if [[ ! -f .env ]]; then
  echo "Error: .env not found. Copy .env.example to .env and configure it."
  exit 1
fi

if [[ "${SKIP_BACKUP}" == false ]]; then
  bash "${SCRIPT_DIR}/backup.sh"
fi

if [[ "${SKIP_PULL}" == false ]] && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Pulling latest changes..."
  git pull --ff-only
fi

echo "Building and starting services..."
docker compose build api proxy
docker compose up -d

echo "Applying migrations..."
docker compose exec -T api python run_migrations.py upgrade head

echo "Running health check..."
bash "${SCRIPT_DIR}/healthcheck.sh"

echo "Deploy complete. Archive service: http://localhost/archive/documents"
