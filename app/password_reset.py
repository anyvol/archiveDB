"""Password reset one-time codes and email delivery."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth import get_password_hash
from app.mail.sender import send_email, smtp_configured
from app.models import PasswordResetToken, User

RESET_TTL_MINUTES = 60
RESEND_COOLDOWN_SECONDS = 60


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _generate_reset_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def _latest_reset_token(session: AsyncSession, user_id: int) -> PasswordResetToken | None:
    result = await session.execute(
        select(PasswordResetToken)
        .where(PasswordResetToken.user_id == user_id)
        .order_by(PasswordResetToken.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def request_password_reset(
    session: AsyncSession,
    login_or_email: str,
) -> str | None:
    """Send a 6-digit reset code. Returns user login when mail was sent."""
    login_or_email = login_or_email.strip()
    if not login_or_email:
        return None

    if not await smtp_configured(session):
        return None

    normalized = login_or_email.lower()
    result = await session.execute(
        select(User).where(
            (User.login == login_or_email) | (User.email == normalized)
        )
    )
    user = result.scalars().first()
    if user is None or not user.email or not user.email_verified:
        return None

    latest = await _latest_reset_token(session, user.id)
    if latest and latest.used_at is None and (datetime.utcnow() - latest.created_at).total_seconds() < RESEND_COOLDOWN_SECONDS:
        return user.login

    code = _generate_reset_code()
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(code),
            expires_at=datetime.utcnow() + timedelta(minutes=RESET_TTL_MINUTES),
        )
    )
    await session.commit()

    body = (
        "Вы запросили восстановление пароля в archiveDB.\n\n"
        f"Код для сброса пароля: {code}\n\n"
        f"Код действителен {RESET_TTL_MINUTES} минут.\n"
        "Если вы не запрашивали сброс — проигнорируйте письмо."
    )
    await send_email(
        session,
        to_address=user.email,
        subject="archiveDB — восстановление пароля",
        body_text=body,
    )
    return user.login


async def verify_reset_code(session: AsyncSession, user: User, code: str) -> None:
    token_hash = _hash_token(code.strip())
    result = await session.execute(
        select(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.token_hash == token_hash)
        .limit(1)
    )
    row = result.scalars().first()
    if row is None or row.used_at is not None:
        raise HTTPException(status_code=400, detail="Неверный или использованный код.")

    if datetime.utcnow() > row.expires_at:
        raise HTTPException(status_code=400, detail="Срок действия кода истёк. Запросите новый.")


async def reset_password_with_token(
    session: AsyncSession,
    token: str,
    new_password: str,
) -> None:
    token_hash = _hash_token(token.strip())
    result = await session.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    row = result.scalars().first()
    if row is None or row.used_at is not None:
        raise HTTPException(status_code=400, detail="Недействительный или использованный код.")

    if datetime.utcnow() > row.expires_at:
        raise HTTPException(status_code=400, detail="Срок действия кода истёк.")

    user_result = await session.execute(select(User).where(User.id == row.user_id))
    user = user_result.scalars().first()
    if user is None:
        raise HTTPException(status_code=400, detail="Пользователь не найден.")

    user.password_hash = get_password_hash(new_password)
    row.used_at = datetime.utcnow()
    await session.commit()
