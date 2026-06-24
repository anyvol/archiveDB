# app/main.py

from fastapi import FastAPI, Request, Depends, Cookie, Form, HTTPException, status, File, UploadFile, Response
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from urllib.parse import urlencode
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from typing import Optional
import os
import logging

from sqlalchemy.exc import SQLAlchemyError

from app.database import (
    engine,
    get_session,
    get_or_create_org_id,
    get_or_create_class_id,
    check_org_exists,
    get_next_prni,
    get_next_prn,
    check_prni_unique,
    check_prn_unique,
)
from app.models import (
    Base,
    BaseDocument,
    DesignDocument,
    TechDocument,
    User,
    UserRole,
    DocumentStatus,
    DOCUMENT_STATUS_LABELS,
)
from app.routers import router as user_router
from app import docs
from app.auth import get_current_user_from_token, authenticate_user, get_password_hash
from app.document_queries import fetch_documents
from app.document_helpers import save_upload_file, remove_file_if_exists
from app.config import UPLOAD_DIR, AUTO_CREATE_TABLES, app_path, cookie_path
from app.permissions import (
    can_create_document,
    can_edit_document_metadata,
    can_set_document_status,
    can_upload_file,
    can_delete_document,
    require_delete_permission,
    require_edit_metadata_permission,
    require_status_change_permission,
    require_upload_permission,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if AUTO_CREATE_TABLES:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
templates.env.globals["DOCUMENT_STATUS_LABELS"] = DOCUMENT_STATUS_LABELS
templates.env.globals["DocumentStatus"] = DocumentStatus
templates.env.globals["UserRole"] = UserRole
templates.env.globals["base_path"] = app_path("")
templates.env.globals["can_upload_file"] = can_upload_file
templates.env.globals["can_set_document_status"] = can_set_document_status
templates.env.globals["can_delete_document"] = can_delete_document
templates.env.globals["can_edit_document_metadata"] = can_edit_document_metadata

app.include_router(user_router, prefix="/users")
app.include_router(docs.router, prefix="/docs")


async def _get_authenticated_user(
    access_token: Optional[str],
    session: AsyncSession,
) -> User:
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Не авторизован")
    return await get_current_user_from_token(access_token=access_token, db=session)


def _redirect_to_login() -> RedirectResponse:
    response = RedirectResponse(url=app_path("/login"), status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token", path=cookie_path())
    return response


async def _require_user(access_token: Optional[str], session: AsyncSession) -> User:
    try:
        return await _get_authenticated_user(access_token, session)
    except HTTPException:
        raise


def _filter_params(request: Request) -> dict:
    qp = request.query_params
    return {
        "designation": qp.get("designation") or None,
        "okpo": qp.get("okpo") or None,
        "developed_by": qp.get("developed_by") or None,
        "doc_name": qp.get("doc_name") or None,
        "file_name": qp.get("file_name") or None,
        "doc_type": qp.get("doc_type") or None,
        "created_by": qp.get("created_by") or None,
        "status": qp.get("status") or None,
        "created_from": qp.get("created_from") or None,
        "created_to": qp.get("created_to") or None,
        "updated_from": qp.get("updated_from") or None,
        "updated_to": qp.get("updated_to") or None,
        "sort": qp.get("sort") or "created_at",
        "order": qp.get("order") or "desc",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse(url=app_path("/documents"))


@app.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if access_token:
        try:
            await get_current_user_from_token(access_token=access_token, db=session)
            return RedirectResponse(url=app_path("/documents"), status_code=status.HTTP_303_SEE_OTHER)
        except HTTPException:
            response = RedirectResponse(url=app_path("/login"))
            response.delete_cookie("access_token", path=cookie_path())
            return response

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": request.query_params.get("error") == "true",
            "success": request.query_params.get("success") == "true",
        },
    )


@app.post("/login", response_class=RedirectResponse)
async def handle_login(
    username: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    try:
        token_data = await authenticate_user(session, username, password)
        response = RedirectResponse(url=app_path("/documents"), status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            key="access_token",
            value=f"Bearer {token_data['access_token']}",
            max_age=3600,
            httponly=True,
            samesite="lax",
            path=cookie_path(),
        )
        return response
    except HTTPException:
        return RedirectResponse(url=app_path("/login?error=true"), status_code=status.HTTP_303_SEE_OTHER)
    except SQLAlchemyError:
        logger.exception("Database error during login for username: %s", username)
        return RedirectResponse(url=app_path("/login?error=true"), status_code=status.HTTP_303_SEE_OTHER)
    except Exception:
        logger.exception("Unexpected error during login for username: %s", username)
        return RedirectResponse(url=app_path("/login?error=true"), status_code=status.HTTP_303_SEE_OTHER)


@app.get("/logout", response_class=RedirectResponse)
async def logout():
    response = RedirectResponse(url=app_path("/login"), status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token", path=cookie_path())
    return response


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "error": request.query_params.get("error") == "true"},
    )


@app.post("/register", response_class=RedirectResponse)
async def handle_register(
    login: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    position: str = Form(""),
    department: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    try:
        existing = await session.execute(select(User).where(User.login == login))
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail="Пользователь уже существует.")

        session.add(
            User(
                login=login,
                password_hash=get_password_hash(password),
                full_name=full_name,
                position=position,
                department=department,
                role=UserRole.user,
            )
        )
        await session.commit()
        return RedirectResponse(url=app_path("/login?success=true"), status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException:
        return RedirectResponse(url=app_path("/register?error=true"), status_code=status.HTTP_303_SEE_OTHER)
    except SQLAlchemyError:
        await session.rollback()
        logger.exception("Database error during registration for login: %s", login)
        return RedirectResponse(url=app_path("/register?error=true"), status_code=status.HTTP_303_SEE_OTHER)
    except Exception:
        await session.rollback()
        logger.exception("Unexpected error during registration for login: %s", login)
        return RedirectResponse(url=app_path("/register?error=true"), status_code=status.HTTP_303_SEE_OTHER)


@app.get("/documents", response_class=HTMLResponse)
async def documents_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    try:
        user = await _get_authenticated_user(access_token, session)
    except HTTPException:
        return _redirect_to_login()

    filters = _filter_params(request)
    documents_from_db = await fetch_documents(session, **filters)

    return templates.TemplateResponse(
        "documents.html",
        {
            "request": request,
            "documents": documents_from_db,
            "user": user,
            "filters": filters,
            "can_create": can_create_document(user),
        },
    )


@app.post("/documents/create", response_class=RedirectResponse)
async def create_document_record(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=app_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    if not can_create_document(user):
        raise HTTPException(status_code=403, detail="Недостаточно прав для создания документа.")

    form_data = await request.form()
    doc_type = form_data.get("doc_type")
    org_code = form_data.get("org_code")
    class_code = form_data.get("class_code")
    reg_number = form_data.get("reg_number")
    doc_name = form_data.get("doc_name")
    developed_by = form_data.get("developed_by")
    is_okpo = form_data.get("is_okpo") == "true"
    org_name = form_data.get("org_name")
    doc_kind_code = form_data.get("doc_kind_code", "")

    if not developed_by:
        raise HTTPException(status_code=400, detail="Необходимо указать ФИО разработчика.")
    if doc_type not in ("DD", "TD"):
        raise HTTPException(status_code=400, detail="Неверный тип документа.")
    if not all([org_code, class_code]):
        raise HTTPException(status_code=400, detail="Код организации и код классификации обязательны.")

    base_doc = BaseDocument(
        type=doc_type,
        doc_name=doc_name,
        developed_by=developed_by,
        created_by=user.full_name,
        uploaded_by=user.id,
        position=user.position,
        department=user.department,
        status=DocumentStatus.pending_review,
    )
    session.add(base_doc)
    await session.flush()

    org_id = await get_or_create_org_id(session, org_code, is_okpo=is_okpo, org_name=org_name or None)
    is_kd = doc_type == "DD"
    class_code_id = await get_or_create_class_id(session, class_code, is_kd=is_kd)

    if is_kd:
        if reg_number:
            prni_to_save = int(reg_number)
            if not await check_prni_unique(session, org_id, class_code_id, prni_to_save):
                raise HTTPException(status_code=400, detail="Указанный ПРНИ уже используется.")
        else:
            prni_to_save = await get_next_prni(session, org_id, class_code_id)

        designation = f"{org_code}.{class_code}.{prni_to_save:03d}"
        if doc_kind_code:
            designation += doc_kind_code

        session.add(
            DesignDocument(
                id=base_doc.id,
                org_id=org_id,
                kd_class_code_id=class_code_id,
                prni=prni_to_save,
                designation=designation,
                org_code_str=org_code,
                class_code_str=class_code,
                doc_kind_code=doc_kind_code or None,
            )
        )
    else:
        if reg_number:
            prn_to_save = int(reg_number)
            if not await check_prn_unique(session, org_id, class_code_id, prn_to_save):
                raise HTTPException(status_code=400, detail="Указанный ПРН уже используется.")
        else:
            prn_to_save = await get_next_prn(session, org_id, class_code_id)

        designation = f"{org_code}.{class_code}.{prn_to_save:03d}"
        session.add(
            TechDocument(
                id=base_doc.id,
                org_id=org_id,
                td_class_code_id=class_code_id,
                prn=prn_to_save,
                designation=designation,
                org_code_str=org_code,
                class_code_str=class_code,
            )
        )

    await session.commit()
    return RedirectResponse(url=app_path(f"/documents/{base_doc.id}/upload"), status_code=status.HTTP_303_SEE_OTHER)


@app.get("/documents/{doc_id}/upload", response_class=HTMLResponse)
async def upload_page(
    doc_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=app_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    result = await session.execute(
        select(BaseDocument)
        .options(joinedload(BaseDocument.design_document), joinedload(BaseDocument.tech_document))
        .where(BaseDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден.")

    designation = None
    if doc.design_document:
        designation = doc.design_document.designation
    elif doc.tech_document:
        designation = doc.tech_document.designation

    can_upload = can_upload_file(user, doc)
    return templates.TemplateResponse(
        "upload.html",
        {
            "request": request,
            "doc_id": doc_id,
            "designation": designation,
            "doc": doc,
            "can_upload": can_upload,
            "error": request.query_params.get("error"),
        },
    )


@app.post("/documents/{doc_id}/upload", response_class=RedirectResponse)
async def handle_upload(
    doc_id: int,
    file: Optional[UploadFile] = File(None),
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=app_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    doc = await session.get(BaseDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден.")

    require_upload_permission(user, doc)

    try:
        file_path, unique_file_name = await save_upload_file(doc_id, file, doc.file_path)
    except HTTPException:
        return RedirectResponse(url=app_path(f"/documents/{doc_id}/upload?error=invalid"), status_code=303)

    doc.file_path = file_path
    doc.file_name = unique_file_name
    doc.status = DocumentStatus.pending_review
    await session.commit()

    return RedirectResponse(url=app_path("/documents"), status_code=status.HTTP_303_SEE_OTHER)


@app.get("/documents/{doc_id}/download")
async def download_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    await _require_user(access_token, session)
    doc = await session.get(BaseDocument, doc_id)
    if not doc or not doc.file_path or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="Файл не найден")

    return FileResponse(path=doc.file_path, filename=doc.file_name, media_type="application/octet-stream")


@app.get("/documents/{doc_id}/edit", response_class=HTMLResponse)
async def edit_document_page(
    doc_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=app_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    doc = await session.get(BaseDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден.")
    if not can_edit_document_metadata(user, doc):
        raise HTTPException(status_code=403, detail="Редактирование доступно только администратору.")

    return templates.TemplateResponse("edit_document.html", {"request": request, "doc": doc, "user": user})


@app.post("/documents/{doc_id}/edit", response_class=RedirectResponse)
async def edit_document(
    doc_id: int,
    doc_name: str = Form(""),
    developed_by: str = Form(...),
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=app_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    doc = await session.get(BaseDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден.")

    require_edit_metadata_permission(user, doc)
    doc.doc_name = doc_name or None
    doc.developed_by = developed_by
    await session.commit()
    return RedirectResponse(url=app_path("/documents"), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/documents/{doc_id}/status", response_class=RedirectResponse)
async def set_document_status(
    doc_id: int,
    new_status: str = Form(...),
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=app_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    require_status_change_permission(user)

    try:
        status_enum = DocumentStatus(new_status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный статус.")

    if status_enum not in (DocumentStatus.verified, DocumentStatus.requires_correction):
        raise HTTPException(status_code=400, detail="Можно установить только «Проверено» или «Требуется исправление».")

    doc = await session.get(BaseDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден.")

    doc.status = status_enum
    await session.commit()
    return RedirectResponse(url=app_path("/documents"), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/documents/{doc_id}/delete", response_class=RedirectResponse)
async def delete_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=app_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    require_delete_permission(user)

    doc = await session.get(BaseDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден.")

    remove_file_if_exists(doc.file_path)
    await session.delete(doc)
    await session.commit()
    return RedirectResponse(url=app_path("/documents"), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/api/check_org", response_model=dict)
async def check_org_endpoint(
    org_code: str = Form(...),
    is_okpo_str: str = Form("false"),
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    await _require_user(access_token, session)
    is_okpo = is_okpo_str == "true"
    return await check_org_exists(session, org_code, is_okpo)
