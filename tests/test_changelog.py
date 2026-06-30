"""Tests for CHANGELOG rendering."""

from app.changelog import get_changelog_sections, render_changelog_html


def test_get_changelog_sections_includes_all_versions():
    sections = get_changelog_sections()
    versions = [version for version, _ in sections]
    assert "0.9.2" in versions
    assert "0.9.1" in versions
    assert "0.9.0" in versions
    assert "0.8.0" in versions
    assert versions.index("0.9.2") < versions.index("0.9.1")


def test_render_changelog_html_includes_history():
    html = render_changelog_html()
    assert "0.9.2" in html
    assert "0.9.1" in html
    assert "0.9.0" in html
    assert "0.8.0" in html
