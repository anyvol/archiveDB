"""Extract page/image dimensions from uploaded files for format detection."""

from __future__ import annotations

import io
import os

from app.document_format import detect_format_from_dimensions

_POINTS_TO_MM = 25.4 / 72.0


def _pdf_dimensions_mm(contents: bytes) -> tuple[float, float] | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None

    try:
        reader = PdfReader(io.BytesIO(contents))
        if not reader.pages:
            return None
        page = reader.pages[0]
        box = page.mediabox
        width_pt = float(box.width)
        height_pt = float(box.height)
        return width_pt * _POINTS_TO_MM, height_pt * _POINTS_TO_MM
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
            width_mm = img.width / x_dpi * 25.4
            height_mm = img.height / y_dpi * 25.4
            return width_mm, height_mm
    except Exception:
        return None


def detect_document_format_from_bytes(contents: bytes, filename: str) -> str | None:
    ext = os.path.splitext(filename)[1].lower()
    dims: tuple[float, float] | None = None

    if ext == ".pdf":
        dims = _pdf_dimensions_mm(contents)
    elif ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}:
        dims = _image_dimensions_mm(contents)

    if not dims:
        return None
    return detect_format_from_dimensions(dims[0], dims[1])
