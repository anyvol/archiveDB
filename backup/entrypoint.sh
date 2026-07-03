#!/bin/sh
set -e

SCHEDULE="${BACKUP_SCHEDULE:-0 2 * * *}"

if [ -n "$BACKUP_SCHEDULE" ]; then
  echo "$SCHEDULE root cd /app && python3 -c \"from main import _run_backup; _run_backup(['db','files'],'cron')\"" > /etc/cron.d/backup-cron
  chmod 0644 /etc/cron.d/backup-cron
  crontab /etc/cron.d/backup-cron
  cron
fi

exec uvicorn main:app --host 0.0.0.0 --port 9002
