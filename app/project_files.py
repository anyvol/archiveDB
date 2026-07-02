"""Save and manage project-attached files and images."""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.document_helpers import _read_upload_contents, _sanitize_storage_name
from app.models import IMAGES_FOLDER, MISC_DOCS_FOLDER, Project, ProjectFile, ProjectImage, User
from app.project_helpers import ensure_project_directory, ensure_project_images_directory

DEFAULT_DEV_ORDER_TITLE = "Приказ на разработку"
_DEV_ORDER_UUID_PREFIX = re.compile(r"^[0-9a-f]{8}_", re.IGNORECASE)


def title_from_misc_filename(file_name: str) -> str:
    base = os.path.splitext(file_name)[0].strip()
    if not base:
        return DEFAULT_DEV_ORDER_TITLE
    if _DEV_ORDER_UUID_PREFIX.match(base):
        stripped = _DEV_ORDER_UUID_PREFIX.sub("", base, count=1).strip()
        return stripped or DEFAULT_DEV_ORDER_TITLE
    parts = base.rsplit("_", 1)
    if len(parts) == 2 and len(parts[1]) == 8 and parts[1].isalnum():
        return parts[0] or DEFAULT_DEV_ORDER_TITLE
    return base


async def save_project_file(
    session: AsyncSession,
    project: Project,
    title: str,
    file: UploadFile,
    user: User,
) -> ProjectFile:
    title = title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Укажите название документа.")

    contents, original_name = await _read_upload_contents(file)
    misc_dir = os.path.join(ensure_project_directory(project.slug), MISC_DOCS_FOLDER)
    os.makedirs(misc_dir, exist_ok=True)

    base_name = _sanitize_storage_name(os.path.splitext(original_name)[0])
    ext = os.path.splitext(original_name)[1].lower()
    stored_name = f"{base_name}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(misc_dir, stored_name)

    with open(file_path, "wb") as handle:
        handle.write(contents)

    record = ProjectFile(
        project_id=project.id,
        title=title,
        file_name=stored_name,
        file_path=file_path,
        uploaded_by=user.id,
        created_at=datetime.utcnow(),
    )
    session.add(record)
    await session.flush()
    return record


async def save_development_order_file(
    session: AsyncSession,
    project: Project,
    file: UploadFile,
    user: User,
    *,
    title: str | None = None,
) -> ProjectFile:
    if title is None:
        original = os.path.splitext(os.path.basename(file.filename or ""))[0].strip()
        title = original or DEFAULT_DEV_ORDER_TITLE
    return await save_project_file(session, project, title, file, user)


async def sync_project_misc_files(
    session: AsyncSession,
    project: Project,
    user: User,
) -> int:
    """Register files in «Прочие документы» that exist on disk but not in project_files."""
    misc_dir = os.path.join(ensure_project_directory(project.slug), MISC_DOCS_FOLDER)
    if not os.path.isdir(misc_dir):
        return 0

    result = await session.execute(
        select(ProjectFile.file_name, ProjectFile.file_path).where(
            ProjectFile.project_id == project.id
        )
    )
    rows = result.all()
    known_names = {row.file_name for row in rows}
    known_paths = {os.path.normpath(row.file_path) for row in rows}

    added = 0
    for entry in os.scandir(misc_dir):
        if not entry.is_file():
            continue
        norm_path = os.path.normpath(entry.path)
        if entry.name in known_names or norm_path in known_paths:
            continue
        session.add(
            ProjectFile(
                project_id=project.id,
                title=title_from_misc_filename(entry.name),
                file_name=entry.name,
                file_path=norm_path,
                uploaded_by=user.id,
                created_at=datetime.utcfromtimestamp(entry.stat().st_mtime),
            )
        )
        added += 1

    if added:
        await session.flush()
    return added


async def save_project_images(
    session: AsyncSession,
    project: Project,
    files: list[UploadFile],
) -> list[ProjectImage]:
    images_dir = ensure_project_images_directory(project.slug)
    saved: list[ProjectImage] = []

    for file in files:
        if not file or not file.filename:
            continue
        contents, original_name = await _read_upload_contents(file)
        ext = os.path.splitext(original_name)[1].lower()
        if ext not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".bmp"}:
            raise HTTPException(
                status_code=400,
                detail="Для фото проекта допустимы изображения: PNG, JPG, GIF, WEBP, TIFF, BMP.",
            )

        base_name = _sanitize_storage_name(os.path.splitext(original_name)[0])
        stored_name = f"{base_name}_{uuid.uuid4().hex[:8]}{ext}"
        file_path = os.path.join(images_dir, stored_name)
        with open(file_path, "wb") as handle:
            handle.write(contents)

        image = ProjectImage(
            project_id=project.id,
            file_name=stored_name,
            file_path=file_path,
            created_at=datetime.utcnow(),
        )
        session.add(image)
        saved.append(image)

    await session.flush()
    return saved


def remove_project_file_from_disk(file_path: str) -> None:
    if file_path and os.path.isfile(file_path):
        os.remove(file_path)
