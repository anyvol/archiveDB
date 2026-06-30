"""Business logic for document change workflow (GOST 2.503-2013)."""

import os
from datetime import datetime

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.change_log import (
    archive_current_file,
    is_governed_document,
    log_change_event,
    log_document_status_change,
    log_file_upload,
    resolve_ii_storage_path,
)
from app.document_helpers import (
    compute_stored_file_name,
    save_upload_file,
    validate_upload_file,
    _read_upload_contents,
    _sanitize_storage_name,
    compose_display_file_name,
    extract_stored_file_name,
    resolve_record_display_name,
)
from app.models import (
    BaseDocument,
    ChangeNotification,
    DocumentChangeEventType,
    DocumentStatus,
    User,
)
from app.notifications import (
    get_document_designation,
    notify_correction_request,
    notify_correction_request_response,
    notify_formal_change,
    notify_status_change,
)


async def fetch_document(session: AsyncSession, doc_id: int) -> BaseDocument | None:
    result = await session.execute(
        select(BaseDocument)
        .options(
            joinedload(BaseDocument.design_document),
            joinedload(BaseDocument.tech_document),
            joinedload(BaseDocument.project),
        )
        .where(BaseDocument.id == doc_id)
    )
    return result.scalar_one_or_none()


async def request_minor_correction(
    session: AsyncSession,
    doc: BaseDocument,
    actor: User,
    comment: str,
) -> None:
    if doc.status != DocumentStatus.pending_review:
        raise HTTPException(status_code=400, detail="Запрос доступен только для документов «На проверке».")
    if not comment.strip():
        raise HTTPException(status_code=400, detail="Укажите, что именно нужно исправить.")
    if len(comment.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail="Опишите правки подробнее (минимум 10 символов). Укажите, что изменения незначительные.",
        )

    doc.status = DocumentStatus.correction_requested
    doc.correction_request_comment = comment.strip()
    old_status = DocumentStatus.pending_review
    await log_change_event(
        session,
        doc,
        actor,
        DocumentChangeEventType.correction_request,
        comment=comment.strip(),
    )
    await log_document_status_change(
        session, doc, actor, old_status, DocumentStatus.correction_requested
    )
    await notify_correction_request(session, doc, actor, comment.strip())


async def respond_correction_request(
    session: AsyncSession,
    doc: BaseDocument,
    actor: User,
    *,
    approved: bool,
    comment: str = "",
) -> None:
    if doc.status != DocumentStatus.correction_requested:
        raise HTTPException(status_code=400, detail="Нет активного запроса на исправление.")

    request_comment = doc.correction_request_comment or ""
    old_status = doc.status
    if approved:
        doc.status = DocumentStatus.requires_correction
        doc.review_comment = comment.strip() or "Одобрен запрос на незначительное исправление."
        doc.correction_request_comment = None
        event_type = DocumentChangeEventType.correction_request_approved
        log_comment = f"Запрос: «{request_comment}». {doc.review_comment}"
        new_status = DocumentStatus.requires_correction
    else:
        if not comment.strip():
            raise HTTPException(status_code=400, detail="Укажите причину отклонения запроса.")
        doc.status = DocumentStatus.pending_review
        doc.correction_request_comment = None
        doc.review_comment = None
        event_type = DocumentChangeEventType.correction_request_rejected
        log_comment = f"Запрос: «{request_comment}». Отклонено: {comment.strip()}"
        new_status = DocumentStatus.pending_review

    await log_change_event(session, doc, actor, event_type, comment=log_comment)
    await log_document_status_change(session, doc, actor, old_status, new_status)
    await notify_correction_request_response(session, doc, actor, approved, comment.strip() or None)


async def apply_cosmetic_file_replace(
    session: AsyncSession,
    doc: BaseDocument,
    actor: User,
    file: UploadFile,
    change_comment: str,
) -> None:
    if not change_comment.strip():
        raise HTTPException(status_code=400, detail="Укажите комментарий: что было изменено в файле.")
    if doc.status != DocumentStatus.requires_correction:
        raise HTTPException(status_code=400, detail="Замена файла доступна только при статусе «Требуется исправление».")

    await session.refresh(doc, ["project"])
    project_slug = doc.project.slug if doc.project else "_legacy"
    designation = get_document_designation(doc)

    file_revision = None
    if is_governed_document(doc) and doc.file_path:
        file_revision = archive_current_file(doc, project_slug, revision_label="cosmetic")
        if file_revision:
            session.add(file_revision)

    file_path, unique_file_name = await save_upload_file(
        file,
        project_slug,
        doc.file_path if not is_governed_document(doc) else None,
        doc_kind_code=doc.design_document.doc_kind_code if doc.design_document else None,
        designation=designation if (doc.design_document or doc.tech_document) else None,
    )

    record_name = resolve_record_display_name(doc.doc_name, designation)
    display_file_name = compose_display_file_name(unique_file_name, record_name)

    old_status = doc.status
    doc.file_path = file_path
    doc.file_name = display_file_name
    doc.status = DocumentStatus.pending_review
    doc.review_comment = None

    await log_change_event(
        session,
        doc,
        actor,
        DocumentChangeEventType.file_replace_cosmetic,
        comment=change_comment.strip(),
        file_revision=file_revision,
    )
    await log_file_upload(session, doc, actor, display_file_name, replacement=True)
    await log_document_status_change(session, doc, actor, old_status, DocumentStatus.pending_review)


