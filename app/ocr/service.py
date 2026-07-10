"""OCR batch/job processing against the sidecar."""

from __future__ import annotations

import logging
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

from app.config import MAX_UPLOAD_SIZE_MB, OCR_ALLOWED_EXTENSIONS, OCR_LOW_CONF_THRESHOLD, UPLOAD_DIR
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
from app.name_helpers import (
    fetch_known_org_codes,
    fetch_known_person_names,
    suggest_org_codes,
    suggest_person_names,
)
from app.ocr.client import OcrServiceError, call_extract, call_extract_cells, check_ocr_health
from app.ocr.normalize import coerce_document_format

logger = logging.getLogger(__name__)

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_name(name: str) -> str:
    cleaned = _UNSAFE.sub("_", os.path.basename(name)).strip()
    return cleaned or "file"


def path_for_ocr_service(stored_path: str) -> str:
    """Map API-local path under UPLOAD_DIR to a path relative to the shared volume.

    API mounts uploads at ``/app/uploaded_files`` (UPLOAD_DIR), OCR at ``/uploads``.
    The sidecar must receive a path relative to that shared root, e.g.
    ``_ocr_inbox/1/file.pdf``, not ``/app/uploaded_files/...``.
    """
    abs_stored = os.path.abspath(stored_path)
    abs_upload = os.path.abspath(UPLOAD_DIR)
    try:
        common = os.path.commonpath([abs_stored, abs_upload])
    except ValueError:
        return stored_path.replace("\\", "/")
    if common != abs_upload:
        return stored_path.replace("\\", "/")
    rel = os.path.relpath(abs_stored, abs_upload)
    return rel.replace("\\", "/")


