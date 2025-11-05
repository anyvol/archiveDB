# app/main.py

from fastapi import FastAPI, Security, Request, Depends, Cookie, Form, HTTPException, status
from fastapi import UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from typing import Optional
import shutil
import os

from app.database import engine, get_session
from app.models import Base
from app.models import BaseDocument, DesignDocument
from app.routers import router as user_router
from app import docs
from app.services import authenticate_user 

UPLOAD_DIR = "uploaded_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)

templates = Jinja2Templates(directory="templates")

app = FastAPI()

app.include_router(user_router, prefix="/users")
app.include_router(docs.router, prefix="/docs")

@app.on_event("startup")
async def startup_event():
    # Создание таблиц
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # для проверки
    print("DATABASE_URL:", os.getenv("DATABASE_URL"))
    print("SECRET_KEY:", os.getenv("SECRET_KEY"))
    print("ACCESS_TOKEN_MINUTES:", os.getenv("ACCESS_TOKEN_MINUTES"))
    print("ALGORITHM:", os.getenv("ALGORITHM"))

@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse(url="/documents")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=RedirectResponse)
async def handle_login(
    username: str = Form(...),
    password: str = Form(...)
):
    try:
        # Используем сервисную функцию
        async for session in get_session():
            token_data = await authenticate_user(
                session=session, 
                username=username, 
                password=password
            )
            break  # Выходим после первой итерации

        access_token = token_data['access_token']
        
        response = RedirectResponse(url="/documents", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            key="access_token", 
            value=f"Bearer {access_token}", 
            httponly=True,  # Cookie доступен только на сервере, защита от XSS
            samesite="lax"  # Защита от CSRF
        )
        return response
        
    except HTTPException:
        # Если аутентификация не удалась, возвращаемся на страницу входа
        return RedirectResponse(url="/login?error=true", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/documents", response_class=HTMLResponse)
async def documents_page(request: Request, access_token: Optional[str] = Cookie(None)):
    if not access_token:
        # Если токена нет, перенаправляем на страницу входа
        return RedirectResponse(url="/login")
    
    # Здесь мы могли бы получить документы из API
    # Но для начала просто отобразим страницу
    documents_from_db = []  # Заглушка, позже заполним данными из API
    
    return templates.TemplateResponse(
        "documents.html", 
        {"request": request, "documents": documents_from_db}
    )

@app.post("/documents/create", response_class=RedirectResponse)
async def create_document_record(
    # --- Поля из новой формы ---
    doc_type: str = Form(...),
    designation_method: Optional[str] = Form(None),
    org_code: Optional[str] = Form(None),
    class_code: Optional[str] = Form(None),
    reg_number: Optional[str] = Form(None), # ПРНИ
    doc_name: Optional[str] = Form(None), # Наименование
    # --- Системные зависимости ---
    session: AsyncSession = Depends(get_session),
    access_token: Optional[str] = Cookie(None)
):
    if not access_token:
        return RedirectResponse(url="/login")
    
    from app.auth import get_current_user_from_token
    user = await get_current_user_from_token(token=access_token.split("Bearer ")[1], db=session)

    if doc_type == "DD" and designation_method == "impersonal":
        # Логика для КД (Обезличенный)
        if not all([org_code, class_code]):
            raise HTTPException(status_code=400, detail="Код организации и код классификации обязательны.")

        # --- Логика генерации ПРНИ ---
        if reg_number is None:
            # Ищем максимальный ПРНИ для данной пары (org_code, class_code)
            # Примечание: Это требует, чтобы org_code и class_code были в таблице DesignDocument
            # Если они в других таблицах (Organization, ClassCodeKD), логика будет сложнее
            
            # Предположим, что org_code и class_code хранятся как строки
            # Для этого нужно добавить их в модель DesignDocument
            
            # Запрос для поиска максимального номера
            # SELECT max(prni) FROM design_documents WHERE org_code = ... AND class_code = ...
            max_prni_result = await session.execute(
                select(func.max(DesignDocument.prni)).where(
                    DesignDocument.org_code_str == org_code, # org_code_str - новое поле
                    DesignDocument.class_code_str == class_code # class_code_str - новое поле
                )
            )
            max_prni = max_prni_result.scalar_one_or_none()
            
            reg_number = (max_prni or 0) + 1 # Новый номер
            
        # Формируем обозначение
        designation = f"{org_code}.{class_code}.{reg_number:03d}"

        # 1. Создаем базовую запись
        base_doc = BaseDocument(
            file_name=doc_name or "", # Используем наименование как имя файла по умолчанию
            file_path="",
            created_by=user.full_name,
            uploaded_by=user.id,
            position=user.position,
            department=user.department,
            type=doc_type
        )
        session.add(base_doc)
        await session.flush()

        # 2. Создаем запись DesignDocument
        specific_doc = DesignDocument(
            id=base_doc.id,
            # Тут нужно будет получить ID организации и класса по их кодам
            # org_id = ...
            # kd_class_code_id = ...
            prni=reg_number,
            designation=designation,
            # Добавим новые поля
            org_code_str=org_code,
            class_code_str=class_code
        )
        session.add(specific_doc)

    elif doc_type == "TD":
        # Логика для технологических документов (пока заглушка)
        raise HTTPException(status_code=501, detail="Создание ТД пока не реализовано")
    else:
        raise HTTPException(status_code=400, detail="Неверный тип документа или способ обозначения")

    await session.commit()
    
    return RedirectResponse(url=f"/documents/{base_doc.id}/upload", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/documents/{doc_id}/upload", response_class=HTMLResponse)
async def upload_page(request: Request, doc_id: int, session: AsyncSession = Depends(get_session)):
    doc = await session.get(BaseDocument, doc_id)
    return templates.TemplateResponse(
        "upload.html", 
        {"request": request, "doc_id": doc_id, "designation": doc.designation}
    )

@app.post("/documents/{doc_id}/upload", response_class=RedirectResponse)
async def handle_upload(
    doc_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session)
):
    doc = await session.get(BaseDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    file_path = os.path.join(UPLOAD_DIR, f"{doc.id}_{file.filename}")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    doc.file_path = file_path
    doc.file_name = file.filename
    await session.commit()
    
    return RedirectResponse(url="/documents", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout", response_class=RedirectResponse)
async def logout():

    response = RedirectResponse(url="/login")
    response.delete_cookie(key="access_token")  # Удаляем cookie
    return response