"""OCR batch/job processing against the sidecar."""

from __future__ import annotations

import mimetypes
import os
import re
import uuid
from datetime import datetime
from typing import Iterable

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.config import MAX_UPLOAD_SIZE_MB, OCR_ALLOWED_EXTENSIONS, UPLOAD_DIR
from app.metadata_helpers import detect_document_format_from_bytes
from app.models import (
    OCR_INBOX_FOLDER,
    OcrBatch,
    OcrBatchStatus,
    OcrExtraction,
    OcrJob,
    OcrJobStatus,
    User,
)
from app.ocr.client import OcrServiceError, call_extract, check_ocr_health

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_name(name: str) -> str:
    cleaned = _UNSAFE.sub("_", os.path.basename(name)).strip()
    return cleaned or "file"


def _empty_fields() -> dict:
    keys = (
        "designation",
        "doc_name",
        "developed_by",
        "reviewed_by",
        "approved_by",
        "developer_signed_date",
        "reviewer_signed_date",
        "approver_signed_date",
        "document_format",
        "scale",
        "sheet",
        "sheets_total",
    )
    return {k: {"raw": None, "value": None, "conf": None, "bbox": None, "page": 0} for k in keys}


def field_value(fields: dict | None, key: str) -> str:
    if not fields:
        return ""
    entry = fields.get(key) or {}
    value = entry.get("value")
    if value is None:
        value = entry.get("raw")
    return "" if value is None else str(value).strip()


async def create_batch_with_files(
    session: AsyncSession,
    user: User,
    files: Iterable[UploadFile],
) -> OcrBatch:
    file_list = [f for f in files if f and getattr(f, "filename", None)]
    if not file_list:
        raise HTTPException(status_code=400, detail="Выберите хотя бы один файл (PDF или изображение).")

    batch = OcrBatch(
        created_by_user_id=user.id,
        status=OcrBatchStatus.processing,
        created_at=datetime.utcnow(),
    )
    session.add(batch)
    await session.flush()

    inbox = os.path.join(UPLOAD_DIR, OCR_INBOX_FOLDER, str(batch.id))
    os.makedirs(inbox, exist_ok=True)
    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024

    for upload in file_list:
        original = _sanitize_name(upload.filename or "file")
        ext = os.path.splitext(original)[1].lower()
        if ext not in OCR_ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Файл «{original}»: недопустимый тип. "
                    f"Для OCR разрешены: {', '.join(sorted(OCR_ALLOWED_EXTENSIONS))}"
                ),
            )
        contents = await upload.read()
        if len(contents) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"Файл «{original}» слишком большой (максимум {MAX_UPLOAD_SIZE_MB} МБ).",
            )

        disk_name = f"{uuid.uuid4().hex}_{original}"
        stored_path = os.path.join(inbox, disk_name)
        with open(stored_path, "wb") as fh:
            fh.write(contents)

        mime, _ = mimetypes.guess_type(original)
        job = OcrJob(
            batch_id=batch.id,
            original_filename=original,
            stored_path=stored_path,
            mime=mime,
            status=OcrJobStatus.queued,
            created_at=datetime.utcnow(),
        )
        session.add(job)
        await session.flush()
        await process_job(session, job, contents=contents)

    await _refresh_batch_status(session, batch)
    await session.commit()
    await session.refresh(batch)
    return batch


