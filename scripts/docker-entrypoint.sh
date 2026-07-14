#!/bin/sh
set -e

echo "=== Database setup ==="
echo "Alembic heads:"
alembic heads || true
echo "Alembic current (before upgrade):"
alembic current || true

echo "Running Alembic upgrade..."
if ! alembic upgrade head; then
  echo "ERROR: alembic upgrade head failed."
  echo "If the database points at a revision not present in this image"
  echo "(e.g. after switching off an unmerged feature branch), restore that"
  echo "migration file or stamp back to a known revision:"
  echo "  docker compose exec api alembic stamp <known_revision>"
  echo "Then restart the API. Known head files live in alembic/versions/."
  exit 1
fi

echo "Alembic current (after upgrade):"
alembic current || true

echo "Verifying / repairing 0.12.0 schema..."
python3 scripts/ensure_schema.py

echo "=== Database setup complete ==="
echo "Starting API server..."
exec "$@"
