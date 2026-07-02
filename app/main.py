# app/main.py

from fastapi import FastAPI, Request, Depends, Cookie, Form, HTTPException, status, File, UploadFile, Response, Query
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, PlainTextResponse, Response, JSONResponse
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
    BaseDocument,
    DesignDocument,
    TechDocument,
    User,
    UserRole,
    DocumentStatus,
    DOCUMENT_STATUS_LABELS,
    DOCUMENT_TYPE_LABELS,
    DEPARTMENTS,
    USER_ROLE_LABELS,
    Project,
    ProjectFile,
    ProjectImage,
    DOC_KIND_CODES,
)
from app.routers import router as user_router
from app import docs
from app.auth import get_current_user_from_token, authenticate_user, get_password_hash
from app.document_queries import fetch_documents
from app.document_helpers import save_upload_file, remove_file_if_exists
from app.project_helpers import get_project_by_id, create_new_project
from app.project_files import (
    save_development_order_file,
    save_project_file,
    save_project_images,
    remove_project_file_from_disk,
    sync_project_misc_files,
)
from app.document_format import DOCUMENT_FORMATS, DOCUMENT_FORMAT_LABELS, is_valid_document_format
from app.metadata_helpers import detect_document_format_from_bytes
from app.name_helpers import fetch_known_person_names, normalize_person_name
from app.config import UPLOAD_DIR, ROOT_PATH, url_path, app_scope, SERVICE_VERSION, VAPID_PUBLIC_KEY
from app.permissions import (
    can_create_document,
    can_edit_document_metadata,
    can_set_document_status,
    can_upload_file,
    can_delete_document,
    can_apply_formal_change,
    can_request_minor_correction,
    can_respond_correction_request,
    is_admin,
    is_owner,
    require_delete_permission,
    require_edit_metadata_permission,
    require_status_change_permission,
    require_upload_permission,
)
from app.change_log import (
    get_document_change_history,
    format_change_event_summary,
    is_governed_document,
    log_change_event,
    log_document_status_change,
    log_file_upload,
)
from app.document_workflow import (
    fetch_document,
    preview_media_type,
    request_minor_correction,
    respond_correction_request,
    apply_cosmetic_file_replace,
    apply_formal_document_change,
)
from app.models import DocumentChangeEventType
from app.user_helpers import build_full_name, split_full_name, validate_person_fields
from app.column_preferences import DOCUMENT_COLUMNS, get_visible_columns, DEFAULT_VISIBLE_COLUMNS
from app.notifications import (
    count_unread,
    mark_all_read,
    get_notifications_for_user,
    count_notifications_for_user,
    NOTIFICATIONS_PAGE_SIZE,
    poll_new_notifications,
    notify_file_upload,
    notify_document_registered,
    notify_status_change,
    notify_document_edit,
    clear_document_references,
    notify_document_delete,
    send_document_delete_push,
    get_document_designation,
)
from app.document_display import get_document_display_status, format_field_change
from app.cert_scripts import (
    cert_download_url,
    external_base_url,
    server_site_info,
    trust_linux_script,
    trust_macos_script,
    trust_windows_cmd,
    trust_windows_ps1,
)
from app.push import DEFAULT_PUSH_PREFERENCES, normalize_push_preferences
from app.changelog import render_changelog_html

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan, root_path=ROOT_PATH)
templates = Jinja2Templates(directory="templates")
templates.env.globals["DOCUMENT_STATUS_LABELS"] = DOCUMENT_STATUS_LABELS
templates.env.globals["DOCUMENT_TYPE_LABELS"] = DOCUMENT_TYPE_LABELS
templates.env.globals["DOC_KIND_CODES"] = DOC_KIND_CODES
templates.env.globals["DEPARTMENTS"] = DEPARTMENTS
templates.env.globals["USER_ROLE_LABELS"] = USER_ROLE_LABELS
templates.env.globals["url_path"] = url_path
templates.env.globals["app_scope"] = app_scope
templates.env.globals["DocumentStatus"] = DocumentStatus
templates.env.globals["UserRole"] = UserRole
templates.env.globals["can_upload_file"] = can_upload_file
templates.env.globals["can_set_document_status"] = can_set_document_status
templates.env.globals["can_delete_document"] = can_delete_document
templates.env.globals["can_edit_document_metadata"] = can_edit_document_metadata
templates.env.globals["can_apply_formal_change"] = can_apply_formal_change
templates.env.globals["get_document_display_status"] = get_document_display_status
templates.env.globals["can_request_minor_correction"] = can_request_minor_correction
templates.env.globals["can_respond_correction_request"] = can_respond_correction_request
templates.env.globals["is_governed_document"] = is_governed_document
templates.env.globals["service_version"] = SERVICE_VERSION
templates.env.globals["DOCUMENT_COLUMNS"] = DOCUMENT_COLUMNS
templates.env.globals["DOCUMENT_FORMATS"] = DOCUMENT_FORMATS
templates.env.globals["DOCUMENT_FORMAT_LABELS"] = DOCUMENT_FORMAT_LABELS

