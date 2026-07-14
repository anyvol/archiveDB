"""Parse specification table rows from OCR text."""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from pipeline.ocr_engine import ocr_cell
from pipeline.spec_detect import GOST_SECTIONS, _DESIGNATION_RE

_ROW_DES_RE = re.compile(
    r"([A-ZА-ЯЁ]{2,8}\.[A-ZА-ЯЁ0-9]{2,8}\.\d{3}(?:-[0-9]{1,2})?(?:[A-ZА-ЯЁ]{2})?)",
    re.IGNORECASE,
)


def _normalize_section_line(line: str) -> str | None:
    upper = line.upper().strip()
    for section in GOST_SECTIONS:
        if section.upper() in upper and len(upper) < len(section) + 8:
            return section
    return None


def parse_spec_rows_from_text(text: str) -> list[dict[str, Any]]:
    """Heuristic line parser for specification tables."""
    if not text:
        return []
    current_section = ""
    rows: list[dict[str, Any]] = []
    order = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        section = _normalize_section_line(line)
        if section:
            current_section = section
            continue

        des_match = _ROW_DES_RE.search(line.replace(" ", ""))
        if not des_match:
            continue
        designation = des_match.group(1).upper()
        tail = line[des_match.end() :].strip(" -–—\t")
        parts = re.split(r"\s{2,}|\t", tail)
        name = parts[0].strip() if parts else tail
        qty = None
        for part in parts[1:]:
            if re.fullmatch(r"\d+([.,]\d+)?", part.strip()):
                qty = part.strip()
                break

        rows.append(
            {
                "section": current_section,
                "position": None,
                "format": None,
                "zone": None,
                "designation": designation,
                "name": name or None,
                "quantity": qty,
                "note": None,
                "sort_order": order,
            }
        )
        order += 1
    return rows


def extract_spec_rows_from_pages(
    pages: list[np.ndarray],
    spec_page_indices: list[int],
    *,
    embedded_pages: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """OCR spec pages (or embedded top band) and parse table rows."""
    embedded_pages = embedded_pages or []
    embedded_by_page = {int(item.get("page", 0)): item for item in embedded_pages if isinstance(item, dict)}
    all_rows: list[dict[str, Any]] = []
    base_order = 0

    indices = set(spec_page_indices or [])
    for item in embedded_pages:
        indices.add(int(item.get("page", 0)))

    for index in sorted(indices):
        if index < 0 or index >= len(pages):
            continue
        page = pages[index]
        crop = page
        if index in embedded_by_page:
            split_y = float(embedded_by_page[index].get("split_y_norm") or 0.55)
            split_y = max(0.1, min(0.9, split_y))
            crop = page[: int(page.shape[0] * split_y), :, :]
        text = (ocr_cell(crop, category="text").get("raw") or "").strip()
        rows = parse_spec_rows_from_text(text)
        for row in rows:
            row["sort_order"] = base_order
            row["page_index"] = index
            base_order += 1
            all_rows.append(row)
    return all_rows
