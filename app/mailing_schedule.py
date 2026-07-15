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


def _expand_cron_field(field: str, min_v: int, max_v: int) -> set[int] | None:
    """Expand a cron field to allowed integers. None means «any» (* only).

    Supports: ``*``, ``N``, ``N-M``, ``*/S``, ``N-M/S``, and comma lists.
    """
    field = field.strip()
    if field == "*":
        return None

    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if "/" in part:
            base, step_s = part.split("/", 1)
            if not step_s.isdigit():
                continue
            step = int(step_s)
            if step <= 0:
                continue
        else:
            base = part

        if base == "*":
            start, end = min_v, max_v
        elif "-" in base:
            left, right = base.split("-", 1)
            if not (left.isdigit() and right.isdigit()):
                continue
            start, end = int(left), int(right)
            if start > end:
                continue
        elif base.isdigit():
            start = end = int(base)
        else:
            continue

        for value in range(start, end + 1, step):
            if min_v <= value <= max_v:
                values.add(value)
    return values


def cron_matches(cron: str, moment) -> bool:
    """Match standard 5-field cron against a local datetime (minute hour dom month dow).

    Day-of-week uses standard cron numbering: 0 or 7 = Sunday, 1 = Monday … 6 = Saturday.
    Supports ranges/lists/steps, e.g. ``30 17 * * 1-5``.
    """
    parts = cron.strip().split()
    if len(parts) != 5:
        return False
    minute, hour, dom, month, dow = parts

    def _match(field: str, value: int, min_v: int, max_v: int) -> bool:
        allowed = _expand_cron_field(field, min_v, max_v)
        return allowed is None or value in allowed

    # Python weekday: Mon=0 … Sun=6 → cron: Sun=0, Mon=1 … Sat=6
    cron_dow = (moment.weekday() + 1) % 7
    dow_allowed = _expand_cron_field(dow, 0, 7)
    if dow_allowed is None:
        dow_ok = True
    else:
        if 7 in dow_allowed:
            dow_allowed = set(dow_allowed)
            dow_allowed.add(0)
            dow_allowed.discard(7)
        dow_ok = cron_dow in dow_allowed

    return (
        _match(minute, moment.minute, 0, 59)
        and _match(hour, moment.hour, 0, 23)
        and _match(dom, moment.day, 1, 31)
        and _match(month, moment.month, 1, 12)
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