app.include_router(user_router, prefix="/users")
app.include_router(docs.router, prefix="/docs")

_COOKIE_PATH = ROOT_PATH or "/"
_CERT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "nginx", "certs", "fullchain.pem")
_SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
_CERT_SCRIPT_FILES = {
    "windows-forward-ports.ps1": ("windows-forward-ports.ps1", "application/octet-stream"),
    "trust-cert-windows.ps1": ("trust-cert-windows.ps1", "application/octet-stream"),
}
_GENERATED_CERT_SCRIPTS = {
    "trust-windows.cmd": ("trust-windows.cmd", trust_windows_cmd),
    "trust-windows.ps1": ("trust-windows.ps1", trust_windows_ps1),
    "trust-linux.sh": ("trust-linux.sh", trust_linux_script),
    "trust-macos.sh": ("trust-macos.sh", trust_macos_script),
}


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


@app.get("/sw.js", response_class=PlainTextResponse)
async def service_worker():
    sw_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "sw.js")
    with open(sw_path, encoding="utf-8") as f:
        content = f.read()
    return PlainTextResponse(
        content,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@app.get("/changelog", response_class=HTMLResponse)
async def changelog_page(
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
        except HTTPException:
            ctx["user"] = None
            ctx["unread_count"] = 0
    else:
        ctx["user"] = None
        ctx["unread_count"] = 0

    return templates.TemplateResponse(
        "changelog.html",
        {
            "request": request,
            "changelog_html": render_changelog_html(),
            **ctx,
        },
    )


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

    field_error = validate_person_fields(last_name, first_name, patronymic, position)
    if field_error:
        form_ctx["error"] = field_error
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
    known_person_names = await fetch_known_person_names(session)
    ctx = await _page_context(session, user)

    return templates.TemplateResponse(
        "documents.html",
        {
            "request": request,
            "documents": documents_from_db,
            "filters": filters,
            "projects": projects,
            "known_person_names": known_person_names,
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
    developed_by = normalize_person_name(form_data.get("developed_by") or "")
    reviewed_by = normalize_person_name(form_data.get("reviewed_by") or "") or None
    approved_by = normalize_person_name(form_data.get("approved_by") or "") or None
    developer_signed_date = (form_data.get("developer_signed_date") or "").strip() or None
    reviewer_signed_date = (form_data.get("reviewer_signed_date") or "").strip() or None
    approver_signed_date = (form_data.get("approver_signed_date") or "").strip() or None
    is_ajax = form_data.get("_ajax") == "1"
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
            await save_development_order_file(session, project, project_dev_order, user)
    else:
        raise HTTPException(status_code=400, detail="Необходимо выбрать или указать проект.")

    base_doc = BaseDocument(
        type=doc_type,
        doc_name=doc_name,
        developed_by=developed_by,
        reviewed_by=reviewed_by,
        approved_by=approved_by,
        developer_signed_date=developer_signed_date,
        reviewer_signed_date=reviewer_signed_date,
        approver_signed_date=approver_signed_date,
        created_by=user.full_name,
        uploaded_by=user.id,
        position=user.position,
        department=user.department,
        project_id=project.id,
        status=DocumentStatus.pending_review,
    )
    session.add(base_doc)
    await session.flush()
    await session.refresh(base_doc, ["design_document", "tech_document"])
    await log_change_event(
        session,
        base_doc,
        user,
        DocumentChangeEventType.register,
        comment="Регистрация записи в архиве",
    )

    org_id = await get_or_create_org_id(session, org_code, is_okpo=is_okpo, org_name=org_name or None)
    is_kd = doc_type == "DD"
    class_code_id = await get_or_create_class_id(session, class_code, is_kd=is_kd)

    if is_kd:
        if reg_number:
            prni_to_save = int(reg_number)
            if not await check_prni_unique(session, org_id, class_code_id, prni_to_save):
                raise HTTPException(status_code=400, detail="Указанный порядковый номер уже используется.")
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
    redirect_url = url_path(f"/documents/{base_doc.id}/upload")
    if is_ajax:
        return JSONResponse({"ok": True, "redirect": redirect_url})
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


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
    is_replace = bool(doc.file_name) and is_governed_document(doc)
    ctx = await _page_context(session, user)
    return templates.TemplateResponse(
        "upload.html",
        {
            "request": request,
            "doc_id": doc_id,
            "designation": designation,
            "doc": doc,
            "can_upload": can_upload,
            "is_replace": is_replace,
            "document_formats": DOCUMENT_FORMATS,
            "detected_format": request.query_params.get("detected_format"),
            "error": request.query_params.get("error"),
            "service_version": SERVICE_VERSION,
            **ctx,
        },
    )


@app.post("/documents/{doc_id}/upload", response_class=RedirectResponse)
async def handle_upload(
    doc_id: int,
    file: Optional[UploadFile] = File(None),
    change_comment: str = Form(""),
    document_format: str = Form(""),
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    doc = await fetch_document(session, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден.")

    require_upload_permission(user, doc)
    await session.refresh(doc, ["project"])
    project_slug = doc.project.slug if doc.project else "_legacy"
    had_file_before = bool(doc.file_name)
    registration_already_notified = bool(doc.registration_notified_at)
    is_replace = had_file_before

    if is_replace and is_governed_document(doc):
        if not change_comment.strip():
            return RedirectResponse(
                url=url_path(f"/documents/{doc_id}/upload?error=comment_required"),
                status_code=303,
            )
        try:
            await apply_cosmetic_file_replace(session, doc, user, file, change_comment)
        except HTTPException:
            return RedirectResponse(url=url_path(f"/documents/{doc_id}/upload?error=invalid"), status_code=303)
        await notify_file_upload(
            session,
            doc,
            user,
            had_file_before=True,
            registration_already_notified=registration_already_notified,
        )
        await session.commit()
        return RedirectResponse(url=url_path(f"/documents/{doc_id}"), status_code=status.HTTP_303_SEE_OTHER)

    if not document_format or not is_valid_document_format(document_format):
        return RedirectResponse(
            url=url_path(f"/documents/{doc_id}/upload?error=format_required"),
            status_code=303,
        )

    try:
        file_path, unique_file_name = await save_upload_file(
            file,
            project_slug,
            doc.file_path if not is_governed_document(doc) else None,
            doc_kind_code=doc.design_document.doc_kind_code if doc.design_document else None,
            designation=get_document_designation(doc) if (doc.design_document or doc.tech_document) else None,
        )
    except HTTPException:
        return RedirectResponse(url=url_path(f"/documents/{doc_id}/upload?error=invalid"), status_code=303)

    doc.file_path = file_path
    doc.file_name = unique_file_name
    doc.document_format = document_format
    old_status = doc.status
    doc.status = DocumentStatus.pending_review
    if not doc.registration_notified_at:
        doc.registration_notified_at = datetime.utcnow()
    await log_file_upload(session, doc, user, unique_file_name, replacement=had_file_before)
    await log_document_status_change(session, doc, user, old_status, DocumentStatus.pending_review)
    await notify_file_upload(
        session,
        doc,
        user,
        had_file_before=had_file_before,
        registration_already_notified=registration_already_notified,
    )
    await session.commit()

    return RedirectResponse(url=url_path(f"/documents/{doc_id}"), status_code=status.HTTP_303_SEE_OTHER)


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


@app.get("/documents/{doc_id}/preview")
async def preview_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    await _require_user(access_token, session)
    doc = await session.get(BaseDocument, doc_id)
    if not doc or not doc.file_path or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="Файл не найден")

    media_type = preview_media_type(doc.file_path)
    if not media_type:
        raise HTTPException(status_code=415, detail="Предпросмотр недоступен для этого формата.")

    return FileResponse(
        path=doc.file_path,
        media_type=media_type,
        content_disposition_type="inline",
    )


@app.get("/documents/{doc_id}/ii/{ii_id}/preview")
async def preview_change_notification(
    doc_id: int,
    ii_id: int,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    await _require_user(access_token, session)
    from app.models import ChangeNotification

    ii = await session.get(ChangeNotification, ii_id)
    if not ii or ii.document_id != doc_id or not os.path.exists(ii.file_path):
        raise HTTPException(status_code=404, detail="Извещение не найдено.")

    return FileResponse(
        path=ii.file_path,
        media_type="application/pdf",
        content_disposition_type="inline",
    )


@app.get("/documents/{doc_id}", response_class=HTMLResponse)
async def document_detail_page(
    doc_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    doc = await fetch_document(session, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден.")

    designation = get_document_designation(doc)
    history = await get_document_change_history(session, doc_id)
    for event in history:
        await session.refresh(event, ["actor", "change_notification"])
        event.summary = format_change_event_summary(event)

    can_preview = bool(doc.file_path and preview_media_type(doc.file_path))
    preview_is_image = bool(
        doc.file_path and preview_media_type(doc.file_path or "").startswith("image/")
    )

    ctx = await _page_context(session, user)
    return templates.TemplateResponse(
        "document_detail.html",
        {
            "request": request,
            "doc": doc,
            "designation": designation,
            "change_history": history,
            "is_governed": is_governed_document(doc),
            "can_preview": can_preview,
            "preview_is_image": preview_is_image,
            "error": request.query_params.get("error"),
            "service_version": SERVICE_VERSION,
            **ctx,
        },
    )


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
    old_status = doc.status
    doc.status = DocumentStatus.pending_review
    if changes:
        await log_change_event(
            session,
            doc,
            user,
            DocumentChangeEventType.metadata_edit,
            comment="; ".join(changes),
        )
    await log_document_status_change(session, doc, user, old_status, DocumentStatus.pending_review)
    await notify_document_edit(session, doc, user, changes)
    await session.commit()
    return RedirectResponse(url=url_path("/documents"), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/documents/{doc_id}/status", response_class=RedirectResponse)
async def set_document_status(
    doc_id: int,
    request: Request,
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

    if status_enum not in (DocumentStatus.approved, DocumentStatus.requires_correction):
        raise HTTPException(status_code=400, detail="Можно установить только «Утверждено» или «Требуется исправление».")

    if status_enum == DocumentStatus.requires_correction and not comment.strip():
        raise HTTPException(status_code=400, detail="Для статуса «Требуется исправление» необходим комментарий.")

    doc = await session.get(BaseDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден.")

    old_status = doc.status
    doc.status = status_enum
    if status_enum == DocumentStatus.requires_correction:
        doc.review_comment = comment.strip()
    elif status_enum == DocumentStatus.approved:
        doc.review_comment = None
    await log_document_status_change(
        session,
        doc,
        user,
        old_status,
        status_enum,
        comment=comment.strip() or None,
    )
    await notify_status_change(session, doc, user, status_enum, comment.strip() or None)
    await session.commit()
    redirect_to = request.headers.get("referer") or url_path("/documents")
    if f"/documents/{doc_id}" in (redirect_to or ""):
        return RedirectResponse(url=url_path(f"/documents/{doc_id}"), status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=url_path("/documents"), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/documents/{doc_id}/request-correction", response_class=RedirectResponse)
async def request_correction(
    doc_id: int,
    comment: str = Form(...),
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    doc = await fetch_document(session, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден.")
    if not can_request_minor_correction(user, doc):
        raise HTTPException(status_code=403, detail="Запрос на исправление недоступен.")

    await request_minor_correction(session, doc, user, comment)
    await session.commit()
    return RedirectResponse(url=url_path(f"/documents/{doc_id}"), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/documents/{doc_id}/respond-correction", response_class=RedirectResponse)
async def respond_correction(
    doc_id: int,
    approved: str = Form(...),
    comment: str = Form(""),
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    doc = await fetch_document(session, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден.")
    if not can_respond_correction_request(user, doc):
        raise HTTPException(status_code=403, detail="Недостаточно прав.")

    is_approved = approved.lower() in ("true", "1", "yes")
    await respond_correction_request(session, doc, user, approved=is_approved, comment=comment)
    await session.commit()
    return RedirectResponse(url=url_path(f"/documents/{doc_id}"), status_code=status.HTTP_303_SEE_OTHER)


@app.get("/documents/{doc_id}/apply-change", response_class=HTMLResponse)
async def apply_change_page(
    doc_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    doc = await fetch_document(session, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден.")
    if not can_apply_formal_change(user, doc):
        raise HTTPException(status_code=403, detail="Формальное изменение недоступно для этого документа.")

    ctx = await _page_context(session, user)
    return templates.TemplateResponse(
        "apply_change.html",
        {
            "request": request,
            "doc": doc,
            "designation": get_document_designation(doc),
            "error": request.query_params.get("error"),
            "form": _empty_apply_change_form(),
            "service_version": SERVICE_VERSION,
            **ctx,
        },
    )


def _empty_apply_change_form() -> dict:
    return {
        "ii_number": "",
        "change_number": "",
        "change_date": "",
        "comment": "",
        "developer_signed": False,
        "reviewer_signed": False,
        "approver_signed": False,
    }


async def _render_apply_change_error(
    request: Request,
    session: AsyncSession,
    user: User,
    doc: BaseDocument,
    *,
    error: str,
    ii_number: str = "",
    change_number: str = "",
    change_date: str = "",
    comment: str = "",
    developer_signed: bool = False,
    reviewer_signed: bool = False,
    approver_signed: bool = False,
) -> HTMLResponse:
    ctx = await _page_context(session, user)
    return templates.TemplateResponse(
        "apply_change.html",
        {
            "request": request,
            "doc": doc,
            "designation": get_document_designation(doc),
            "error": error,
            "form": {
                "ii_number": ii_number,
                "change_number": change_number,
                "change_date": change_date,
                "comment": comment,
                "developer_signed": developer_signed,
                "reviewer_signed": reviewer_signed,
                "approver_signed": approver_signed,
            },
            "service_version": SERVICE_VERSION,
            **ctx,
        },
    )


@app.post("/documents/{doc_id}/apply-change")
async def apply_change_submit(
    doc_id: int,
    request: Request,
    ii_file: Optional[UploadFile] = File(None),
    new_doc_file: Optional[UploadFile] = File(None),
    ii_number: str = Form(""),
    change_number: str = Form(""),
    change_date: str = Form(""),
    comment: str = Form(""),
    developer_signed: Optional[str] = Form(None),
    reviewer_signed: Optional[str] = Form(None),
    approver_signed: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    doc = await fetch_document(session, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден.")
    if not can_apply_formal_change(user, doc):
        raise HTTPException(status_code=403, detail="Формальное изменение недоступно.")

    form_kwargs = dict(
        ii_number=ii_number,
        change_number=change_number,
        change_date=change_date,
        comment=comment,
        developer_signed=bool(developer_signed),
        reviewer_signed=bool(reviewer_signed),
        approver_signed=bool(approver_signed),
    )

    async def form_error(message: str) -> HTMLResponse:
        return await _render_apply_change_error(
            request, session, user, doc, error=message, **form_kwargs
        )

    if not ii_file or not ii_file.filename:
        return await form_error("Приложите файл извещения об изменении (ИИ).")
    if not new_doc_file or not new_doc_file.filename:
        return await form_error("Приложите новую версию документа.")

    try:
        parsed_date = datetime.strptime(change_date, "%Y-%m-%d")
    except ValueError:
        return await form_error("Укажите корректную дату изменения.")

    try:
        await apply_formal_document_change(
            session,
            doc,
            user,
            ii_file=ii_file,
            new_doc_file=new_doc_file,
            ii_number=ii_number,
            change_number=change_number,
            change_date=parsed_date,
            developer_signed=bool(developer_signed),
            reviewer_signed=bool(reviewer_signed),
            approver_signed=bool(approver_signed),
            comment=comment,
        )
    except HTTPException as exc:
        return await form_error(exc.detail)

    await session.commit()
    return RedirectResponse(url=url_path(f"/documents/{doc_id}"), status_code=status.HTTP_303_SEE_OTHER)


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

    push_info = await notify_document_delete(session, doc, user, comment.strip())
    await clear_document_references(session, doc_id)
    remove_file_if_exists(doc.file_path)
    await session.delete(doc)
    await session.commit()
    if push_info:
        recipients, message = push_info
        await send_document_delete_push(session, recipients, message)
    return RedirectResponse(url=url_path("/documents"), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/api/detect-document-format", response_model=dict)
async def detect_document_format_endpoint(
    file: UploadFile = File(...),
    access_token: Optional[str] = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    await _require_user(access_token, session)
    if not file or not file.filename:
        return {"detected": False, "format": None, "message": "Файл не выбран."}

    contents = await file.read()
    detected = detect_document_format_from_bytes(contents, file.filename)
    if detected:
        return {
            "detected": True,
            "format": detected,
            "label": DOCUMENT_FORMAT_LABELS.get(detected, detected),
            "message": f"Формат определён из метаданных файла: {DOCUMENT_FORMAT_LABELS.get(detected, detected)}",
        }
    return {
        "detected": False,
        "format": None,
        "message": "Не удалось определить формат из метаданных файла. Выберите формат вручную.",
    }


@app.get("/projects", response_class=HTMLResponse)
async def projects_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    result = await session.execute(select(Project).order_by(Project.name))
    projects = result.scalars().all()
    ctx = await _page_context(session, user)

    return templates.TemplateResponse(
        "projects.html",
        {
            "request": request,
            "projects": projects,
            "can_create": can_create_document(user),
            "error": request.query_params.get("error"),
            "service_version": SERVICE_VERSION,
            **ctx,
        },
    )


@app.post("/projects/create", response_class=RedirectResponse)
async def create_project_record(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    if not can_create_document(user):
        raise HTTPException(status_code=403, detail="Недостаточно прав.")

    form_data = await request.form()
    new_project_name = (form_data.get("new_project_name") or "").strip()
    new_project_cipher = (form_data.get("new_project_cipher") or "").strip()
    description = (form_data.get("description") or "").strip()
    project_dev_order = form_data.get("project_dev_order")
    image_files = [f for f in form_data.getlist("project_images") if getattr(f, "filename", None)]

    if not new_project_name or not new_project_cipher:
        return RedirectResponse(url=url_path("/projects?error=name_required"), status_code=303)

    project = await create_new_project(session, new_project_name, new_project_cipher)
    project.description = description or None
    project.created_at = datetime.utcnow()

    if project_dev_order and getattr(project_dev_order, "filename", None):
        await save_development_order_file(session, project, project_dev_order, user)

    if image_files:
        await save_project_images(session, project, image_files)

    await session.commit()
    return RedirectResponse(url=url_path(f"/projects/{project.id}"), status_code=status.HTTP_303_SEE_OTHER)


@app.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail_page(
    project_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    result = await session.execute(
        select(Project)
        .options(
            joinedload(Project.project_files),
            joinedload(Project.project_images),
            joinedload(Project.documents),
        )
        .where(Project.id == project_id)
    )
    project = result.unique().scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден.")

    await sync_project_misc_files(session, project, user)
    await session.commit()
    await session.refresh(project, ["project_files", "project_images", "documents"])

    ctx = await _page_context(session, user)
    return templates.TemplateResponse(
        "project_detail.html",
        {
            "request": request,
            "project": project,
            "can_manage": can_create_document(user),
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
            "service_version": SERVICE_VERSION,
            **ctx,
        },
    )


@app.post("/projects/{project_id}/update", response_class=RedirectResponse)
async def update_project(
    project_id: int,
    description: str = Form(""),
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    if not can_create_document(user):
        raise HTTPException(status_code=403, detail="Недостаточно прав.")

    project = await get_project_by_id(session, project_id)
    project.description = description.strip() or None
    await session.commit()
    return RedirectResponse(
        url=url_path(f"/projects/{project_id}?success=updated"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/projects/{project_id}/upload-file", response_class=RedirectResponse)
async def upload_project_file(
    project_id: int,
    title: str = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    if not can_create_document(user):
        raise HTTPException(status_code=403, detail="Недостаточно прав.")

    project = await get_project_by_id(session, project_id)
    try:
        await save_project_file(session, project, title, file, user)
    except HTTPException:
        return RedirectResponse(url=url_path(f"/projects/{project_id}?error=upload"), status_code=303)

    await session.commit()
    return RedirectResponse(
        url=url_path(f"/projects/{project_id}?success=file"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/projects/{project_id}/upload-images", response_class=RedirectResponse)
async def upload_project_images(
    project_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))

    user = await get_current_user_from_token(access_token=access_token, db=session)
    if not can_create_document(user):
        raise HTTPException(status_code=403, detail="Недостаточно прав.")

    form_data = await request.form()
    image_files = [f for f in form_data.getlist("project_images") if getattr(f, "filename", None)]
    if not image_files:
        return RedirectResponse(url=url_path(f"/projects/{project_id}?error=images"), status_code=303)

    project = await get_project_by_id(session, project_id)
    try:
        await save_project_images(session, project, image_files)
    except HTTPException:
        return RedirectResponse(url=url_path(f"/projects/{project_id}?error=images"), status_code=303)

    await session.commit()
    return RedirectResponse(
        url=url_path(f"/projects/{project_id}?success=images"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/projects/{project_id}/files/{file_id}/download")
async def download_project_file(
    project_id: int,
    file_id: int,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    await _require_user(access_token, session)
    record = await session.get(ProjectFile, file_id)
    if not record or record.project_id != project_id or not os.path.exists(record.file_path):
        raise HTTPException(status_code=404, detail="Файл не найден.")
    return FileResponse(path=record.file_path, filename=record.file_name, media_type="application/octet-stream")


@app.get("/projects/{project_id}/images/{image_id}")
async def serve_project_image(
    project_id: int,
    image_id: int,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    await _require_user(access_token, session)
    image = await session.get(ProjectImage, image_id)
    if not image or image.project_id != project_id or not os.path.exists(image.file_path):
        raise HTTPException(status_code=404, detail="Изображение не найдено.")
    return FileResponse(path=image.file_path, filename=image.file_name)


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
            "error": request.query_params.get("error"),
            "last_name": last_name,
            "first_name": first_name,
            "patronymic": patronymic,
            "visible_columns": get_visible_columns(user),
            "service_version": SERVICE_VERSION,
            "nav_context": "profile",
            "push_preferences": normalize_push_preferences(user.push_preferences),
            "vapid_public_key": VAPID_PUBLIC_KEY,
            "has_push_subscription": bool(user.push_subscription),
            "cert_available": os.path.isfile(_CERT_FILE),
            "cert_base_url": external_base_url(request, https=True),
            "sw_scope": app_scope(),
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

    field_error = validate_person_fields(last_name, first_name, patronymic, position)
    if field_error:
        return RedirectResponse(
            url=url_path(f"/profile?error={field_error}"),
            status_code=status.HTTP_303_SEE_OTHER,
        )

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

    push_prefs = normalize_push_preferences(user.push_preferences)
    push_prefs["enabled"] = form_data.get("push_enabled") == "true"
    for key in DEFAULT_PUSH_PREFERENCES:
        if key == "enabled":
            continue
        push_prefs[key] = form_data.get(f"push_{key}") == "true"
    user.push_preferences = push_prefs

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
    notifications = await get_notifications_for_user(session, user, limit=NOTIFICATIONS_PAGE_SIZE)
    total_count = await count_notifications_for_user(session, user.id)
    has_more = len(notifications) < total_count
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
            "has_more": has_more,
            "notifications_page_size": NOTIFICATIONS_PAGE_SIZE,
            "service_version": SERVICE_VERSION,
            "nav_context": "notifications",
            **ctx,
        },
    )


@app.get("/api/notifications")
async def list_notifications_api(
    offset: int = Query(0, ge=0),
    limit: int = Query(NOTIFICATIONS_PAGE_SIZE, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Не авторизован")
    user = await get_current_user_from_token(access_token=access_token, db=session)
    notifications = await get_notifications_for_user(session, user, limit=limit, offset=offset)
    total_count = await count_notifications_for_user(session, user.id)
    return {
        "notifications": [
            {
                "id": n.id,
                "message": n.message,
                "created_at": n.created_at.strftime("%Y-%m-%d %H:%M") if n.created_at else "",
            }
            for n in notifications
        ],
        "has_more": offset + len(notifications) < total_count,
    }


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


@app.get("/api/push/vapid-public-key")
async def push_vapid_public_key(
    access_token: Optional[str] = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    await _require_user(access_token, session)
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=503, detail="Push-уведомления не настроены на сервере.")
    return {"public_key": VAPID_PUBLIC_KEY}


@app.post("/api/push/subscribe")
async def push_subscribe(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    user = await _require_user(access_token, session)
    subscription = await request.json()
    if not subscription.get("endpoint"):
        raise HTTPException(status_code=400, detail="Некорректная подписка.")
    user.push_subscription = subscription
    prefs = normalize_push_preferences(user.push_preferences)
    prefs["enabled"] = True
    user.push_preferences = prefs
    await session.commit()
    return {"status": "subscribed"}


@app.post("/api/push/unsubscribe")
async def push_unsubscribe(
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
):
    user = await _require_user(access_token, session)
    user.push_subscription = None
    prefs = normalize_push_preferences(user.push_preferences)
    prefs["enabled"] = False
    user.push_preferences = prefs
    await session.commit()
    return {"status": "unsubscribed"}


@app.get("/cert/fullchain.pem")
async def download_site_certificate():
    if not os.path.isfile(_CERT_FILE):
        raise HTTPException(status_code=404, detail="Сертификат недоступен.")
    return FileResponse(
        _CERT_FILE,
        filename="archive-site.pem",
        media_type="application/x-pem-file",
    )


@app.get("/cert/site-info.json")
async def download_site_info(request: Request):
    """Public server connection info for universal client trust scripts."""
    return server_site_info(request)


@app.get("/cert/scripts/{script_key}")
async def download_cert_script(
    script_key: str,
    request: Request,
    access_token: Optional[str] = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    await _require_user(access_token, session)

    if script_key in _GENERATED_CERT_SCRIPTS:
        filename, builder = _GENERATED_CERT_SCRIPTS[script_key]
        info = server_site_info(request)
        content = builder(info)
        media_type = "application/x-sh" if filename.endswith(".sh") else "application/octet-stream"
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    if script_key not in _CERT_SCRIPT_FILES:
        raise HTTPException(status_code=404, detail="Скрипт не найден.")
    filename, media_type = _CERT_SCRIPT_FILES[script_key]
    script_path = os.path.join(_SCRIPTS_DIR, filename)
    if not os.path.isfile(script_path):
        raise HTTPException(status_code=404, detail="Скрипт не найден.")
    return FileResponse(script_path, filename=filename, media_type=media_type)
