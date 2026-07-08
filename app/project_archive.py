"""Create downloadable archives of project folders."""

import io
import os
import zipfile
from datetime import datetime
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.config import UPLOAD_DIR
from app.models import Project


def build_attachment_content_disposition(filename: str) -> str:
    """Build a latin-1-safe Content-Disposition header for non-ASCII filenames."""
    ascii_filename = filename.encode("ascii", "ignore").decode("ascii").strip() or "archive.zip"
    encoded_filename = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{encoded_filename}"


def build_project_archive_filename(project: Project) -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{project.slug}_{timestamp}_{project.id}.zip"


def iter_project_archive(project: Project):
    project_dir = os.path.join(UPLOAD_DIR, project.slug)
    if not os.path.isdir(project_dir):
        raise HTTPException(status_code=404, detail="Папка проекта на сервере не найдена.")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for root, _dirs, files in os.walk(project_dir):
            for name in files:
                full_path = os.path.join(root, name)
                arcname = os.path.relpath(full_path, project_dir)
                archive.write(full_path, arcname)

    buffer.seek(0)
    return buffer


def stream_project_archive(project: Project) -> StreamingResponse:
    archive_buffer = iter_project_archive(project)
    filename = build_project_archive_filename(project)
    return StreamingResponse(
        archive_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": build_attachment_content_disposition(filename)},
    )
