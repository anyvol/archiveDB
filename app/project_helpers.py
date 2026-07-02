"""Project name slugification and get-or-create helpers."""

import os
import re
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import UPLOAD_DIR
from app.models import IMAGES_FOLDER, Project

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


def ensure_project_directory(project_slug: str) -> str:
    project_dir = os.path.join(UPLOAD_DIR, project_slug)
    os.makedirs(project_dir, exist_ok=True)
    return project_dir


def ensure_project_images_directory(project_slug: str) -> str:
    images_dir = os.path.join(UPLOAD_DIR, project_slug, IMAGES_FOLDER)
    os.makedirs(images_dir, exist_ok=True)
    return images_dir


def format_project_name(name: str, cipher: str) -> str:
    return f"{name.strip()} ({cipher.strip()})"


async def get_project_by_id(session: AsyncSession, project_id: int) -> Project:
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=400, detail="Выбранный проект не найден.")
    return project


async def create_new_project(session: AsyncSession, name: str, cipher: str) -> Project:
    name = name.strip()
    cipher = cipher.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название проекта обязательно.")
    if not cipher:
        raise HTTPException(status_code=400, detail="Шифр проекта обязателен для нового проекта.")
    full_name = format_project_name(name, cipher)
    if len(full_name) > 255:
        raise HTTPException(status_code=400, detail="Название проекта не может превышать 255 символов.")

    result = await session.execute(select(Project).where(Project.name == full_name))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Проект с таким названием уже существует.")

    base_slug = slugify_project_name(full_name)
    slug = await _unique_slug(session, base_slug)
    project = Project(name=full_name, slug=slug, created_at=datetime.utcnow())
    session.add(project)
    await session.flush()
    ensure_project_directory(slug)
    return project


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
    ensure_project_directory(slug)
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