def _empty_fields() -> dict:
    keys = (
        "designation",
        "doc_name",
        "developed_by",
        "reviewed_by",
        "approved_by",
        "developer_signature",
        "reviewer_signature",
        "approver_signature",
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

    # Load format-bound stamp ROI + cell boxes before first extract (A4 ≠ A3)
    stamp_roi_norm = None
    template_cells = None
    fmt_hint = coerce_document_format(local_format)
    if fmt_hint:
        from app.ocr.annotate import get_format_template

        template = await get_format_template(session, fmt_hint)
        if template and template.labels:
            roi = template.labels.get("stamp_roi_norm")
            if isinstance(roi, (list, tuple)) and len(roi) == 4:
                stamp_roi_norm = [float(v) for v in roi]
            cells = template.labels.get("cells")
            if cells:
                template_cells = cells

    try:
        result = await call_extract(
            job_id=job.id,
            file_path=path_for_ocr_service(job.stored_path),
            mime=job.mime,
            original_filename=job.original_filename,
            stamp_roi_norm=stamp_roi_norm,
            cells=template_cells,
            document_format_hint=fmt_hint or None,
        )
        fields = result.get("fields") or _empty_fields()
        geometry = dict(result.get("geometry") or {})
        if local_format and not geometry.get("format_from_dims"):
            geometry["format_from_dims"] = local_format
        if stamp_roi_norm:
            geometry["stamp_roi_from_template"] = True
            geometry["format_template"] = fmt_hint

        # Normalize format to a valid dropdown code; prefer dims when OCR is invalid
        fmt = (
            coerce_document_format(field_value(fields, "document_format"))
            or coerce_document_format(geometry.get("format_from_dims"))
            or coerce_document_format(local_format)
        )
        if fmt:
            geometry["format_from_dims"] = geometry.get("format_from_dims") or fmt
            fields = dict(fields)
            if coerce_document_format(field_value(fields, "document_format")) != fmt:
                fields["document_format"] = {
                    "raw": fields.get("document_format", {}).get("raw") or fmt,
                    "value": fmt,
                    "conf": 0.9,
                    "bbox": (fields.get("document_format") or {}).get("bbox"),
                    "page": 0,
                }

        job.pipeline_version = result.get("pipeline_version")
        job.page_count = geometry.get("page_count")
        job.finished_at = datetime.utcnow()

        # Map crop paths from OCR volume-relative to API UPLOAD_DIR absolute
        stamp_rel = result.get("stamp_crop_path")
        preview_rel = result.get("page_preview_path")
        stamp_path = _abs_upload_path(stamp_rel) if stamp_rel else None
        preview_path = _abs_upload_path(preview_rel) if preview_rel else None

        # If we had cell template but no stamp_roi yet, still re-OCR cells on the crop
        if fmt and stamp_path and os.path.isfile(stamp_path) and not template_cells:
            from app.ocr.annotate import get_format_template

            template = await get_format_template(session, fmt)
            cells = (template.labels or {}).get("cells") if template else None
            if cells:
                try:
                    cell_result = await call_extract_cells(
                        job_id=job.id,
                        stamp_crop_path=path_for_ocr_service(stamp_path),
                        cells=cells,
                    )
                    cell_fields = cell_result.get("fields") or {}
                    if cell_fields:
                        fields = {**fields, **cell_fields}
                        if not coerce_document_format(field_value(fields, "document_format")):
                            fields["document_format"] = {
                                "raw": fmt,
                                "value": fmt,
                                "conf": 0.9,
                                "bbox": None,
                                "page": 0,
                            }
                        cell_geo = cell_result.get("geometry") or {}
                        geometry = {
                            **geometry,
                            **{k: v for k, v in cell_geo.items() if k not in {"format_from_dims"}},
                            "format_from_dims": geometry.get("format_from_dims") or fmt,
                            "format_template": fmt,
                            "source": "auto+format_template",
                        }
                        if cell_result.get("pipeline_version"):
                            job.pipeline_version = cell_result.get("pipeline_version")
                except OcrServiceError as exc:
                    logger.warning("format-template re-OCR skipped for job %s: %s", job.id, exc)
        elif template_cells:
            geometry["source"] = "auto+format_template"

        suggestions = await _build_field_suggestions(session, fields)

        low_conf = geometry.get("low_conf_fields") or []
        critical_empty = not field_value(fields, "designation") and not field_value(fields, "doc_name")
        if critical_empty and not any(field_value(fields, k) for k in ("developed_by", "document_format")):
            job.status = OcrJobStatus.needs_annotation
            job.error_message = "Не удалось уверенно распознать поля штампа — проверьте вручную."
        else:
            job.status = OcrJobStatus.needs_review
            job.error_message = None

        mean_conf = geometry.get("mean_conf")
        logger.info(
            "OCR job %s done pipeline=%s mean_conf=%s low_conf=%s status=%s latency_ms=%s",
            job.id,
            job.pipeline_version,
            mean_conf,
            low_conf,
            job.status,
            geometry.get("latency_ms"),
        )

        session.add(
            OcrExtraction(
                job_id=job.id,
                source="auto",
                fields=fields,
                geometry={
                    **geometry,
                    "low_conf_threshold": OCR_LOW_CONF_THRESHOLD,
                },
                stamp_crop_path=stamp_path,
                page_preview_path=preview_path,
                person_suggestions=suggestions,
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


def _abs_upload_path(rel_or_abs: str) -> str:
    if os.path.isabs(rel_or_abs):
        return rel_or_abs
    return os.path.normpath(os.path.join(UPLOAD_DIR, rel_or_abs))


async def _build_field_suggestions(session: AsyncSession, fields: dict) -> dict:
    """Build FIO + org_code suggestion chips (never auto-applied)."""
    known = await fetch_known_person_names(session)
    suggestions: dict = {}
    for key in ("developed_by", "reviewed_by", "approved_by"):
        raw = field_value(fields, key)
        if not raw:
            suggestions[key] = []
            continue
        suggestions[key] = suggest_person_names(raw, known, limit=5)

    org_raw = ""
    designation = field_value(fields, "designation")
    if designation:
        org_raw = designation.replace(" ", "").split(".")[0]
    known_orgs = await fetch_known_org_codes(session)
    suggestions["org_code"] = suggest_org_codes(org_raw, known_orgs, limit=5) if org_raw else []
    return suggestions


# Back-compat alias
async def _build_person_suggestions(session: AsyncSession, fields: dict) -> dict:
    return await _build_field_suggestions(session, fields)


def field_confidence(fields: dict | None, key: str) -> float | None:
    if not fields:
        return None
    entry = fields.get(key) or {}
    conf = entry.get("conf")
    try:
        return float(conf) if conf is not None else None
    except (TypeError, ValueError):
        return None
