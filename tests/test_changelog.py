"""Tests for CHANGELOG rendering."""

from app.changelog import get_changelog_sections, render_changelog_html
from app.config import SERVICE_VERSION


def test_get_changelog_sections_from_current_version():
    sections = get_changelog_sections(SERVICE_VERSION)
    versions = [version for version, _ in sections]
    assert SERVICE_VERSION in versions
    assert "0.9.0" not in versions


def test_render_changelog_html_includes_current_version():
    html = render_changelog_html(SERVICE_VERSION)
    assert SERVICE_VERSION in html
    assert "0.9.0" not in html
