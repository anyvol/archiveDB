"""Shared document/file helpers."""

import os
import re
import uuid
import shutil
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, UploadFile

from app.config import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE_MB, UPLOAD_DIR
from app.models import DOC_KIND_CODES, MISC_DOCS_FOLDER

_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


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


def _sanitize_storage_name(name: str) -> str:
    sanitized = _UNSAFE_FILENAME_CHARS.sub("_", name).strip()
    return sanitized or "file"


def _matches_renamed_with_doc_name(base: str, designation: str, doc_name: str) -> bool:
    des = designation.strip()
    title = doc_name.strip()
    if base.casefold() == f"{des} - {title}".casefold():
        return True
    suffix = f") - {title}"
    if not base.casefold().endswith(suffix.casefold()):
        return False
    paren_start = base.find(" (")
    if paren_start < 0:
        return False
    return base[:paren_start].casefold() == des.casefold()


def file_name_matches_designation(
    original_name: str,
    designation: str,
    doc_name: Optional[str] = None,
) -> bool:
    filename_base, _ = os.path.splitext(os.path.basename(original_name))
    base = filename_base.strip()
    des = designation.strip()
    title = (doc_name or "").strip()
    if title:
        return _matches_renamed_with_doc_name(base, des, title)
    if base.casefold() == des.casefold():
        return True
    prefix = f"{des} ("
    return base.casefold().startswith(prefix.casefold()) and base.endswith(")")


def compute_stored_file_name(
    designation: Optional[str],
    original_name: str,
    doc_name: Optional[str] = None,
) -> str:
    original_name = os.path.basename(original_name)
    des = (designation or "").strip()
    title = (doc_name or "").strip()

    if des and file_name_matches_designation(original_name, des, title or None):
        return original_name

    filename_base, extension = os.path.splitext(original_name)
    filename_base = filename_base.strip()

    if des and title:
        if filename_base.casefold() == des.casefold():
            return f"{des} - {title}{extension}"
        return f"{des} ({filename_base}) - {title}{extension}"

    if des and filename_base.casefold() != des.casefold():
        return f"{des} ({filename_base}){extension}"
    return original_name


def build_upload_rename_message(
    designation: str,
    original_name: str,
    doc_name: Optional[str] = None,
) -> str:
    stored_name = compute_stored_file_name(designation, original_name, doc_name)
    return f"Файл будет переименован в {stored_name}"


async def save_upload_file(
    file: UploadFile,
    project_slug: str,
    old_path: Optional[str] = None,
    *,
    doc_kind_code: Optional[str] = None,
    designation: Optional[str] = None,
    doc_name: Optional[str] = None,
    archive_old: bool = False,
    archive_dest_dir: Optional[str] = None,
) -> tuple[str, str]:
    contents, safe_name = await _read_upload_contents(file)

    if archive_old and old_path and os.path.exists(old_path) and archive_dest_dir:
        os.makedirs(archive_dest_dir, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        archived_name = f"{timestamp}_{os.path.basename(old_path)}"
        shutil.copy2(old_path, os.path.join(archive_dest_dir, archived_name))
    elif old_path and os.path.exists(old_path) and not archive_old:
        os.remove(old_path)

    stored_name = compute_stored_file_name(designation, safe_name, doc_name)
    disk_name = _sanitize_storage_name(stored_name)

    upload_dir = _resolve_upload_subdirectory(project_slug, doc_kind_code=doc_kind_code)
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, disk_name)

    with open(file_path, "wb") as buffer:
        buffer.write(contents)

    return file_path, stored_name


def remove_file_if_exists(file_path: Optional[str]) -> None:
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
