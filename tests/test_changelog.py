"""Tests for CHANGELOG rendering."""

from app.changelog import get_changelog_sections, render_changelog_html


def test_get_changelog_sections_from_current_version():
    sections = get_changelog_sections("0.9.1")
    versions = [version for version, _ in sections]
    assert "0.9.1" in versions
    assert "0.9.0" not in versions


def test_render_changelog_html_includes_current_version():
    html = render_changelog_html("0.9.1")
    assert "0.9.1" in html
    assert "HTTPS" in html
    assert "0.9.0" not in html
