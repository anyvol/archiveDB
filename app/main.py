# app/main.py

from fastapi import FastAPI, Request, Depends, Cookie, Form, HTTPException, status, File, UploadFile, Response
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse  
from fastapi.templating import Jinja2Templates
from urllib.parse import urlencode
from contextlib import asynccontextmanager
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from typing import Optional
import shutil
import os
import logging
from datetime import datetime

from app.database import engine, get_session, get_or_create_org_id, get_or_create_class_id
from app.models import Base, Organization, ClassCodeKD, ClassCodeTD, BaseDocument, DesignDocument, TechDocument, User
from app.routers import router as user_router
from app import docs  # Предполагаю, что это ваш docs.router
from app.auth import get_current_user_from_token, authenticate_user, get_password_hash  # Импорты из auth.py (authenticate_user и hash сюда)

UPLOAD_DIR = "uploaded_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__) 

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Создание таблиц (async с run_sync)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield  # Приложение работает
    
    # Shutdown: Закрытие engine
    await engine.dispose()

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

app.include_router(user_router, prefix="/users")
app.include_router(docs.router, prefix="/docs")

@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse(url="/documents")

@app.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None)
):
    # Если токен существует и валиден — редирект на documents
    if access_token:
        try:
            await get_current_user_from_token(access_token=access_token, db=session)
            return RedirectResponse(url="/documents", status_code=status.HTTP_303_SEE_OTHER)
        except HTTPException:
            # Токен неверный — очищаем cookie и показываем форму
            response = RedirectResponse(url="/login")
            response.delete_cookie("access_token")
            return response
    
    # Получаем query params для сообщений
    error = request.query_params.get("error")
    success = request.query_params.get("success")
    
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": error == "true",
            "success": success == "true"
        }
    )

@app.post("/login", response_class=RedirectResponse)
async def handle_login(
    username: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session)
):
    try:
        token_data = await authenticate_user(session, username, password)
        access_token = token_data['access_token']
        response = RedirectResponse(url="/documents", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            key="access_token", 
            value=f"Bearer {access_token}", 
            max_age=3600,  # 1 час
            httponly=True, 
            samesite="lax"
        )
        return response
    except HTTPException:
        return RedirectResponse(url="/login?error=true", status_code=status.HTTP_303_SEE_OTHER)
    
@app.get("/logout", response_class=RedirectResponse)
async def logout(
    response: Response,
    access_token: Optional[str] = Cookie(None)
):
    """
    Logout: Удаление cookie access_token и редирект на /login.
    """
    # Установка cookie в пустое значение с истечением (удаление)
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token",
        value="",  # Пустое значение
        max_age=0,  # Немедленное истечение
        httponly=True,  # Защита от JS
        secure=False,  # True в production с HTTPS
        samesite="lax"  # Защита от CSRF
    )
    logger.info("User logged out")  # Лог выхода
    return response

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    error = request.query_params.get("error") == "true"
    return templates.TemplateResponse("register.html", {"request": request, "error": error})

@app.post("/register", response_class=RedirectResponse)
async def handle_register(
    login: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),  # Required в шаблоне
    position: str = Form(""),
    department: str = Form(""),
    role: str = Form("user"),  # <-- Добавлено: default "user"
    session: AsyncSession = Depends(get_session)
):
    try:
        # Валидация role (опционально: только user/admin)
        if role not in ["user", "admin"]:
            raise HTTPException(status_code=400, detail="Неверная роль. Доступны: user, admin.")
        
        # Проверка на существующий login
        existing_user_result = await session.execute(select(User).where(User.login == login))
        if existing_user_result.scalars().first():
            raise HTTPException(status_code=400, detail="Пользователь с таким логином уже существует.")
        
        # Хэширование пароля
        hashed_password = get_password_hash(password)
        new_user = User(
            login=login,
            password_hash=hashed_password,
            full_name=full_name,
            position=position,
            department=department,
            role=role  # <-- Используем из формы (user или admin)
        )
        session.add(new_user)
        await session.commit()
        
        # Успех: Редирект на login
        query_params = {"success": "true"}
        url = f"/login?{urlencode(query_params)}"
        return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
        
    except HTTPException as e:
        query_params = {"error": "true"}
        url = f"/register?{urlencode(query_params)}"
        return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)

