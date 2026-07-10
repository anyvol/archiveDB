"""Re-OCR stamp cells using caller-provided bounding boxes (phase 2)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import numpy as np
from PIL import Image

from pipeline.ocr_engine import engine_name, ocr_cell
from pipeline.stamp import CELL_TEMPLATE_FORM1, crop_norm

logger = logging.getLogger(__name__)

# Map field key → OCR category for whitelist
_KEY_CATEGORY = {spec.key: (spec.whitelist or spec.key) for spec in CELL_TEMPLATE_FORM1}
_KEY_CATEGORY.update(
    {
        "document_format": "format",
        "sheets_total": "digits",
        "sheet": "digits",
        "developed_by": "fio",
        "reviewed_by": "fio",
        "approved_by": "fio",
        "developer_signature": "signature",
        "reviewer_signature": "signature",
        "approver_signature": "signature",
        "developer_signed_date": "date",
        "reviewer_signed_date": "date",
        "approver_signed_date": "date",
        "doc_name": "text",
        "designation": "designation",
        "scale": "scale",
    }
)

_EMPTY_KEYS = tuple(_KEY_CATEGORY.keys())


def _empty_field() -> dict[str, Any]:
    return {"raw": None, "value": None, "conf": None, "bbox": None, "page": 0}


def run_extract_cells(
    *,
    job_id: int,
    stamp_path: str,
    cells: list[dict[str, Any]],
    pipeline_version: str,
) -> dict[str, Any]:
    """OCR only the provided cells on an existing stamp crop image."""
    started = time.perf_counter()
    with Image.open(stamp_path) as img:
        stamp = np.array(img.convert("RGB"))

    h, w = stamp.shape[:2]
    fields = {key: _empty_field() for key in _EMPTY_KEYS}

    for cell in cells:
        key = (cell.get("key") or "").strip()
        if not key:
            continue
        bbox_norm = cell.get("bbox_norm")
        if not bbox_norm or len(bbox_norm) != 4:
            continue
        try:
            box = tuple(float(v) for v in bbox_norm)
        except (TypeError, ValueError):
            continue
        category = cell.get("category") or _KEY_CATEGORY.get(key, "text")
        cell_img, local_bbox = crop_norm(stamp, box)

        # Optional ground-truth text from annotator skips OCR for that cell
        manual_text = (cell.get("text") or "").strip()
        if manual_text:
            result = {"raw": manual_text, "value": manual_text, "conf": 1.0}
        else:
            result = ocr_cell(cell_img, category=category)

        fields[key] = {
            "raw": result.get("raw"),
            "value": result.get("value"),
            "conf": result.get("conf"),
            "bbox": list(local_bbox),
            "bbox_norm": list(box),
            "page": 0,
        }

    elapsed = int((time.perf_counter() - started) * 1000)
    confs = [float(f["conf"]) for f in fields.values() if f.get("conf") is not None]
    mean_conf = round(sum(confs) / len(confs), 3) if confs else 0.0
    low_conf_fields = [k for k, f in fields.items() if f.get("value") and (f.get("conf") or 0) < 0.5]

    # Relative path for stamp is caller's concern; echo basename only in geometry
    geometry = {
        "job_id": job_id,
        "engine": engine_name(),
        "latency_ms": elapsed,
        "mean_conf": mean_conf,
        "low_conf_fields": low_conf_fields,
        "stamp_size": [w, h],
        "source": "annotated_cells",
        "cell_count": len(cells),
    }

    logger.info(
        "extract-cells job=%s cells=%s latency_ms=%s mean_conf=%s",
        job_id,
        len(cells),
        elapsed,
        mean_conf,
    )

    return {
        "pipeline_version": f"{pipeline_version}+annotated",
        "fields": fields,
        "geometry": geometry,
        "stamp_crop_path": None,  # caller keeps existing crop
        "page_preview_path": None,
        "person_suggestions": {},
    }


def default_template_cells() -> list[dict[str, Any]]:
    """Default cell boxes from the built-in GOST approx template."""
    return [
        {
            "key": spec.key,
            "bbox_norm": list(spec.box),
            "category": spec.whitelist or spec.key,
            "text": "",
        }
        for spec in CELL_TEMPLATE_FORM1
    ]
