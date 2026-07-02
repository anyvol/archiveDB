"""Collect known person names and surnames from the database."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BaseDocument, User
from app.user_helpers import build_full_name, split_full_name

_PERSON_SPLIT = re.compile(r"[,;\n]+")


def normalize_person_name(value: str) -> str:
    """Return a single FIO string with empty parts trimmed (surname-only is allowed)."""
    value = (value or "").strip()
    if not value:
        return ""
    last_name, first_name, patronymic = split_full_name(value)
    if not last_name and not first_name and not patronymic:
        parts = [part for part in value.split() if part.strip()]
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return f"{parts[0]} {parts[1]}"
        return f"{parts[0]} {parts[1]} {' '.join(parts[2:])}"
    return build_full_name(last_name, first_name, patronymic)


def _add_person_value(names: set[str], raw: str | None) -> None:
    if not raw or not raw.strip():
        return
    for segment in _PERSON_SPLIT.split(raw):
        normalized = normalize_person_name(segment)
        if normalized:
            names.add(normalized)


async def fetch_known_person_names(session: AsyncSession) -> list[str]:
    """Return sorted unique normalized FIO values from users and documents."""
    names: set[str] = set()

    user_rows = await session.execute(select(User.full_name).where(User.full_name.isnot(None)))
    for (full_name,) in user_rows:
        _add_person_value(names, full_name)

    doc_rows = await session.execute(
        select(
            BaseDocument.developed_by,
            BaseDocument.created_by,
            BaseDocument.reviewed_by,
            BaseDocument.approved_by,
        )
    )
    for developed_by, created_by, reviewed_by, approved_by in doc_rows:
        _add_person_value(names, developed_by)
        _add_person_value(names, created_by)
        _add_person_value(names, reviewed_by)
        _add_person_value(names, approved_by)

    return sorted(names, key=lambda item: item.casefold())
