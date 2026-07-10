"""Orchestrate phase-1B extract: render → deskew → stamp ROI → cell OCR."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

from format_detect import detect_format_from_file
from pipeline.ocr_engine import engine_name, ocr_cell
from pipeline.render import deskew, render_pages, save_rgb
from pipeline.stamp import extract_stamp, iter_cells

logger = logging.getLogger(__name__)

PIPELINE_VERSION = os.getenv("OCR_PIPELINE_VERSION", "stamp-cells-1.0")
RENDER_DPI = int(os.getenv("OCR_RENDER_DPI", "250"))

_EMPTY_KEYS = (
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


def _empty_field() -> dict[str, Any]:
    return {"raw": None, "value": None, "conf": None, "bbox": None, "page": 0}


def run_extract(
    *,
    job_id: int,
    full_path: str,
    uploads_dir: str,
    original_filename: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    format_code, page_count = detect_format_from_file(full_path)
    fields = {key: _empty_field() for key in _EMPTY_KEYS}

    pages = render_pages(full_path, dpi=RENDER_DPI, max_pages=1)
    if not pages:
        elapsed = int((time.perf_counter() - started) * 1000)
        return {
            "pipeline_version": PIPELINE_VERSION,
            "fields": fields,
            "geometry": {
                "format_from_dims": format_code,
                "format_from_ocr": None,
                "page_count": page_count,
                "stamp_roi": None,
                "job_id": job_id,
                "engine": engine_name(),
                "latency_ms": elapsed,
                "error": "no_pages",
            },
            "stamp_crop_path": None,
            "page_preview_path": None,
            "person_suggestions": {},
        }

    page, angle = deskew(pages[0])
    stamp, stamp_bbox, stamp_meta = extract_stamp(page)

    # Persist crops under the same inbox folder as the source file when possible
    rel_dir = _artifact_dir(full_path, uploads_dir, job_id)
    abs_dir = os.path.join(uploads_dir, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    stamp_name = f"job_{job_id}_stamp.png"
    preview_name = f"job_{job_id}_page.png"
    stamp_abs = os.path.join(abs_dir, stamp_name)
    preview_abs = os.path.join(abs_dir, preview_name)
    save_rgb(stamp_abs, stamp)
    # smaller preview
    save_rgb(preview_abs, _downscale(page, max_side=1600))

    for spec, cell_img, local_bbox in iter_cells(stamp):
        result = ocr_cell(cell_img, category=spec.whitelist or spec.key)
        # bbox in stamp-crop coordinates + normalized for annotation UI
        fields[spec.key] = {
            "raw": result.get("raw"),
            "value": result.get("value"),
            "conf": result.get("conf"),
            "bbox": list(local_bbox),
            "bbox_norm": list(spec.box),
            "page": 0,
        }

    # Prefer geometry format when OCR format is weak or not a known A-series code
    ocr_format = fields.get("document_format", {}).get("value")
    format_from_ocr = ocr_format if ocr_format else None
    ocr_conf = fields["document_format"].get("conf") or 0
    ocr_looks_valid = bool(format_from_ocr and re.match(r"^A[0-5](?:x[0-9]+)?$", str(format_from_ocr), re.I))
    if format_code and (not ocr_looks_valid or ocr_conf < 0.45):
        fields["document_format"] = {
            "raw": fields["document_format"].get("raw"),
            "value": format_code,
            "conf": 0.9,
            "bbox": fields["document_format"].get("bbox"),
            "bbox_norm": fields["document_format"].get("bbox_norm"),
            "page": 0,
        }

    elapsed = int((time.perf_counter() - started) * 1000)
    confs = [float(f["conf"]) for f in fields.values() if f.get("conf") is not None]
    mean_conf = round(sum(confs) / len(confs), 3) if confs else 0.0
    low_conf_fields = [k for k, f in fields.items() if f.get("value") and (f.get("conf") or 0) < 0.5]

    geometry = {
        "format_from_dims": format_code,
        "format_from_ocr": format_from_ocr,
        "page_count": page_count or len(pages),
        "stamp_roi": stamp_meta,
        "stamp_bbox_px": list(stamp_bbox),
        "stamp_size": [int(stamp.shape[1]), int(stamp.shape[0])],
        "deskew_angle_deg": angle,
        "job_id": job_id,
        "engine": engine_name(),
        "latency_ms": elapsed,
        "mean_conf": mean_conf,
        "low_conf_fields": low_conf_fields,
        "dpi": RENDER_DPI,
    }

    logger.info(
        "extract job=%s engine=%s latency_ms=%s mean_conf=%s designation=%r",
        job_id,
        engine_name(),
        elapsed,
        mean_conf,
        fields.get("designation", {}).get("value"),
    )

    return {
        "pipeline_version": PIPELINE_VERSION,
        "fields": fields,
        "geometry": geometry,
        "stamp_crop_path": f"{rel_dir}/{stamp_name}".replace("\\", "/"),
        "page_preview_path": f"{rel_dir}/{preview_name}".replace("\\", "/"),
        "person_suggestions": {},
    }


def _artifact_dir(full_path: str, uploads_dir: str, job_id: int) -> str:
    parent = os.path.dirname(full_path)
    try:
        rel_parent = os.path.relpath(parent, uploads_dir)
        if not rel_parent.startswith(".."):
            return os.path.join(rel_parent, "crops").replace("\\", "/")
    except ValueError:
        pass
    return f"_ocr_inbox/crops/{job_id}"


def _downscale(image, max_side: int):
    import cv2

    h, w = image.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale >= 0.99:
        return image
    return cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
