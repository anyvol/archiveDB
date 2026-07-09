"""Backup schedule settings stored in system settings."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings_store import SETTING_BACKUP_SCHEDULE, get_setting, set_setting

ScheduleMode = Literal["cron", "interval"]


class BackupScheduleConfig(BaseModel):
    enabled: bool = False
    mode: ScheduleMode = "cron"
    cron: str = "0 2 * * *"
    interval_hours: int = Field(default=24, ge=1, le=168)
    backup_db: bool = True
    backup_files: bool = True


DEFAULT_BACKUP_SCHEDULE = BackupScheduleConfig()


def _normalize_schedule(raw: Any) -> BackupScheduleConfig:
    if not isinstance(raw, dict):
        return DEFAULT_BACKUP_SCHEDULE.model_copy()
    try:
        return BackupScheduleConfig.model_validate(raw)
    except Exception:
        return DEFAULT_BACKUP_SCHEDULE.model_copy()


async def get_backup_schedule(session: AsyncSession) -> BackupScheduleConfig:
    raw = await get_setting(session, SETTING_BACKUP_SCHEDULE, None)
    return _normalize_schedule(raw)


async def save_backup_schedule(
    session: AsyncSession,
    config: BackupScheduleConfig,
    *,
    updated_by_id: int | None = None,
) -> BackupScheduleConfig:
    normalized = _normalize_schedule(config.model_dump())
    await set_setting(
        session,
        SETTING_BACKUP_SCHEDULE,
        normalized.model_dump(),
        updated_by_id=updated_by_id,
    )
    return normalized
