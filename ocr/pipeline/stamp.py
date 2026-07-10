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
STAMP_ROI_PAGE = (0.55, 0.72, 0.995, 0.995)  # x0,y0,x1,y1

# Cells inside the stamp crop (relative). Layout approximates форма 1:
# top: designation | format/scale/sheets
# mid: doc_name
# bottom rows: developed / reviewed / approved + dates
CELL_TEMPLATE_FORM1: tuple[CellSpec, ...] = (
    CellSpec("designation", (0.02, 0.02, 0.62, 0.18), "designation"),
    CellSpec("document_format", (0.64, 0.02, 0.78, 0.18), "format"),
    CellSpec("scale", (0.79, 0.02, 0.88, 0.18), "scale"),
    CellSpec("sheets_total", (0.89, 0.02, 0.98, 0.18), "digits"),
    CellSpec("doc_name", (0.02, 0.18, 0.62, 0.42), "text"),
    CellSpec("sheet", (0.89, 0.18, 0.98, 0.30), "digits"),
    CellSpec("developed_by", (0.18, 0.55, 0.45, 0.68), "fio"),
    CellSpec("developer_signed_date", (0.46, 0.55, 0.62, 0.68), "date"),
    CellSpec("reviewed_by", (0.18, 0.68, 0.45, 0.81), "fio"),
    CellSpec("reviewer_signed_date", (0.46, 0.68, 0.62, 0.81), "date"),
    CellSpec("approved_by", (0.18, 0.81, 0.45, 0.96), "fio"),
    CellSpec("approver_signed_date", (0.46, 0.81, 0.62, 0.96), "date"),
)


def crop_norm(image: np.ndarray, box: tuple[float, float, float, float]) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Crop using normalized box; returns crop and absolute pixel bbox (x0,y0,x1,y1)."""
    h, w = image.shape[:2]
    x0 = max(0, min(w - 1, int(box[0] * w)))
    y0 = max(0, min(h - 1, int(box[1] * h)))
    x1 = max(x0 + 1, min(w, int(box[2] * w)))
    y1 = max(y0 + 1, min(h, int(box[3] * h)))
    return image[y0:y1, x0:x1].copy(), (x0, y0, x1, y1)


def extract_stamp(page: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int], dict[str, Any]]:
    stamp, bbox = crop_norm(page, STAMP_ROI_PAGE)
    meta = {
        "stamp_roi_norm": list(STAMP_ROI_PAGE),
        "stamp_roi_px": list(bbox),
        "template": "gost_2_104_form1_approx",
    }
    return stamp, bbox, meta


def iter_cells(stamp: np.ndarray):
    for spec in CELL_TEMPLATE_FORM1:
        cell_img, local_bbox = crop_norm(stamp, spec.box)
        yield spec, cell_img, local_bbox
