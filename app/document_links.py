"""Cross-references between archive records."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.models import (
    BaseDocument,
    DesignDocument,
    DocumentChangeEventType,
    DocumentLink,
    DocumentStatus,
    TechDocument,
    User,
)
from app.notifications import get_document_designation, notify_document_edit
from app.change_log import log_change_event, log_document_status_change


async def search_documents_by_designation(
    session: AsyncSession,
    query: str,
    *,
    exclude_document_id: int | None = None,
    limit: int = 20,
) -> list[dict]:
    pattern = f"%{query.strip()}%"
    if not query.strip():
        return []

    stmt = (
        select(BaseDocument)
        .options(
            joinedload(BaseDocument.design_document),
            joinedload(BaseDocument.tech_document),
        )
        .where(
            BaseDocument.design_document.has(DesignDocument.designation.ilike(pattern))
            | BaseDocument.tech_document.has(TechDocument.designation.ilike(pattern))
        )
        .order_by(BaseDocument.id.desc())
        .limit(limit)
    )
    if exclude_document_id is not None:
        stmt = stmt.where(BaseDocument.id != exclude_document_id)

    result = await session.execute(stmt)
    documents = result.scalars().unique().all()
    return [
        {
            "id": doc.id,
            "designation": get_document_designation(doc),
            "doc_name": doc.doc_name or "",
        }
        for doc in documents
    ]


async def get_outgoing_links(session: AsyncSession, document_id: int) -> list[DocumentLink]:
    result = await session.execute(
        select(DocumentLink)
        .options(
            joinedload(DocumentLink.target_document).joinedload(BaseDocument.design_document),
            joinedload(DocumentLink.target_document).joinedload(BaseDocument.tech_document),
        )
        .where(DocumentLink.source_document_id == document_id)
        .order_by(DocumentLink.created_at.asc())
    )
    return list(result.scalars().unique().all())


async def add_document_links(
    session: AsyncSession,
    source_doc: BaseDocument,
    target_ids: list[int],
    user: User,
) -> list[DocumentLink]:
    if not target_ids:
        raise HTTPException(status_code=400, detail="Выберите хотя бы одну запись.")

    unique_ids = []
    seen = set()
    for target_id in target_ids:
        if target_id in seen:
            continue
        seen.add(target_id)
        if target_id == source_doc.id:
            raise HTTPException(status_code=400, detail="Нельзя добавить ссылку на ту же запись.")
        unique_ids.append(target_id)

    existing = await session.execute(
        select(DocumentLink.target_document_id).where(
            DocumentLink.source_document_id == source_doc.id,
            DocumentLink.target_document_id.in_(unique_ids),
        )
    )
    already_linked = {row[0] for row in existing.all()}
    to_add = [target_id for target_id in unique_ids if target_id not in already_linked]

    if not to_add:
        raise HTTPException(status_code=400, detail="Выбранные ссылки уже добавлены.")

    found = await session.execute(select(BaseDocument.id).where(BaseDocument.id.in_(to_add)))
    found_ids = {row[0] for row in found.all()}
    missing = [target_id for target_id in to_add if target_id not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail="Одна или несколько записей не найдены.")

    created: list[DocumentLink] = []
    for target_id in to_add:
        link = DocumentLink(
            source_document_id=source_doc.id,
            target_document_id=target_id,
            created_by=user.id,
        )
        session.add(link)
        created.append(link)

    target_docs_result = await session.execute(
        select(BaseDocument)
        .options(
            joinedload(BaseDocument.design_document),
            joinedload(BaseDocument.tech_document),
        )
        .where(BaseDocument.id.in_(to_add))
    )
    target_docs = target_docs_result.scalars().unique().all()
    designations = [get_document_designation(doc) for doc in target_docs]
    old_status = source_doc.status
    source_doc.status = DocumentStatus.pending_review

    await log_change_event(
        session,
        source_doc,
        user,
        DocumentChangeEventType.metadata_edit,
        comment="Добавлены ссылки: " + ", ".join(designations),
    )
    await log_document_status_change(
        session,
        source_doc,
        user,
        old_status,
        DocumentStatus.pending_review,
    )
    await notify_document_edit(
        session,
        source_doc,
        user,
        [f"добавлены ссылки: {', '.join(designations)}"],
    )

    await session.flush()
    return created


async def remove_document_link(
    session: AsyncSession,
    link_id: int,
    source_document_id: int,
) -> None:
    link = await session.get(DocumentLink, link_id)
    if not link or link.source_document_id != source_document_id:
        raise HTTPException(status_code=404, detail="Ссылка не найдена.")
    await session.delete(link)
