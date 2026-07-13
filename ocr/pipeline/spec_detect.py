"""Detect specification pages and referenced designations in multi-page drawings."""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from pipeline.ocr_engine import ocr_cell

_SPEC_TITLE_RE = re.compile(r"СПЕЦИФИКАЦ", re.IGNORECASE)
_DESIGNATION_RE = re.compile(
    r"[A-ZА-ЯЁ]{2,8}\.[A-ZА-ЯЁ0-9]{2,8}\.\d{3}(?:-[0-9]{1,2})?(?:[A-ZА-ЯЁ]{2})?",
    re.IGNORECASE,
)


def _page_header_text(page: np.ndarray) -> str:
    """OCR the top band of a page to find a specification title."""
    if page.ndim != 3 or page.shape[0] < 40:
        return ""
    header_h = max(40, int(page.shape[0] * 0.12))
    header = page[:header_h, :, :]
    result = ocr_cell(header, category="text")
    return (result.get("raw") or result.get("value") or "").strip()


def _page_designations(page: np.ndarray) -> list[str]:
    """Extract designation-like tokens from a full page (downscaled for speed)."""
    import cv2

    h, w = page.shape[:2]
    max_side = 2200
    scale = min(1.0, max_side / max(h, w))
    if scale < 0.99:
        page = cv2.resize(page, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    result = ocr_cell(page, category="text")
    text = (result.get("raw") or result.get("value") or "").upper()
    if not text:
        return []

    found: list[str] = []
    seen: set[str] = set()
    for match in _DESIGNATION_RE.finditer(text.replace(" ", "")):
        token = match.group(0).upper()
        if token not in seen:
            seen.add(token)
            found.append(token)
    return found


def detect_specification_pages(pages: list[np.ndarray]) -> dict[str, Any]:
    """Return spec page indices and designations found on specification sheets."""
    if len(pages) <= 1:
        return {
            "has_specification": False,
            "spec_page_indices": [],
            "designations": [],
        }

    spec_indices: list[int] = []
    designations: list[str] = []
    seen_designations: set[str] = set()

    for index, page in enumerate(pages):
        header = _page_header_text(page)
        is_spec = bool(_SPEC_TITLE_RE.search(header))
        if not is_spec and index > 0:
            # Secondary heuristic: spec sheets often contain many designations in a table.
            page_designations = _page_designations(page)
            if len(page_designations) >= 3:
                is_spec = True

        if not is_spec:
            continue

        spec_indices.append(index)
        for designation in _page_designations(page):
            if designation not in seen_designations:
                seen_designations.add(designation)
                designations.append(designation)

    return {
        "has_specification": bool(spec_indices),
        "spec_page_indices": spec_indices,
        "designations": designations,
    }
