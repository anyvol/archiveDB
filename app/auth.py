# app/auth.py
"""
JWT-аутентификация: создание токенов, проверка пользователей.
Поддержка cookie (для браузера) и header (для API).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from passlib.context import CryptContext  # pip install passlib[bcrypt]
import logging

from app.database import get_session
from app.models import User

load_dotenv()

# JWT настройки (с fallback, если .env не задан)
SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key-change-this-32-chars-min!")  # Генерируйте: openssl rand -hex 32
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# OAuth2 для API (header Authorization: Bearer token, используется в Swagger)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# Password hashing (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Логирование
logging.basicConfig(level=logging.INFO)  # Базовая настройка (DEBUG в .env или Docker)
logger = logging.getLogger(__name__)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверка пароля (bcrypt).
    Используется в authenticate_user.
    """
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """
    Хэширование пароля (bcrypt).
    Используется в register.
    """
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Создание JWT-токена.
    data: {"sub": login}, expires_delta: опционально.
    """
    to_encode = data.copy()
    # Исправление: datetime.now(timezone.utc) вместо utcnow() (deprecated)
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    logger.debug(f"Created token for sub: {data.get('sub')}")
    return encoded_jwt

async def authenticate_user(session: AsyncSession, username: str, password: str) -> Dict[str, str]:
    """
    Аутентификация: Поиск пользователя и проверка пароля.
    Возвращает {"access_token": jwt} или raises HTTPException.
    Используется в POST /login.
    """
    if not username or not password:
        raise HTTPException(status_code=400, detail="Логин и пароль обязательны.")
    
    result = await session.execute(select(User).where(User.login == username))
    user = result.scalars().first()
    if not user or not verify_password(password, user.password_hash):
        logger.warning(f"Failed login attempt for username: {username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Создание токена
    access_token = create_access_token(data={"sub": user.login})
    logger.info(f"User {username} authenticated")
    return {"access_token": access_token, "token_type": "bearer"}

# Для API (header-based, используется в Swagger /docs)
async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_session)) -> User:
    """
    Проверка токена из header (OAuth2).
    Для API-клиентов (Postman, Swagger).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        login: str = payload.get("sub")
        if login is None:
            raise credentials_exception
    except JWTError:
        logger.error("JWT decode error in get_current_user")
        raise credentials_exception
    result = await db.execute(select(User).where(User.login == login))
    user = result.scalars().first()
    if user is None:
        raise credentials_exception
    return user

# Для браузера (cookie-based)
async def get_current_user_from_token(access_token: str, db: AsyncSession) -> User:
    """
    Проверка токена из cookie.
    Используется в main.py для защищённых страниц (documents, create).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not access_token:
        logger.warning("Empty access_token in cookie")
        raise credentials_exception
    
    # Парсинг: Извлекаем чистый JWT (убираем "Bearer ")
    token = access_token
    if "Bearer " in token:
        token = token.split("Bearer ")[-1].strip()  # Robust парсинг
    logger.debug(f"Parsed token starts with: {token[:20]}...")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        login: str = payload.get("sub")  # <-- login определяется здесь
        if login is None:
            logger.warning("No 'sub' in payload")
            raise credentials_exception
        logger.info(f"Decoded sub from cookie: {login}")
    except JWTError as e:
        logger.error(f"JWT decode failed in cookie auth: {str(e)} (check SECRET_KEY?)")
        raise credentials_exception
    
    # Async SELECT пользователя (db используется здесь)
    result = await db.execute(select(User).where(User.login == login))
    user = result.scalars().first()
    if user is None:
        logger.warning(f"User '{login}' not found in DB")
        raise credentials_exception
    
    logger.info(f"User '{login}' authenticated from cookie")
    return user