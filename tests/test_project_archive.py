from app.models import Project
from app.project_archive import build_attachment_content_disposition, build_project_archive_filename


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


def test_build_attachment_content_disposition_is_latin1_safe_for_cyrillic():
    filename = "Танк (Т-300)_20250708_123456_6.zip"
    header = build_attachment_content_disposition(filename)
    header.encode("latin-1")
    assert 'filename="' in header
    assert "filename*=UTF-8''" in header
    assert "%D0" in header
