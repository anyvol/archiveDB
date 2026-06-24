from datetime import timedelta

import pytest
from jose import jwt

from app.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    get_password_hash,
    verify_password,
)
from app.config import app_path, cookie_path
from app.models import User, UserRole


def test_password_hash_roundtrip():
    hashed = get_password_hash("secure-password-123")
    assert verify_password("secure-password-123", hashed)
    assert not verify_password("wrong-password", hashed)


def test_create_access_token_decodes():
    token = create_access_token({"sub": "testuser"})
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "testuser"
    assert "exp" in payload


def test_create_access_token_custom_expiry():
    token = create_access_token({"sub": "testuser"}, expires_delta=timedelta(minutes=5))
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "testuser"


def test_app_path_with_archive_prefix(monkeypatch):
    monkeypatch.setenv("APP_BASE_PATH", "/archive")
    from importlib import reload

    import app.config as config

    reload(config)
    assert config.app_path("") == "/archive"
    assert config.app_path("/login") == "/archive/login"
    assert config.cookie_path() == "/archive"


def test_app_path_without_prefix(monkeypatch):
    monkeypatch.setenv("APP_BASE_PATH", "")
    from importlib import reload

    import app.config as config

    reload(config)
    assert config.app_path("/documents") == "/documents"
    assert config.cookie_path() == "/"


def test_user_role_enum_uses_existing_postgres_type():
    role_column = User.__table__.c.role
    assert role_column.type.name == "userrole"


def test_document_status_enum_uses_existing_postgres_type():
    from app.models import BaseDocument

    column = BaseDocument.__table__.c.status
    assert column.type.name == "documentstatus"
