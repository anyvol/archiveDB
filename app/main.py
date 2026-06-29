# app/main.py

from fastapi import FastAPI, Request, Depends, Cookie, Form, HTTPException, status, File, UploadFile, Response, Query
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
from datetime import datetime

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
    DOCUMENT_TYPE_LABELS,
    DEPARTMENTS,
    Project,
    DOC_KIND_CODES,
)
from app.routers import router as user_router
from app import docs
from app.auth import get_current_user_from_token, authenticate_user, get_password_hash
from app.document_queries import fetch_documents
from app.document_helpers import save_upload_file, remove_file_if_exists, save_development_order_file
from app.project_helpers import get_project_by_id, create_new_project
from app.config import UPLOAD_DIR, ROOT_PATH, url_path, SERVICE_VERSION
from app.permissions import (
    can_create_document,
    can_edit_document_metadata,
    can_set_document_status,
    can_upload_file,
    can_delete_document,
    is_admin,
    is_owner,
    require_delete_permission,
    require_edit_metadata_permission,
    require_status_change_permission,
    require_upload_permission,
)
from app.user_helpers import build_full_name, split_full_name
from app.column_preferences import DOCUMENT_COLUMNS, get_visible_columns, DEFAULT_VISIBLE_COLUMNS
from app.notifications import (
    count_unread,
    mark_all_read,
    get_notifications_for_user,
    poll_new_notifications,
    notify_file_upload,
    notify_document_registered,
    notify_status_change,
    notify_document_edit,
    clear_document_references,
    notify_document_delete,
)
from app.document_display import get_document_display_status, format_field_change

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan, root_path=ROOT_PATH)
templates = Jinja2Templates(directory="templates")
templates.env.globals["DOCUMENT_STATUS_LABELS"] = DOCUMENT_STATUS_LABELS
templates.env.globals["DOCUMENT_TYPE_LABELS"] = DOCUMENT_TYPE_LABELS
templates.env.globals["DOC_KIND_CODES"] = DOC_KIND_CODES
templates.env.globals["DEPARTMENTS"] = DEPARTMENTS
templates.env.globals["url_path"] = url_path
templates.env.globals["DocumentStatus"] = DocumentStatus
templates.env.globals["UserRole"] = UserRole
templates.env.globals["can_upload_file"] = can_upload_file
templates.env.globals["can_set_document_status"] = can_set_document_status
templates.env.globals["can_delete_document"] = can_delete_document
templates.env.globals["can_edit_document_metadata"] = can_edit_document_metadata
templates.env.globals["service_version"] = SERVICE_VERSION
templates.env.globals["DOCUMENT_COLUMNS"] = DOCUMENT_COLUMNS
templates.env.globals["get_document_display_status"] = get_document_display_status

app.include_router(user_router, prefix="/users")
app.include_router(docs.router, prefix="/docs")

_COOKIE_PATH = ROOT_PATH or "/"


async def _page_context(session: AsyncSession, user: User) -> dict:
    return {
        "user": user,
        "unread_count": await count_unread(session, user.id),
    }


async def _require_user(access_token: Optional[str], session: AsyncSession) -> User:
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Не авторизован")
    return await get_current_user_from_token(access_token=access_token, db=session)


