"""Notification creation and retrieval."""

from datetime import datetime

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BaseDocument,
    Notification,
    NotificationEventType,
    User,
    UserRole,
    DocumentStatus,
    DOCUMENT_STATUS_LABELS,
)
from app.push import send_push_to_users


def get_document_designation(doc: BaseDocument) -> str:
    if doc.design_document:
        return doc.design_document.designation
    if doc.tech_document:
        return doc.tech_document.designation
    return f"#{doc.id}"


def _actor_name(user: User) -> str:
    return user.full_name or user.login


async def _get_admin_reviewer_ids(session: AsyncSession) -> list[int]:
    result = await session.execute(
        select(User.id).where(User.role.in_([UserRole.admin, UserRole.reviewer]))
    )
    return list(result.scalars().all())


async def _create_notifications(
    session: AsyncSession,
    recipient_ids: set[int],
    message: str,
    document_id: int | None,
    event_type: NotificationEventType,
) -> None:
    if not recipient_ids:
        return
    for user_id in recipient_ids:
        session.add(
            Notification(
                user_id=user_id,
                document_id=document_id,
                message=message,
                event_type=event_type,
                created_at=datetime.utcnow(),
                is_read=False,
            )
        )
    await send_push_to_users(session, recipient_ids, message, event_type)


async def _notify_admin_reviewers(
    session: AsyncSession,
    doc: BaseDocument,
    message: str,
    event_type: NotificationEventType,
) -> None:
    recipients: set[int] = set(await _get_admin_reviewer_ids(session))
    await _create_notifications(session, recipients, message, doc.id, event_type)


async def notify_document_registered(session: AsyncSession, doc: BaseDocument, actor: User) -> None:
    await session.refresh(doc, ["design_document", "tech_document"])
    designation = get_document_designation(doc)
    message = f"{_actor_name(actor)} зарегистрировал(а) документ «{designation}»"
    await _notify_admin_reviewers(session, doc, message, NotificationEventType.document_register)


async def notify_file_upload(
    session: AsyncSession,
    doc: BaseDocument,
    actor: User,
    *,
    had_file_before: bool,
    registration_already_notified: bool,
) -> None:
    await session.refresh(doc, ["design_document", "tech_document"])
    designation = get_document_designation(doc)
    actor_label = _actor_name(actor)

    if had_file_before:
        message = f"{actor_label} заменил(а) файл документа «{designation}»"
        event_type = NotificationEventType.upload
    elif registration_already_notified:
        message = f"{actor_label} добавил(а) файл к документу «{designation}»"
        event_type = NotificationEventType.upload
    else:
        message = f"{actor_label} зарегистрировал(а) и добавил(а) электронный документ «{designation}»"
        event_type = NotificationEventType.document_register

    await _notify_admin_reviewers(session, doc, message, event_type)


async def notify_status_change(
    session: AsyncSession,
    doc: BaseDocument,
    actor: User,
    new_status: DocumentStatus,
    comment: str | None = None,
) -> None:
    await session.refresh(doc, ["design_document", "tech_document"])
    designation = get_document_designation(doc)
    status_label = DOCUMENT_STATUS_LABELS[new_status]
    message = f"{_actor_name(actor)} изменил(а) статус документа «{designation}» на «{status_label}»"
    if comment:
        message += f" с комментарием «{comment}»"

    recipients: set[int] = set(await _get_admin_reviewer_ids(session))
    if doc.uploaded_by:
        recipients.add(doc.uploaded_by)
    recipients.discard(actor.id)
    await _create_notifications(
        session, recipients, message, doc.id, NotificationEventType.status_change
    )


async def notify_document_edit(
    session: AsyncSession,
    doc: BaseDocument,
    actor: User,
    changes: list[str],
) -> None:
    await session.refresh(doc, ["design_document", "tech_document"])
    designation = get_document_designation(doc)
    if changes:
        changes_text = "; ".join(changes)
        message = f"{_actor_name(actor)} изменил(а) документ «{designation}»: {changes_text}"
    else:
        message = f"{_actor_name(actor)} изменил(а) документ «{designation}»"

    recipients: set[int] = set(await _get_admin_reviewer_ids(session))
    if doc.uploaded_by:
        recipients.add(doc.uploaded_by)
    recipients.discard(actor.id)
    await _create_notifications(
        session, recipients, message, doc.id, NotificationEventType.document_edit
    )


async def notify_document_delete(
    session: AsyncSession,
    doc: BaseDocument,
    actor: User,
    comment: str,
) -> None:
    await session.refresh(doc, ["design_document", "tech_document"])
    designation = get_document_designation(doc)
    message = (
        f"{_actor_name(actor)} удалил(а) документ «{designation}» "
        f"с комментарием «{comment}»"
    )

    recipients: set[int] = set(await _get_admin_reviewer_ids(session))
    if doc.uploaded_by:
        recipients.add(doc.uploaded_by)
    recipients.discard(actor.id)
    await _create_notifications(
        session, recipients, message, None, NotificationEventType.document_delete
    )


async def clear_document_references(session: AsyncSession, document_id: int) -> None:
    await session.execute(
        update(Notification)
        .where(Notification.document_id == document_id)
        .values(document_id=None)
    )


async def count_unread(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
        )
    )
    return result.scalar() or 0


async def mark_all_read(session: AsyncSession, user_id: int) -> None:
    await session.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True)
    )


async def get_notifications_for_user(
    session: AsyncSession, user: User, limit: int = 100
) -> list[Notification]:
    query = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def poll_new_notifications(
    session: AsyncSession, user: User, after_id: int = 0
) -> list[dict]:
    query = (
        select(Notification)
        .where(
            Notification.user_id == user.id,
            Notification.is_read.is_(False),
            Notification.id > after_id,
        )
        .order_by(Notification.id.asc())
        .limit(20)
    )
    result = await session.execute(query)
    notifications = result.scalars().all()
    return [
        {
            "id": n.id,
            "message": n.message,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "document_id": n.document_id,
        }
        for n in notifications
    ]
