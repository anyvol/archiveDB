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
from pipeline.spec_detect import classify_document
from pipeline.spec_extract import extract_spec_rows_from_pages
from pipeline.stamp import extract_stamp, iter_cells

logger = logging.getLogger(__name__)

PIPELINE_VERSION = os.getenv("OCR_PIPELINE_VERSION", "stamp-cells-1.1")
RENDER_DPI = int(os.getenv("OCR_RENDER_DPI", "400"))
PAGE_PREVIEW_MAX_SIDE = int(os.getenv("OCR_PAGE_PREVIEW_MAX_SIDE", "2800"))

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
    stamp_roi_norm: list[float] | tuple[float, float, float, float] | None = None,
    cells: list[dict[str, Any]] | None = None,
    document_format_hint: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    format_code, page_count = detect_format_from_file(full_path)
    fmt_hint = document_format_hint or format_code
    fields = {key: _empty_field() for key in _EMPTY_KEYS}

    total_pages = page_count or 1
    max_render = min(total_pages, 8)
    all_pages_raw = render_pages(full_path, dpi=RENDER_DPI, max_pages=max_render)
    if not all_pages_raw:
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

    page, angle = deskew(all_pages_raw[0])
    stamp, stamp_bbox, stamp_meta = extract_stamp(
        page,
        stamp_roi_norm,
        document_format=fmt_hint,
    )

    # Persist crops under the same inbox folder as the source file when possible
    rel_dir = _artifact_dir(full_path, uploads_dir, job_id)
    abs_dir = os.path.join(uploads_dir, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    stamp_name = f"job_{job_id}_stamp.png"
    stamp_abs = os.path.join(abs_dir, stamp_name)
    save_rgb(stamp_abs, stamp)

    page_preview_paths: list[str] = []
    for index, raw_page in enumerate(all_pages_raw):
        preview_name = f"job_{job_id}_page_{index}.png"
        preview_abs = os.path.join(abs_dir, preview_name)
        page_img = page if index == 0 else raw_page
        save_rgb(preview_abs, _downscale(page_img, max_side=PAGE_PREVIEW_MAX_SIDE))
        page_preview_paths.append(f"{rel_dir}/{preview_name}".replace("\\", "/"))
    preview_name = page_preview_paths[0] if page_preview_paths else None

    for spec, cell_img, local_bbox in iter_cells(stamp, cells):
        category = spec.whitelist or spec.key
        result = ocr_cell(cell_img, category=category)
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

    spec_analysis: dict[str, Any] = {}
    spec_rows: list[dict[str, Any]] = []
    try:
        stamp_roi_norm = None
        if stamp_meta and isinstance(stamp_meta.get("stamp_roi_norm"), (list, tuple)):
            roi = stamp_meta["stamp_roi_norm"]
            if len(roi) == 4:
                stamp_roi_norm = float(roi[1])
        spec_analysis = classify_document(
            all_pages_raw,
            format_hint=fmt_hint or format_code,
            stamp_roi_top_norm=stamp_roi_norm,
        )
        if spec_analysis.get("has_specification"):
            spec_rows = extract_spec_rows_from_pages(
                all_pages_raw,
                spec_analysis.get("spec_page_indices") or [],
                embedded_pages=spec_analysis.get("embedded_spec_pages"),
            )
    except Exception as exc:
        logger.warning("spec classification failed job=%s: %s", job_id, exc)

    geometry = {
        "format_from_dims": format_code,
        "format_from_ocr": format_from_ocr,
        "page_count": total_pages,
        "page_preview_paths": page_preview_paths,
        "document_role": spec_analysis.get("document_role"),
        "has_specification": spec_analysis.get("has_specification", False),
        "is_specification_document": spec_analysis.get("is_specification_document", False),
        "spec_page_indices": spec_analysis.get("spec_page_indices", []),
        "assembly_page_indices": spec_analysis.get("assembly_page_indices", []),
        "embedded_spec_pages": spec_analysis.get("embedded_spec_pages", []),
        "spec_designations": spec_analysis.get("spec_designations", spec_analysis.get("designations", [])),
        "sections_found": spec_analysis.get("sections_found", []),
        "spec_rows": spec_rows,
        "detection_confidence": spec_analysis.get("detection_confidence", 0.0),
        "markers": spec_analysis.get("markers", {}),
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
        "page_preview_path": preview_name,
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
