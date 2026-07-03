"""Timezone-aware datetime formatting for display."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def resolve_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def to_local(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(resolve_timezone(timezone_name))


def format_datetime(value: datetime | None, timezone_name: str) -> str:
    if value is None:
        return "—"
    return to_local(value, timezone_name).strftime("%d.%m.%Y %H:%M:%S")


def format_datetime_short(value: datetime | None, timezone_name: str) -> str:
    if value is None:
        return "—"
    return to_local(value, timezone_name).strftime("%Y-%m-%d %H:%M")


def format_datetime_date(value: datetime | None, timezone_name: str) -> str:
    if value is None:
        return "—"
    return to_local(value, timezone_name).strftime("%Y-%m-%d")


def parse_filter_date(value: str | None, timezone_name: str, *, end_of_day: bool = False) -> datetime | None:
    """Parse a date filter string as start/end of day in admin TZ, return naive UTC."""
    if not value:
        return None
    tz = resolve_timezone(timezone_name)
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%d.%m.%Y"):
        try:
            parsed = datetime.strptime(value.strip(), fmt)
            break
        except ValueError:
            parsed = None
    if parsed is None:
        return None
    if end_of_day:
        local = datetime.combine(parsed.date(), time(23, 59, 59, 999999), tzinfo=tz)
    else:
        local = datetime.combine(parsed.date(), time.min, tzinfo=tz)
    return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


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
