"""HTTP client for the backup sidecar."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from datetime import datetime

from app.config import BACKUP_AGENT_TOKEN, BACKUP_AGENT_URL, BACKUP_HOST_PATH
from app.models import BackupRecord


def _headers() -> dict[str, str]:
    if not BACKUP_AGENT_TOKEN:
        return {}
    return {"Authorization": f"Bearer {BACKUP_AGENT_TOKEN}"}


async def trigger_backup(types: list[str], triggered_by: str) -> dict:
    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(
            f"{BACKUP_AGENT_URL}/backup/run",
            json={"types": types, "triggered_by": triggered_by},
            headers=_headers(),
        )
        response.raise_for_status()
        return response.json()


async def get_remote_backup_schedule() -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{BACKUP_AGENT_URL}/backup/schedule", headers=_headers())
            response.raise_for_status()
            return response.json()
    except Exception:
        return None


async def apply_remote_backup_schedule(schedule: dict) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BACKUP_AGENT_URL}/backup/schedule",
            json=schedule,
            headers=_headers(),
        )
        response.raise_for_status()
        return response.json()


async def list_remote_backups() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{BACKUP_AGENT_URL}/backup/list", headers=_headers())
            response.raise_for_status()
            return response.json()
    except Exception:
        return []


async def sync_backup_records(session: AsyncSession, remote_items: list[dict]) -> None:
    if not remote_items:
        return
    for item in remote_items:
        backup_id = item.get("backup_id")
        if not backup_id:
            continue
        result = await session.execute(select(BackupRecord).where(BackupRecord.backup_id == backup_id))
        row = result.scalars().first()
        created_at = None
        raw_created = item.get("created_at")
        if raw_created:
            try:
                created_at = datetime.fromisoformat(str(raw_created).replace("Z", "+00:00"))
            except ValueError:
                created_at = None
        if row is None:
            session.add(
                BackupRecord(
                    backup_id=backup_id,
                    backup_type=item.get("backup_type", "unknown"),
                    file_path=item.get("file_path", ""),
                    size_bytes=item.get("size_bytes"),
                    status=item.get("status", "completed"),
                    checksum_sha256=item.get("checksum_sha256"),
                    triggered_by=item.get("triggered_by"),
                    created_at=created_at or datetime.utcnow(),
                )
            )
        else:
            row.size_bytes = item.get("size_bytes", row.size_bytes)
            row.status = item.get("status", row.status)
            row.checksum_sha256 = item.get("checksum_sha256", row.checksum_sha256)
            row.triggered_by = item.get("triggered_by", row.triggered_by)
            if created_at:
                row.created_at = created_at
    await session.commit()


def backup_host_path_display() -> str:
    return BACKUP_HOST_PATH
