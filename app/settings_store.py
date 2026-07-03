"""Persistent system settings stored in PostgreSQL."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import SystemSetting

SETTING_APP_TIMEZONE = "app_timezone"
SETTING_SMTP = "smtp"
DEFAULT_APP_TIMEZONE = "UTC"


async def get_setting(session: AsyncSession, key: str, default: Any = None) -> Any:
    result = await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    row = result.scalars().first()
    if row is None:
        return default
    return row.value


async def set_setting(
    session: AsyncSession,
    key: str,
    value: Any,
    updated_by_id: int | None = None,
) -> None:
    result = await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    row = result.scalars().first()
    if row is None:
        session.add(
            SystemSetting(
                key=key,
                value=value,
                updated_at=datetime.utcnow(),
                updated_by_id=updated_by_id,
            )
        )
    else:
        row.value = value
        row.updated_at = datetime.utcnow()
        row.updated_by_id = updated_by_id
    await session.commit()


async def get_app_timezone(session: AsyncSession) -> str:
    value = await get_setting(session, SETTING_APP_TIMEZONE, DEFAULT_APP_TIMEZONE)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return DEFAULT_APP_TIMEZONE


async def get_smtp_config(session: AsyncSession) -> dict[str, Any]:
    value = await get_setting(session, SETTING_SMTP, {})
    return value if isinstance(value, dict) else {}