async def apply_formal_document_change(
    session: AsyncSession,
    doc: BaseDocument,
    actor: User,
    *,
    ii_file: UploadFile,
    new_doc_file: UploadFile,
    ii_number: str,
    change_number: str,
    change_date: datetime,
    developer_signed: bool,
    reviewer_signed: bool,
    approver_signed: bool,
    comment: str = "",
) -> None:
    if doc.status != DocumentStatus.approved:
        raise HTTPException(status_code=400, detail="Формальное изменение доступно только для утверждённых документов.")
    if not ii_number.strip():
        raise HTTPException(status_code=400, detail="Укажите номер извещения об изменении (ИИ).")
    if not change_number.strip():
        raise HTTPException(status_code=400, detail="Укажите номер изменения (1, 2, 3…).")
    if not developer_signed or not reviewer_signed or not approver_signed:
        raise HTTPException(
            status_code=400,
            detail="Документ должен быть проверен всеми специалистами",
        )

    validate_upload_file(ii_file)
    validate_upload_file(new_doc_file)

    await session.refresh(doc, ["project"])
    project_slug = doc.project.slug if doc.project else "_legacy"
    designation = get_document_designation(doc)

    record_name = resolve_record_display_name(doc.doc_name, designation)
    stored_file_name = extract_stored_file_name(doc.file_name or "", record_name)
    expected_name = compute_stored_file_name(designation, os.path.basename(new_doc_file.filename or ""))
    if stored_file_name and expected_name != stored_file_name:
        raise HTTPException(
            status_code=400,
            detail=f"Имя файла должно совпадать с текущим документом: «{stored_file_name}».",
        )

    ii_contents, ii_original = await _read_upload_contents(ii_file)
    ii_stored = compute_stored_file_name(None, ii_original)
    ii_path = resolve_ii_storage_path(project_slug, _sanitize_storage_name(ii_stored))
    with open(ii_path, "wb") as f:
        f.write(ii_contents)

    file_revision = archive_current_file(
        doc, project_slug, revision_label=f"change_{change_number.strip()}"
    )
    if file_revision:
        session.add(file_revision)

    file_path, unique_file_name = await save_upload_file(
        new_doc_file,
        project_slug,
        None,
        doc_kind_code=doc.design_document.doc_kind_code if doc.design_document else None,
        designation=designation,
    )
    display_file_name = compose_display_file_name(unique_file_name, record_name)

    ii_record = ChangeNotification(
        document_id=doc.id,
        number=ii_number.strip(),
        date=change_date,
        file_name=ii_stored,
        file_path=ii_path,
        developer_signed=developer_signed,
        reviewer_signed=reviewer_signed,
        approver_signed=approver_signed,
        created_at=datetime.utcnow(),
        created_by_user_id=actor.id,
    )
    session.add(ii_record)
    await session.flush()

    old_status = doc.status
    doc.file_path = file_path
    doc.file_name = display_file_name
    doc.status = DocumentStatus.pending_review
    doc.review_comment = None

    await log_change_event(
        session,
        doc,
        actor,
        DocumentChangeEventType.file_replace_formal,
        comment=comment.strip() or None,
        change_number=change_number.strip(),
        change_date=change_date,
        change_notification=ii_record,
        file_revision=file_revision,
    )
    await log_file_upload(session, doc, actor, display_file_name, replacement=True)
    await log_document_status_change(session, doc, actor, old_status, DocumentStatus.pending_review)
    await notify_formal_change(session, doc, actor, ii_number.strip(), change_number.strip())


def preview_media_type(file_path: str) -> str | None:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return "application/pdf"
    if ext in (".png",):
        return "image/png"
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext in (".tif", ".tiff"):
        return "image/tiff"
    return None