def _filter_params(request: Request) -> dict:
    qp = request.query_params
    return {
        "designation": qp.get("designation") or None,
        "okpo": qp.get("okpo") or None,
        "org_name": qp.get("org_name") or None,
        "project_id": qp.get("project_id") or None,
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


@app.get("/version")
async def version():
    return {"version": SERVICE_VERSION}


@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse(url=url_path("/documents"))


@app.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if access_token:
        try:
            await get_current_user_from_token(access_token=access_token, db=session)
            return RedirectResponse(url=url_path("/documents"), status_code=status.HTTP_303_SEE_OTHER)
        except HTTPException:
            response = RedirectResponse(url=url_path("/login"))
            response.delete_cookie("access_token", path=_COOKIE_PATH)
            return response

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": request.query_params.get("error") == "true",
            "success": request.query_params.get("success") == "true",
            "service_version": SERVICE_VERSION,
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
        response = RedirectResponse(url=url_path("/documents"), status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            key="access_token",
            value=f"Bearer {token_data['access_token']}",
            max_age=3600,
            httponly=True,
            samesite="lax",
            path=_COOKIE_PATH,
        )
        return response
    except HTTPException:
        return RedirectResponse(url=url_path("/login?error=true"), status_code=status.HTTP_303_SEE_OTHER)


@app.get("/logout", response_class=RedirectResponse)
async def logout():
    response = RedirectResponse(url=url_path("/login"), status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token", path=_COOKIE_PATH)
    return response


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {
            "request": request,
            "error": request.query_params.get("error"),
        },
    )


def _register_form_context(
    request: Request,
    error: str | None = None,
    login: str = "",
    last_name: str = "",
    first_name: str = "",
    patronymic: str = "",
    email: str = "",
    position: str = "",
    department: str = "",
) -> dict:
    return {
        "request": request,
        "error": error,
        "form_login": login,
        "form_last_name": last_name,
        "form_first_name": first_name,
        "form_patronymic": patronymic,
        "form_email": email,
        "form_position": position,
        "form_department": department,
    }


@app.post("/register", response_class=HTMLResponse)
async def handle_register(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    last_name: str = Form(...),
    first_name: str = Form(...),
    patronymic: str = Form(""),
    email: str = Form(""),
    position: str = Form(""),
    department: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    form_ctx = _register_form_context(
        request,
        login=login,
        last_name=last_name,
        first_name=first_name,
        patronymic=patronymic,
        email=email,
        position=position,
        department=department,
    )

    if password != password_confirm:
        form_ctx["error"] = "mismatch"
        return templates.TemplateResponse("register.html", form_ctx, status_code=400)

    if department not in DEPARTMENTS:
        form_ctx["error"] = "department"
        return templates.TemplateResponse("register.html", form_ctx, status_code=400)

    full_name = build_full_name(last_name, first_name, patronymic)
    if not full_name:
        form_ctx["error"] = "name"
        return templates.TemplateResponse("register.html", form_ctx, status_code=400)

    try:
        existing = await session.execute(select(User).where(User.login == login))
        if existing.scalars().first():
            form_ctx["error"] = "exists"
            return templates.TemplateResponse("register.html", form_ctx, status_code=400)

        session.add(
            User(
                login=login,
                password_hash=get_password_hash(password),
                full_name=full_name,
                position=position or None,
                department=department,
                email=email.strip() or None,
                role=UserRole.user,
            )
        )
        await session.commit()
        return RedirectResponse(url=url_path("/login?success=true"), status_code=status.HTTP_303_SEE_OTHER)
    except Exception:
        logger.exception("Registration failed for login=%s", login)
        form_ctx["error"] = "server"
        return templates.TemplateResponse("register.html", form_ctx, status_code=500)


@app.get("/documents", response_class=HTMLResponse)
async def documents_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    filters = _filter_params(request)
    documents_from_db = await fetch_documents(session, **filters)
    projects_result = await session.execute(select(Project).order_by(Project.name))
    projects = projects_result.scalars().all()
    ctx = await _page_context(session, user)

    return templates.TemplateResponse(
        "documents.html",
        {
            "request": request,
            "documents": documents_from_db,
            "filters": filters,
            "projects": projects,
            "can_create": can_create_document(user),
            "preferred_org_code": user.preferred_org_code or "",
            "preferred_org_okpo": user.preferred_org_okpo,
            "default_developed_by": user.full_name or "",
            "visible_columns": get_visible_columns(user),
            "service_version": SERVICE_VERSION,
            **ctx,
        },
    )


@app.post("/documents/create", response_class=RedirectResponse)
async def create_document_record(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

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
    doc_kind_code = (form_data.get("doc_kind_code") or "").strip()
    existing_project_id = (form_data.get("existing_project_id") or "").strip()
    new_project_name = (form_data.get("new_project_name") or "").strip()
    new_project_cipher = (form_data.get("new_project_cipher") or "").strip()
    project_dev_order = form_data.get("project_dev_order")

    if not developed_by:
        raise HTTPException(status_code=400, detail="Необходимо указать ФИО разработчика.")
    if doc_type not in ("DD", "TD"):
        raise HTTPException(status_code=400, detail="Неверный тип документа.")
    if not all([org_code, class_code]):
        raise HTTPException(status_code=400, detail="Код организации и код классификации обязательны.")
    if doc_kind_code and doc_kind_code not in DOC_KIND_CODES:
        raise HTTPException(status_code=400, detail="Неверный код вида документа.")

    if existing_project_id and new_project_name:
        raise HTTPException(status_code=400, detail="Выберите существующий проект или укажите новый, но не оба сразу.")
    if existing_project_id:
        project = await get_project_by_id(session, int(existing_project_id))
    elif new_project_name:
        project = await create_new_project(session, new_project_name, new_project_cipher)
        if project_dev_order and getattr(project_dev_order, "filename", None):
            await save_development_order_file(project_dev_order, project.slug)
    else:
        raise HTTPException(status_code=400, detail="Необходимо выбрать или указать проект.")

    base_doc = BaseDocument(
        type=doc_type,
        doc_name=doc_name,
        developed_by=developed_by,
        created_by=user.full_name,
        uploaded_by=user.id,
        position=user.position,
        department=user.department,
        project_id=project.id,
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
    return RedirectResponse(url=url_path(f"/documents/{base_doc.id}/upload"), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/documents/{doc_id}/skip-upload", response_class=RedirectResponse)
async def skip_upload(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
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
        raise HTTPException(status_code=404, detail="Документ не найден.")

    if not is_admin(user) and not is_owner(user, doc):
        raise HTTPException(status_code=403, detail="Недостаточно прав.")

    if not doc.registration_notified_at:
        await notify_document_registered(session, doc, user)
        doc.registration_notified_at = datetime.utcnow()

    await session.commit()
    return RedirectResponse(url=url_path("/documents"), status_code=status.HTTP_303_SEE_OTHER)


@app.get("/documents/{doc_id}/upload", response_class=HTMLResponse)
async def upload_page(
    doc_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    result = await session.execute(
        select(BaseDocument)
        .options(
            joinedload(BaseDocument.design_document),
            joinedload(BaseDocument.tech_document),
            joinedload(BaseDocument.project),
        )
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
    ctx = await _page_context(session, user)
    return templates.TemplateResponse(
        "upload.html",
        {
            "request": request,
            "doc_id": doc_id,
            "designation": designation,
            "doc": doc,
            "can_upload": can_upload,
            "error": request.query_params.get("error"),
            "service_version": SERVICE_VERSION,
            **ctx,
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
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
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
        raise HTTPException(status_code=404, detail="Документ не найден.")

    require_upload_permission(user, doc)
    await session.refresh(doc, ["project"])
    project_slug = doc.project.slug if doc.project else "_legacy"
    had_file_before = bool(doc.file_name)
    registration_already_notified = bool(doc.registration_notified_at)

    try:
        file_path, unique_file_name = await save_upload_file(
            doc_id,
            file,
            project_slug,
            doc.file_path,
            doc_kind_code=doc.design_document.doc_kind_code if doc.design_document else None,
        )
    except HTTPException:
        return RedirectResponse(url=url_path(f"/documents/{doc_id}/upload?error=invalid"), status_code=303)

    doc.file_path = file_path
    doc.file_name = unique_file_name
    doc.status = DocumentStatus.pending_review
    if not doc.registration_notified_at:
        doc.registration_notified_at = datetime.utcnow()
    await notify_file_upload(
        session,
        doc,
        user,
        had_file_before=had_file_before,
        registration_already_notified=registration_already_notified,
    )
    await session.commit()

    return RedirectResponse(url=url_path("/documents"), status_code=status.HTTP_303_SEE_OTHER)


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
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    doc = await session.get(BaseDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден.")
    if not can_edit_document_metadata(user, doc):
        raise HTTPException(
            status_code=403,
            detail="Редактирование недоступно. Новое изменение можно сделать только после проверки или отправки на исправление.",
        )

    ctx = await _page_context(session, user)
    return templates.TemplateResponse(
        "edit_document.html",
        {"request": request, "doc": doc, "service_version": SERVICE_VERSION, **ctx},
    )


@app.post("/documents/{doc_id}/edit", response_class=RedirectResponse)
async def edit_document(
    doc_id: int,
    doc_name: str = Form(""),
    developed_by: str = Form(...),
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    doc = await session.get(BaseDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден.")

    require_edit_metadata_permission(user, doc)
    old_doc_name = doc.doc_name
    old_developed_by = doc.developed_by
    new_doc_name = doc_name or None
    changes = []
    name_change = format_field_change("наименование", old_doc_name, new_doc_name)
    if name_change:
        changes.append(name_change)
    dev_change = format_field_change("разработчик", old_developed_by, developed_by)
    if dev_change:
        changes.append(dev_change)

    doc.doc_name = new_doc_name
    doc.developed_by = developed_by
    doc.status = DocumentStatus.pending_review
    await notify_document_edit(session, doc, user, changes)
    await session.commit()
    return RedirectResponse(url=url_path("/documents"), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/documents/{doc_id}/status", response_class=RedirectResponse)
async def set_document_status(
    doc_id: int,
    new_status: str = Form(...),
    comment: str = Form(""),
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    require_status_change_permission(user)

    try:
        status_enum = DocumentStatus(new_status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный статус.")

    if status_enum not in (DocumentStatus.verified, DocumentStatus.requires_correction):
        raise HTTPException(status_code=400, detail="Можно установить только «Проверено» или «Требуется исправление».")

    if status_enum == DocumentStatus.requires_correction and not comment.strip():
        raise HTTPException(status_code=400, detail="Для статуса «Требуется исправление» необходим комментарий.")

    doc = await session.get(BaseDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден.")

    doc.status = status_enum
    if status_enum == DocumentStatus.requires_correction:
        doc.review_comment = comment.strip()
    elif status_enum == DocumentStatus.verified:
        doc.review_comment = None
    await notify_status_change(session, doc, user, status_enum, comment.strip() or None)
    await session.commit()
    return RedirectResponse(url=url_path("/documents"), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/documents/{doc_id}/delete", response_class=RedirectResponse)
async def delete_document(
    doc_id: int,
    comment: str = Form(...),
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    require_delete_permission(user)

    if not comment.strip():
        raise HTTPException(status_code=400, detail="Для удаления документа необходим комментарий.")

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
        raise HTTPException(status_code=404, detail="Документ не найден.")

    await notify_document_delete(session, doc, user, comment.strip())
    await clear_document_references(session, doc_id)
    remove_file_if_exists(doc.file_path)
    await session.delete(doc)
    await session.commit()
    return RedirectResponse(url=url_path("/documents"), status_code=status.HTTP_303_SEE_OTHER)


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


@app.get("/help", response_class=HTMLResponse)
async def help_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    ctx: dict = {"service_version": SERVICE_VERSION}
    if access_token:
        try:
            user = await get_current_user_from_token(access_token=access_token, db=session)
            ctx.update(await _page_context(session, user))
            ctx["user"] = user
            ctx["nav_context"] = "help"
        except HTTPException:
            ctx["user"] = None
            ctx["unread_count"] = 0
    else:
        ctx["user"] = None
        ctx["unread_count"] = 0

    return templates.TemplateResponse(
        "help.html",
        {"request": request, **ctx},
    )


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    org_display_name = ""
    if user.preferred_org_code:
        org_info = await check_org_exists(session, user.preferred_org_code, user.preferred_org_okpo)
        if org_info.get("exists"):
            org_display_name = org_info.get("name", "")

    last_name, first_name, patronymic = split_full_name(user.full_name)
    ctx = await _page_context(session, user)

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "org_display_name": org_display_name,
            "success": request.query_params.get("success") == "true",
            "last_name": last_name,
            "first_name": first_name,
            "patronymic": patronymic,
            "visible_columns": get_visible_columns(user),
            "service_version": SERVICE_VERSION,
            "nav_context": "profile",
            **ctx,
        },
    )


@app.post("/profile", response_class=RedirectResponse)
async def handle_profile(
    request: Request,
    last_name: str = Form(...),
    first_name: str = Form(...),
    patronymic: str = Form(""),
    email: str = Form(""),
    position: str = Form(""),
    department: str = Form(...),
    preferred_org_code: str = Form(""),
    preferred_org_okpo: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    if department not in DEPARTMENTS:
        raise HTTPException(status_code=400, detail="Недопустимый отдел.")

    full_name = build_full_name(last_name, first_name, patronymic)
    if not full_name:
        raise HTTPException(status_code=400, detail="Необходимо указать фамилию и имя.")

    form_data = await request.form()
    selected_columns = [
        key for key, _ in DOCUMENT_COLUMNS if form_data.get(f"col_{key}") == "true"
    ]
    if not selected_columns:
        selected_columns = list(DEFAULT_VISIBLE_COLUMNS)

    user.full_name = full_name
    user.position = position or None
    user.department = department
    user.email = email.strip() or None
    user.preferred_org_code = preferred_org_code.strip() or None
    user.preferred_org_okpo = preferred_org_okpo == "true"
    user.visible_columns = selected_columns

    await session.commit()
    return RedirectResponse(url=url_path("/profile?success=true"), status_code=status.HTTP_303_SEE_OTHER)


@app.get("/notifications", response_class=HTMLResponse)
async def notifications_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    notifications = await get_notifications_for_user(session, user)
    unread_ids = {n.id for n in notifications if not n.is_read}
    await mark_all_read(session, user.id)
    await session.commit()
    ctx = await _page_context(session, user)

    return templates.TemplateResponse(
        "notifications.html",
        {
            "request": request,
            "notifications": notifications,
            "unread_ids": unread_ids,
            "service_version": SERVICE_VERSION,
            "nav_context": "notifications",
            **ctx,
        },
    )


@app.get("/api/notifications/poll")
async def poll_notifications_api(
    after: int = 0,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Не авторизован")
    user = await get_current_user_from_token(access_token=access_token, db=session)
    notifications = await poll_new_notifications(session, user, after_id=after)
    unread = await count_unread(session, user.id)
    return {"notifications": notifications, "unread_count": unread}
