"""Admin user management helpers."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AdminAccessCode,
    BaseDocument,
    ChangeNotification,
    EmailVerificationCode,
    Notification,
    PasswordResetToken,
    ProjectFile,
    User,
    UserRole,
)
from app.permissions import is_master_admin


async def _user_activity_counts(session: AsyncSession, user_id: int) -> dict[str, int]:
    docs = await session.scalar(
        select(func.count()).select_from(BaseDocument).where(BaseDocument.uploaded_by == user_id)
    )
    project_files = await session.scalar(
        select(func.count()).select_from(ProjectFile).where(ProjectFile.uploaded_by == user_id)
    )
    change_notes = await session.scalar(
        select(func.count())
        .select_from(ChangeNotification)
        .where(ChangeNotification.created_by_user_id == user_id)
    )
    return {
        "documents": docs or 0,
        "project_files": project_files or 0,
        "change_notifications": change_notes or 0,
    }


async def delete_user_account(session: AsyncSession, actor: User, target: User) -> None:
    if actor.id == target.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить собственную учётную запись.")
    if target.role == UserRole.master_admin:
        raise HTTPException(status_code=400, detail="Нельзя удалить главного администратора.")
    if is_master_admin(target) and not is_master_admin(actor):
        raise HTTPException(status_code=403, detail="Недостаточно прав.")

    counts = await _user_activity_counts(session, target.id)
    blocking = {key: value for key, value in counts.items() if value > 0}
    if blocking:
        parts = []
        if blocking.get("documents"):
            parts.append(f"документов: {blocking['documents']}")
        if blocking.get("project_files"):
            parts.append(f"файлов проектов: {blocking['project_files']}")
        if blocking.get("change_notifications"):
            parts.append(f"извещений: {blocking['change_notifications']}")
        raise HTTPException(
            status_code=400,
            detail="Нельзя удалить пользователя с данными в системе (" + ", ".join(parts) + ").",
        )

    user_id = target.id
    await session.execute(delete(Notification).where(Notification.user_id == user_id))
    await session.execute(delete(EmailVerificationCode).where(EmailVerificationCode.user_id == user_id))
    await session.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id))
    await session.execute(delete(AdminAccessCode).where(AdminAccessCode.user_id == user_id))
    await session.delete(target)
    await session.commit()
