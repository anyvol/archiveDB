#!/bin/sh
set -e

echo "Waiting for database..."
until python -c "
import os, sys
from sqlalchemy import create_engine, text
url = os.environ['DATABASE_URL'].replace('+asyncpg', '+psycopg2')
engine = create_engine(url, pool_pre_ping=True)
with engine.connect() as conn:
    conn.execute(text('SELECT 1'))
" 2>/dev/null; do
    echo "Database not ready, retrying in 2s..."
    sleep 2
done

echo "Running migrations..."
python run_migrations.py upgrade head

WORKERS="${UVICORN_WORKERS:-2}"
echo "Starting uvicorn with ${WORKERS} worker(s)..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WORKERS}"
