"""Save and manage project-attached files and images."""

from __future__ import annotations

import os
import uuid
from datetime import datetime

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.document_helpers import _read_upload_contents, _sanitize_storage_name
from app.models import IMAGES_FOLDER, MISC_DOCS_FOLDER, Project, ProjectFile, ProjectImage, User
from app.project_helpers import ensure_project_directory, ensure_project_images_directory


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
