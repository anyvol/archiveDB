"""Document applicability across products (GOST 2.501-2013)."""

import os
import shutil
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.config import UPLOAD_DIR
from app.document_helpers import _resolve_upload_subdirectory, _sanitize_storage_name
from app.models import BaseDocument, DocumentApplicability, DocumentChangeEventType, Product, User
from app.notifications import get_document_designation, notify_document_edit
from app.change_log import log_change_event


def _resolve_doc_kind_code(doc: BaseDocument) -> Optional[str]:
    if doc.design_document:
        return doc.design_document.doc_kind_code
    return None


def _resolve_applicability_directory(project_slug: str, product_slug: str, doc: BaseDocument) -> str:
    return _resolve_upload_subdirectory(
        project_slug,
        product_slug=product_slug,
        doc_kind_code=_resolve_doc_kind_code(doc),
    )


async def get_applicability_entries(
    session: AsyncSession,
    document_id: int,
) -> list[DocumentApplicability]:
    result = await session.execute(
        select(DocumentApplicability)
        .options(joinedload(DocumentApplicability.product).joinedload(Product.project))
        .where(DocumentApplicability.document_id == document_id)
        .order_by(DocumentApplicability.created_at.asc())
    )
    return list(result.scalars().unique().all())


async def get_available_applicability_products(
    session: AsyncSession,
    doc: BaseDocument,
) -> list[Product]:
    existing = await session.execute(
        select(DocumentApplicability.product_id).where(DocumentApplicability.document_id == doc.id)
    )
    used_ids = {row[0] for row in existing.all()}
    if doc.product_id:
        used_ids.add(doc.product_id)

    result = await session.execute(
        select(Product)
        .options(joinedload(Product.project))
        .order_by(Product.name)
    )
    return [product for product in result.scalars().unique().all() if product.id not in used_ids]


def copy_document_to_product(doc: BaseDocument, target_product: Product) -> tuple[str, str]:
    if not doc.file_path or not os.path.exists(doc.file_path):
        raise HTTPException(
            status_code=400,
            detail="Невозможно добавить применяемость: у записи нет загруженного файла.",
        )

    if not target_product.project:
        raise HTTPException(status_code=400, detail="Изделие не привязано к проекту.")

    target_dir = _resolve_applicability_directory(target_product.project.slug, target_product.slug, doc)
    os.makedirs(target_dir, exist_ok=True)

    file_name = doc.file_name or os.path.basename(doc.file_path)
    disk_name = _sanitize_storage_name(file_name)
    target_path = os.path.join(target_dir, disk_name)

    if os.path.exists(target_path):
        base, ext = os.path.splitext(disk_name)
        counter = 1
        while os.path.exists(target_path):
            disk_name = _sanitize_storage_name(f"{base}_{counter}{ext}")
            target_path = os.path.join(target_dir, disk_name)
            counter += 1

    shutil.copy2(doc.file_path, target_path)
    return target_path, file_name


async def add_document_applicability(
    session: AsyncSession,
    doc: BaseDocument,
    product_id: int,
    user: User,
) -> DocumentApplicability:
    if doc.product_id and product_id == doc.product_id:
        raise HTTPException(status_code=400, detail="Запись уже относится к этому изделию.")

    existing = await session.execute(
        select(DocumentApplicability).where(
            DocumentApplicability.document_id == doc.id,
            DocumentApplicability.product_id == product_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Применяемость для этого изделия уже добавлена.")

    product = await session.get(Product, product_id, options=[joinedload(Product.project)])
    if not product:
        raise HTTPException(status_code=404, detail="Изделие не найдено.")

    file_path, file_name = copy_document_to_product(doc, product)
    entry = DocumentApplicability(
        document_id=doc.id,
        product_id=product.id,
        file_path=file_path,
        file_name=file_name,
        created_by=user.id,
    )
    session.add(entry)
    await session.flush()
    await session.refresh(entry, ["product"])

    label = format_applicability_label(doc, product)
    await log_change_event(
        session,
        doc,
        user,
        DocumentChangeEventType.metadata_edit,
        comment=f"Добавлена применяемость: {label}",
    )
    await notify_document_edit(
        session,
        doc,
        user,
        [f"добавлена применяемость: {label}"],
    )

    return entry


async def cleanup_document_applicability_files(session: AsyncSession, document_id: int) -> None:
    entries = await get_applicability_entries(session, document_id)
    for entry in entries:
        if entry.file_path and os.path.exists(entry.file_path):
            os.remove(entry.file_path)


async def remove_document_applicability(
    session: AsyncSession,
    applicability_id: int,
    document_id: int,
) -> None:
    entry = await session.get(DocumentApplicability, applicability_id)
    if not entry or entry.document_id != document_id:
        raise HTTPException(status_code=404, detail="Применяемость не найдена.")

    if entry.file_path and os.path.exists(entry.file_path):
        os.remove(entry.file_path)

    await session.delete(entry)


def format_applicability_label(doc: BaseDocument, product: Product) -> str:
    designation = get_document_designation(doc)
    project_name = product.project.name if product.project else "—"
    return f"{designation} → {project_name} / {product.name}"
