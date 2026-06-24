"""Build filtered and sorted document queries."""

from datetime import datetime
from typing import Optional

from sqlalchemy import asc, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.models import BaseDocument, DesignDocument, DocumentStatus, Organization, Project, TechDocument

SORTABLE_COLUMNS = {
    "designation": "designation",
    "okpo": "okpo",
    "org_name": "org_name",
    "project": "project",
    "developed_by": BaseDocument.developed_by,
    "doc_name": BaseDocument.doc_name,
    "file_name": BaseDocument.file_name,
    "type": BaseDocument.type,
    "created_by": BaseDocument.created_by,
    "created_at": BaseDocument.created_at,
    "last_update": BaseDocument.last_update,
    "status": BaseDocument.status,
}


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def build_documents_query(
    *,
    designation: Optional[str] = None,
    okpo: Optional[str] = None,
    org_name: Optional[str] = None,
    project_id: Optional[int] = None,
    developed_by: Optional[str] = None,
    doc_name: Optional[str] = None,
    file_name: Optional[str] = None,
    doc_type: Optional[str] = None,
    created_by: Optional[str] = None,
    status: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    updated_from: Optional[str] = None,
    updated_to: Optional[str] = None,
    sort: str = "created_at",
    order: str = "desc",
):
    query = select(BaseDocument).options(
        joinedload(BaseDocument.project),
        joinedload(BaseDocument.design_document).joinedload(DesignDocument.org),
        joinedload(BaseDocument.tech_document).joinedload(TechDocument.org),
    )

    if designation:
        pattern = f"%{designation.strip()}%"
        query = query.where(
            or_(
                BaseDocument.design_document.has(DesignDocument.designation.ilike(pattern)),
                BaseDocument.tech_document.has(TechDocument.designation.ilike(pattern)),
            )
        )

    if okpo in ("yes", "no"):
        is_okpo = okpo == "yes"
        query = query.where(
            or_(
                BaseDocument.design_document.has(
                    DesignDocument.org.has(Organization.code_okpo == is_okpo)
                ),
                BaseDocument.tech_document.has(
                    TechDocument.org.has(Organization.code_okpo == is_okpo)
                ),
            )
        )

    if org_name:
        pattern = f"%{org_name.strip()}%"
        query = query.where(
            or_(
                BaseDocument.design_document.has(
                    DesignDocument.org.has(Organization.name.ilike(pattern))
                ),
                BaseDocument.tech_document.has(
                    TechDocument.org.has(Organization.name.ilike(pattern))
                ),
            )
        )

    if project_id is not None:
        try:
            pid = int(project_id)
            query = query.where(BaseDocument.project_id == pid)
        except (TypeError, ValueError):
            pass

    if developed_by:
        query = query.where(BaseDocument.developed_by.ilike(f"%{developed_by.strip()}%"))
    if doc_name:
        query = query.where(BaseDocument.doc_name.ilike(f"%{doc_name.strip()}%"))
    if file_name:
        query = query.where(BaseDocument.file_name.ilike(f"%{file_name.strip()}%"))
    if doc_type in ("DD", "TD"):
        query = query.where(BaseDocument.type == doc_type)
    if created_by:
        query = query.where(BaseDocument.created_by.ilike(f"%{created_by.strip()}%"))

    if status:
        try:
            status_enum = DocumentStatus(status)
            query = query.where(BaseDocument.status == status_enum)
        except ValueError:
            pass

    created_from_dt = _parse_date(created_from)
    created_to_dt = _parse_date(created_to)
    if created_from_dt:
        query = query.where(BaseDocument.created_at >= created_from_dt)
    if created_to_dt:
        query = query.where(BaseDocument.created_at <= created_to_dt)

    updated_from_dt = _parse_date(updated_from)
    updated_to_dt = _parse_date(updated_to)
    if updated_from_dt:
        query = query.where(BaseDocument.last_update >= updated_from_dt)
    if updated_to_dt:
        query = query.where(BaseDocument.last_update <= updated_to_dt)

    sort_key = SORTABLE_COLUMNS.get(sort, BaseDocument.created_at)
    if sort_key in ("designation", "okpo", "org_name", "project"):
        sort_col = BaseDocument.created_at
    else:
        sort_col = sort_key

    direction = desc if order.lower() == "desc" else asc
    query = query.order_by(direction(sort_col))

    return query


def _org_name(doc: BaseDocument) -> str:
    if doc.design_document and doc.design_document.org:
        return doc.design_document.org.name or ""
    if doc.tech_document and doc.tech_document.org:
        return doc.tech_document.org.name or ""
    return ""


async def fetch_documents(session: AsyncSession, **filters):
    query = build_documents_query(**filters)
    result = await session.execute(query)
    documents = result.unique().scalars().all()

    sort = filters.get("sort", "created_at")
    order = filters.get("order", "desc")
    reverse = order.lower() == "desc"

    if sort == "designation":
        documents = sorted(
            documents,
            key=lambda d: (
                d.design_document.designation if d.design_document
                else d.tech_document.designation if d.tech_document
                else ""
            ),
            reverse=reverse,
        )
    elif sort == "okpo":
        def okpo_key(d):
            org = None
            if d.design_document and d.design_document.org:
                org = d.design_document.org
            elif d.tech_document and d.tech_document.org:
                org = d.tech_document.org
            return org.code_okpo if org else False

        documents = sorted(documents, key=okpo_key, reverse=reverse)
    elif sort == "org_name":
        documents = sorted(documents, key=_org_name, reverse=reverse)
    elif sort == "project":
        documents = sorted(
            documents,
            key=lambda d: d.project.name if d.project else "",
            reverse=reverse,
        )

    return documents
