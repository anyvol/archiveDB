"""Timezone-aware date formatting for display."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def resolve_timezone(timezone_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def parse_user_date(value: str | date | datetime | None) -> datetime | None:
    """Parse a user-facing date string (DD.MM.YYYY or YYYY-MM-DD) into datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def normalize_date_string(value: str | date | datetime | None) -> str | None:
    """Normalize a date to YYYY-MM-DD for storage/forms, or None if empty/invalid."""
    parsed = parse_user_date(value)
    if parsed is None:
        return None
    return parsed.strftime("%Y-%m-%d")


def format_date(value: date | datetime | str | None, timezone_name: str | None = "UTC") -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return "—"
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed.strftime("%d.%m.%Y")
            except ValueError:
                continue
        return value
    if isinstance(value, datetime):
        tz = resolve_timezone(timezone_name)
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo("UTC"))
        value = value.astimezone(tz)
    return value.strftime("%d.%m.%Y")


def format_datetime(value: datetime | None, timezone_name: str | None = "UTC") -> str:
    if value is None:
        return "—"
    tz = resolve_timezone(timezone_name)
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    value = value.astimezone(tz)
    return value.strftime("%d.%m.%Y %H:%M")


def date_input_value(value: date | datetime | str | None) -> str:
    """Return YYYY-MM-DD for HTML date inputs / ru-date storage, or empty string."""
    return normalize_date_string(value) or ""


def common_timezones() -> list[str]:
    return [
        "UTC",
        "Europe/Moscow",
        "Europe/Kaliningrad",
        "Europe/Samara",
        "Asia/Yekaterinburg",
        "Asia/Novosibirsk",
        "Asia/Krasnoyarsk",
        "Asia/Irkutsk",
        "Asia/Yakutsk",
        "Asia/Vladivostok",
        "Asia/Magadan",
        "Asia/Kamchatka",
    ]
