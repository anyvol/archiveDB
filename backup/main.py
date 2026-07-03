"""Backup service: PostgreSQL dumps and uploaded files archives."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "/backups"))
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", "/uploads"))
RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
TOKEN = os.getenv("BACKUP_AGENT_TOKEN", "").strip()

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "archiveuser")
POSTGRES_DB = os.getenv("POSTGRES_DB", "archivedb")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

app = FastAPI(title="archiveDB backup-agent")
security = HTTPBearer(auto_error=False)


class BackupRunRequest(BaseModel):
    types: list[str]
    triggered_by: str = "system"


def _auth(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> None:
    if not TOKEN:
        return
    if credentials is None or credentials.credentials != TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


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
    _cleanup_old_backups()
    return results


def _cleanup_old_backups() -> None:
    if not BACKUP_DIR.exists():
        return
    cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
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


@app.on_event("startup")
def startup() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