async def process_job(
    session: AsyncSession,
    job: OcrJob,
    *,
    contents: bytes | None = None,
) -> None:
    job.status = OcrJobStatus.processing
    job.started_at = datetime.utcnow()
    job.error_message = None
    await session.flush()

    if contents is None:
        try:
            with open(job.stored_path, "rb") as fh:
                contents = fh.read()
        except OSError as exc:
            job.status = OcrJobStatus.failed
            job.error_message = f"Не удалось прочитать файл: {exc}"
            job.finished_at = datetime.utcnow()
            session.add(
                OcrExtraction(
                    job_id=job.id,
                    source="auto",
                    fields=_empty_fields(),
                    geometry={},
                    created_at=datetime.utcnow(),
                )
            )
            return

    local_format = detect_document_format_from_bytes(contents, job.original_filename)

    try:
        result = await call_extract(
            job_id=job.id,
            file_path=job.stored_path,
            mime=job.mime,
            original_filename=job.original_filename,
        )
        fields = result.get("fields") or _empty_fields()
        geometry = dict(result.get("geometry") or {})
        if local_format and not geometry.get("format_from_dims"):
            geometry["format_from_dims"] = local_format
        if local_format and not field_value(fields, "document_format"):
            fields = dict(fields)
            fields["document_format"] = {
                "raw": local_format,
                "value": local_format,
                "conf": 0.9,
                "bbox": None,
                "page": 0,
            }

        job.pipeline_version = result.get("pipeline_version")
        job.page_count = geometry.get("page_count")
        job.status = OcrJobStatus.needs_review
        job.finished_at = datetime.utcnow()
        session.add(
            OcrExtraction(
                job_id=job.id,
                source="auto",
                fields=fields,
                geometry=geometry,
                stamp_crop_path=result.get("stamp_crop_path"),
                page_preview_path=result.get("page_preview_path"),
                person_suggestions=result.get("person_suggestions") or {},
                created_at=datetime.utcnow(),
            )
        )
    except OcrServiceError as exc:
        fields = _empty_fields()
        geometry: dict = {}
        if local_format:
            geometry["format_from_dims"] = local_format
            fields["document_format"] = {
                "raw": local_format,
                "value": local_format,
                "conf": 0.9,
                "bbox": None,
                "page": 0,
            }
        job.status = OcrJobStatus.failed
        job.error_message = str(exc)
        job.finished_at = datetime.utcnow()
        session.add(
            OcrExtraction(
                job_id=job.id,
                source="auto",
                fields=fields,
                geometry=geometry,
                created_at=datetime.utcnow(),
            )
        )


async def retry_job(session: AsyncSession, job: OcrJob) -> OcrJob:
    if job.status == OcrJobStatus.committed:
        raise HTTPException(status_code=400, detail="Документ уже создан из этой задачи.")
    if job.status == OcrJobStatus.discarded:
        raise HTTPException(status_code=400, detail="Задача отклонена.")
    await process_job(session, job)
    batch = await session.get(OcrBatch, job.batch_id)
    if batch:
        await _refresh_batch_status(session, batch)
    await session.commit()
    await session.refresh(job)
    return job


async def _refresh_batch_status(session: AsyncSession, batch: OcrBatch) -> None:
    result = await session.execute(select(OcrJob).where(OcrJob.batch_id == batch.id))
    jobs = list(result.scalars().all())
    if not jobs:
        batch.status = OcrBatchStatus.failed
        return
    statuses = {j.status for j in jobs}
    if statuses <= {OcrJobStatus.failed, OcrJobStatus.discarded}:
        batch.status = OcrBatchStatus.failed
    elif any(s in statuses for s in (OcrJobStatus.queued, OcrJobStatus.processing)):
        batch.status = OcrBatchStatus.processing
    else:
        batch.status = OcrBatchStatus.completed


async def get_batch(session: AsyncSession, batch_id: int) -> OcrBatch | None:
    result = await session.execute(
        select(OcrBatch)
        .where(OcrBatch.id == batch_id)
        .options(joinedload(OcrBatch.jobs).joinedload(OcrJob.extractions))
    )
    return result.scalars().unique().first()


async def get_job(session: AsyncSession, job_id: int) -> OcrJob | None:
    result = await session.execute(
        select(OcrJob)
        .where(OcrJob.id == job_id)
        .options(
            joinedload(OcrJob.batch),
            joinedload(OcrJob.extractions),
        )
    )
    return result.scalars().unique().first()


def latest_extraction(job: OcrJob) -> OcrExtraction | None:
    if not job.extractions:
        return None
    return max(job.extractions, key=lambda e: (e.created_at or datetime.min, e.id or 0))


async def ocr_service_available() -> bool:
    return (await check_ocr_health()) is not None
