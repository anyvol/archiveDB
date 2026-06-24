#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

HTTP_PORT="${HTTP_PORT:-80}"
HEALTH_URL="http://localhost:${HTTP_PORT}/health"

for i in $(seq 1 30); do
  if curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "Health check OK: ${HEALTH_URL}"
    exit 0
  fi
  sleep 2
done

echo "Health check failed: ${HEALTH_URL}"
docker compose ps
exit 1
