"""Scheduled mailing settings stored in system settings."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings_store import get_setting, set_setting
from app.timezone_utils import normalize_date_string

SETTING_MAILING_SCHEDULE = "mailing_schedule"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(address: str) -> bool:
    return bool(_EMAIL_RE.match(address.strip().lower()))


class MailingScheduleConfig(BaseModel):
    enabled: bool = False
    cron: str = "0 9 * * 1"
    addresses: list[str] = Field(default_factory=list)
    signature: str = ""
    subject: str = ""
    body: str = ""
    stop_date: str | None = None
    last_sent_at: str | None = None
    last_sent_count: int = 0
    last_error: str | None = None
    last_run_minute: str | None = None

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, value: str) -> str:
        parts = value.strip().split()
        if len(parts) != 5:
            raise ValueError("cron must have 5 fields")
        return value.strip()

    @field_validator("stop_date", mode="before")
    @classmethod
    def validate_stop_date(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        normalized = normalize_date_string(text)
        if not normalized:
            raise ValueError("invalid stop_date")
        return normalized

    @field_validator("addresses")
    @classmethod
    def normalize_addresses(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for raw in value:
            addr = raw.strip().lower()
            if not addr or addr in seen:
                continue
            if not is_valid_email(addr):
                continue
            seen.add(addr)
            result.append(addr)
        return result


DEFAULT_MAILING_SCHEDULE = MailingScheduleConfig()


def parse_address_text(raw: str) -> list[str]:
    """Split addresses entered as newlines, commas, or semicolons."""
    parts = re.split(r"[\n,;]+", raw or "")
    return [p.strip() for p in parts if p.strip()]


def parse_stop_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def is_before_or_on_stop_date(config: MailingScheduleConfig, moment: datetime | date) -> bool:
    """Return True if mailing is still allowed for this local day (stop_date inclusive)."""
    stop = parse_stop_date(config.stop_date)
    if stop is None:
        return True
    local_day = moment.date() if isinstance(moment, datetime) else moment
    return local_day <= stop


def cron_matches(cron: str, moment) -> bool:
    """Match standard 5-field cron against a local datetime (minute hour dom month dow).

    Day-of-week uses standard cron numbering: 0 or 7 = Sunday, 1 = Monday … 6 = Saturday.
    """
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
            try:
                step = int(field[2:])
            except ValueError:
                return False
            if step <= 0:
                return False
            return value % step == 0
        return False

    # Python weekday: Mon=0 … Sun=6 → cron: Sun=0, Mon=1 … Sat=6
    cron_dow = (moment.weekday() + 1) % 7
    dow_ok = dow == "*" or _match(dow, cron_dow) or (dow == "7" and cron_dow == 0)

    return (
        _match(minute, moment.minute)
        and _match(hour, moment.hour)
        and _match(dom, moment.day)
        and _match(month, moment.month)
        and dow_ok
    )


def _normalize_schedule(raw: Any) -> MailingScheduleConfig:
    if not isinstance(raw, dict):
        return DEFAULT_MAILING_SCHEDULE.model_copy()
    try:
        return MailingScheduleConfig.model_validate(raw)
    except Exception:
        return DEFAULT_MAILING_SCHEDULE.model_copy()


async def get_mailing_schedule(session: AsyncSession) -> MailingScheduleConfig:
    raw = await get_setting(session, SETTING_MAILING_SCHEDULE, None)
    return _normalize_schedule(raw)


async def save_mailing_schedule(
    session: AsyncSession,
    config: MailingScheduleConfig,
    *,
    updated_by_id: int | None = None,
) -> MailingScheduleConfig:
    normalized = _normalize_schedule(config.model_dump())
    await set_setting(
        session,
        SETTING_MAILING_SCHEDULE,
        normalized.model_dump(),
        updated_by_id=updated_by_id,
    )
    return normalized
