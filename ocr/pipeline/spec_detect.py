"""GOST R 2.106-2019 based specification detection and document classification."""

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
_ASSEMBLY_KIND_RE = re.compile(r"СБ\s*$", re.IGNORECASE)

GOST_SECTIONS = (
    "Документация",
    "Комплексы",
    "Сборочные единицы",
    "Детали",
    "Стандартные изделия",
    "Прочие изделия",
    "Материалы",
    "Комплекты",
)

_COLUMN_MARKERS = (
    ("поз", 3.0),
    ("обознач", 3.0),
    ("наимен", 3.0),
    ("кол", 2.0),
    ("формат", 1.5),
    ("зона", 1.0),
    ("примеч", 1.0),
)


def _page_header_text(page: np.ndarray) -> str:
    if page.ndim != 3 or page.shape[0] < 40:
        return ""
    header_h = max(40, int(page.shape[0] * 0.12))
    header = page[:header_h, :, :]
    result = ocr_cell(header, category="text")
    return (result.get("raw") or result.get("value") or "").strip()


def _page_body_text(page: np.ndarray, *, max_side: int = 2200) -> str:
    import cv2

    h, w = page.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    work = page
    if scale < 0.99:
        work = cv2.resize(page, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    result = ocr_cell(work, category="text")
    return (result.get("raw") or result.get("value") or "").upper()


def _find_sections(text: str) -> list[str]:
    upper = text.upper()
    found: list[str] = []
    for section in GOST_SECTIONS:
        if section.upper() in upper:
            found.append(section)
    return found


def _column_score(text: str) -> float:
    upper = text.upper().replace(".", "").replace(" ", "")
    score = 0.0
    for marker, weight in _COLUMN_MARKERS:
        if marker in upper:
            score += weight
    return score


def _page_designations(text: str) -> list[str]:
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


def _score_spec_page(page: np.ndarray) -> dict[str, Any]:
    header = _page_header_text(page)
    body = _page_body_text(page)
    sections = _find_sections(body)
    col_score = _column_score(body)
    designations = _page_designations(body)
    title_hit = bool(_SPEC_TITLE_RE.search(header)) or bool(_SPEC_TITLE_RE.search(body[:200]))

    score = 0.0
    markers: dict[str, Any] = {
        "title": title_hit,
        "sections": sections,
        "column_score": col_score,
        "designation_count": len(designations),
    }

    if title_hit:
        score += 4.0
    if len(sections) >= 2:
        score += 3.0
    elif len(sections) == 1:
        score += 1.5
    score += min(col_score, 6.0)
    if len(designations) >= 3:
        score += 2.0
    elif len(designations) >= 1 and col_score >= 4:
        score += 1.0

    is_spec = score >= 5.0 or (title_hit and col_score >= 3.0)
    return {
        "score": score,
        "is_spec": is_spec,
        "sections": sections,
        "designations": designations,
        "markers": markers,
        "body_text": body,
    }


def _detect_assembly_on_page(page: np.ndarray, body_text: str | None = None) -> bool:
    body = body_text or _page_body_text(page)
    if _ASSEMBLY_KIND_RE.search(body):
        return True
    if "СБ" in body and "СБОРОЧ" in body:
        return True
    return False


def _estimate_embedded_split_y(page: np.ndarray, stamp_roi_top: float | None = None) -> float:
    """Normalized Y where spec table ends above stamp (combined A4)."""
    if stamp_roi_top is not None and 0.05 < stamp_roi_top < 0.95:
        return max(0.15, stamp_roi_top - 0.02)
    return 0.55


def classify_document(
    pages: list[np.ndarray],
    *,
    format_hint: str | None = None,
    stamp_roi_top_norm: float | None = None,
) -> dict[str, Any]:
    """Classify uploaded document and locate specification content."""
    if not pages:
        return {
            "document_role": "assembly_drawing",
            "has_specification": False,
            "is_specification_document": False,
            "spec_page_indices": [],
            "assembly_page_indices": [],
            "embedded_spec_pages": [],
            "designations": [],
            "spec_designations": [],
            "sections_found": [],
            "detection_confidence": 0.0,
            "markers": {},
        }

    page_scores: list[dict[str, Any]] = []
    all_sections: list[str] = []
    all_designations: list[str] = []
    seen_des: set[str] = set()
    seen_sections: set[str] = set()

    for page in pages:
        scored = _score_spec_page(page)
        page_scores.append(scored)
        for section in scored["sections"]:
            if section not in seen_sections:
                seen_sections.add(section)
                all_sections.append(section)
        for des in scored["designations"]:
            if des not in seen_des:
                seen_des.add(des)
                all_designations.append(des)

    spec_indices = [i for i, s in enumerate(page_scores) if s["is_spec"]]
    assembly_indices = [
        i for i, page in enumerate(pages) if not page_scores[i]["is_spec"] or _detect_assembly_on_page(page, page_scores[i].get("body_text"))
    ]
    if not assembly_indices and pages:
        assembly_indices = [0]

    embedded: list[dict[str, Any]] = []
    is_a4 = (format_hint or "").upper() == "A4"
    if len(pages) == 1 and page_scores[0]["is_spec"] and is_a4:
        split_y = _estimate_embedded_split_y(pages[0], stamp_roi_top_norm)
        embedded.append({"page": 0, "split_y_norm": split_y})
        document_role = "combined_a4"
        has_spec = True
        is_spec_doc = False
    elif spec_indices and len(spec_indices) == len(pages):
        document_role = "standalone_specification"
        has_spec = True
        is_spec_doc = True
        assembly_indices = []
    elif spec_indices and assembly_indices:
        document_role = "assembly_with_spec_pages"
        has_spec = True
        is_spec_doc = False
    elif spec_indices:
        document_role = "standalone_specification"
        has_spec = True
        is_spec_doc = True
    else:
        document_role = "assembly_drawing"
        has_spec = False
        is_spec_doc = False

    confidence_vals = [page_scores[i]["score"] for i in spec_indices] if spec_indices else [0.0]
    max_conf = max(confidence_vals) if confidence_vals else 0.0
    detection_confidence = min(1.0, max_conf / 10.0)

    return {
        "document_role": document_role,
        "has_specification": has_spec,
        "is_specification_document": is_spec_doc,
        "spec_page_indices": spec_indices,
        "assembly_page_indices": sorted(set(assembly_indices)),
        "embedded_spec_pages": embedded,
        "designations": all_designations,
        "spec_designations": all_designations,
        "sections_found": all_sections,
        "detection_confidence": round(detection_confidence, 3),
        "markers": {
            "page_scores": [p["markers"] for p in page_scores],
            "format_hint": format_hint,
        },
    }


def detect_specification_pages(pages: list[np.ndarray]) -> dict[str, Any]:
    """Backward-compatible wrapper used by existing tests."""
    result = classify_document(pages)
    return {
        "has_specification": result["has_specification"],
        "spec_page_indices": result["spec_page_indices"],
        "designations": result["designations"],
    }
