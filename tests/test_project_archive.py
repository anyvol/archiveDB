import os
import zipfile
from unittest.mock import patch

from app.models import Project
from app.project_archive import (
    _archive_entry_name,
    build_project_archive_file,
    build_project_archive_filename,
)


def test_build_project_archive_filename_contains_slug_date_and_id():
    project = Project(id=42, name="Demo", slug="demo-project")
    filename = build_project_archive_filename(project)
    assert filename.startswith("demo-project_")
    assert filename.endswith("_42.zip")
    body = filename.removesuffix(".zip")
    assert body.endswith("_42")
    timestamp_part = body[len("demo-project_") : -len("_42")]
    assert len(timestamp_part) == 15
    assert timestamp_part.replace("_", "").isdigit()


def test_archive_entry_name_uses_forward_slashes():
    assert _archive_entry_name("/data/project", "/data/project/СБ\\file.pdf") == "СБ/file.pdf"


def test_build_project_archive_file_creates_zip(tmp_path):
    upload_dir = tmp_path / "uploads"
    project_dir = upload_dir / "demo"
    kind_dir = project_dir / "СБ"
    kind_dir.mkdir(parents=True)
    sample = kind_dir / "doc.pdf"
    sample.write_bytes(b"pdf")

    project = Project(id=7, name="Demo", slug="demo")

    with patch("app.project_archive.UPLOAD_DIR", str(upload_dir)):
        archive_path, filename = build_project_archive_file(project)

    try:
        assert os.path.isfile(archive_path)
        assert filename.endswith("_7.zip")
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
        assert any(name.startswith("СБ/") for name in names)
        assert "СБ/doc.pdf" in names
    finally:
        if os.path.exists(archive_path):
            os.remove(archive_path)
