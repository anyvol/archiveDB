"""Minimal ISO A-series format detection for the OCR sidecar (stub phase)."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class _Format:
    code: str
    width_mm: float
    height_mm: float


_FORMATS = (
    _Format("A0", 841, 1189),
    _Format("A1", 594, 841),
    _Format("A2", 420, 594),
    _Format("A3", 297, 420),
    _Format("A4", 210, 297),
    _Format("A5", 148, 210),
    _Format("A3x3", 1260, 297),
    _Format("A2x2", 420, 1188),
    _Format("A1x2", 594, 1682),
)

_TOLERANCE_MM = 4.0
_POINTS_TO_MM = 25.4 / 72.0


def _normalize(width: float, height: float) -> tuple[float, float]:
    if width <= 0 or height <= 0:
        return width, height
    return (min(width, height), max(width, height))


def detect_format_from_dimensions(width_mm: float, height_mm: float) -> str | None:
    aw, ah = _normalize(width_mm, height_mm)
    for fmt in _FORMATS:
        ew, eh = _normalize(fmt.width_mm, fmt.height_mm)
        if abs(aw - ew) <= _TOLERANCE_MM and abs(ah - eh) <= _TOLERANCE_MM:
            return fmt.code
    return None


def _pdf_dimensions_mm(contents: bytes) -> tuple[float, float] | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(io.BytesIO(contents))
        if not reader.pages:
            return None
        box = reader.pages[0].mediabox
        return float(box.width) * _POINTS_TO_MM, float(box.height) * _POINTS_TO_MM
    except Exception:
        return None


def _image_dimensions_mm(contents: bytes) -> tuple[float, float] | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(contents)) as img:
            dpi = img.info.get("dpi")
            if dpi and isinstance(dpi, tuple) and dpi[0] and dpi[1]:
                x_dpi, y_dpi = float(dpi[0]), float(dpi[1])
            else:
                x_dpi = y_dpi = 96.0
            return img.width / x_dpi * 25.4, img.height / y_dpi * 25.4
    except Exception:
        return None


def detect_format_from_file(path: str) -> tuple[str | None, int]:
    """Return (format_code, page_count). Stub: page_count is 1 for images, PDF page count for PDFs."""
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, "rb") as fh:
            contents = fh.read()
    except OSError:
        return None, 0

    page_count = 1
    dims: tuple[float, float] | None = None
    if ext == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(contents))
            page_count = len(reader.pages) or 0
        except Exception:
            page_count = 0
        dims = _pdf_dimensions_mm(contents)
    elif ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}:
        dims = _image_dimensions_mm(contents)

    if not dims:
        return None, page_count
    return detect_format_from_dimensions(dims[0], dims[1]), page_count
