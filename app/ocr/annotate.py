"""OCR annotation helpers (phase 2): save labels and re-OCR by cell boxes."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import OCR_LOW_CONF_THRESHOLD
from app.models import OcrAnnotation, OcrExtraction, OcrFormatTemplate, OcrJob, OcrJobStatus, User
from app.ocr.client import OcrServiceError, call_extract_cells
from app.ocr.normalize import coerce_document_format
from app.ocr.service import (
    _build_field_suggestions,
    field_value,
    latest_extraction,
    path_for_ocr_service,
)

# Built-in default template (mirrors ocr/pipeline/stamp.py CELL_TEMPLATE_FORM1)
DEFAULT_CELL_TEMPLATE: list[dict[str, Any]] = [
    {"key": "designation", "bbox_norm": [0.02, 0.02, 0.62, 0.18], "category": "designation", "text": ""},
    {"key": "document_format", "bbox_norm": [0.64, 0.02, 0.78, 0.18], "category": "format", "text": ""},
    {"key": "scale", "bbox_norm": [0.79, 0.02, 0.88, 0.18], "category": "scale", "text": ""},
    {"key": "sheets_total", "bbox_norm": [0.89, 0.02, 0.98, 0.18], "category": "digits", "text": ""},
    {"key": "doc_name", "bbox_norm": [0.02, 0.18, 0.62, 0.42], "category": "text", "text": ""},
    {"key": "sheet", "bbox_norm": [0.89, 0.18, 0.98, 0.30], "category": "digits", "text": ""},
    {"key": "developed_by", "bbox_norm": [0.18, 0.55, 0.40, 0.68], "category": "fio", "text": ""},
    {"key": "developer_signature", "bbox_norm": [0.40, 0.55, 0.52, 0.68], "category": "signature", "text": ""},
    {"key": "developer_signed_date", "bbox_norm": [0.52, 0.55, 0.68, 0.68], "category": "date", "text": ""},
    {"key": "reviewed_by", "bbox_norm": [0.18, 0.68, 0.40, 0.81], "category": "fio", "text": ""},
    {"key": "reviewer_signature", "bbox_norm": [0.40, 0.68, 0.52, 0.81], "category": "signature", "text": ""},
    {"key": "reviewer_signed_date", "bbox_norm": [0.52, 0.68, 0.68, 0.81], "category": "date", "text": ""},
    {"key": "approved_by", "bbox_norm": [0.18, 0.81, 0.40, 0.96], "category": "fio", "text": ""},
    {"key": "approver_signature", "bbox_norm": [0.40, 0.81, 0.52, 0.96], "category": "signature", "text": ""},
    {"key": "approver_signed_date", "bbox_norm": [0.52, 0.81, 0.68, 0.96], "category": "date", "text": ""},
]

FIELD_KEY_LABELS = {
    "designation": "Обозначение",
    "doc_name": "Наименование",
    "document_format": "Формат",
    "scale": "Масштаб",
    "sheet": "Лист",
    "sheets_total": "Листов",
    "developed_by": "Разработал",
    "developer_signature": "Подпись (разраб.)",
    "developer_signed_date": "Дата (разраб.)",
    "reviewed_by": "Проверил",
    "reviewer_signature": "Подпись (пров.)",
    "reviewer_signed_date": "Дата (пров.)",
    "approved_by": "Утвердил",
    "approver_signature": "Подпись (утв.)",
    "approver_signed_date": "Дата (утв.)",
}


async def latest_annotation(session: AsyncSession, job_id: int) -> OcrAnnotation | None:
    result = await session.execute(
        select(OcrAnnotation)
        .where(OcrAnnotation.job_id == job_id)
        .order_by(OcrAnnotation.updated_at.desc(), OcrAnnotation.id.desc())
        .limit(1)
    )
    return result.scalars().first()


async def get_format_template(session: AsyncSession, document_format: str | None) -> OcrFormatTemplate | None:
    fmt = coerce_document_format(document_format)
    if not fmt:
        return None
    result = await session.execute(
        select(OcrFormatTemplate).where(OcrFormatTemplate.document_format == fmt).limit(1)
    )
    return result.scalars().first()


def resolve_document_format(extraction: OcrExtraction | None, labels: dict | None = None) -> str:
    if labels:
        fmt = coerce_document_format(labels.get("document_format"))
        if fmt:
            return fmt
    if not extraction:
        return ""
    fields = extraction.fields or {}
    geometry = extraction.geometry or {}
    return (
        coerce_document_format(field_value(fields, "document_format"))
        or coerce_document_format(geometry.get("format_from_dims"))
        or ""
    )


async def upsert_format_template(
    session: AsyncSession,
    *,
    document_format: str,
    labels: dict[str, Any],
    user: User,
) -> OcrFormatTemplate | None:
    fmt = coerce_document_format(document_format)
    if not fmt:
        return None
    cells = labels.get("cells") or []
    if not cells:
        return None
    payload = {
        "cells": cells,
        "document_format": fmt,
    }
    if isinstance(labels.get("stamp_size"), (list, tuple)) and len(labels["stamp_size"]) == 2:
        payload["stamp_size"] = [int(labels["stamp_size"][0]), int(labels["stamp_size"][1])]
    now = datetime.utcnow()
    existing = await get_format_template(session, fmt)
    if existing:
        existing.labels = payload
        existing.updated_by_user_id = user.id
        existing.updated_at = now
        return existing
    row = OcrFormatTemplate(
        document_format=fmt,
        labels=payload,
        updated_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    return row


def cells_from_extraction(extraction: OcrExtraction | None) -> list[dict[str, Any]]:
    """Build editable cells from last OCR field bboxes (normalized if possible)."""
    if not extraction or not extraction.fields:
        return [dict(c) for c in DEFAULT_CELL_TEMPLATE]

    fields = extraction.fields
    stamp_w = stamp_h = None
    geometry = extraction.geometry or {}
    size = geometry.get("stamp_size")
    if isinstance(size, (list, tuple)) and len(size) == 2:
        stamp_w, stamp_h = float(size[0]), float(size[1])

    cells: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key, entry in fields.items():
        if not isinstance(entry, dict):
            continue
        bbox_norm = entry.get("bbox_norm")
        bbox = entry.get("bbox")
        if bbox_norm and len(bbox_norm) == 4:
            norm = [float(v) for v in bbox_norm]
        elif bbox and len(bbox) == 4 and stamp_w and stamp_h and stamp_w > 0 and stamp_h > 0:
            x0, y0, x1, y1 = [float(v) for v in bbox]
            norm = [x0 / stamp_w, y0 / stamp_h, x1 / stamp_w, y1 / stamp_h]
        else:
            continue
        # clamp
        norm = [
            max(0.0, min(1.0, norm[0])),
            max(0.0, min(1.0, norm[1])),
            max(0.0, min(1.0, norm[2])),
            max(0.0, min(1.0, norm[3])),
        ]
        if norm[2] <= norm[0] or norm[3] <= norm[1]:
            continue
        category = "signature" if key.endswith("_signature") else key
        cells.append(
            {
                "key": key,
                "bbox_norm": norm,
                "category": category,
                "text": "",
            }
        )
        seen.add(key)

    if not cells:
        return [dict(c) for c in DEFAULT_CELL_TEMPLATE]

    # Keep template order for known keys, append extras
    ordered: list[dict[str, Any]] = []
    by_key = {c["key"]: c for c in cells}
    for tmpl in DEFAULT_CELL_TEMPLATE:
        if tmpl["key"] in by_key:
            ordered.append(by_key[tmpl["key"]])
        else:
            ordered.append(dict(tmpl))
    for key, cell in by_key.items():
        if key not in {t["key"] for t in DEFAULT_CELL_TEMPLATE}:
            ordered.append(cell)
    return ordered


def normalize_labels_payload(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    cells_in = raw.get("cells") or []
    cells: list[dict[str, Any]] = []
    for item in cells_in:
        if not isinstance(item, dict):
            continue
        key = (item.get("key") or "").strip()
        bbox = item.get("bbox_norm")
        if not key or not bbox or len(bbox) != 4:
            continue
        try:
            norm = [float(v) for v in bbox]
        except (TypeError, ValueError):
            continue
        if norm[2] <= norm[0] or norm[3] <= norm[1]:
            continue
        category = (item.get("category") or key)
        if key.endswith("_signature"):
            category = "signature"
        cells.append(
            {
                "key": key,
                "bbox_norm": norm,
                "category": category,
                "text": (item.get("text") or "").strip(),
            }
        )
    if not cells:
        raise HTTPException(status_code=400, detail="Добавьте хотя бы одну ячейку с bbox.")
    stamp_size = raw.get("stamp_size")
    labels: dict[str, Any] = {"cells": cells}
    if isinstance(stamp_size, (list, tuple)) and len(stamp_size) == 2:
        labels["stamp_size"] = [int(stamp_size[0]), int(stamp_size[1])]
    notes = (raw.get("notes") or "").strip()
    if notes:
        labels["notes"] = notes
    fmt = coerce_document_format(raw.get("document_format"))
    if fmt:
        labels["document_format"] = fmt
    return labels


async def save_annotation(
    session: AsyncSession,
    job: OcrJob,
    user: User,
    labels_raw: dict[str, Any],
    *,
    commit: bool = True,
) -> OcrAnnotation:
    if job.status == OcrJobStatus.committed:
        raise HTTPException(status_code=400, detail="Документ уже создан — разметка недоступна.")
    if job.status == OcrJobStatus.discarded:
        raise HTTPException(status_code=400, detail="Задача отклонена.")

    labels = normalize_labels_payload(labels_raw)
    extraction = latest_extraction(job)
    fmt = labels.get("document_format") or resolve_document_format(extraction)
    if fmt:
        labels["document_format"] = fmt

    existing = await latest_annotation(session, job.id)
    now = datetime.utcnow()
    if existing:
        existing.labels = labels
        existing.annotator_user_id = user.id
        existing.updated_at = now
        annotation = existing
    else:
        annotation = OcrAnnotation(
            job_id=job.id,
            annotator_user_id=user.id,
            labels=labels,
            created_at=now,
            updated_at=now,
        )
        session.add(annotation)

    if fmt:
        await upsert_format_template(session, document_format=fmt, labels=labels, user=user)

    if job.status in {OcrJobStatus.failed, OcrJobStatus.needs_annotation, OcrJobStatus.queued}:
        job.status = OcrJobStatus.needs_review

    if commit:
        await session.commit()
        await session.refresh(annotation)
    else:
        await session.flush()
        await session.refresh(annotation)
    return annotation


async def reocr_from_annotation(
    session: AsyncSession,
    job: OcrJob,
    user: User,
    *,
    labels_raw: dict[str, Any] | None = None,
) -> OcrExtraction:
    """Save labels (optional) and run cell OCR against the stamp crop."""
    if job.status == OcrJobStatus.committed:
        raise HTTPException(status_code=400, detail="Документ уже создан.")
    if job.status == OcrJobStatus.discarded:
        raise HTTPException(status_code=400, detail="Задача отклонена.")

    extraction = latest_extraction(job)
    if not extraction or not extraction.stamp_crop_path or not os.path.isfile(extraction.stamp_crop_path):
        raise HTTPException(
            status_code=400,
            detail="Нет crop штампа. Сначала выполните обычное распознавание (Повторить OCR).",
        )

    if labels_raw is not None:
        annotation = await save_annotation(session, job, user, labels_raw, commit=False)
    else:
        annotation = await latest_annotation(session, job.id)
        if not annotation:
            raise HTTPException(status_code=400, detail="Сначала сохраните разметку.")

    labels = annotation.labels or {}
    cells = labels.get("cells") or []
    if not cells:
        raise HTTPException(status_code=400, detail="В разметке нет ячеек.")

    stamp_rel = path_for_ocr_service(extraction.stamp_crop_path)
    job.status = OcrJobStatus.processing
    job.started_at = datetime.utcnow()
    job.error_message = None
    await session.flush()

    try:
        result = await call_extract_cells(
            job_id=job.id,
            stamp_crop_path=stamp_rel,
            cells=cells,
        )
    except OcrServiceError as exc:
        job.status = OcrJobStatus.failed
        job.error_message = str(exc)
        job.finished_at = datetime.utcnow()
        await session.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    fields = result.get("fields") or {}
    geometry = dict(result.get("geometry") or {})
    # Preserve paper format from prior auto-extract / dims
    prev_geo = extraction.geometry or {}
    if prev_geo.get("format_from_dims") and not geometry.get("format_from_dims"):
        geometry["format_from_dims"] = prev_geo["format_from_dims"]
    fmt = resolve_document_format(extraction, labels)
    if fmt and not coerce_document_format(field_value(fields, "document_format")):
        fields = dict(fields)
        fields["document_format"] = {
            "raw": fmt,
            "value": fmt,
            "conf": 0.9,
            "bbox": None,
            "page": 0,
        }
    geometry["low_conf_threshold"] = OCR_LOW_CONF_THRESHOLD
    geometry["annotation_id"] = annotation.id
    if fmt:
        geometry["format_template"] = fmt

    suggestions = await _build_field_suggestions(session, fields)

    new_extraction = OcrExtraction(
        job_id=job.id,
        source="annotated",
        fields=fields,
        geometry=geometry,
        stamp_crop_path=extraction.stamp_crop_path,
        page_preview_path=extraction.page_preview_path,
        person_suggestions=suggestions,
        created_at=datetime.utcnow(),
    )
    session.add(new_extraction)

    job.pipeline_version = result.get("pipeline_version")
    job.finished_at = datetime.utcnow()
    job.status = OcrJobStatus.needs_review
    job.error_message = None

    await session.commit()
    await session.refresh(new_extraction)
    return new_extraction


async def annotation_bootstrap(
    session: AsyncSession,
    job: OcrJob,
    extraction: OcrExtraction | None,
    annotation: OcrAnnotation | None,
) -> dict:
    fmt = resolve_document_format(extraction, (annotation.labels if annotation else None))
    format_template = await get_format_template(session, fmt) if fmt else None

    if annotation and annotation.labels and annotation.labels.get("cells"):
        labels = annotation.labels
        cells = labels.get("cells") or []
        stamp_size = labels.get("stamp_size")
        source = "job_annotation"
    elif format_template and format_template.labels and format_template.labels.get("cells"):
        labels = format_template.labels
        cells = labels.get("cells") or []
        stamp_size = labels.get("stamp_size") or (
            (extraction.geometry or {}).get("stamp_size") if extraction else None
        )
        source = "format_template"
    else:
        cells = cells_from_extraction(extraction)
        stamp_size = (extraction.geometry or {}).get("stamp_size") if extraction else None
        source = "extraction_or_default"

    return {
        "cells": cells,
        "stamp_size": stamp_size,
        "document_format": fmt,
        "template_source": source,
        "field_keys": [
            {"key": k, "label": FIELD_KEY_LABELS.get(k, k)} for k in FIELD_KEY_LABELS
        ],
        "has_stamp_crop": bool(extraction and extraction.stamp_crop_path and os.path.isfile(extraction.stamp_crop_path)),
    }
