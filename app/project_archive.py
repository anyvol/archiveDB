"""Create downloadable archives of project folders."""

import os
import tempfile
import zipfile
from datetime import datetime

from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from app.config import UPLOAD_DIR
from app.models import Project


def build_project_archive_filename(project: Project) -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{project.slug}_{timestamp}_{project.id}.zip"


def _archive_entry_name(project_dir: str, full_path: str) -> str:
    """Use forward slashes inside ZIP entries (portable on Windows and Linux)."""
    return os.path.relpath(full_path, project_dir).replace("\\", "/")


def build_project_archive_file(project: Project) -> tuple[str, str]:
    project_dir = os.path.join(UPLOAD_DIR, project.slug)
    if not os.path.isdir(project_dir):
        raise HTTPException(status_code=404, detail="Папка проекта на сервере не найдена.")

    fd, temp_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            has_files = False
            for root, _dirs, files in os.walk(project_dir):
                for name in files:
                    full_path = os.path.join(root, name)
                    if not os.path.isfile(full_path):
                        continue
                    archive.write(full_path, _archive_entry_name(project_dir, full_path))
                    has_files = True
            if not has_files:
                archive.writestr(".keep", "")
    except OSError as exc:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(
            status_code=500,
            detail="Не удалось создать архив проекта. Проверьте доступ к файлам на сервере.",
        ) from exc
    except Exception as exc:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    return temp_path, build_project_archive_filename(project)


def stream_project_archive(project: Project, background_tasks: BackgroundTasks) -> FileResponse:
    temp_path, filename = build_project_archive_file(project)
    background_tasks.add_task(os.remove, temp_path)
    return FileResponse(
        path=temp_path,
        filename=filename,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
