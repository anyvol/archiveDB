"""Unit tests for email normalization."""

from app.email_verification import normalize_email


def test_normalize_email_lowercase():
    assert normalize_email("  User@Example.COM ") == "user@example.com"
