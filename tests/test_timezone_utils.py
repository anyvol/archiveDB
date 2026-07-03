"""Tests for timezone formatting and filter parsing."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.timezone_utils import (
    format_datetime,
    format_datetime_date,
    format_datetime_short,
    parse_filter_date,
)


def test_format_datetime_short_converts_utc_to_moscow():
    utc = datetime(2026, 7, 3, 21, 30)
    assert format_datetime_short(utc, "Europe/Moscow") == "2026-07-04 00:30"


def test_format_datetime_date_converts_utc_to_moscow():
    utc = datetime(2026, 7, 3, 21, 30)
    assert format_datetime_date(utc, "Europe/Moscow") == "2026-07-04"


def test_format_datetime_none_returns_dash():
    assert format_datetime(None, "UTC") == "—"
    assert format_datetime_short(None, "UTC") == "—"


def test_parse_filter_date_start_of_day_in_timezone():
    utc = parse_filter_date("2026-07-03", "Europe/Moscow")
    assert utc == datetime(2026, 7, 2, 21, 0)


def test_parse_filter_date_end_of_day_in_timezone():
    utc = parse_filter_date("2026-07-03", "Europe/Moscow", end_of_day=True)
    assert utc == datetime(2026, 7, 3, 20, 59, 59, 999999)


def test_parse_filter_date_invalid_returns_none():
    assert parse_filter_date("not-a-date", "UTC") is None
    assert parse_filter_date(None, "UTC") is None
