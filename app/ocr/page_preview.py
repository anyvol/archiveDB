"""Render OCR job source pages to PNG for the review UI."""

from __future__ import annotations

import mimetypes
import os
from io import BytesIO

from fastapi import HTTPException
from PIL import Image


def guess_media_type(path: str, mime: str | None = None) -> str:
    if mime:
        return mime
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def _abs_path_under_upload(upload_dir: str, path: str) -> str:
    abs_upload = os.path.abspath(upload_dir)
    abs_path = os.path.abspath(path)
    if not (abs_path == abs_upload or abs_path.startswith(abs_upload + os.sep)):
        raise HTTPException(status_code=404, detail="Файл не найден.")
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Файл не найден.")
    return abs_path


def resolve_job_source_path(upload_dir: str, stored_path: str) -> str:
    return _abs_path_under_upload(upload_dir, stored_path)


def resolve_preview_path(upload_dir: str, rel_or_abs_path: str) -> str:
    path = rel_or_abs_path
    if not os.path.isabs(path):
        path = os.path.join(upload_dir, rel_or_abs_path)
    return _abs_path_under_upload(upload_dir, path)


def render_page_png_bytes(stored_path: str, page_index: int, *, dpi: int = 200) -> bytes:
    ext = os.path.splitext(stored_path)[1].lower()
    if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
        if page_index != 0:
            raise HTTPException(status_code=404, detail="Страница не найдена.")
        with Image.open(stored_path) as img:
            buf = BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            return buf.getvalue()

    if ext != ".pdf":
        raise HTTPException(status_code=400, detail="Предпросмотр страниц недоступен для этого формата.")

    try:
        import fitz
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="Предпросмотр PDF недоступен: не установлен PyMuPDF.",
        ) from exc

    doc = fitz.open(stored_path)
    try:
        if page_index < 0 or page_index >= len(doc):
            raise HTTPException(status_code=404, detail="Страница не найдена.")
        page = doc[page_index]
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()
