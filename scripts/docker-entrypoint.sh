#!/bin/sh
set -e

echo "=== Database setup ==="
echo "Alembic heads:"
alembic heads || true
echo "Alembic current (before upgrade):"
alembic current || true

echo "Running Alembic upgrade..."
alembic upgrade head

echo "Alembic current (after upgrade):"
alembic current || true

echo "Verifying / repairing 0.12.0 schema..."
python3 scripts/ensure_schema.py

echo "=== Database setup complete ==="
echo "Starting API server..."
exec "$@"
