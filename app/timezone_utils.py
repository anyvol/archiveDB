"""Timezone-aware date formatting for display."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def resolve_timezone(timezone_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


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
