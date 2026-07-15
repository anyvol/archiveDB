"""Tests for scheduled mailing config and cron matching."""

from datetime import date, datetime

from app.mailing_schedule import (
    MailingScheduleConfig,
    cron_matches,
    is_before_or_on_stop_date,
    parse_address_text,
)
from app.admin.services.messaging import format_admin_email_body, ADMIN_MAIL_SIGNATURE


def test_default_mailing_schedule():
    config = MailingScheduleConfig()
    assert config.enabled is False
    assert config.cron == "0 9 * * 1"
    assert config.addresses == []
    assert config.stop_date is None


def test_parse_address_text():
    raw = "a@example.com\nb@example.com; c@example.com, d@example.com"
    assert parse_address_text(raw) == [
        "a@example.com",
        "b@example.com",
        "c@example.com",
        "d@example.com",
    ]


def test_mailing_schedule_normalizes_addresses():
    config = MailingScheduleConfig(
        addresses=["A@Example.COM", "bad", "a@example.com", "other@test.ru"]
    )
    assert config.addresses == ["a@example.com", "other@test.ru"]


def test_mailing_schedule_rejects_bad_cron():
    try:
        MailingScheduleConfig(cron="0 9 * *")
        assert False, "expected validation error"
    except Exception:
        pass


def test_mailing_schedule_stop_date_normalization():
    config = MailingScheduleConfig(stop_date="15.07.2026")
    assert config.stop_date == "2026-07-15"
    empty = MailingScheduleConfig(stop_date="")
    assert empty.stop_date is None


def test_mailing_schedule_rejects_bad_stop_date():
    try:
        MailingScheduleConfig(stop_date="not-a-date")
        assert False, "expected validation error"
    except Exception:
        pass


def test_is_before_or_on_stop_date_inclusive():
    config = MailingScheduleConfig(stop_date="2026-07-15")
    assert is_before_or_on_stop_date(config, date(2026, 7, 15))
    assert is_before_or_on_stop_date(config, datetime(2026, 7, 15, 23, 59))
    assert not is_before_or_on_stop_date(config, date(2026, 7, 16))
    open_ended = MailingScheduleConfig(stop_date=None)
    assert is_before_or_on_stop_date(open_ended, date(2099, 1, 1))


def test_cron_matches_monday_morning():
    # 2026-07-13 is a Monday
    moment = datetime(2026, 7, 13, 9, 0)
    assert cron_matches("0 9 * * 1", moment)
    assert not cron_matches("0 10 * * 1", moment)
    assert not cron_matches("0 9 * * 2", moment)


def test_cron_matches_weekday_range_evening():
    # Mon–Fri 17:30 — 2026-07-13 Monday, 2026-07-18 Saturday
    monday = datetime(2026, 7, 13, 17, 30)
    friday = datetime(2026, 7, 17, 17, 30)
    saturday = datetime(2026, 7, 18, 17, 30)
    monday_wrong_minute = datetime(2026, 7, 13, 17, 0)
    assert cron_matches("30 17 * * 1-5", monday)
    assert cron_matches("30 17 * * 1-5", friday)
    assert not cron_matches("30 17 * * 1-5", saturday)
    assert not cron_matches("30 17 * * 1-5", monday_wrong_minute)


def test_cron_matches_list_and_step():
    tuesday = datetime(2026, 7, 14, 9, 0)  # Tue
    thursday = datetime(2026, 7, 16, 9, 0)  # Thu
    wednesday = datetime(2026, 7, 15, 9, 0)  # Wed
    assert cron_matches("0 9 * * 2,4", tuesday)
    assert cron_matches("0 9 * * 2,4", thursday)
    assert not cron_matches("0 9 * * 2,4", wednesday)
    assert cron_matches("*/15 9 * * *", datetime(2026, 7, 13, 9, 0))
    assert cron_matches("*/15 9 * * *", datetime(2026, 7, 13, 9, 30))
    assert not cron_matches("*/15 9 * * *", datetime(2026, 7, 13, 9, 10))


def test_format_admin_email_body_default_signature():
    text = format_admin_email_body("Hello")
    assert text.startswith("Hello")
    assert ADMIN_MAIL_SIGNATURE.strip() in text


def test_format_admin_email_body_custom_signature():
    text = format_admin_email_body("Hello", signature="С уважением,\nИван")
    assert text == "Hello\n\n--\nС уважением,\nИван"


def test_format_admin_email_body_empty_signature():
    text = format_admin_email_body("Hello", signature="")
    assert text == "Hello"
