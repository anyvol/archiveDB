"""Storage and traffic statistics for the admin dashboard."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.config import BACKUP_HOST_PATH, UPLOAD_DIR
from app.models import BaseDocument, Project, ProjectFile, ProjectImage, User


def _dir_size(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    total_bytes = 0
    file_count = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            file_count += 1
            try:
                total_bytes += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total_bytes, file_count


async def collect_traffic_stats(session: AsyncSession) -> dict:
    upload_path = Path(UPLOAD_DIR)
    upload_bytes, upload_files = _dir_size(upload_path)

    backup_path = Path(BACKUP_HOST_PATH)
    backup_bytes, backup_files = _dir_size(backup_path)

    users_count = (await session.execute(select(func.count(User.id)))).scalar() or 0
    docs_count = (await session.execute(select(func.count(BaseDocument.id)))).scalar() or 0
    projects_count = (await session.execute(select(func.count(Project.id)))).scalar() or 0
    project_files_count = (await session.execute(select(func.count(ProjectFile.id)))).scalar() or 0
    project_images_count = (await session.execute(select(func.count(ProjectImage.id)))).scalar() or 0

    return {
        "upload_bytes": upload_bytes,
        "upload_files": upload_files,
        "backup_bytes": backup_bytes,
        "backup_files": backup_files,
        "users_count": users_count,
        "docs_count": docs_count,
        "projects_count": projects_count,
        "project_files_count": project_files_count,
        "project_images_count": project_images_count,
        "upload_path": str(upload_path.resolve()) if upload_path.exists() else UPLOAD_DIR,
        "backup_path": BACKUP_HOST_PATH,
    }


def format_bytes(num: int) -> str:
    if num < 1024:
        return f"{num} B"
    if num < 1024 ** 2:
        return f"{num / 1024:.1f} KB"
    if num < 1024 ** 3:
        return f"{num / 1024 ** 2:.1f} MB"
    return f"{num / 1024 ** 3:.2f} GB"
