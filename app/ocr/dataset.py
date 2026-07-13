"""Phase 3 — build a training dataset ZIP from OCR annotations / ground-truth extractions."""

from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.config import UPLOAD_DIR
from app.models import (
    OcrAnnotation,
    OcrExtraction,
    OcrFormatTemplate,
    OcrJob,
    OcrJobStatus,
)
from app.specification_helpers import build_dataset_spec_payload
from app.ocr.service import field_value, latest_extraction


def _safe_under_upload(path: str | None) -> str | None:
    if not path:
        return None
    candidate = path if os.path.isabs(path) else os.path.join(UPLOAD_DIR, path)
    if not os.path.isfile(candidate):
        return None
    abs_upload = os.path.abspath(UPLOAD_DIR)
    abs_path = os.path.abspath(candidate)
    if abs_path == abs_upload or abs_path.startswith(abs_upload + os.sep):
        return abs_path
    return None


async def list_exportable_jobs(session: AsyncSession) -> list[OcrJob]:
    """Jobs with human labels useful for training."""
    result = await session.execute(
        select(OcrJob)
        .options(
            joinedload(OcrJob.extractions),
            joinedload(OcrJob.annotations),
        )
        .order_by(OcrJob.id.desc())
    )
    jobs = list(result.scalars().unique().all())
    out: list[OcrJob] = []
    for job in jobs:
        if job.status == OcrJobStatus.discarded and not job.annotations:
            continue
        has_ann = bool(job.annotations)
        has_gt = any(
            (e.source or "") in {"training", "corrected", "annotated", "annotated_stamp"}
            for e in (job.extractions or [])
        )
        if has_ann or has_gt or job.status in {OcrJobStatus.labeled, OcrJobStatus.committed}:
            if has_ann or has_gt:
                out.append(job)
    return out


def _pick_ground_truth(job: OcrJob) -> OcrExtraction | None:
    preferred = ("training", "corrected", "annotated_stamp", "annotated")
    by_source = {e.source: e for e in (job.extractions or [])}
    for src in preferred:
        if src in by_source:
            return by_source[src]
    return latest_extraction(job)


def _sample_payload(job: OcrJob, annotation: OcrAnnotation | None, gt: OcrExtraction | None) -> dict[str, Any]:
    labels = (annotation.labels if annotation else {}) or {}
    fields = (gt.fields if gt else {}) or {}
    geometry = (gt.geometry if gt else {}) or {}
    stamp_roi = labels.get("stamp_roi_norm") or (geometry.get("stamp_roi") or {}).get("stamp_roi_norm")
    cells = labels.get("cells") or []
    if not cells and fields:
        for key, entry in fields.items():
            if isinstance(entry, dict) and entry.get("bbox_norm"):
                cells.append(
                    {
                        "key": key,
                        "bbox_norm": entry.get("bbox_norm"),
                        "category": key,
                        "text": entry.get("value") or entry.get("raw") or "",
                    }
                )
    gt_fields = {
        key: {
            "value": field_value(fields, key) or None,
            "raw": (fields.get(key) or {}).get("raw"),
            "conf": (fields.get(key) or {}).get("conf"),
            "bbox_norm": (fields.get(key) or {}).get("bbox_norm"),
        }
        for key in fields
        if isinstance(fields.get(key), dict)
    }
    return {
        "job_id": job.id,
        "batch_id": job.batch_id,
        "original_filename": job.original_filename,
        "mime": job.mime,
        "status": job.status.value if job.status else None,
        "pipeline_version": job.pipeline_version,
        "document_format": labels.get("document_format")
        or field_value(fields, "document_format")
        or geometry.get("format_from_dims"),
        "stamp_roi_norm": stamp_roi,
        "cells": cells,
        "ground_truth_fields": gt_fields,
        "extraction_source": gt.source if gt else None,
        "annotation_id": annotation.id if annotation else None,
        "geometry": {
            "format_from_dims": geometry.get("format_from_dims"),
            "stamp_size": geometry.get("stamp_size") or labels.get("stamp_size"),
            "stamp_roi_source": (geometry.get("stamp_roi") or {}).get("stamp_roi_source"),
            "dpi": geometry.get("dpi"),
            "document_role": geometry.get("document_role"),
            "spec_page_indices": geometry.get("spec_page_indices"),
            "sections_found": geometry.get("sections_found"),
            "spec_rows": geometry.get("spec_rows"),
        },
        "spec_ground_truth": build_dataset_spec_payload(geometry),
    }


