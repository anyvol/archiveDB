"""Document change log and file versioning helpers."""

import os
import shutil
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import UPLOAD_DIR
from app.models import (
    BaseDocument,
    ChangeNotification,
    DocumentChangeEvent,
    DocumentChangeEventType,
    DocumentStatus,
    DOCUMENT_CHANGE_EVENT_LABELS,
    DOCUMENT_STATUS_LABELS,
    FileRevision,
    GOVERNED_DOCUMENT_TYPES,
    II_FOLDER,
    User,
    VERSIONS_FOLDER,
)


def is_governed_document(doc: BaseDocument) -> bool:
    return doc.type in GOVERNED_DOCUMENT_TYPES


def _versions_dir(project_slug: str, document_id: int) -> str:
    return os.path.join(UPLOAD_DIR, project_slug, VERSIONS_FOLDER, str(document_id))


def _ii_dir(project_slug: str) -> str:
    return os.path.join(UPLOAD_DIR, project_slug, II_FOLDER)


def archive_current_file(
    doc: BaseDocument,
    project_slug: str,
    *,
    revision_label: str | None = None,
) -> FileRevision | None:
    """Move current file to versions folder; return FileRevision row (not yet persisted)."""
    if not doc.file_path or not os.path.exists(doc.file_path):
        return None

    versions_path = _versions_dir(project_slug, doc.id)
    os.makedirs(versions_path, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base_name = os.path.basename(doc.file_path)
    archived_name = f"{timestamp}_{base_name}"
    dest_path = os.path.join(versions_path, archived_name)
    shutil.copy2(doc.file_path, dest_path)

    return FileRevision(
        document_id=doc.id,
        file_name=doc.file_name or base_name,
        file_path=dest_path,
        archived_at=datetime.utcnow(),
        revision_label=revision_label,
    )


async def log_change_event(
    session: AsyncSession,
    doc: BaseDocument,
    actor: User | None,
    event_type: DocumentChangeEventType,
    *,
    comment: str | None = None,
    change_number: str | None = None,
    change_date: datetime | None = None,
    change_notification: ChangeNotification | None = None,
    file_revision: FileRevision | None = None,
    payload: dict | None = None,
) -> DocumentChangeEvent:
    event = DocumentChangeEvent(
        document_id=doc.id,
        actor_user_id=actor.id if actor else None,
        event_type=event_type,
        created_at=datetime.utcnow(),
        comment=comment,
        change_number=change_number,
        change_date=change_date,
        change_notification=change_notification,
        file_revision=file_revision,
        payload=payload,
    )
    session.add(event)
    if change_notification and change_notification.change_event is None:
        change_notification.change_event = event
    return event


async def log_document_status_change(
    session: AsyncSession,
    doc: BaseDocument,
    actor: User | None,
    old_status: DocumentStatus,
    new_status: DocumentStatus,
    *,
    comment: str | None = None,
) -> None:
    if old_status == new_status:
        return
    old_label = DOCUMENT_STATUS_LABELS[old_status]
    new_label = DOCUMENT_STATUS_LABELS[new_status]
    await log_change_event(
        session,
        doc,
        actor,
        DocumentChangeEventType.status_change,
        comment=comment or f"{old_label} → {new_label}",
        payload={"old_status": old_status.value, "new_status": new_status.value},
    )


async def log_file_upload(
    session: AsyncSession,
    doc: BaseDocument,
    actor: User | None,
    file_name: str,
    *,
    replacement: bool = False,
) -> None:
    action = "Замена файла" if replacement else "Загрузка файла"
    await log_change_event(
        session,
        doc,
        actor,
        DocumentChangeEventType.file_upload,
        comment=f"{action}: {file_name}",
    )


async def get_document_change_history(
    session: AsyncSession,
    document_id: int,
) -> list[DocumentChangeEvent]:
    result = await session.execute(
        select(DocumentChangeEvent)
        .where(DocumentChangeEvent.document_id == document_id)
        .order_by(DocumentChangeEvent.created_at.desc())
    )
    return list(result.scalars().all())


def format_change_event_summary(event: DocumentChangeEvent) -> str:
    label = DOCUMENT_CHANGE_EVENT_LABELS.get(event.event_type, event.event_type.value)
    parts = [label]
    if event.change_number:
        parts.append(f"изм. № {event.change_number}")
    if event.change_notification and event.event_type == DocumentChangeEventType.file_replace_formal:
        parts.append(f"ИИ № {event.change_notification.number}")
    if event.event_type == DocumentChangeEventType.status_change and event.payload:
        old_s = event.payload.get("old_status")
        new_s = event.payload.get("new_status")
        if old_s and new_s:
            try:
                parts.append(
                    f"{DOCUMENT_STATUS_LABELS[DocumentStatus(old_s)]} → "
                    f"{DOCUMENT_STATUS_LABELS[DocumentStatus(new_s)]}"
                )
            except ValueError:
                pass
    elif event.comment and event.event_type != DocumentChangeEventType.status_change:
        parts.append(event.comment)
    elif event.comment and event.event_type == DocumentChangeEventType.status_change:
        if not event.payload:
            parts.append(event.comment)
    return " — ".join(parts)


def resolve_ii_storage_path(project_slug: str, stored_name: str) -> str:
    upload_dir = _ii_dir(project_slug)
    os.makedirs(upload_dir, exist_ok=True)
    return os.path.join(upload_dir, stored_name)
