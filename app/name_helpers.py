"""Collect known person names and surnames from the database."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BaseDocument, User


def _split_name_parts(value: str) -> list[str]:
    parts = [part.strip() for part in value.replace(",", " ").split() if part.strip()]
    return parts


async def fetch_known_person_names(session: AsyncSession) -> list[str]:
    """Return sorted unique full names and surnames from users and documents."""
    names: set[str] = set()

    user_rows = await session.execute(select(User.full_name).where(User.full_name.isnot(None)))
    for (full_name,) in user_rows:
        if full_name and full_name.strip():
            names.add(full_name.strip())

    doc_rows = await session.execute(
        select(BaseDocument.developed_by, BaseDocument.created_by)
    )
    for developed_by, created_by in doc_rows:
        for value in (developed_by, created_by):
            if value and value.strip():
                cleaned = value.strip()
                names.add(cleaned)
                for part in _split_name_parts(cleaned):
                    if len(part) >= 2:
                        names.add(part)

    return sorted(names, key=lambda item: item.casefold())
