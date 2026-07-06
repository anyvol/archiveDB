"""Tests for admin access codes and permissions (0.14.0)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.admin_access import issue_admin_access_code, verify_admin_access_code, CODE_TTL_MINUTES
from app.models import User, UserRole
from app.permissions import can_manage_project, user_has_full_access


def test_can_manage_project_admin_only():
    assert can_manage_project(User(id=1, login="a", role=UserRole.admin, password_hash="x"))
    assert can_manage_project(User(id=1, login="m", role=UserRole.master_admin, password_hash="x"))
    assert not can_manage_project(User(id=1, login="u", role=UserRole.user, password_hash="x"))
    assert not can_manage_project(User(id=1, login="r", role=UserRole.reviewer, password_hash="x"))


def test_user_has_full_access():
    assert user_has_full_access(User(id=1, login="a", role=UserRole.admin, password_hash="x", access_granted=False))
    assert user_has_full_access(User(id=1, login="u", role=UserRole.user, password_hash="x", access_granted=True))
    assert not user_has_full_access(User(id=1, login="u", role=UserRole.user, password_hash="x", access_granted=False))


@pytest.mark.asyncio
async def test_issue_and_verify_admin_access_code():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()

    user = User(id=5, login="newbie", role=UserRole.user, password_hash="x", email_verified=True, access_granted=False)
    with patch("app.admin_access._generate_code", return_value="123456"):
        code = await issue_admin_access_code(session, user, created_by_id=1)
    assert code == "123456"
    assert session.add.called

    from app.models import AdminAccessCode
    from datetime import datetime, timedelta

    stored = AdminAccessCode(
        user_id=5,
        code_hash="unused",
        expires_at=datetime.utcnow() + timedelta(minutes=CODE_TTL_MINUTES),
        attempts=0,
    )
    import hashlib

    stored.code_hash = hashlib.sha256(b"123456").hexdigest()

    async def fake_execute(stmt):
        result = MagicMock()
        result.scalars.return_value.first.return_value = stored
        return result

    session.execute = fake_execute
    await verify_admin_access_code(session, user, "123456")
    assert user.access_granted is True
    assert stored.used_at is not None
