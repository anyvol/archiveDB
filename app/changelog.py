"""Parse and render CHANGELOG.md for the web UI."""

from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path

_CHANGELOG_FILE = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
_VERSION_HEADER = re.compile(r"^##\s+(\d+\.\d+\.\d+)\s*$")


def _parse_version(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


@lru_cache(maxsize=1)
def _load_sections() -> list[tuple[str, list[str]]]:
    if not _CHANGELOG_FILE.is_file():
        return []

    sections: list[tuple[str, list[str]]] = []
    current_version: str | None = None
    current_lines: list[str] = []

    for raw_line in _CHANGELOG_FILE.read_text(encoding="utf-8").splitlines():
        match = _VERSION_HEADER.match(raw_line.strip())
        if match:
            if current_version is not None:
                sections.append((current_version, current_lines))
            current_version = match.group(1)
            current_lines = []
            continue
        if current_version is not None:
            current_lines.append(raw_line)

    if current_version is not None:
        sections.append((current_version, current_lines))
    return sections


def get_changelog_sections(from_version: str | None = None) -> list[tuple[str, list[str]]]:
    sections = _load_sections()
    if from_version is None:
        return sections
    threshold = _parse_version(from_version)
    return [
        (version, lines)
        for version, lines in sections
        if _parse_version(version) >= threshold
    ]


def render_changelog_html(from_version: str | None = None) -> str:
    sections = get_changelog_sections(from_version)
    if not sections:
        return "<p>Changelog is not available.</p>"

    parts: list[str] = []
    for version, lines in sections:
        parts.append(f'<section class="changelog-section" id="v{html.escape(version)}">')
        parts.append(f"<h2>{html.escape(version)}</h2>")
        parts.append("<ul>")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- "):
                parts.append(f"<li>{html.escape(stripped[2:])}</li>")
        parts.append("</ul>")
        parts.append("</section>")
    return "\n".join(parts)
