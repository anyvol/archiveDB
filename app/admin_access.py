"""One-time admin access codes for first login after registration."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import AdminAccessCode, User

CODE_TTL_MINUTES = 15
MAX_ATTEMPTS = 5


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def _latest_code(session: AsyncSession, user_id: int) -> AdminAccessCode | None:
    result = await session.execute(
        select(AdminAccessCode)
        .where(AdminAccessCode.user_id == user_id, AdminAccessCode.used_at.is_(None))
        .order_by(AdminAccessCode.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def issue_admin_access_code(
    session: AsyncSession,
    user: User,
    *,
    created_by_id: int,
) -> str:
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email пользователя не подтверждён.",
        )
    if user.access_granted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователю уже выдан доступ.",
        )

    code = _generate_code()
    session.add(
        AdminAccessCode(
            user_id=user.id,
            code_hash=_hash_code(code),
            expires_at=datetime.utcnow() + timedelta(minutes=CODE_TTL_MINUTES),
            attempts=0,
            created_by_id=created_by_id,
        )
    )
    await session.commit()
    return code


async def verify_admin_access_code(session: AsyncSession, user: User, code: str) -> None:
    latest = await _latest_code(session, user.id)
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Код доступа не найден. Обратитесь к администратору.",
        )

    if latest.attempts >= MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Превышено число попыток. Запросите новый код у администратора.",
        )

    latest.attempts += 1

    if datetime.utcnow() > latest.expires_at:
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Срок действия кода истёк. Запросите новый код у администратора.",
        )

    if _hash_code(code.strip()) != latest.code_hash:
        await session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный код.")

    latest.used_at = datetime.utcnow()
    user.access_granted = True
    user.is_active = True
    await session.commit()
