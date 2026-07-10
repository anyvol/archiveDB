"""Password reset tokens and email delivery."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlparse, urlunparse

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth import get_password_hash, verify_password
from app.cert_scripts import external_base_url
from app.config import PUBLIC_HTTPS_PORT, ROOT_PATH, url_path
from app.mail.sender import send_email, smtp_configured
from app.models import PasswordResetToken, User

RESET_TTL_MINUTES = 60


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _public_base_url(request_base: str | None = None, request: Request | None = None) -> str:
    if request is not None:
        return external_base_url(request, https=True)
    if request_base:
        parsed = urlparse(request_base.rstrip("/"))
        if parsed.scheme == "http":
            parsed = parsed._replace(scheme="https")
        return urlunparse(parsed).rstrip("/")
    port = PUBLIC_HTTPS_PORT.strip()
    if port and port not in ("443", "80"):
        return f"https://localhost:{port}{ROOT_PATH}".rstrip("/")
    return f"https://localhost{ROOT_PATH}".rstrip("/")


async def request_password_reset(
    session: AsyncSession,
    login_or_email: str,
    request_base: str | None = None,
    request: Request | None = None,
) -> None:
    login_or_email = login_or_email.strip()
    if not login_or_email:
        return

    if not await smtp_configured(session):
        return

    normalized = login_or_email.lower()
    result = await session.execute(
        select(User).where(
            (User.login == login_or_email) | (User.email == normalized)
        )
    )
    user = result.scalars().first()
    if user is None or not user.email or not user.email_verified:
        return

    token = secrets.token_urlsafe(32)
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(token),
            expires_at=datetime.utcnow() + timedelta(minutes=RESET_TTL_MINUTES),
        )
    )
    await session.commit()

    reset_url = f"{_public_base_url(request_base, request)}{url_path('/reset-password')}?token={token}"
    body = (
        "Вы запросили восстановление пароля в archiveDB.\n\n"
        f"Перейдите по ссылке (действительна {RESET_TTL_MINUTES} мин.):\n{reset_url}\n\n"
        "Если вы не запрашивали сброс — проигнорируйте письмо."
    )
    await send_email(
        session,
        to_address=user.email,
        subject="archiveDB — восстановление пароля",
        body_text=body,
    )


async def request_password_reset_for_user(
    session: AsyncSession,
    user: User,
    request: Request | None = None,
    request_base: str | None = None,
) -> None:
    if not user.email or not user.email_verified:
        raise HTTPException(status_code=400, detail="Для смены пароля необходим подтверждённый email.")
    if not await smtp_configured(session):
        raise HTTPException(status_code=400, detail="Отправка email не настроена.")
    await request_password_reset(session, user.login, request_base=request_base, request=request)


async def change_password(
    session: AsyncSession,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Новый пароль должен содержать не менее 8 символов.")
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Неверный текущий пароль.")
    user.password_hash = get_password_hash(new_password)
    await session.commit()


async def reset_password_with_token(
    session: AsyncSession,
    token: str,
    new_password: str,
) -> None:
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Пароль должен содержать не менее 8 символов.")
    token_hash = _hash_token(token.strip())
    result = await session.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    row = result.scalars().first()
    if row is None or row.used_at is not None:
        raise HTTPException(status_code=400, detail="Недействительная или использованная ссылка.")

    if datetime.utcnow() > row.expires_at:
        raise HTTPException(status_code=400, detail="Срок действия ссылки истёк.")

    user_result = await session.execute(select(User).where(User.id == row.user_id))
    user = user_result.scalars().first()
    if user is None:
        raise HTTPException(status_code=400, detail="Пользователь не найден.")

    user.password_hash = get_password_hash(new_password)
    row.used_at = datetime.utcnow()
    await session.commit()
