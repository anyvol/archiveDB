"""Admin broadcast and direct email helpers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.mail.sender import send_email, smtp_configured
from app.models import User

ADMIN_MAIL_SIGNATURE = '\n\n--\nАдминистратор сервиса "Архив документов"'


def format_admin_email_body(body: str) -> str:
    text = body.strip()
    if not text:
        return ADMIN_MAIL_SIGNATURE.strip()
    return f"{text}{ADMIN_MAIL_SIGNATURE}"


async def send_admin_email(session: AsyncSession, to_address: str, subject: str, body: str) -> None:
    if not await smtp_configured(session):
        raise RuntimeError("Почтовый сервер не настроен.")
    await send_email(
        session,
        to_address=to_address,
        subject=subject.strip(),
        body_text=format_admin_email_body(body),
    )


async def send_admin_email_to_user(session: AsyncSession, user: User, subject: str, body: str) -> None:
    if not user.email:
        raise ValueError("У пользователя не указан email.")
    await send_admin_email(session, user.email, subject, body)


async def send_admin_email_to_all(session: AsyncSession, subject: str, body: str) -> int:
    result = await session.execute(
        select(User).where(User.email.is_not(None), User.email != "", User.email_verified.is_(True))
    )
    users = result.scalars().all()
    sent = 0
    for user in users:
        await send_admin_email(session, user.email, subject, body)
        sent += 1
    return sent
