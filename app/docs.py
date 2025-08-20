# app/docs.py

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import shutil
import os

from app.database import get_session
from app.models import BaseDocument, DesignDocument, TechDocument, User, ClassCodeKD, ClassCodeTD, Organization
from app.schemas import (
    BaseDocument as BaseDocumentSchema,
    DesignDocument as DesignDocumentSchema,
    DesignDocumentCreate,
    TechDocument as TechDocumentSchema,
    TechDocumentCreate,
)
from app.auth import get_current_user

router = APIRouter()

# Путь для хранения файлов
UPLOAD_DIR = "uploaded_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- List all documents with optional filtering by type ---
@router.get("/documents/", response_model=List[BaseDocumentSchema])
async def list_documents(
    skip: int = 0,
    limit: int = 10,
    type: Optional[str] = None,  # 'DD' or 'TD'
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    query = select(BaseDocument)
    if type:
        query = query.where(BaseDocument.type == type)
    query = query.offset(skip).limit(limit)
    result = await session.execute(query)
    docs = result.scalars().all()
    return docs

# --- Create Design Document ---
@router.post("/design-documents/", response_model=DesignDocumentSchema, status_code=status.HTTP_201_CREATED)
async def create_design_document(
    doc_in: DesignDocumentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    # Create BaseDocument record
    base_doc = BaseDocument(
        file_path="",  # to be set after file upload
        file_name="",
        created_by=current_user.login,
        uploaded_by=current_user.id,
        position=current_user.position,
        department=current_user.department,
        type="DD"
    )
    session.add(base_doc)
    await session.flush()  # to get base_doc.id

    # Create DesignDocument record
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

# --- Create Tech Document ---
@router.post("/tech-documents/", response_model=TechDocumentSchema, status_code=status.HTTP_201_CREATED)
async def create_tech_document(
    doc_in: TechDocumentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    # Create BaseDocument record
    base_doc = BaseDocument(
        file_path="",  # to be set after file upload
        file_name="",
        created_by=current_user.login,
        uploaded_by=current_user.id,
        position=current_user.position,
        department=current_user.department,
        type="TD"
    )
    session.add(base_doc)
    await session.flush()  # to get base_doc.id

    # Create TechDocument record
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

# --- Get Design Document by ID ---
@router.get("/design-documents/{doc_id}", response_model=DesignDocumentSchema)
async def get_design_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    result = await session.execute(select(DesignDocument).where(DesignDocument.id == doc_id))
    design_doc = result.scalars().first()
    if not design_doc:
        raise HTTPException(status_code=404, detail="Design Document not found")
    return design_doc

# --- Get Tech Document by ID ---
@router.get("/tech-documents/{doc_id}", response_model=TechDocumentSchema)
async def get_tech_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    result = await session.execute(select(TechDocument).where(TechDocument.id == doc_id))
    tech_doc = result.scalars().first()
    if not tech_doc:
        raise HTTPException(status_code=404, detail="Tech Document not found")
    return tech_doc

# --- Update Design Document ---
@router.put("/design-documents/{doc_id}", response_model=DesignDocumentSchema)
async def update_design_document(
    doc_id: int,
    doc_in: DesignDocumentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    result = await session.execute(select(DesignDocument).where(DesignDocument.id == doc_id))
    design_doc = result.scalars().first()
    if not design_doc:
        raise HTTPException(status_code=404, detail="Design Document not found")

    # Update fields
    design_doc.org_id = doc_in.org_id
    design_doc.kd_class_code_id = doc_in.kd_class_code_id
    design_doc.prni = doc_in.prni
    design_doc.designation = doc_in.designation

    await session.commit()
    await session.refresh(design_doc)
    return design_doc

# --- Update Tech Document ---
@router.put("/tech-documents/{doc_id}", response_model=TechDocumentSchema)
async def update_tech_document(
    doc_id: int,
    doc_in: TechDocumentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    result = await session.execute(select(TechDocument).where(TechDocument.id == doc_id))
    tech_doc = result.scalars().first()
    if not tech_doc:
        raise HTTPException(status_code=404, detail="Tech Document not found")

    # Update fields
    tech_doc.org_id = doc_in.org_id
    tech_doc.td_class_code_id = doc_in.td_class_code_id
    tech_doc.prn = doc_in.prn
    tech_doc.designation = doc_in.designation

    await session.commit()
    await session.refresh(tech_doc)
    return tech_doc

# --- Delete Document (Design or Tech) ---
@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    result = await session.execute(select(BaseDocument).where(BaseDocument.id == doc_id))
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await session.delete(doc)
    await session.commit()

    # TODO: удалять связанные DesignDocument или TechDocument, либо настроить каскад на уровне БД

    return

# --- Upload file endpoint ---
@router.post("/documents/{doc_id}/upload", status_code=status.HTTP_200_OK)
async def upload_file(
    doc_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    result = await session.execute(select(BaseDocument).where(BaseDocument.id == doc_id))
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_location = os.path.join(UPLOAD_DIR, f"{doc_id}_{file.filename}")
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    # update BaseDocument.file_path and file_name
    doc.file_path = file_location
    doc.file_name = file.filename
    await session.commit()
    return {"filename": file.filename}

# --- Download file endpoint ---
@router.get("/documents/{doc_id}/download")
async def download_file(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    result = await session.execute(select(BaseDocument).where(BaseDocument.id == doc_id))
    doc = result.scalars().first()
    if not doc or not doc.file_path:
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(doc.file_path, filename=doc.file_name, media_type="application/pdf")
