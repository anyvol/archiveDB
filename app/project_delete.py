"""Delete projects and related files."""

from __future__ import annotations

import os
import shutil

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import UPLOAD_DIR
from app.models import BaseDocument, Project, ProjectFile, ProjectImage

LEGACY_PROJECT_SLUG = "_legacy"


async def delete_project(session: AsyncSession, project: Project) -> None:
    if project.slug == LEGACY_PROJECT_SLUG:
        raise HTTPException(status_code=400, detail="Системный проект нельзя удалить.")

    doc_count = await session.scalar(
        select(func.count()).select_from(BaseDocument).where(BaseDocument.project_id == project.id)
    )
    if doc_count:
        raise HTTPException(
            status_code=400,
            detail=f"Нельзя удалить проект: в архиве {doc_count} записей. Сначала перенесите или удалите документы.",
        )

    project_id = project.id
    project_slug = project.slug

    await session.execute(delete(ProjectFile).where(ProjectFile.project_id == project_id))
    await session.execute(delete(ProjectImage).where(ProjectImage.project_id == project_id))
    await session.delete(project)
    await session.commit()

    project_dir = os.path.join(UPLOAD_DIR, project_slug)
    if os.path.isdir(project_dir):
        shutil.rmtree(project_dir, ignore_errors=True)
