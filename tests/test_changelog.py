"""Tests for CHANGELOG rendering."""

from app.changelog import get_changelog_sections, render_changelog_html
from app.config import SERVICE_VERSION


def test_get_changelog_sections_all_versions():
    sections = get_changelog_sections()
    versions = [version for version, _ in sections]
    assert SERVICE_VERSION in versions
    assert "0.9.0" in versions
    assert "0.8.0" in versions


def test_get_changelog_sections_from_version():
    sections = get_changelog_sections(SERVICE_VERSION)
    versions = [version for version, _ in sections]
    assert SERVICE_VERSION in versions
    assert "0.9.0" not in versions


def test_render_changelog_html_includes_all_versions():
    html = render_changelog_html()
    assert SERVICE_VERSION in html
    assert "0.9.0" in html
    assert "0.8.0" in html
