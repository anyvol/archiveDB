"""Tests for scheduled mailing config and cron matching."""

from datetime import datetime

from app.mailing_schedule import (
    MailingScheduleConfig,
    cron_matches,
    parse_address_text,
)
from app.admin.services.messaging import format_admin_email_body, ADMIN_MAIL_SIGNATURE


def test_default_mailing_schedule():
    config = MailingScheduleConfig()
    assert config.enabled is False
    assert config.cron == "0 9 * * 1"
    assert config.addresses == []


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


def test_cron_matches_monday_morning():
    # 2026-07-13 is a Monday
    moment = datetime(2026, 7, 13, 9, 0)
    assert cron_matches("0 9 * * 1", moment)
    assert not cron_matches("0 10 * * 1", moment)
    assert not cron_matches("0 9 * * 2", moment)


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
