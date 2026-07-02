"""ISO A-series document format definitions and dimension matching."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentFormatOption:
    code: str
    label: str
    width_mm: float
    height_mm: float


# Portrait orientation; landscape is matched by swapping dimensions.
DOCUMENT_FORMATS: tuple[DocumentFormatOption, ...] = (
    DocumentFormatOption("A0", "A0 — 841×1189 мм", 841, 1189),
    DocumentFormatOption("A1", "A1 — 594×841 мм", 594, 841),
    DocumentFormatOption("A2", "A2 — 420×594 мм", 420, 594),
    DocumentFormatOption("A3", "A3 — 297×420 мм", 297, 420),
    DocumentFormatOption("A4", "A4 — 210×297 мм", 210, 297),
    DocumentFormatOption("A5", "A5 — 148×210 мм", 148, 210),
    DocumentFormatOption("A3x3", "A3×3 — 1260×297 мм", 1260, 297),
    DocumentFormatOption("A2x2", "A2×2 — 420×1188 мм", 420, 1188),
    DocumentFormatOption("A1x2", "A1×2 — 594×1682 мм", 594, 1682),
)

DOCUMENT_FORMAT_CODES = frozenset(fmt.code for fmt in DOCUMENT_FORMATS)
DOCUMENT_FORMAT_LABELS = {fmt.code: fmt.label for fmt in DOCUMENT_FORMATS}

_TOLERANCE_MM = 4.0


def _normalize_dimensions(width: float, height: float) -> tuple[float, float]:
    if width <= 0 or height <= 0:
        return width, height
    return (min(width, height), max(width, height))


def _dimensions_match(
    actual_w: float,
    actual_h: float,
    expected_w: float,
    expected_h: float,
    tolerance: float = _TOLERANCE_MM,
) -> bool:
    aw, ah = _normalize_dimensions(actual_w, actual_h)
    ew, eh = _normalize_dimensions(expected_w, expected_h)
    return abs(aw - ew) <= tolerance and abs(ah - eh) <= tolerance


def detect_format_from_dimensions(width_mm: float, height_mm: float) -> str | None:
    """Return format code if dimensions match a known format (portrait or landscape)."""
    for fmt in DOCUMENT_FORMATS:
        if _dimensions_match(width_mm, height_mm, fmt.width_mm, fmt.height_mm):
            return fmt.code
    return None


def is_valid_document_format(code: str) -> bool:
    return code in DOCUMENT_FORMAT_CODES