@app.get("/documents", response_class=HTMLResponse)
async def documents_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None)
):
    if not access_token:
        return RedirectResponse(url="/login")
    
    user = await get_current_user_from_token(access_token=access_token, db=session)
    

    query = select(BaseDocument).options(
        joinedload(BaseDocument.design_document),
        joinedload(BaseDocument.tech_document)
    ).order_by(BaseDocument.created_at.desc())
    
    result = await session.execute(query)
    documents_from_db = result.scalars().all()
    
    return templates.TemplateResponse(
        "documents.html", 
        {
            "request": request, 
            "documents": documents_from_db,
            "user": user
        }
    )

@app.post("/documents/create", response_class=RedirectResponse)
async def create_document_record(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None)
):
    if not access_token:
        return RedirectResponse(url="/login")

    user = await get_current_user_from_token(access_token=access_token, db=session)
    
    # Получение данных из формы
    form_data = await request.form()
    doc_type = form_data.get("doc_type")
    designation_method = form_data.get("designation_method")
    org_code = form_data.get("org_code")
    class_code = form_data.get("class_code")
    reg_number = form_data.get("reg_number")
    doc_name = form_data.get("doc_name")
    developed_by = form_data.get("developed_by")
    if not developed_by:
        raise HTTPException(status_code=400, detail="Необходимо указать ФИО разработчика.")

    if not doc_type or doc_type not in ["DD", "TD"]:
        raise HTTPException(status_code=400, detail="Неверный тип документа.")

    # Инициализация base_doc с новыми полями
    base_doc = BaseDocument(
        type=doc_type,
        doc_name=doc_name,
        developed_by=developed_by,
        created_by=user.full_name,
        uploaded_by=user.id,
        position=user.position,
        department=user.department,
        checked=False  # По умолчанию "не проверено"
        # file_name и file_path остаются NULL до загрузки файла
    )
    session.add(base_doc)
    await session.flush()  # Получаем ID для связанных документов

    # Логика для конкретных типов документов (DD/TD)
    if doc_type == "DD" and designation_method == "impersonal":
        if not all([org_code, class_code]):
            raise HTTPException(status_code=400, detail="Код организации и код классификации обязательны.")
        
        org_id = await get_or_create_org_id(session, org_code)
        class_code_id = await get_or_create_class_id(session, class_code, is_kd=True)
        
        prni_to_save = None
        if reg_number:
            try:
                prni_to_save = int(reg_number)
            except ValueError:
                raise HTTPException(status_code=400, detail="ПРНИ должен быть числом.")
        else:
            max_prni_result = await session.execute(
                select(func.max(DesignDocument.prni)).where(
                    DesignDocument.org_id == org_id,
                    DesignDocument.kd_class_code_id == class_code_id
                )
            )
            max_prni = max_prni_result.scalar_one_or_none()
            prni_to_save = (max_prni or 0) + 1
        
        designation = f"{org_code}.{class_code}.{prni_to_save:03d}"
        
        specific_doc = DesignDocument(
            id=base_doc.id,
            org_id=org_id,
            kd_class_code_id=class_code_id,
            prni=prni_to_save,
            designation=designation,
            org_code_str=org_code,
            class_code_str=class_code
        )
        session.add(specific_doc)
        
    elif doc_type == "TD" and designation_method == "impersonal":
        # Предполагается, что для TD фронтенд также отправляет designation_method
        if not all([org_code, class_code]):
            raise HTTPException(status_code=400, detail="Код организации и код классификации обязательны.")
        
        org_id = await get_or_create_org_id(session, org_code)
        class_code_id = await get_or_create_class_id(session, class_code, is_kd=False)
        
        prn_to_save = None
        if reg_number:
            try:
                prn_to_save = int(reg_number)
            except ValueError:
                raise HTTPException(status_code=400, detail="PRN должен быть числом.")
        else:
            max_prn_result = await session.execute(
                select(func.max(TechDocument.prn)).where(
                    TechDocument.org_id == org_id,
                    TechDocument.td_class_code_id == class_code_id
                )
            )
            max_prn = max_prn_result.scalar_one_or_none()
            prn_to_save = (max_prn or 0) + 1
        
        designation = f"{org_code}.{class_code}.{prn_to_save:03d}"
        
        specific_doc = TechDocument(
            id=base_doc.id,
            org_id=org_id,
            td_class_code_id=class_code_id,
            prn=prn_to_save,
            designation=designation,
            org_code_str=org_code,
            class_code_str=class_code
        )
        session.add(specific_doc)
        
    else:
        pass
    
    await session.commit()
    logger.info(f"Document record {base_doc.id} created by user {user.login}")
    
    return RedirectResponse(url=f"/documents/{base_doc.id}/upload", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/documents/{doc_id}/upload", response_class=HTMLResponse)
async def upload_page(
    request: Request, 
    doc_id: int, 
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None)
):
    if not access_token:
        return RedirectResponse(url="/login")
    
    user = await get_current_user_from_token(access_token=access_token, db=session)
    
    # Загрузка с joinedload (как ранее)
    result = await session.execute(
        select(BaseDocument)
        .options(
            joinedload(BaseDocument.design_document),
            joinedload(BaseDocument.tech_document)
        )
        .where(BaseDocument.id == doc_id)
    )
    doc = result.scalars().first()
    
    if not doc or doc.uploaded_by != user.id:
        raise HTTPException(status_code=404, detail="Документ не найден или нет доступа")
    
    # Получение designation
    designation = None
    if doc.design_document:
        designation = doc.design_document.designation
    elif doc.tech_document:
        designation = doc.tech_document.designation
    
    return templates.TemplateResponse(
        "upload.html", 
        {
            "request": request, 
            "doc_id": doc_id, 
            "designation": designation or "N/A",
            "file_name": doc.file_name or None  # Для показа в шаблоне, если уже загружен
        }
    )

