# app/database.py
"""
Async SQLAlchemy setup: engine, sessionmaker, сессии и helpers для справочников.
Используется для async операций с PostgreSQL (asyncpg).
"""
import os
import re
from dotenv import load_dotenv
from typing import AsyncGenerator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncEngine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException, status

# Импорты моделей (предполагаем, что они в app/models.py)
from app.models import Organization, ClassCodeKD, ClassCodeTD

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in .env")


# Создание async engine (echo=True для логов SQL-запросов)
engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async-генератор сессий для Depends в эндпоинтах.
    Автоматически открывает/закрывает сессию в контексте.
    """
    async with async_session() as session:
        yield session

async def get_or_create_org_id(session: AsyncSession, org_code: str) -> int:
    """
    Находит ID организации по коду или создаёт новую запись.
    Валидация: 4 заглавные кириллические буквы или 8 цифр.
    """
    if not org_code:
        raise HTTPException(status_code=400, detail="Код организации обязателен.")
    
    # Валидация длины
    if len(org_code) != 4 and len(org_code) != 8:
        raise HTTPException(status_code=400, detail="Код организации должен иметь длину 4 (буквы) или 8 (цифры).")
    
    # Валидация содержимого с regex
    if len(org_code) == 4:
        # 4 заглавные кириллические буквы (А-Я)
        if not re.match(r'^[А-Я]{4}$', org_code):
            raise HTTPException(status_code=400, detail="Код организации (буквы) должен состоять из 4 заглавных кириллических букв (А-Я).")
    elif len(org_code) == 8:
        # 8 цифр
        if not re.match(r'^\d{8}$', org_code):
            raise HTTPException(status_code=400, detail="Код организации (цифры) должен состоять из 8 цифр.")
    
    # Поиск существующей записи (await для async execute)
    result = await session.execute(
        select(Organization).where(Organization.code == org_code)
    )
    org = result.scalars().first()
    
    if org:
        return org.id
    
    # Создание новой записи
    new_org = Organization(
        code=org_code,
        name=f"Организация с кодом {org_code}",  # Заглушка; можно расширить
        department="Не указано"
    )
    session.add(new_org)
    await session.flush()  # Await для получения ID
    return new_org.id

async def get_or_create_class_id(session: AsyncSession, class_code: str, is_kd: bool = True) -> int:
    """
    Находит ID класса КД/ТД по коду или создаёт новую запись.
    is_kd=True для КД (6 цифр), False для ТД (7 цифр).
    """
    expected_length = 6 if is_kd else 7
    if not class_code or len(class_code) != expected_length:
        raise HTTPException(status_code=400, detail=f"Код класса {'КД' if is_kd else 'ТД'} должен состоять из {expected_length} цифр.")
    
    # Валидация: только цифры
    if not re.match(rf'^\d{{{expected_length}}}$', class_code):
        raise HTTPException(status_code=400, detail=f"Код класса {'КД' if is_kd else 'ТД'} должен состоять только из цифр.")
    
    model = ClassCodeKD if is_kd else ClassCodeTD
    result = await session.execute(  # Await
        select(model).where(model.code == class_code)
    )
    class_obj = result.scalars().first()
    
    if class_obj:
        return class_obj.id
    
    # Создание новой записи
    new_class = model(
        code=class_code,
        description=f"Класс {'КД' if is_kd else 'ТД'} {class_code}"  # Заглушка
    )
    session.add(new_class)
    await session.flush()  # Await
    return new_class.id