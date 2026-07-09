"""Backup service: PostgreSQL dumps and uploaded files archives."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "/backups"))
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", "/uploads"))
RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
TOKEN = os.getenv("BACKUP_AGENT_TOKEN", "").strip()
SCHEDULE_FILE = BACKUP_DIR / "schedule.json"

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "archiveuser")
POSTGRES_DB = os.getenv("POSTGRES_DB", "archivedb")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

app = FastAPI(title="archiveDB backup-agent")
security = HTTPBearer(auto_error=False)

_schedule_lock = asyncio.Lock()
_last_auto_run_at: datetime | None = None


class BackupRunRequest(BaseModel):
    types: list[str]
    triggered_by: str = "system"


class BackupScheduleRequest(BaseModel):
    enabled: bool = False
    mode: Literal["cron", "interval"] = "cron"
    cron: str = "0 2 * * *"
    interval_hours: int = Field(default=24, ge=1, le=168)
    backup_db: bool = True
    backup_files: bool = True
    retention_days: int = Field(default=30, ge=1, le=365)


def _auth(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> None:
    if not TOKEN:
        return
    if credentials is None or credentials.credentials != TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _default_schedule() -> dict:
    env_cron = os.getenv("BACKUP_SCHEDULE", "0 2 * * *").strip()
    return {
        "enabled": bool(env_cron),
        "mode": "cron",
        "cron": env_cron or "0 2 * * *",
        "interval_hours": 24,
        "backup_db": True,
        "backup_files": True,
        "retention_days": RETENTION_DAYS,
    }


def _retention_days(schedule: dict | None = None) -> int:
    if schedule and schedule.get("retention_days"):
        try:
            return max(1, min(int(schedule["retention_days"]), 365))
        except (TypeError, ValueError):
            pass
    return RETENTION_DAYS


def _load_schedule() -> dict:
    if SCHEDULE_FILE.exists():
        try:
            data = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {**_default_schedule(), **data}
        except Exception:
            pass
    return _default_schedule()


def _save_schedule(data: dict) -> dict:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    merged = {**_default_schedule(), **data}
    SCHEDULE_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_backup(types: list[str], triggered_by: str) -> list[dict]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    batch_dir = BACKUP_DIR / stamp
    batch_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    env = os.environ.copy()
    if POSTGRES_PASSWORD:
        env["PGPASSWORD"] = POSTGRES_PASSWORD

    if "db" in types:
        out = batch_dir / "db.dump"
        cmd = [
            "pg_dump",
            "-Fc",
            "-h", POSTGRES_HOST,
            "-U", POSTGRES_USER,
            "-f", str(out),
            POSTGRES_DB,
        ]
        subprocess.run(cmd, check=True, env=env)
        backup_id = f"{stamp}_db"
        results.append(
            {
                "backup_id": backup_id,
                "backup_type": "db",
                "file_path": str(out),
                "size_bytes": out.stat().st_size,
                "status": "completed",
                "checksum_sha256": _sha256(out),
                "triggered_by": triggered_by,
            }
        )

    if "files" in types:
        out = batch_dir / "files.tar.gz"
        subprocess.run(["tar", "-czf", str(out), "-C", str(UPLOADS_DIR), "."], check=True)
        backup_id = f"{stamp}_files"
        results.append(
            {
                "backup_id": backup_id,
                "backup_type": "files",
                "file_path": str(out),
                "size_bytes": out.stat().st_size,
                "status": "completed",
                "checksum_sha256": _sha256(out),
                "triggered_by": triggered_by,
            }
        )

    manifest = batch_dir / "manifest.json"
    manifest.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    _cleanup_old_backups(_load_schedule())
    return results


def _cleanup_old_backups(schedule: dict | None = None) -> None:
    if not BACKUP_DIR.exists():
        return
    retention = _retention_days(schedule)
    cutoff = datetime.utcnow() - timedelta(days=retention)
    for child in BACKUP_DIR.iterdir():
        if not child.is_dir():
            continue
        try:
            created = datetime.strptime(child.name[:16], "%Y-%m-%d_%H%M")
        except ValueError:
            continue
        if created < cutoff:
            for p in child.rglob("*"):
                if p.is_file():
                    p.unlink(missing_ok=True)
            for p in sorted(child.rglob("*"), reverse=True):
                if p.is_dir():
                    p.rmdir()
            child.rmdir()


def _list_backups() -> list[dict]:
    items: list[dict] = []
    if not BACKUP_DIR.exists():
        return items
    for batch in sorted(BACKUP_DIR.iterdir(), reverse=True):
        manifest = batch / "manifest.json"
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(data, list):
                items.extend(data)
            continue
        for path in batch.iterdir():
            if path.suffix == ".dump":
                items.append({"backup_id": f"{batch.name}_db", "backup_type": "db", "file_path": str(path), "size_bytes": path.stat().st_size, "status": "completed"})
            elif path.name == "files.tar.gz":
                items.append({"backup_id": f"{batch.name}_files", "backup_type": "files", "file_path": str(path), "size_bytes": path.stat().st_size, "status": "completed"})
    return items


def _cron_matches(cron: str, moment: datetime) -> bool:
    parts = cron.strip().split()
    if len(parts) != 5:
        return False
    minute, hour, dom, month, dow = parts

    def _match(field: str, value: int) -> bool:
        if field == "*":
            return True
        if field.isdigit():
            return int(field) == value
        if field.startswith("*/"):
            step = int(field[2:])
            return value % step == 0
        return False

    return (
        _match(minute, moment.minute)
        and _match(hour, moment.hour)
        and _match(dom, moment.day)
        and _match(month, moment.month)
        and (dow == "*" or _match(dow, moment.weekday()))
    )


def _schedule_types(schedule: dict) -> list[str]:
    types: list[str] = []
    if schedule.get("backup_db", True):
        types.append("db")
    if schedule.get("backup_files", True):
        types.append("files")
    return types


def _interval_due(schedule: dict, last_run: datetime | None, now: datetime) -> bool:
    if last_run is None:
        return True
    hours = int(schedule.get("interval_hours", 24))
    return now - last_run >= timedelta(hours=hours)


async def _auto_backup_loop() -> None:
    global _last_auto_run_at
    while True:
        try:
            await asyncio.sleep(60)
            schedule = _load_schedule()
            if not schedule.get("enabled"):
                continue

            types = _schedule_types(schedule)
            if not types:
                continue

            now = datetime.utcnow()
            due = False
            if schedule.get("mode") == "interval":
                due = _interval_due(schedule, _last_auto_run_at, now)
            else:
                due = _cron_matches(str(schedule.get("cron", "0 2 * * *")), now)

            if not due:
                continue

            async with _schedule_lock:
                if schedule.get("mode") == "interval":
                    if not _interval_due(schedule, _last_auto_run_at, now):
                        continue
                elif not _cron_matches(str(schedule.get("cron", "0 2 * * *")), now):
                    continue

                await asyncio.to_thread(_run_backup, types, "auto-schedule")
                _last_auto_run_at = now
        except asyncio.CancelledError:
            raise
        except Exception:
            continue


@app.on_event("startup")
async def startup() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if not SCHEDULE_FILE.exists():
        _save_schedule(_default_schedule())
    app.state.auto_backup_task = asyncio.create_task(_auto_backup_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    task = getattr(app.state, "auto_backup_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@app.post("/backup/run")
def run_backup(body: BackupRunRequest, _: None = Depends(_auth)) -> dict:
    allowed = [t for t in body.types if t in ("db", "files")]
    if not allowed:
        raise HTTPException(status_code=400, detail="No valid backup types")
    results = _run_backup(allowed, body.triggered_by)
    return {"results": results}


@app.get("/backup/list")
def list_backups(_: None = Depends(_auth)) -> list[dict]:
    return _list_backups()


@app.get("/backup/schedule")
def get_schedule(_: None = Depends(_auth)) -> dict:
    return _load_schedule()


@app.post("/backup/schedule")
def set_schedule(body: BackupScheduleRequest, _: None = Depends(_auth)) -> dict:
    return _save_schedule(body.model_dump())
