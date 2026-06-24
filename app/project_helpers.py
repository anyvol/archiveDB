"""Project name slugification and get-or-create helpers."""

import re
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project

_INVALID_CHARS = re.compile(r'[/\\:*?"<>|]+')
_MULTI_SPACE = re.compile(r"\s+")


def slugify_project_name(name: str) -> str:
    slug = _INVALID_CHARS.sub("_", name.strip())
    slug = _MULTI_SPACE.sub("-", slug)
    slug = slug.strip("._-")[:200]
    return slug or "project"


async def _unique_slug(session: AsyncSession, base_slug: str) -> str:
    slug = base_slug
    suffix = 2
    while True:
        result = await session.execute(select(Project).where(Project.slug == slug))
        if not result.scalars().first():
            return slug
        slug = f"{base_slug}-{suffix}"
        suffix += 1


async def get_or_create_project(session: AsyncSession, name: str) -> Project:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название проекта обязательно.")
    if len(name) > 255:
        raise HTTPException(status_code=400, detail="Название проекта не может превышать 255 символов.")

    result = await session.execute(select(Project).where(Project.name == name))
    project = result.scalars().first()
    if project:
        return project

    base_slug = slugify_project_name(name)
    slug = await _unique_slug(session, base_slug)
    project = Project(name=name, slug=slug)
    session.add(project)
    await session.flush()
    return project


async def get_legacy_project(session: AsyncSession) -> Project:
    result = await session.execute(select(Project).where(Project.slug == "_legacy"))
    project = result.scalars().first()
    if project:
        return project
    project = Project(name="Без проекта", slug="_legacy")
    session.add(project)
    await session.flush()
    return project
