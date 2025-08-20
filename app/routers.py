from fastapi.security import OAuth2PasswordRequestForm
from fastapi import APIRouter, Depends, HTTPException, status, Security
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker
from app.database import get_session
from app.models import UserRole, User # ORM-модель для запросов к БД
from app.schemas import UserCreate, Token
from app.schemas import User as UserSchema # Pydantic-модель для response_model
from app.utils import hash_password, verify_password
from app.auth import create_access_token, get_current_user
from app.dependencies import oauth2_scheme

router = APIRouter()

@router.post("/register", response_model=Token)
async def register(user_create: UserCreate, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(User).where(User.login == user_create.login)
    )
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Login already registered")

    user = User(
        login=user_create.login,
        password_hash=hash_password(user_create.password),
        full_name=user_create.full_name,
        position=user_create.position,
        department=user_create.department,
        role=UserRole(user_create.role)
    )
    session.add(user)
    await session.commit()
    access_token = create_access_token({"sub": user.login})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).where(User.login == form_data.username))
    user = result.scalars().first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect login or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token({"sub": user.login})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserSchema, dependencies=[Security(oauth2_scheme)])
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user