@app.post("/documents/{doc_id}/upload", response_class=RedirectResponse)
async def handle_upload(
    doc_id: int,
    file: Optional[UploadFile] = File(None),  # <-- Опциональный: None если нет file
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None)
):
    if not access_token:
        return RedirectResponse(url="/login")
    
    user = await get_current_user_from_token(access_token=access_token, db=session)
    
    result = await session.execute(
        select(BaseDocument)
        .options(
            joinedload(BaseDocument.design_document),
            joinedload(BaseDocument.tech_document)
        )
        .where(BaseDocument.id == doc_id)
    )
    doc = result.scalars().first()
    
    if not doc or doc.uploaded_by != user.id:
        raise HTTPException(status_code=404, detail="Документ не найден или нет доступа")
    
    if not file or file.filename is None or file.size == 0:  # <-- Проверка: если file не предоставлен
        raise HTTPException(status_code=400, detail="Файл обязателен для загрузки")
    
    # Генерация путей и unique file_name (как ранее)
    file_path = os.path.join(UPLOAD_DIR, f"{doc.id}_{file.filename}")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    filename_base, extension = os.path.splitext(file.filename)
    unique_file_name = f"{filename_base}_{doc.id}{extension}"
    
    doc.file_path = file_path
    doc.file_name = unique_file_name
    await session.commit()
    
    logger.info(f"File uploaded for document {doc_id} by user {user.login}")
    return RedirectResponse(url="/documents", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/documents/{doc_id}/download")
async def download_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None)
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    user = await get_current_user_from_token(access_token=access_token, db=session)
    
    # Загрузка doc (joinedload не обязательно; доступ ко всем, если авторизован)
    doc = await session.get(BaseDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")
    
    if not doc.file_path or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    # Убрали проверку doc.uploaded_by == user.id — все видят/скачивают все
    return FileResponse(
        path=doc.file_path,
        filename=doc.file_name,  # Уникальное имя для скачивания (e.g., "angle_table1_2.pdf")
        media_type="application/octet-stream"  # Универсальный; можно по extension
    )

@app.post("/documents/{doc_id}/delete", response_class=RedirectResponse)
async def delete_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None)
):
    if not access_token:
        return RedirectResponse(url="/login")
    
    user = await get_current_user_from_token(access_token=access_token, db=session)
    
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Доступ запрещен (только админ)")
    
    # Загрузка doc (joinedload для удаления связанных, если нужно)
    result = await session.execute(
        select(BaseDocument)
        .options(
            joinedload(BaseDocument.design_document),
            joinedload(BaseDocument.tech_document)
        )
        .where(BaseDocument.id == doc_id)
    )
    doc = result.scalars().first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")
    
    # Удаление файла с FS, если существует
    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)
    
    # Удаление связанных записей (design/tech), если есть
    if doc.design_document:
        session.delete(doc.design_document)
    if doc.tech_document:
        session.delete(doc.tech_document)
    
    # Удаление base_doc
    session.delete(doc)
    await session.commit()
    logger.info(f"Document record {doc_id} deleted (including related documents and file if present)")
    return RedirectResponse(url="/documents", status_code=status.HTTP_303_SEE_OTHER)