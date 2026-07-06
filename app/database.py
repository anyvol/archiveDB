"""
Async SQLAlchemy setup: engine, sessionmaker, сессии и helpers для справочников.
Используется для async операций с PostgreSQL (asyncpg).
"""
import os
import re
from dotenv import load_dotenv
from typing import AsyncGenerator, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncEngine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException, status


from app.models import Organization, ClassCodeKD, ClassCodeTD, DesignDocument, TechDocument
from app.designation_helpers import build_designation


load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in .env")


engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async-генератор сессий для Depends в эндпоинтах.
    Автоматически открывает/закрывает сессию в контексте.
    """
    async with async_session() as session:
        yield session


async def get_or_create_org_id(
    session: AsyncSession, 
    org_code: str, 
    is_okpo: bool = False, 
    org_name: Optional[str] = None
) -> int:
    """
    Находит ID организации по коду или создаёт новую запись.
    Поддержка ОКПО: если is_okpo=True, валидация и хранение как 8-значный ОКПО.
    Если org_name предоставлено и не пустое – использует его для новой организации (с валидацией).
    Если org_name None/пустое для новой – использует заглушку.
    """
    if not org_code:
        raise HTTPException(status_code=400, detail="Код организации обязателен.")
    
    # Валидация org_name, если используется (только для новых, но проверим заранее)
    if org_name:
        org_name_stripped = org_name.strip()
        if not org_name_stripped:
            org_name = None  # Игнорируем пустое
        elif len(org_name_stripped) > 255:
            raise HTTPException(status_code=400, detail="Название организации не может превышать 255 символов.")
        else:
            org_name = org_name_stripped
    
    if is_okpo:
        if len(org_code) != 8:
            raise HTTPException(status_code=400, detail="Код ОКПО должен иметь длину 8 цифр.")
        if not re.match(r'^\d{8}$', org_code):
            raise HTTPException(status_code=400, detail="Код ОКПО должен состоять из 8 цифр.")
        
        # Поиск по num_code_okpo
        result = await session.execute(
            select(Organization).where(Organization.num_code_okpo == int(org_code))
        )
        org = result.scalars().first()
        
        if org:
            if not org.code_okpo:
                raise HTTPException(status_code=400, detail="Этот числовой код уже используется как общий, не ОКПО.")
            return org.id
        
        # Создание новой
        new_name = org_name or f"Организация с ОКПО {org_code}"
        new_org = Organization(
            code=None,
            name=new_name,  # User-provided или заглушка
            code_okpo=True,
            num_code=None,
            num_code_okpo=int(org_code)
        )
        session.add(new_org)
        await session.flush()
        return new_org.id
    else:
        # Стандартная валидация (как раньше, но с хранением num_code для 8 цифр)
        if len(org_code) != 4 and len(org_code) != 8:
            raise HTTPException(status_code=400, detail="Код организации должен иметь длину 4 (буквы) или 8 (цифры).")
        
        if len(org_code) == 4:
            # 4 заглавные кириллические буквы
            if not re.match(r'^[А-Я]{4}$', org_code):
                raise HTTPException(status_code=400, detail="Код организации (буквы) должен состоять из 4 заглавных кириллических букв (А-Я).")
        elif len(org_code) == 8:
            # 8 цифр (общий числовой)
            if not re.match(r'^\d{8}$', org_code):
                raise HTTPException(status_code=400, detail="Код организации (цифры) должен состоять из 8 цифр.")
        
        # Поиск: сначала по code (буквы), затем по num_code (цифры)
        if len(org_code) == 4:
            result = await session.execute(
                select(Organization).where(Organization.code == org_code)
            )
        else:
            result = await session.execute(
                select(Organization).where(Organization.num_code == int(org_code))
            )
        org = result.scalars().first()
        
        if org:
            if len(org_code) == 8 and org.code_okpo:
                raise HTTPException(status_code=400, detail="Этот код уже используется как ОКПО.")
            return org.id
        
        # Создание новой
        new_name = org_name or f"Организация с кодом {org_code}"
        new_org = Organization(
            code=org_code if len(org_code) == 4 else None,
            name=new_name,  # User-provided или заглушка
            code_okpo=False,
            num_code=int(org_code) if len(org_code) == 8 else None,
            num_code_okpo=None
        )
        session.add(new_org)
        await session.flush()
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
    result = await session.execute(
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
    await session.flush() 
    return new_class.id


async def check_org_exists(session: AsyncSession, org_code: str, is_okpo: bool = False) -> dict:
    """
    Проверяет существование организации по коду (учитывая is_okpo).
    Возвращает {'exists': True, 'name': str} если найдена, иначе {'exists': False}.
    """
    # Валидация (как в get_or_create_org_id, но без создания)
    if not org_code:
        return {'exists': False}
    
    if is_okpo:
        if len(org_code) != 8 or not re.match(r'^\d{8}$', org_code):
            return {'exists': False}
        result = await session.execute(
            select(Organization).where(Organization.num_code_okpo == int(org_code))
        )
        org = result.scalars().first()
        if org:
            return {'exists': True, 'name': org.name}
        return {'exists': False}
    else:
        if len(org_code) == 4:
            if not re.match(r'^[А-Я]{4}$', org_code):
                return {'exists': False}
            result = await session.execute(
                select(Organization).where(Organization.code == org_code)
            )
        else:  # 8 цифр
            if len(org_code) != 8 or not re.match(r'^\d{8}$', org_code):
                return {'exists': False}
            result = await session.execute(
                select(Organization).where(Organization.num_code == int(org_code))
            )
        org = result.scalars().first()
        if org:
            return {'exists': True, 'name': org.name}
        return {'exists': False}


async def check_designation_unique(
    session: AsyncSession,
    designation: str,
    *,
    is_kd: bool = True,
) -> bool:
    """Returns True when no document with this designation exists yet."""
    model = DesignDocument if is_kd else TechDocument
    result = await session.execute(select(model).where(model.designation == designation))
    return result.scalar_one_or_none() is None


async def get_next_prni(
    session: AsyncSession,
    org_id: int,
    kd_class_code_id: int,
    org_code: str,
    class_code: str,
    *,
    execution: Optional[str] = None,
    doc_kind_code: Optional[str] = None,
) -> int:
    """
    Returns the minimum serial number whose full designation is not yet used
    for the given org/class, execution, and document kind code.
    """
    prni = 1
    while True:
        designation = build_designation(
            org_code,
            class_code,
            prni,
            execution=execution,
            doc_kind_code=doc_kind_code,
        )
        if await check_designation_unique(session, designation, is_kd=True):
            return prni
        prni += 1


async def get_next_prn(
    session: AsyncSession,
    org_id: int,
    td_class_code_id: int,
    org_code: str,
    class_code: str,
    *,
    execution: Optional[str] = None,
) -> int:
    """
    Returns the minimum serial number whose full designation is not yet used
    for the given org/class and execution.
    """
    prn = 1
    while True:
        designation = build_designation(
            org_code,
            class_code,
            prn,
            execution=execution,
        )
        if await check_designation_unique(session, designation, is_kd=False):
            return prn
        prn += 1


async def check_prni_unique(
    session: AsyncSession,
    org_id: int,
    kd_class_code_id: int,
    prni: int,
    org_code: str,
    class_code: str,
    *,
    execution: Optional[str] = None,
    doc_kind_code: Optional[str] = None,
) -> bool:
    """Checks whether the full designation for a manual serial number is free."""
    designation = build_designation(
        org_code,
        class_code,
        prni,
        execution=execution,
        doc_kind_code=doc_kind_code,
    )
    return await check_designation_unique(session, designation, is_kd=True)


async def check_prn_unique(
    session: AsyncSession,
    org_id: int,
    td_class_code_id: int,
    prn: int,
    org_code: str,
    class_code: str,
    *,
    execution: Optional[str] = None,
) -> bool:
    """Checks whether the full designation for a manual serial number is free."""
    designation = build_designation(
        org_code,
        class_code,
        prn,
        execution=execution,
    )
    return await check_designation_unique(session, designation, is_kd=False)
