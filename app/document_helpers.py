"""Shared document/file helpers."""

import os
import shutil
from typing import Optional

from fastapi import HTTPException, UploadFile

from app.config import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE_MB, UPLOAD_DIR


def validate_upload_file(file: UploadFile) -> None:
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Файл обязателен для загрузки.")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый тип файла. Разрешены: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )


async def save_upload_file(doc_id: int, file: UploadFile, old_path: Optional[str] = None) -> tuple[str, str]:
    validate_upload_file(file)

    contents = await file.read()
    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Файл слишком большой (максимум {MAX_UPLOAD_SIZE_MB} МБ).",
        )

    if old_path and os.path.exists(old_path):
        os.remove(old_path)

    safe_name = os.path.basename(file.filename)
    file_path = os.path.join(UPLOAD_DIR, f"{doc_id}_{safe_name}")

    with open(file_path, "wb") as buffer:
        buffer.write(contents)

    filename_base, extension = os.path.splitext(safe_name)
    unique_file_name = f"{filename_base}_{doc_id}{extension}"
    return file_path, unique_file_name


def remove_file_if_exists(file_path: Optional[str]) -> None:
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
