# app/docs.py

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import os

from app.database import get_session
from app.models import BaseDocument, DesignDocument, TechDocument, User, DocumentStatus, Project
from app.schemas import (
    BaseDocument as BaseDocumentSchema,
    DesignDocument as DesignDocumentSchema,
    DesignDocumentCreate,
    TechDocument as TechDocumentSchema,
    TechDocumentCreate,
    DocumentStatusUpdate,
)
from app.auth import get_current_user
from app.dependencies import get_current_admin_user, get_current_reviewer_or_admin
from app.document_helpers import save_upload_file, remove_file_if_exists
from app.notifications import (
    notify_file_upload,
    notify_status_change,
    clear_document_references,
    notify_document_delete,
    send_document_delete_push,
    get_document_designation,
)
from app.permissions import require_upload_permission
from datetime import datetime
from app.document_queries import fetch_documents
from app.project_helpers import get_legacy_project

router = APIRouter()


@router.get("/documents/", response_model=List[BaseDocumentSchema])
async def list_documents(
    skip: int = 0,
    limit: int = 100,
    type: Optional[str] = None,
    status_filter: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    docs, _total = await fetch_documents(
        session,
        doc_type=type,
        status=status_filter,
        sort="created_at",
        order="desc",
        limit=limit,
        offset=skip,
    )
    return docs


@router.post("/design-documents/", response_model=DesignDocumentSchema, status_code=status.HTTP_201_CREATED)
async def create_design_document(
    doc_in: DesignDocumentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    legacy = await get_legacy_project(session)
    base_doc = BaseDocument(
        created_by=current_user.login,
        uploaded_by=current_user.id,
        position=current_user.position,
        department=current_user.department,
        type="DD",
        project_id=legacy.id,
        status=DocumentStatus.pending_review,
    )
    session.add(base_doc)
    await session.flush()

    design_doc = DesignDocument(
        id=base_doc.id,
        org_id=doc_in.org_id,
        kd_class_code_id=doc_in.kd_class_code_id,
        prni=doc_in.prni,
        designation=doc_in.designation,
    )
    session.add(design_doc)

    try:
        await session.commit()
        await session.refresh(design_doc)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Design Document with this designation already exists.")

    return design_doc


@router.post("/tech-documents/", response_model=TechDocumentSchema, status_code=status.HTTP_201_CREATED)
async def create_tech_document(
    doc_in: TechDocumentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    legacy = await get_legacy_project(session)
    base_doc = BaseDocument(
        created_by=current_user.login,
        uploaded_by=current_user.id,
        position=current_user.position,
        department=current_user.department,
        type="TD",
        project_id=legacy.id,
        status=DocumentStatus.pending_review,
    )
    session.add(base_doc)
    await session.flush()

    tech_doc = TechDocument(
        id=base_doc.id,
        org_id=doc_in.org_id,
        td_class_code_id=doc_in.td_class_code_id,
        prn=doc_in.prn,
        designation=doc_in.designation,
    )
    session.add(tech_doc)

    try:
        await session.commit()
        await session.refresh(tech_doc)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Tech Document with this designation already exists.")

    return tech_doc


@router.get("/design-documents/{doc_id}", response_model=DesignDocumentSchema)
async def get_design_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    result = await session.execute(select(DesignDocument).where(DesignDocument.id == doc_id))
    design_doc = result.scalars().first()
    if not design_doc:
        raise HTTPException(status_code=404, detail="Design Document not found")
    return design_doc


@router.get("/tech-documents/{doc_id}", response_model=TechDocumentSchema)
async def get_tech_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    result = await session.execute(select(TechDocument).where(TechDocument.id == doc_id))
    tech_doc = result.scalars().first()
    if not tech_doc:
        raise HTTPException(status_code=404, detail="Tech Document not found")
    return tech_doc


@router.put("/design-documents/{doc_id}", response_model=DesignDocumentSchema)
async def update_design_document(
    doc_id: int,
    doc_in: DesignDocumentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
):
    result = await session.execute(select(DesignDocument).where(DesignDocument.id == doc_id))
    design_doc = result.scalars().first()
    if not design_doc:
        raise HTTPException(status_code=404, detail="Design Document not found")

    design_doc.org_id = doc_in.org_id
    design_doc.kd_class_code_id = doc_in.kd_class_code_id
    design_doc.prni = doc_in.prni
    design_doc.designation = doc_in.designation

    await session.commit()
    await session.refresh(design_doc)
    return design_doc


@router.put("/tech-documents/{doc_id}", response_model=TechDocumentSchema)
async def update_tech_document(
    doc_id: int,
    doc_in: TechDocumentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
):
    result = await session.execute(select(TechDocument).where(TechDocument.id == doc_id))
    tech_doc = result.scalars().first()
    if not tech_doc:
        raise HTTPException(status_code=404, detail="Tech Document not found")

    tech_doc.org_id = doc_in.org_id
    tech_doc.td_class_code_id = doc_in.td_class_code_id
    tech_doc.prn = doc_in.prn
    tech_doc.designation = doc_in.designation

    await session.commit()
    await session.refresh(tech_doc)
    return tech_doc


@router.patch("/documents/{doc_id}/status", response_model=BaseDocumentSchema)
async def update_document_status(
    doc_id: int,
    payload: DocumentStatusUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_reviewer_or_admin),
):
    if payload.status not in (DocumentStatus.approved, DocumentStatus.requires_correction):
        raise HTTPException(status_code=400, detail="Invalid status for review action")

    if payload.status == DocumentStatus.requires_correction and not (payload.comment or "").strip():
        raise HTTPException(status_code=400, detail="Comment is required for requires_correction status")

    doc = await session.get(BaseDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.status = payload.status
    if payload.status == DocumentStatus.requires_correction:
        doc.review_comment = (payload.comment or "").strip()
    elif payload.status == DocumentStatus.approved:
        doc.review_comment = None
    await notify_status_change(
        session, doc, current_user, payload.status, (payload.comment or "").strip() or None
    )
    await session.commit()
    await session.refresh(doc)
    return doc


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: int,
    comment: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
):
    result = await session.execute(
        select(BaseDocument)
        .options(
            joinedload(BaseDocument.design_document),
            joinedload(BaseDocument.tech_document),
        )
        .where(BaseDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    push_info = await notify_document_delete(session, doc, current_user, comment.strip())
    remove_file_if_exists(doc.file_path)
    await clear_document_references(session, doc_id)
    await session.delete(doc)
    await session.commit()
    if push_info:
        recipients, message = push_info
        await send_document_delete_push(session, recipients, message)


@router.post("/documents/{doc_id}/upload", status_code=status.HTTP_200_OK)
async def upload_file(
    doc_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    doc = await session.get(BaseDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    require_upload_permission(current_user, doc)
    await session.refresh(doc, ["project", "design_document", "tech_document"])
    project_slug = doc.project.slug if doc.project else "_legacy"
    had_file_before = bool(doc.file_name)
    registration_already_notified = bool(doc.registration_notified_at)
    file_path, file_name = await save_upload_file(
        file,
        project_slug,
        doc.file_path,
        doc_kind_code=doc.design_document.doc_kind_code if doc.design_document else None,
        designation=get_document_designation(doc) if (doc.design_document or doc.tech_document) else None,
        doc_name=doc.doc_name,
    )
    doc.file_path = file_path
    doc.file_name = file_name
    doc.status = DocumentStatus.pending_review
    if not doc.registration_notified_at:
        doc.registration_notified_at = datetime.utcnow()
    await notify_file_upload(
        session,
        doc,
        current_user,
        had_file_before=had_file_before,
        registration_already_notified=registration_already_notified,
    )
    await session.commit()
    return {"filename": file_name}


@router.get("/documents/{doc_id}/download")
async def download_file(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    doc = await session.get(BaseDocument, doc_id)
    if not doc or not doc.file_path or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(doc.file_path, filename=doc.file_name, media_type="application/octet-stream")
