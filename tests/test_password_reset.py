"""Tests for password reset URL generation."""

from app.password_reset import _public_base_url


def test_public_base_url_forces_https_from_http_request_base():
    url = _public_base_url("http://example.com/archive")
    assert url == "https://example.com/archive"


def test_public_base_url_keeps_https():
    url = _public_base_url("https://example.com/archive")
    assert url == "https://example.com/archive"
