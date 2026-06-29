"""Shared document/file helpers."""

import os
import uuid
from typing import Optional

from fastapi import HTTPException, UploadFile

from app.config import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE_MB, UPLOAD_DIR
from app.models import DOC_KIND_CODES, MISC_DOCS_FOLDER


def validate_upload_file(file: UploadFile) -> None:
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Файл обязателен для загрузки.")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый тип файла. Разрешены: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )


async def _read_upload_contents(file: UploadFile) -> tuple[bytes, str]:
    validate_upload_file(file)
    contents = await file.read()
    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Файл слишком большой (максимум {MAX_UPLOAD_SIZE_MB} МБ).",
        )
    return contents, os.path.basename(file.filename)


def _resolve_upload_subdirectory(
    project_slug: str,
    *,
    doc_kind_code: Optional[str] = None,
    misc_document: bool = False,
) -> str:
    if misc_document:
        return os.path.join(UPLOAD_DIR, project_slug, MISC_DOCS_FOLDER)
    if doc_kind_code and doc_kind_code in DOC_KIND_CODES:
        return os.path.join(UPLOAD_DIR, project_slug, doc_kind_code)
    return os.path.join(UPLOAD_DIR, project_slug)


async def save_upload_file(
    doc_id: int,
    file: UploadFile,
    project_slug: str,
    old_path: Optional[str] = None,
    *,
    doc_kind_code: Optional[str] = None,
) -> tuple[str, str]:
    contents, safe_name = await _read_upload_contents(file)

    if old_path and os.path.exists(old_path):
        os.remove(old_path)

    upload_dir = _resolve_upload_subdirectory(project_slug, doc_kind_code=doc_kind_code)
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{doc_id}_{safe_name}")

    with open(file_path, "wb") as buffer:
        buffer.write(contents)

    filename_base, extension = os.path.splitext(safe_name)
    unique_file_name = f"{filename_base}_{doc_id}{extension}"
    return file_path, unique_file_name


async def save_development_order_file(
    file: UploadFile,
    project_slug: str,
) -> tuple[str, str]:
    contents, safe_name = await _read_upload_contents(file)
    upload_dir = _resolve_upload_subdirectory(project_slug, misc_document=True)
    os.makedirs(upload_dir, exist_ok=True)
    unique_code = uuid.uuid4().hex[:8]
    filename_base, extension = os.path.splitext(safe_name)
    stored_name = f"{unique_code}_{filename_base}{extension}"
    file_path = os.path.join(upload_dir, stored_name)
    with open(file_path, "wb") as buffer:
        buffer.write(contents)
    return file_path, stored_name


def remove_file_if_exists(file_path: Optional[str]) -> None:
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
