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
    product_slug: Optional[str] = None,
    doc_kind_code: Optional[str] = None,
    misc_document: bool = False,
) -> str:
    base = os.path.join(UPLOAD_DIR, project_slug)
    if product_slug:
        base = os.path.join(base, product_slug)
    if misc_document:
        return os.path.join(base, MISC_DOCS_FOLDER)
    if doc_kind_code and doc_kind_code in DOC_KIND_CODES:
        return os.path.join(base, doc_kind_code)
    return base


def resolve_document_storage_slugs(doc) -> tuple[str, Optional[str]]:
    """Return (project_slug, product_slug) for a document; product_slug may be None for legacy records."""
    project_slug = doc.project.slug if doc.project else "_legacy"
    product_slug = doc.product.slug if getattr(doc, "product", None) else None
    return project_slug, product_slug


def _sanitize_storage_name(name: str) -> str:
    sanitized = _UNSAFE_FILENAME_CHARS.sub("_", name).strip()
    return sanitized or "file"


def _upload_basename_matches_designation(original_name: str, designation: str) -> bool:
    filename_base, _ = os.path.splitext(os.path.basename(original_name))
    return filename_base.strip().casefold() == designation.strip().casefold()


def _matches_stored_file_name(
    original_name: str,
    designation: str,
    doc_name: Optional[str] = None,
) -> bool:
    original_name = os.path.basename(original_name)
    filename_base, extension = os.path.splitext(original_name)
    title = (doc_name or "").strip()
    if not title:
        return False

    des = designation.strip()
    if original_name.casefold() == f"{des} - {title}{extension}".casefold():
        return True

    prefix = f"{des} ("
    suffix = f") - {title}"
    base = filename_base.strip()
    return base.casefold().startswith(prefix.casefold()) and base.casefold().endswith(suffix.casefold())


def compute_stored_file_name(
    designation: Optional[str],
    original_name: str,
    doc_name: Optional[str] = None,
) -> str:
    original_name = os.path.basename(original_name)
    if not designation:
        return original_name

    if _matches_stored_file_name(original_name, designation, doc_name):
        return original_name

    filename_base, extension = os.path.splitext(original_name)
    title = (doc_name or "").strip() or filename_base
    if _upload_basename_matches_designation(original_name, designation):
        stored = f"{designation} - {title}{extension}"
    else:
        stored = f"{designation} ({filename_base}) - {title}{extension}"

    if original_name.casefold() == stored.casefold():
        return original_name
    return stored


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
    product_slug: Optional[str] = None,
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

    upload_dir = _resolve_upload_subdirectory(
        project_slug,
        product_slug=product_slug,
        doc_kind_code=doc_kind_code,
    )
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, disk_name)

    with open(file_path, "wb") as buffer:
        buffer.write(contents)

    return file_path, stored_name


def compute_renamed_file_name_for_doc_name_change(
    designation: Optional[str],
    current_file_name: str,
    new_doc_name: Optional[str],
) -> str:
    """Compute a new stored file name when only doc_name changes."""
    current_file_name = os.path.basename(current_file_name)
    if not designation:
        return current_file_name

    new_title = (new_doc_name or "").strip()
    if not new_title:
        return current_file_name

    filename_base, extension = os.path.splitext(current_file_name)
    des = designation.strip()

    simple_prefix = f"{des} - "
    if filename_base.casefold().startswith(simple_prefix.casefold()):
        stored = f"{des} - {new_title}{extension}"
        if current_file_name.casefold() == stored.casefold():
            return current_file_name
        return stored

    paren_prefix = f"{des} ("
    paren_suffix = ") - "
    base = filename_base.strip()
    if base.casefold().startswith(paren_prefix.casefold()) and paren_suffix in base:
        inner_end = base.rfind(paren_suffix)
        inner_part = base[len(paren_prefix):inner_end]
        stored = f"{des} ({inner_part}) - {new_title}{extension}"
        if current_file_name.casefold() == stored.casefold():
            return current_file_name
        return stored

    return compute_stored_file_name(designation, current_file_name, new_doc_name)


def remove_file_if_exists(file_path: Optional[str]) -> None:
    if file_path and os.path.exists(file_path):
        os.remove(file_path)


def rename_document_file_for_doc_name(
    doc,
    new_doc_name: Optional[str],
    designation: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Rename the stored file when doc_name changes.

    Returns (old_file_name, new_file_name) when a rename was performed,
    otherwise (None, None). Raises HTTPException on disk conflicts.
    """
    if not doc.file_path or not doc.file_name or not os.path.exists(doc.file_path):
        return None, None

    new_file_name = compute_renamed_file_name_for_doc_name_change(
        designation, doc.file_name, new_doc_name
    )
    if new_file_name.casefold() == doc.file_name.casefold():
        return None, None

    new_disk_name = _sanitize_storage_name(new_file_name)
    new_path = os.path.join(os.path.dirname(doc.file_path), new_disk_name)
    if (
        os.path.exists(new_path)
        and os.path.normcase(new_path) != os.path.normcase(doc.file_path)
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Файл «{new_file_name}» уже существует на сервере.",
        )

    os.rename(doc.file_path, new_path)
    old_file_name = doc.file_name
    doc.file_path = new_path
    doc.file_name = new_file_name
    return old_file_name, new_file_name
