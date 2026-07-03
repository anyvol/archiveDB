"""Encrypt sensitive settings (e.g. SMTP password) at rest."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.auth import SECRET_KEY


def _fernet() -> Fernet:
    digest = hashlib.sha256(SECRET_KEY.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
