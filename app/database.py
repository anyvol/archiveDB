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


load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in .env")


engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=True)
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


async def get_next_prni(session: AsyncSession, org_id: int, kd_class_code_id: int) -> int:
    """
    Генерирует следующий доступный ПРНИ для DD, заполняя пробелы в последовательности.
    Находит минимальное положительное целое число, отсутствующее в существующих prni.
    """
    # Загружаем все существующие prni как множество
    result = await session.execute(
        select(DesignDocument.prni).where(
            DesignDocument.org_id == org_id,
            DesignDocument.kd_class_code_id == kd_class_code_id
        )
    )
    used_prnis = {row[0] for row in result.fetchall() if row[0] is not None}
    
    # Находим минимальный свободный номер
    next_prni = 1
    while next_prni in used_prnis:
        next_prni += 1
    
    return next_prni



async def get_next_prn(session: AsyncSession, org_id: int, td_class_code_id: int) -> int:
    """
    Генерирует следующий доступный PRN для TD, заполняя пробелы в последовательности.
    Аналогично ПРНИ, но для TechDocument.
    """
    # Загружаем все существующие prn как множество
    result = await session.execute(
        select(TechDocument.prn).where(
            TechDocument.org_id == org_id,
            TechDocument.td_class_code_id == td_class_code_id
        )
    )
    used_prns = {row[0] for row in result.fetchall() if row[0] is not None}
    
    # Находим минимальный свободный номер
    next_prn = 1
    while next_prn in used_prns:
        next_prn += 1
    
    return next_prn



async def check_prni_unique(session: AsyncSession, org_id: int, kd_class_code_id: int, prni: int) -> bool:
    """
    Проверяет уникальность ручного ПРНИ для DD.
    Возвращает False, если номер уже используется.
    """
    result = await session.execute(
        select(DesignDocument).where(
            DesignDocument.org_id == org_id,
            DesignDocument.kd_class_code_id == kd_class_code_id,
            DesignDocument.prni == prni
        )
    )
    existing = result.scalar_one_or_none()
    return existing is None



async def check_prn_unique(session: AsyncSession, org_id: int, td_class_code_id: int, prn: int) -> bool:
    """
    Проверяет уникальность ручного PRN для TD.
    Возвращает False, если номер уже используется.
    """
    result = await session.execute(
        select(TechDocument).where(
            TechDocument.org_id == org_id,
            TechDocument.td_class_code_id == td_class_code_id,
            TechDocument.prn == prn
        )
    )
    existing = result.scalar_one_or_none()
    return existing is None