async def build_dataset_zip(
    session: AsyncSession,
    *,
    mark_exported: bool = True,
    job_ids: list[int] | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Return (zip_bytes, summary)."""
    jobs = await list_exportable_jobs(session)
    if job_ids:
        wanted = set(job_ids)
        jobs = [j for j in jobs if j.id in wanted]
    if not jobs:
        raise HTTPException(
            status_code=400,
            detail="Нет размеченных задач для экспорта. Сохраните разметку или «учебный пример».",
        )

    templates_result = await session.execute(select(OcrFormatTemplate))
    format_templates = [
        {
            "document_format": t.document_format,
            "labels": t.labels,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in templates_result.scalars().all()
    ]

    now = datetime.utcnow()
    root = f"archivedb-ocr-dataset-{now.strftime('%Y%m%d-%H%M%S')}"
    samples_meta: list[dict[str, Any]] = []
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for job in jobs:
            annotation = None
            if job.annotations:
                annotation = max(
                    job.annotations,
                    key=lambda a: (a.updated_at or datetime.min, a.id or 0),
                )
            gt = _pick_ground_truth(job)
            sample = _sample_payload(job, annotation, gt)
            sample_dir = f"{root}/samples/job_{job.id}"

            stamp_path = _safe_under_upload(gt.stamp_crop_path if gt else None)
            page_path = _safe_under_upload(gt.page_preview_path if gt else None)
            files: dict[str, str] = {}
            if stamp_path:
                zf.write(stamp_path, f"{sample_dir}/stamp.png")
                files["stamp"] = "stamp.png"
            if page_path:
                zf.write(page_path, f"{sample_dir}/page.png")
                files["page"] = "page.png"
            if files:
                sample["files"] = files
            zf.writestr(
                f"{sample_dir}/labels.json",
                json.dumps(sample, ensure_ascii=False, indent=2),
            )
            samples_meta.append(
                {
                    "job_id": job.id,
                    "document_format": sample.get("document_format"),
                    "has_stamp": bool(stamp_path),
                    "has_page": bool(page_path),
                    "cell_count": len(sample.get("cells") or []),
                    "extraction_source": sample.get("extraction_source"),
                }
            )
            if mark_exported and annotation:
                annotation.exported_at = now

        manifest = {
            "created_at": now.isoformat() + "Z",
            "schema_version": "1.0",
            "sample_count": len(samples_meta),
            "samples": samples_meta,
            "notes": (
                "Phase 3 dataset: stamp.png is the title-block crop; page.png is the page preview; "
                "labels.json holds stamp_roi_norm, cell boxes, and ground-truth field values."
            ),
        }
        zf.writestr(f"{root}/manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr(
            f"{root}/format_templates.json",
            json.dumps(format_templates, ensure_ascii=False, indent=2),
        )
        zf.writestr(
            f"{root}/README.txt",
            (
                "archiveDB OCR dataset (phase 3)\n"
                "================================\n"
                "manifest.json         — index of samples\n"
                "format_templates.json — learned stamp/cell ROI per paper format\n"
                "samples/job_*/stamp.png, page.png, labels.json\n\n"
                "Train a stamp detector with ocr/training/train_stamp_detector.py\n"
                "See docs/ocr/PHASE3.md for the full pipeline.\n"
            ),
        )

    if mark_exported:
        await session.commit()

    summary = {
        "sample_count": len(samples_meta),
        "format_template_count": len(format_templates),
        "created_at": now.isoformat() + "Z",
        "filename": f"{root}.zip",
    }
    return buf.getvalue(), summary


async def dataset_stats(session: AsyncSession) -> dict[str, Any]:
    jobs = await list_exportable_jobs(session)
    templates = await session.execute(select(OcrFormatTemplate))
    tmpl = list(templates.scalars().all())
    return {
        "exportable_jobs": len(jobs),
        "format_templates": [
            {"document_format": t.document_format, "has_stamp_roi": bool((t.labels or {}).get("stamp_roi_norm"))}
            for t in tmpl
        ],
        "labeled_jobs": sum(1 for j in jobs if j.status == OcrJobStatus.labeled),
        "annotated_jobs": sum(1 for j in jobs if j.annotations),
    }
