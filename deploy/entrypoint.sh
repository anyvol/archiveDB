#!/bin/sh
set -e

export PYTHONIOENCODING=utf-8
export LANG=C.UTF-8

echo "=== Archive API startup ==="

echo "Waiting for database..."
until python -c "
from sqlalchemy import create_engine, text
from app.migration_config import resolve_alembic_url

url = resolve_alembic_url()
print(f'Database reachable at: {url.split(\"@\")[-1]}')
engine = create_engine(url, pool_pre_ping=True)
with engine.connect() as conn:
    conn.execute(text('SELECT 1'))
engine.dispose()
"; do
    echo "Database not ready, retrying in 2s..."
    sleep 2
done

echo "Running migrations..."
python run_migrations.py upgrade head

WORKERS="${UVICORN_WORKERS:-2}"
echo "Starting uvicorn with ${WORKERS} worker(s)..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WORKERS}"
