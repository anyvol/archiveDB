import re
from pathlib import Path

from app.config import SERVICE_VERSION, read_version


def test_version_file_exists():
    version_path = Path(__file__).resolve().parents[1] / "VERSION"
    assert version_path.is_file()


def test_read_version_matches_file():
    version_path = Path(__file__).resolve().parents[1] / "VERSION"
    assert read_version() == version_path.read_text(encoding="utf-8").strip()


def test_service_version_is_semver():
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", SERVICE_VERSION)


def test_service_version_is_current_release():
    assert SERVICE_VERSION == "0.23.1"
