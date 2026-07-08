"""Product (изделие) helpers within projects."""

from __future__ import annotations

import os
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import UPLOAD_DIR
from app.models import Product, Project
from app.project_helpers import slugify_project_name


async def _unique_product_slug(session: AsyncSession, project_id: int, base_slug: str) -> str:
    slug = base_slug
    suffix = 2
    while True:
        result = await session.execute(
            select(Product).where(Product.project_id == project_id, Product.slug == slug)
        )
        if not result.scalars().first():
            return slug
        slug = f"{base_slug}-{suffix}"
        suffix += 1


def ensure_product_directory(project_slug: str, product_slug: str) -> str:
    product_dir = os.path.join(UPLOAD_DIR, project_slug, product_slug)
    os.makedirs(product_dir, exist_ok=True)
    return product_dir


async def get_product_by_id(session: AsyncSession, product_id: int) -> Product:
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=400, detail="Выбранное изделие не найдено.")
    return product


async def get_products_for_project(session: AsyncSession, project_id: int) -> list[Product]:
    result = await session.execute(
        select(Product).where(Product.project_id == project_id).order_by(Product.name)
    )
    return list(result.scalars().all())


async def get_all_products(session: AsyncSession) -> list[Product]:
    result = await session.execute(select(Product).options(joinedload(Product.project)))
    products = list(result.scalars().unique().all())
    return sorted(
        products,
        key=lambda product: (
            product.project.name.casefold() if product.project else "",
            product.name.casefold(),
        ),
    )


async def create_product(session: AsyncSession, project: Project, name: str) -> Product:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Наименование изделия обязательно.")
    if len(name) > 255:
        raise HTTPException(status_code=400, detail="Наименование изделия не может превышать 255 символов.")

    existing = await session.execute(
        select(Product).where(Product.project_id == project.id, Product.name == name)
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Изделие с таким наименованием уже существует в проекте.")

    base_slug = slugify_project_name(name)
    slug = await _unique_product_slug(session, project.id, base_slug)
    product = Product(
        project_id=project.id,
        name=name,
        slug=slug,
        created_at=datetime.utcnow(),
    )
    session.add(product)
    await session.flush()
    ensure_product_directory(project.slug, slug)
    return product


async def validate_product_belongs_to_project(
    session: AsyncSession,
    product_id: int,
    project_id: int,
) -> Product:
    product = await get_product_by_id(session, product_id)
    if product.project_id != project_id:
        raise HTTPException(status_code=400, detail="Изделие не относится к выбранному проекту.")
    return product
