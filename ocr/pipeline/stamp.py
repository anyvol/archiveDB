"""GOST title-block (основная надпись) ROI and cell templates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class CellSpec:
    key: str
    # Normalized coords inside stamp crop: x0,y0,x1,y1 in [0,1]
    box: tuple[float, float, float, float]
    whitelist: str | None = None  # tesseract tessedit_char_whitelist hint category


# Relative stamp ROI on the full page (bottom-right title block, ГОСТ 2.104 form 1-ish).
# Tuned for typical landscape/portrait drawing scans; human review corrects misses.
# Prefer format-bound templates from DB when available (A4 vs A3 differ a lot).
STAMP_ROI_PAGE = (0.55, 0.72, 0.995, 0.995)  # x0,y0,x1,y1

# Starting guesses when no learned template exists yet (still overridable by annotation).
STAMP_ROI_BY_FORMAT: dict[str, tuple[float, float, float, float]] = {
    "A0": (0.62, 0.78, 0.995, 0.995),
    "A1": (0.60, 0.76, 0.995, 0.995),
    "A2": (0.58, 0.74, 0.995, 0.995),
    "A3": (0.55, 0.72, 0.995, 0.995),
    "A4": (0.48, 0.78, 0.995, 0.995),
    "A5": (0.42, 0.76, 0.995, 0.995),
}


def default_stamp_roi(document_format: str | None = None) -> tuple[float, float, float, float]:
    if document_format and document_format in STAMP_ROI_BY_FORMAT:
        return STAMP_ROI_BY_FORMAT[document_format]
    return STAMP_ROI_PAGE


def normalize_roi_box(box: list | tuple) -> tuple[float, float, float, float] | None:
    if not box or len(box) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
    except (TypeError, ValueError):
        return None
    x0 = max(0.0, min(1.0, x0))
    y0 = max(0.0, min(1.0, y0))
    x1 = max(0.0, min(1.0, x1))
    y1 = max(0.0, min(1.0, y1))
    if x1 <= x0 + 0.01 or y1 <= y0 + 0.01:
        return None
    return (x0, y0, x1, y1)
# Cells inside the stamp crop (relative). Layout approximates форма 1:
# top: designation | format/scale/sheets
# mid: doc_name
# bottom rows: FIO | signature | date for developed / reviewed / approved
CELL_TEMPLATE_FORM1: tuple[CellSpec, ...] = (
    CellSpec("designation", (0.02, 0.02, 0.62, 0.18), "designation"),
    CellSpec("document_format", (0.64, 0.02, 0.78, 0.18), "format"),
    CellSpec("scale", (0.79, 0.02, 0.88, 0.18), "scale"),
    CellSpec("sheets_total", (0.89, 0.02, 0.98, 0.18), "digits"),
    CellSpec("doc_name", (0.02, 0.18, 0.62, 0.42), "text"),
    CellSpec("sheet", (0.89, 0.18, 0.98, 0.30), "digits"),
    CellSpec("developed_by", (0.18, 0.55, 0.40, 0.68), "fio"),
    CellSpec("developer_signature", (0.40, 0.55, 0.52, 0.68), "signature"),
    CellSpec("developer_signed_date", (0.52, 0.55, 0.68, 0.68), "date"),
    CellSpec("reviewed_by", (0.18, 0.68, 0.40, 0.81), "fio"),
    CellSpec("reviewer_signature", (0.40, 0.68, 0.52, 0.81), "signature"),
    CellSpec("reviewer_signed_date", (0.52, 0.68, 0.68, 0.81), "date"),
    CellSpec("approved_by", (0.18, 0.81, 0.40, 0.96), "fio"),
    CellSpec("approver_signature", (0.40, 0.81, 0.52, 0.96), "signature"),
    CellSpec("approver_signed_date", (0.52, 0.81, 0.68, 0.96), "date"),
)


def crop_norm(image: np.ndarray, box: tuple[float, float, float, float]) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Crop using normalized box; returns crop and absolute pixel bbox (x0,y0,x1,y1)."""
    h, w = image.shape[:2]
    x0 = max(0, min(w - 1, int(box[0] * w)))
    y0 = max(0, min(h - 1, int(box[1] * h)))
    x1 = max(x0 + 1, min(w, int(box[2] * w)))
    y1 = max(y0 + 1, min(h, int(box[3] * h)))
    return image[y0:y1, x0:x1].copy(), (x0, y0, x1, y1)


def extract_stamp(
    page: np.ndarray,
    roi_norm: tuple[float, float, float, float] | list[float] | None = None,
    *,
    document_format: str | None = None,
    use_detector: bool = True,
) -> tuple[np.ndarray, tuple[int, int, int, int], dict[str, Any]]:
    roi = normalize_roi_box(roi_norm) if roi_norm is not None else None
    source = "provided" if roi is not None else None
    if roi is None and use_detector:
        try:
            from pipeline.detector import detect_stamp_roi

            detected = detect_stamp_roi(page)
            if detected:
                roi = detected
                source = "detector"
        except Exception:
            pass
    if roi is None:
        roi = default_stamp_roi(document_format)
        source = "format_default" if document_format else "builtin_default"
    stamp, bbox = crop_norm(page, roi)
    meta = {
        "stamp_roi_norm": list(roi),
        "stamp_roi_px": list(bbox),
        "template": "gost_2_104_form1_approx",
        "document_format_hint": document_format,
        "stamp_roi_source": source,
    }
    return stamp, bbox, meta


def iter_cells(stamp: np.ndarray, cells: list[dict[str, Any]] | None = None):
    if cells:
        for item in cells:
            key = (item.get("key") or "").strip()
            box = normalize_roi_box(item.get("bbox_norm") or [])
            if not key or not box:
                continue
            category = item.get("category") or key
            cell_img, local_bbox = crop_norm(stamp, box)
            yield CellSpec(key, box, category if isinstance(category, str) else key), cell_img, local_bbox
        return
    for spec in CELL_TEMPLATE_FORM1:
        cell_img, local_bbox = crop_norm(stamp, spec.box)
        yield spec, cell_img, local_bbox
