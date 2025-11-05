# app/services.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException, status

from app.models import User
from app.utils import verify_password
from app.auth import create_access_token

async def authenticate_user(
    session: AsyncSession, 
    username: str, 
    password: str
) -> dict:
    """
    Проверяет логин/пароль и возвращает токен.
    Вызывает HTTPException в случае ошибки.
    """
    result = await session.execute(select(User).where(User.login == username))
    user = result.scalars().first()

    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect login or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token({"sub": user.login})
    return {"access_token": access_token, "token_type": "bearer"}
