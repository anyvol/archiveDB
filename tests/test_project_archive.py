from app.models import Project
from app.project_archive import build_project_archive_filename


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
