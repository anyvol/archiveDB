#!/bin/sh
set -e

echo "Waiting for database..."
until python -c "
import os
from sqlalchemy import create_engine, text
from app.migration_config import resolve_alembic_url

engine = create_engine(resolve_alembic_url(), pool_pre_ping=True)
with engine.connect() as conn:
    conn.execute(text('SELECT 1'))
engine.dispose()
" 2>/dev/null; do
    echo "Database not ready, retrying in 2s..."
    sleep 2
done

echo "Running migrations..."
python run_migrations.py upgrade head

echo "Verifying database schema..."
python -c "from app.migration_config import verify_schema; verify_schema(); print('Schema OK')"

WORKERS="${UVICORN_WORKERS:-2}"
echo "Starting uvicorn with ${WORKERS} worker(s)..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WORKERS}"
