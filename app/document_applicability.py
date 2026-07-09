"""Document applicability across products (GOST 2.501-2013)."""

import os
import shutil
from typing import NotRequired, Optional, TypedDict

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.config import UPLOAD_DIR
from app.document_helpers import _resolve_upload_subdirectory, _sanitize_storage_name
from app.document_links import get_transitive_outgoing_document_ids
from app.document_workflow import fetch_document
from app.models import BaseDocument, DocumentApplicability, DocumentChangeEventType, Product, User
from app.notifications import get_document_designation, notify_document_edit
from app.change_log import log_change_event


class ApplicabilityPropagationResult(TypedDict):
    target_id: int
    designation: str
    product_id: int
    success: bool
    error: NotRequired[str]


class ApplicabilityRevertResult(TypedDict):
    target_id: int
    designation: str
    product_id: int
    success: bool
    error: NotRequired[str]


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


async def get_applicability_product_ids(
    session: AsyncSession,
    document_id: int,
) -> set[int]:
    result = await session.execute(
        select(DocumentApplicability.product_id).where(
            DocumentApplicability.document_id == document_id
        )
    )
    return {row[0] for row in result.all()}


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


def build_applicability_modal_options(products: list[Product]) -> list[dict]:
    """Group available products by project for the applicability modal."""
    projects: dict[int, dict] = {}
    for product in products:
        project = product.project
        if not project:
            continue
        bucket = projects.setdefault(
            project.id,
            {"id": project.id, "name": project.name, "products": []},
        )
        bucket["products"].append({"id": product.id, "name": product.name})
    return sorted(projects.values(), key=lambda item: item["name"].casefold())


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


async def get_child_covered_product_ids(
    session: AsyncSession,
    doc: BaseDocument,
) -> set[int]:
    """Products already covered by applicability entries or the record's own product."""
    covered = await get_applicability_product_ids(session, doc.id)
    if doc.product_id:
        covered.add(doc.product_id)
    return covered


async def propagate_applicability_to_outgoing_links(
    session: AsyncSession,
    doc: BaseDocument,
    user: User,
) -> list[ApplicabilityPropagationResult]:
    """Ensure all documents in outgoing link branches have the same applicability as the source."""
    source_product_ids = await get_applicability_product_ids(session, doc.id)
    if not source_product_ids:
        return []

    linked_ids = await get_transitive_outgoing_document_ids(session, doc.id)
    results: list[ApplicabilityPropagationResult] = []

    for target_id in linked_ids:
        target_doc = await fetch_document(session, target_id)
        if not target_doc:
            continue

        covered = await get_child_covered_product_ids(session, target_doc)
        missing = source_product_ids - covered
        if not missing:
            continue

        designation = get_document_designation(target_doc)
        for product_id in sorted(missing):
            try:
                await add_document_applicability(session, target_doc, product_id, user)
                results.append(
                    {
                        "target_id": target_doc.id,
                        "designation": designation,
                        "product_id": product_id,
                        "success": True,
                    }
                )
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, str) else "Не удалось добавить применяемость."
                results.append(
                    {
                        "target_id": target_doc.id,
                        "designation": designation,
                        "product_id": product_id,
                        "success": False,
                        "error": detail,
                    }
                )

    return results


async def verify_child_applicability(
    session: AsyncSession,
    doc: BaseDocument,
    user: User,
) -> list[ApplicabilityPropagationResult]:
    """Check all child link branches and add any missing parent applicability entries."""
    source_product_ids = await get_applicability_product_ids(session, doc.id)
    if not source_product_ids:
        raise HTTPException(
            status_code=400,
            detail="У записи нет применяемости для проверки дочерних записей.",
        )
    return await propagate_applicability_to_outgoing_links(session, doc, user)


async def revert_parent_applicability_after_link_removed(
    session: AsyncSession,
    parent_doc: BaseDocument,
    target_id: int,
    user: User,
) -> list[ApplicabilityRevertResult]:
    """Remove parent applicability entries from the unlinked target and its subtree."""
    parent_product_ids = await get_applicability_product_ids(session, parent_doc.id)
    if not parent_product_ids:
        return []

    subtree_ids = {target_id, *await get_transitive_outgoing_document_ids(session, target_id)}
    still_reachable = set(await get_transitive_outgoing_document_ids(session, parent_doc.id))
    to_clean = sorted(subtree_ids - still_reachable)
    results: list[ApplicabilityRevertResult] = []

    for doc_id in to_clean:
        doc = await fetch_document(session, doc_id)
        if not doc:
            continue

        designation = get_document_designation(doc)
        entries = await get_applicability_entries(session, doc_id)
        for entry in entries:
            if entry.product_id not in parent_product_ids:
                continue
            try:
                await remove_document_applicability(session, entry.id, doc_id)
                label = format_applicability_label(doc, entry.product)
                await log_change_event(
                    session,
                    doc,
                    user,
                    DocumentChangeEventType.metadata_edit,
                    comment=f"Удалена применяемость (ссылка снята): {label}",
                )
                results.append(
                    {
                        "target_id": doc_id,
                        "designation": designation,
                        "product_id": entry.product_id,
                        "success": True,
                    }
                )
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, str) else "Не удалось удалить применяемость."
                results.append(
                    {
                        "target_id": doc_id,
                        "designation": designation,
                        "product_id": entry.product_id,
                        "success": False,
                        "error": detail,
                    }
                )

    return results


async def add_document_applicability_many(
    session: AsyncSession,
    doc: BaseDocument,
    product_ids: list[int],
    user: User,
) -> tuple[list[DocumentApplicability], list[ApplicabilityPropagationResult]]:
    if not product_ids:
        raise HTTPException(status_code=400, detail="Выберите хотя бы одно изделие.")
    created: list[DocumentApplicability] = []
    for product_id in product_ids:
        created.append(await add_document_applicability(session, doc, product_id, user))
    propagated = await propagate_applicability_to_outgoing_links(session, doc, user)
    return created, propagated


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
