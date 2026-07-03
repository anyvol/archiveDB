"""Tests for password reset one-time codes."""

import hashlib

from app.password_reset import _hash_token


def test_hash_token_is_sha256():
    assert _hash_token("123456") == hashlib.sha256(b"123456").hexdigest()
