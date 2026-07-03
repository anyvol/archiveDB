"""Email verification with one-time numeric codes."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.mail.sender import send_email, smtp_configured
from app.models import EmailVerificationCode, User

CODE_TTL_MINUTES = 15
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def _latest_code(session: AsyncSession, user_id: int) -> EmailVerificationCode | None:
    result = await session.execute(
        select(EmailVerificationCode)
        .where(EmailVerificationCode.user_id == user_id)
        .order_by(EmailVerificationCode.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def issue_verification_code(session: AsyncSession, user: User) -> None:
    if not user.email:
        raise HTTPException(status_code=400, detail="Email обязателен")

    if not await smtp_configured(session):
        raise HTTPException(
            status_code=503,
            detail="Почтовый сервер не настроен. Обратитесь к администратору.",
        )

    latest = await _latest_code(session, user.id)
    if latest and (datetime.utcnow() - latest.created_at).total_seconds() < RESEND_COOLDOWN_SECONDS:
        raise HTTPException(
            status_code=429,
            detail="Повторная отправка возможна через минуту.",
        )

    code = _generate_code()
    session.add(
        EmailVerificationCode(
            user_id=user.id,
            code_hash=_hash_code(code),
            expires_at=datetime.utcnow() + timedelta(minutes=CODE_TTL_MINUTES),
            attempts=0,
        )
    )
    await session.commit()

    body = (
        f"Ваш код подтверждения email для archiveDB: {code}\n\n"
        f"Код действителен {CODE_TTL_MINUTES} минут.\n"
        "Если вы не регистрировались — проигнорируйте это письмо."
    )
    await send_email(
        session,
        to_address=user.email,
        subject="archiveDB — код подтверждения email",
        body_text=body,
    )


async def verify_email_code(session: AsyncSession, user: User, code: str) -> None:
    latest = await _latest_code(session, user.id)
    if latest is None:
        raise HTTPException(status_code=400, detail="Код не найден. Запросите новый.")

    if latest.attempts >= MAX_ATTEMPTS:
        raise HTTPException(status_code=400, detail="Превышено число попыток. Запросите новый код.")

    latest.attempts += 1

    if datetime.utcnow() > latest.expires_at:
        await session.commit()
        raise HTTPException(status_code=400, detail="Срок действия кода истёк. Запросите новый.")

    if _hash_code(code.strip()) != latest.code_hash:
        await session.commit()
        raise HTTPException(status_code=400, detail="Неверный код.")

    user.email_verified = True
    user.is_active = True
    await session.commit()
